"""免费、无需 API Key 的翻译引擎。

面向普通玩家：打开就能用，不需要注册、不需要充值、不需要填 Key。

设计原则：
  - **永不因单条失败而中止整个任务**
  - 翻译不了就返回原文，让流程继续；失败的会被 Translator 记为失败
  - 多后端自动切换，遇限流自动等待重试

包含：
  - MyMemoryEngine：https://mymemory.translated.net/
  - AutoFreeEngine：默认引擎，按顺序尝试多个免费后端
"""

from __future__ import annotations

import asyncio
import html
from typing import Dict, List, Optional

from .base import (
    BaseEngine,
    EngineAuthError,
    EngineError,
    EngineFatalError,
    EngineQuotaError,
    EngineRateLimitError,
    EngineResponseError,
    check_http_response,
    wrap_request_error,
)


# MyMemory 单次查询长度上限（官方文档：q 最大 500 字节）
_MYMEMORY_MAX_BYTES = 500

# 后端连续失败多少次后被暂时跳过
_BACKEND_FAIL_THRESHOLD = 5

# 429 限流时的最大重试次数
_RATE_LIMIT_RETRIES = 2

# 429 限流等待上限（秒）
_MAX_RETRY_WAIT = 10.0


# ---------------------------------------------------------------------------
# MyMemory
# ---------------------------------------------------------------------------

class MyMemoryEngine(BaseEngine):
    """https://mymemory.translated.net/

    - 免费，无需 API Key
    - 匿名每日 10000 字符；带邮箱每日 50000 字符
    - 单次查询最多 500 字节
    - 找不到译文时**返回原文**，不报错（由 Translator 判定为失败）
    """

    name = "mymemory"

    _LANG_MAP = {
        "en": "en-GB",
        "zh": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-CN": "zh-CN",
        "zh_tw": "zh-TW",
        "zh-TW": "zh-TW",
    }

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        # 太长：直接返回原文（Translator 会记为失败）
        if len(text.encode("utf-8")) > _MYMEMORY_MAX_BYTES:
            return text

        sl = self._LANG_MAP.get(src.lower(), "en-GB")
        tl = self._LANG_MAP.get(tgt.lower(), "zh-CN")

        params: Dict[str, str] = {"q": text, "langpair": f"{sl}|{tl}"}
        email = str(self.config.get("email", "") or "").strip()
        if email:
            params["de"] = email

        client = self._get_client(timeout=30.0)
        try:
            resp = await client.get(
                "https://api.mymemory.translated.net/get", params=params
            )
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e

        check_http_response(resp, self.name)

        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise EngineResponseError(f"mymemory: 响应非 JSON: {e}") from e

        translated = ""
        try:
            translated = str(data["responseData"]["translatedText"])
        except (KeyError, TypeError):
            translated = ""

        detail = str(data.get("responseDetails", "") or "")
        upper_detail = detail.upper()
        upper_translated = translated.upper()

        # 配额耗尽：这是**真·致命**，但 AutoFreeEngine 会切到下一个后端
        if (
            data.get("quotaFinished")
            or "MYMEMORY WARNING" in upper_detail
            or "MYMEMORY WARNING" in upper_translated
        ):
            raise EngineQuotaError(
                "mymemory: 今日免费额度已用完"
            )

        # 单条过长：返回原文（不算错误）
        if "QUERY LENGTH LIMIT" in upper_detail or "QUERY LENGTH LIMIT" in upper_translated:
            return text

        # 状态码非 200：抛响应错误，让 AutoFreeEngine 决定是否切换
        if data.get("responseStatus") not in (200, "200", None):
            raise EngineResponseError(
                f"mymemory 状态 {data.get('responseStatus')}: {detail}"
            )

        # 空译文 → 返回原文
        if not translated:
            return text

        # HTML 实体还原
        translated = html.unescape(translated)

        # 原文原样返回是常见情况（短词、专有名词）→ 返回原文
        if translated.strip() == text.strip():
            return text

        return translated


# ---------------------------------------------------------------------------
# AutoFreeEngine
# ---------------------------------------------------------------------------

class AutoFreeEngine(BaseEngine):
    """玩家默认引擎。自动尝试多个免费翻译服务，无需任何配置。

    工作方式：
      1. 按 `_BACKENDS` 顺序尝试每个后端
      2. 一旦某个后端成功，之后优先用它
      3. 某后端连续失败 N 次，暂时跳过它
      4. 某后端配额耗尽 / 认证失败，永久跳过它
      5. **所有后端都失败 → 返回原文**（不抛异常）
      6. 遇 429 限流 → 等待后重试同一后端

    为什么所有后端失败时返回原文，而不是抛异常？
      玩家要的是"能翻多少翻多少"。单条失败不应中止整个任务。
      Translator 会检测到"译文 == 原文"并把它记为失败，但不影响其他条目。
    """

    name = "auto_free"

    # 后端顺序：MyMemory 优先（无 IP 区域限制），Google 备选
    _BACKENDS = [
        ("mymemory", "MyMemory"),
        ("google", "Google 翻译"),
    ]

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self._instances: Dict[str, BaseEngine] = {}
        self._current: Optional[str] = None
        self._fail_count: Dict[str, int] = {}
        # 避免日志刷屏：每个后端只报一次致命错误
        self._reported: Dict[str, bool] = {}

    # ---------- 内部工具 ----------
    def _get_instance(self, backend_name: str) -> BaseEngine:
        if backend_name not in self._instances:
            from .registry import create_engine

            self._instances[backend_name] = create_engine(backend_name, {})
        return self._instances[backend_name]

    def _ordered_backends(self) -> List[str]:
        order: List[str] = []
        if (
            self._current
            and self._fail_count.get(self._current, 0) < _BACKEND_FAIL_THRESHOLD
        ):
            order.append(self._current)
        for name, _ in self._BACKENDS:
            if name in order:
                continue
            if self._fail_count.get(name, 0) >= _BACKEND_FAIL_THRESHOLD:
                continue
            order.append(name)
        return order

    def _on_backend_success(self, backend_name: str) -> None:
        self._current = backend_name
        self._fail_count[backend_name] = 0
        self._reported[backend_name] = False

    def _on_backend_transient_failure(self, backend_name: str) -> None:
        self._fail_count[backend_name] = self._fail_count.get(backend_name, 0) + 1
        if (
            self._current == backend_name
            and self._fail_count[backend_name] >= _BACKEND_FAIL_THRESHOLD
        ):
            self._current = None

    def _on_backend_permanent_failure(self, backend_name: str) -> None:
        self._fail_count[backend_name] = 9999
        if self._current == backend_name:
            self._current = None

    # ---------- 翻译 ----------
    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        backends = self._ordered_backends()
        if not backends:
            # 所有后端都被跳过：返回原文，让流程继续
            return text

        errors: List[str] = []

        for backend_name in backends:
            try:
                inst = self._get_instance(backend_name)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{backend_name}: 初始化失败: {e}")
                self._on_backend_permanent_failure(backend_name)
                continue

            for attempt in range(_RATE_LIMIT_RETRIES + 1):
                try:
                    result = await inst.translate(text, src, tgt)
                except EngineRateLimitError as e:
                    if attempt < _RATE_LIMIT_RETRIES:
                        wait = min(
                            e.retry_after if e.retry_after else 3.0,
                            _MAX_RETRY_WAIT,
                        )
                        await asyncio.sleep(wait)
                        continue
                    errors.append(f"{backend_name}: 429 限流")
                    self._on_backend_transient_failure(backend_name)
                    break
                except (EngineQuotaError, EngineAuthError) as e:
                    errors.append(f"{backend_name}: {e}")
                    self._on_backend_permanent_failure(backend_name)
                    break
                except EngineError as e:
                    errors.append(f"{backend_name}: {type(e).__name__}: {e}")
                    self._on_backend_transient_failure(backend_name)
                    break
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{backend_name}: {type(e).__name__}: {e}")
                    self._on_backend_transient_failure(backend_name)
                    break
                else:
                    # 成功
                    self._on_backend_success(backend_name)
                    return result

        # 所有后端都失败：返回原文，不抛异常
        # （只在第一次出现时记录日志，避免刷屏）
        self._maybe_log_failure(text, errors)
        return text

    def _maybe_log_failure(self, text: str, errors: List[str]) -> None:
        # 只在第一次失败时记录完整错误（避免刷屏）
        if getattr(self, "_failure_logged", False):
            return
        self._failure_logged = True
        try:
            from loguru import logger

            logger.warning(
                f"auto_free: 所有后端均失败（后续不再重复记录）。"
                f"示例文本: {text[:60]!r}；错误: {errors}"
            )
        except Exception:
            pass

    # ---------- 生命周期 ----------
    async def aclose(self) -> None:
        for inst in self._instances.values():
            try:
                await inst.aclose()
            except Exception:
                pass
        self._instances.clear()
        await super().aclose()