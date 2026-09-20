from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import httpx


DEFAULT_SYSTEM_PROMPT = (
    "你是 Minecraft 模组本地化专家。请将用户提供的英文文本翻译为简体中文。"
    "只输出译文，不要解释、不要加引号。"
    "必须保留所有形如 __PH_数字__ 的占位符不变，并且保留其相对位置。"
    "如果文本是物品/方块名称，请使用 Minecraft 官方简体中文译名。"
)


# ---------------------------------------------------------------------------
# 统一异常体系：Translator 通过异常类型判定是否重试、是否需要等待
# ---------------------------------------------------------------------------

class EngineError(RuntimeError):
    """引擎通用错误。"""


class EngineAuthError(EngineError):
    """API Key 无效 / 权限不足（401/403）。不重试。"""


class EngineRateLimitError(EngineError):
    """429 限流。Translator 会读取 ``retry_after`` 后等待。"""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class EngineTimeoutError(EngineError):
    """网络超时。可以重试。"""


class EngineResponseError(EngineError):
    """响应体解析失败 / 字段缺失。可以重试。"""


# ---------------------------------------------------------------------------
# HTTP 响应检查
# ---------------------------------------------------------------------------

def check_http_response(resp: httpx.Response, engine_name: str) -> None:
    """把常见 HTTP 错误转成统一异常。

    - 401/403 -> EngineAuthError
    - 429 -> EngineRateLimitError（带 Retry-After）
    - 其他 4xx/5xx -> EngineError
    """
    if resp.status_code < 400:
        return

    if resp.status_code in (401, 403):
        raise EngineAuthError(
            f"{engine_name}: 认证失败 ({resp.status_code})，请检查 API Key / 权限"
        )

    if resp.status_code == 429:
        retry_after: Optional[float] = None
        ra = resp.headers.get("Retry-After")
        if ra:
            try:
                retry_after = float(ra)
            except ValueError:
                retry_after = None
        raise EngineRateLimitError(
            f"{engine_name}: 429 限流"
            + (f"，Retry-After={retry_after}s" if retry_after else ""),
            retry_after=retry_after,
        )

    text = ""
    try:
        text = resp.text[:300]
    except Exception:
        pass
    raise EngineError(
        f"{engine_name}: HTTP {resp.status_code} {resp.reason_phrase} {text}"
    )


def wrap_request_error(err: Exception, engine_name: str) -> Exception:
    """把 httpx 层的异常映射为引擎异常。"""
    if isinstance(err, (EngineError,)):
        return err
    if isinstance(err, httpx.TimeoutException):
        return EngineTimeoutError(f"{engine_name}: 请求超时 ({err})")
    if isinstance(err, httpx.ConnectError):
        return EngineError(f"{engine_name}: 无法连接 ({err})")
    if isinstance(err, httpx.HTTPError):
        return EngineError(f"{engine_name}: HTTP 异常 ({err})")
    return err


class BaseEngine(ABC):
    name: str = "base"

    def __init__(self, name: str, config: Dict):
        self.name = name
        self.config = config or {}
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self, timeout: float = 60.0) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout, connect=10.0),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
        return self._client

    @abstractmethod
    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        raise NotImplementedError

    async def translate_batch(
        self, texts: List[str], src: str = "en", tgt: str = "zh"
    ) -> List[str]:
        """默认实现：顺序调用 ``translate``。

        子类若支持批量 API 可覆盖此方法。
        """
        results: List[str] = []
        for t in texts:
            results.append(await self.translate(t, src, tgt))
        return results

    async def test(self) -> bool:
        try:
            r = await self.translate("hello", "en", "zh")
            return bool(r)
        except Exception:
            return False

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            finally:
                self._client = None

    def close(self) -> None:
        self._client = None