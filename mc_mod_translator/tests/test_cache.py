from __future__ import annotations

from pathlib import Path

from mc_mod_translator.cache import TranslationCache


def test_put_and_get(tmp_path: Path):
    c = TranslationCache(tmp_path / "c.db")
    try:
        c.put("hello", "openai", "en", "zh_cn", "你好")
        assert c.get("hello", "openai", "en", "zh_cn") == "你好"
        # 不同引擎查不到
        assert c.get("hello", "google", "en", "zh_cn") is None
        # 不同目标语言查不到
        assert c.get("hello", "openai", "en", "zh_tw") is None
    finally:
        c.close()


def test_put_many_and_get_many(tmp_path: Path):
    c = TranslationCache(tmp_path / "c.db")
    try:
        items = [(f"k{i}", f"v{i}") for i in range(100)]
        c.put_many(items, "openai", "en", "zh_cn")
        keys = [f"k{i}" for i in range(100)]
        result = c.get_many(keys, "openai", "en", "zh_cn")
        assert len(result) == 100
        assert result["k0"] == "v0"
        assert result["k99"] == "v99"
    finally:
        c.close()


def test_get_many_empty(tmp_path: Path):
    c = TranslationCache(tmp_path / "c.db")
    try:
        assert c.get_many([], "openai", "en", "zh_cn") == {}
    finally:
        c.close()


def test_put_replace(tmp_path: Path):
    c = TranslationCache(tmp_path / "c.db")
    try:
        c.put("k", "openai", "en", "zh_cn", "v1")
        c.put("k", "openai", "en", "zh_cn", "v2")
        assert c.get("k", "openai", "en", "zh_cn") == "v2"
    finally:
        c.close()


def test_close_idempotent(tmp_path: Path):
    c = TranslationCache(tmp_path / "c.db")
    c.close()
    c.close()  # 重复关闭不应抛异常


def test_manual_engine_isolated(tmp_path: Path):
    c = TranslationCache(tmp_path / "c.db")
    try:
        c.put("hello", "openai", "en", "zh_cn", "引擎翻译")
        c.put("hello", "manual", "en", "zh_cn", "人工翻译")
        assert c.get("hello", "manual", "en", "zh_cn") == "人工翻译"
        assert c.get("hello", "openai", "en", "zh_cn") == "引擎翻译"
    finally:
        c.close()