from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from mc_mod_translator.engines.base import (
    BaseEngine,
    EngineQuotaError,
    EngineRateLimitError,
    EngineResponseError,
)
from mc_mod_translator.engines.free import AutoFreeEngine, MyMemoryEngine
from mc_mod_translator.engines.registry import (
    ENGINE_NAMES,
    ENGINE_REQUIRED_FIELDS,
    create_engine,
    missing_required_fields,
)


# ---------------------------------------------------------------------------
# 通用 stub
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, json_data: dict, status_code: int = 200):
        self._json = json_data
        self.status_code = status_code
        self.reason_phrase = "OK"
        self.text = ""

    def json(self):
        return self._json


def _patch_client(monkeypatch, engine: BaseEngine, resp_json: dict):
    """把 engine._get_client() 返回的 client.get 换成返回固定 JSON。"""

    class _FakeClient:
        def __init__(self, data):
            self.data = data

        async def get(self, *args, **kwargs):
            return _FakeResponse(self.data)

        async def post(self, *args, **kwargs):
            return _FakeResponse(self.data)

        async def aclose(self):
            pass

    monkeypatch.setattr(
        engine, "_get_client", lambda timeout=30.0: _FakeClient(resp_json)
    )


def _mm_ok_payload(translated: str) -> dict:
    return {
        "responseData": {"translatedText": translated},
        "responseStatus": 200,
        "responseDetails": "",
        "quotaFinished": False,
    }


# ---------------------------------------------------------------------------
# Registry 集成
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_auto_free_is_registered(self):
        assert "auto_free" in ENGINE_NAMES
        assert "mymemory" in ENGINE_NAMES

    def test_auto_free_has_no_required_fields(self):
        assert missing_required_fields("auto_free", {}) == []
        assert missing_required_fields("mymemory", {}) == []

    def test_create_auto_free(self):
        eng = create_engine("auto_free", {})
        assert isinstance(eng, AutoFreeEngine)

    def test_auto_free_in_required_map(self):
        assert "auto_free" in ENGINE_REQUIRED_FIELDS
        assert ENGINE_REQUIRED_FIELDS["auto_free"] == []


# ---------------------------------------------------------------------------
# MyMemory 解析
# ---------------------------------------------------------------------------

class TestMyMemoryParse:
    def test_ok(self, monkeypatch):
        eng = MyMemoryEngine("mymemory", {})
        _patch_client(monkeypatch, eng, _mm_ok_payload("你好"))
        out = asyncio.run(eng.translate("hello", "en", "zh_cn"))
        assert out == "你好"

    def test_html_unescape(self, monkeypatch):
        """HTML 实体应被还原，且返回的结果 != 原文。"""
        eng = MyMemoryEngine("mymemory", {})
        _patch_client(monkeypatch, eng, _mm_ok_payload("A &amp; B"))
        # 输入是 "A and B"，服务返回 "A &amp; B"，unescape 后是 "A & B"
        out = asyncio.run(eng.translate("A and B", "en", "zh_cn"))
        assert out == "A & B"

    def test_quota_exhausted_raises(self, monkeypatch):
        """配额耗尽仍抛 EngineQuotaError（让 AutoFree 切到下一个后端）。"""
        eng = MyMemoryEngine("mymemory", {})
        _patch_client(
            monkeypatch,
            eng,
            {
                "responseData": {"translatedText": "MYMEMORY WARNING..."},
                "responseStatus": 200,
                "responseDetails": "MYMEMORY WARNING: quota exceeded",
                "quotaFinished": True,
            },
        )
        with pytest.raises(EngineQuotaError):
            asyncio.run(eng.translate("hello", "en", "zh_cn"))

    def test_length_limit_returns_text(self, monkeypatch):
        """QUERY LENGTH LIMIT：返回原文，不抛异常。"""
        eng = MyMemoryEngine("mymemory", {})
        _patch_client(
            monkeypatch,
            eng,
            {
                "responseData": {"translatedText": ""},
                "responseStatus": 200,
                "responseDetails": "QUERY LENGTH LIMIT EXCEEDED",
                "quotaFinished": False,
            },
        )
        text = "hello world"
        out = asyncio.run(eng.translate(text, "en", "zh_cn"))
        assert out == text

    def test_echo_original_returns_text(self, monkeypatch):
        """服务原样返回（找不到译文）：返回原文，不抛异常。"""
        eng = MyMemoryEngine("mymemory", {})
        _patch_client(monkeypatch, eng, _mm_ok_payload("hello"))
        text = "hello"
        out = asyncio.run(eng.translate(text, "en", "zh_cn"))
        assert out == text

    def test_oversize_text_returns_text(self):
        """超过 500 字节：本地拦截，返回原文。"""
        eng = MyMemoryEngine("mymemory", {})
        long_text = "a" * 600
        out = asyncio.run(eng.translate(long_text, "en", "zh_cn"))
        assert out == long_text

    def test_empty_translation_returns_text(self, monkeypatch):
        """服务返回空译文：返回原文。"""
        eng = MyMemoryEngine("mymemory", {})
        _patch_client(monkeypatch, eng, _mm_ok_payload(""))
        text = "hello"
        out = asyncio.run(eng.translate(text, "en", "zh_cn"))
        assert out == text


# ---------------------------------------------------------------------------
# AutoFreeEngine
# ---------------------------------------------------------------------------

class _StubBackend(BaseEngine):
    """测试用后端：按预设脚本返回或抛异常。

    script 为空时，默认返回 ``<name>:<text>``。
    """

    def __init__(self, name: str, script: list):
        super().__init__(name, {})
        self.script = list(script)
        self.calls = 0

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        self.calls += 1
        if not self.script:
            return f"{self.name}:{text}"
        action = self.script.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action

    async def aclose(self) -> None:
        pass


class TestAutoFree:
    def _make_engine(self, backends_script: dict) -> AutoFreeEngine:
        eng = AutoFreeEngine("auto_free", {})
        stubs: dict = {}

        def _get(name: str):
            if name not in stubs:
                script = backends_script.get(name, [])
                stubs[name] = _StubBackend(name, script)
            return stubs[name]

        eng._get_instance = _get  # type: ignore[assignment]
        return eng

    # ---- 顺序与优先级（MyMemory 优先）----
    def test_first_backend_wins(self):
        """默认顺序：mymemory 先，成功即返回。"""
        eng = self._make_engine(
            {"mymemory": ["mm_ok"], "google": ["google_ok"]}
        )
        out = asyncio.run(eng.translate("hello"))
        assert out == "mm_ok"
        assert eng._current == "mymemory"

    def test_fallback_to_second(self):
        """mymemory 连续失败后切换 google。"""
        eng = self._make_engine(
            {
                # 连续 5 次失败会被标记跳过（_BACKEND_FAIL_THRESHOLD = 5）
                "mymemory": [RuntimeError("boom")] * 5,
                "google": ["google_ok"],
            }
        )
        # 第 1 次：mymemory 失败 → 尝试 google 成功
        out = asyncio.run(eng.translate("hello"))
        assert out == "google_ok"
        assert eng._current == "google"

    def test_prefers_current(self):
        """成功后第二次调用优先使用同一后端。"""
        eng = self._make_engine(
            {"mymemory": ["mm1", "mm2"], "google": ["google_ok"]}
        )
        r1 = asyncio.run(eng.translate("a"))
        r2 = asyncio.run(eng.translate("b"))
        assert r1 == "mm1"
        assert r2 == "mm2"
        assert eng._current == "mymemory"
        # google 不应被调用
        assert "google" not in eng._instances or eng._instances["google"].calls == 0

    # ---- 配额耗尽 ----
    def test_quota_marks_permanently(self):
        """配额耗尽的后端被永久跳过。"""
        eng = self._make_engine(
            {
                "mymemory": [EngineQuotaError("quota")],
                "google": ["google_ok"],
            }
        )
        out = asyncio.run(eng.translate("hello"))
        assert out == "google_ok"
        # mymemory 被标记为永久失败
        assert eng._fail_count["mymemory"] >= 3

    # ---- 所有后端失败 ----
    def test_all_backends_fail_returns_text(self):
        """所有后端失败：返回原文，不抛异常。"""
        eng = self._make_engine(
            {
                "mymemory": [RuntimeError("boom")] * 10,
                "google": [RuntimeError("boom")] * 10,
            }
        )
        text = "hello"
        out = asyncio.run(eng.translate(text))
        assert out == text

    # ---- 429 限流重试 ----
    def test_rate_limit_retry_then_success(self):
        """429 限流：等待后重试，第二次成功。"""
        eng = self._make_engine(
            {
                "mymemory": [
                    EngineRateLimitError("429", retry_after=0.01),
                    "mm_ok_after_retry",
                ],
                "google": [],
            }
        )
        out = asyncio.run(eng.translate("hello"))
        assert out == "mm_ok_after_retry"

    def test_rate_limit_exhausted_falls_to_next(self):
        """连续 429 超过重试次数：切到下一个后端。"""
        eng = self._make_engine(
            {
                "mymemory": [EngineRateLimitError("429", retry_after=0.01)] * 5,
                "google": ["google_ok"],
            }
        )
        out = asyncio.run(eng.translate("hello"))
        assert out == "google_ok"

    # ---- 后端数量 ----
    def test_ordered_backends_respects_fail_count(self):
        """连续失败达到阈值后，该后端被暂时跳过。"""
        eng = AutoFreeEngine("auto_free", {})
        eng._fail_count["mymemory"] = 5
        order = eng._ordered_backends()
        assert "mymemory" not in order
        assert "google" in order

    def test_ordered_backends_prefers_current(self):
        eng = AutoFreeEngine("auto_free", {})
        eng._current = "google"
        eng._fail_count["google"] = 0
        order = eng._ordered_backends()
        assert order[0] == "google"