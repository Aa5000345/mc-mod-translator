from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from mc_mod_translator.cache import TranslationCache
from mc_mod_translator.engines.base import BaseEngine, EngineConfigError
from mc_mod_translator.engines.registry import (
    ENGINE_REQUIRED_FIELDS,
    missing_required_fields,
    validate_engine_config,
)
from mc_mod_translator.scanner import LangEntry
from mc_mod_translator.translator import Translator


# ---------------------------------------------------------------------------
# registry 层面
# ---------------------------------------------------------------------------

class TestMissingRequiredFields:
    def test_baidu_needs_both(self):
        assert missing_required_fields("baidu", {}) == ["app_id", "app_key"]
        assert missing_required_fields("baidu", {"app_id": "x"}) == ["app_key"]
        assert missing_required_fields("baidu", {"app_key": "y"}) == ["app_id"]
        assert missing_required_fields(
            "baidu", {"app_id": "x", "app_key": "y"}
        ) == []

    def test_openai_needs_api_key(self):
        assert missing_required_fields("openai", {}) == ["api_key"]
        assert missing_required_fields("openai", {"api_key": "x"}) == []

    def test_google_has_no_required_fields(self):
        assert missing_required_fields("google", {}) == []
        assert missing_required_fields("ollama", {}) == []
        assert missing_required_fields("nllb", {}) == []

    def test_unknown_engine_has_no_required_fields(self):
        assert missing_required_fields("unknown-engine", {}) == []

    def test_empty_values_treated_as_missing(self):
        assert missing_required_fields("openai", {"api_key": ""}) == ["api_key"]
        assert missing_required_fields("openai", {"api_key": None}) == ["api_key"]


class TestValidateEngineConfig:
    def test_raises_for_missing(self):
        with pytest.raises(EngineConfigError):
            validate_engine_config("openai", {})

    def test_ok(self):
        validate_engine_config("openai", {"api_key": "x"})

    def test_baidu_partial_raises(self):
        with pytest.raises(EngineConfigError):
            validate_engine_config("baidu", {"app_id": "x"})


# ---------------------------------------------------------------------------
# Translator 层面：配置错误快速失败、不重试
# ---------------------------------------------------------------------------

class _ConfigFailingEngine(BaseEngine):
    """所有 translate 调用都抛 EngineConfigError，用来验证 Translator 快速失败。"""

    name = "config-fail"

    def __init__(self):
        super().__init__(self.name, {})
        self.calls = 0

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        self.calls += 1
        raise EngineConfigError("缺少 api_key")


class _TransientThenOkEngine(BaseEngine):
    """前 N 次抛普通异常，之后成功，用于验证重试仍然有效。"""

    name = "transient"

    def __init__(self, fail_times: int = 2):
        super().__init__(self.name, {})
        self.fail_times = fail_times
        self.calls = 0

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("模拟网络抖动")
        return f"译:{text}"


def _make_entry(source: dict) -> LangEntry:
    return LangEntry(
        jar_path=Path("/x.jar"),
        mod_id="m",
        lang_path="assets/m/lang/en_us.json",
        fmt="json",
        source=source,
        existing={},
    )


class TestTranslatorAbortOnConfigError:
    def test_config_error_not_retried(self):
        eng = _ConfigFailingEngine()
        tr = Translator(engine=eng, cache=None, glossary=None, max_retries=3)
        entry = _make_entry({"a": "hello", "b": "world", "c": "foo"})

        with pytest.raises(EngineConfigError):
            asyncio.run(tr.translate_entries([entry], target_lang="zh_cn"))

        # 关键：不重试。3 条文本各调用 1 次，最多 3 次。
        # 早停机制下可能更少，但绝不应出现 3 条 × 3 次 = 9 次。
        assert eng.calls <= 3, f"配置错误被重试了，调用了 {eng.calls} 次"

    def test_transient_error_is_retried(self):
        eng = _TransientThenOkEngine(fail_times=2)
        tr = Translator(engine=eng, cache=None, glossary=None, max_retries=3)
        entry = _make_entry({"a": "hello"})

        results = asyncio.run(tr.translate_entries([entry], target_lang="zh_cn"))
        assert results[0].merged["a"] == "译:hello"
        assert eng.calls == 3  # 2 次失败 + 1 次成功


class TestTranslatorPartialCacheOnAbort:
    def test_completed_items_are_cached_before_raising(self, tmp_path: Path):
        """即使中途因配置错误中止，已翻译完的文本也应写入缓存。"""
        cache = TranslationCache(tmp_path / "c.db")

        class _PartialEngine(BaseEngine):
            name = "partial"

            def __init__(self):
                super().__init__(self.name, {})
                self.calls = 0
                self._lock = threading.Lock()

            async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
                with self._lock:
                    self.calls += 1
                    n = self.calls
                if n == 1:
                    return "ok:" + text
                raise EngineConfigError("缺少 api_key")

        eng = _PartialEngine()
        tr = Translator(
            engine=eng,
            cache=cache,
            glossary=None,
            concurrency=1,  # 串行，保证第一条先完成
            max_retries=1,
        )
        entry = _make_entry({"a": "aaa", "b": "bbb"})

        with pytest.raises(EngineConfigError):
            asyncio.run(tr.translate_entries([entry], target_lang="zh_cn"))

        # 第一条已翻译的应被缓存
        assert cache.get("aaa", "partial", "en", "zh_cn") == "ok:aaa"
        cache.close()


# ---------------------------------------------------------------------------
# ENGINE_REQUIRED_FIELDS 完整性
# ---------------------------------------------------------------------------

def test_required_fields_only_covers_known_engines():
    """ENGINE_REQUIRED_FIELDS 里的 key 都应该是有效引擎。"""
    from mc_mod_translator.engines.registry import ENGINE_NAMES

    for name in ENGINE_REQUIRED_FIELDS:
        assert name in ENGINE_NAMES, f"未知引擎出现在必填表里: {name}"