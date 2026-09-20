from __future__ import annotations

import pytest

# 优雅处理 PySide6 不可用的情况：
#   1. 没装 PySide6  → ModuleNotFoundError
#   2. Linux 缺系统库（libEGL 等） → ImportError: libEGL.so.1: cannot open ...
#   3. 其他加载失败
# 三种情况都应该跳过此文件而不是中断整个测试收集。
try:
    from mc_mod_translator.gui.engine_dialog import _collect_field_keys
except Exception as e:  # noqa: BLE001
    pytest.skip(
        f"PySide6 不可用，跳过 GUI 测试: {type(e).__name__}: {e}",
        allow_module_level=True,
    )

from mc_mod_translator.engines.registry import (  # noqa: E402
    DEFAULT_ENGINE_CONFIGS,
    ENGINE_REQUIRED_FIELDS,
)


class TestCollectFieldKeys:
    def test_baidu_shows_app_id_and_app_key(self):
        """核心回归：baidu 的字段必须在对话框里显示出来。"""
        keys = _collect_field_keys("baidu", {}, DEFAULT_ENGINE_CONFIGS["baidu"])
        assert "app_id" in keys
        assert "app_key" in keys

    def test_openai_shows_api_key(self):
        keys = _collect_field_keys("openai", {}, DEFAULT_ENGINE_CONFIGS["openai"])
        assert "api_key" in keys

    def test_microsoft_shows_region_and_key(self):
        keys = _collect_field_keys(
            "microsoft", {}, DEFAULT_ENGINE_CONFIGS["microsoft"]
        )
        assert "api_key" in keys
        assert "region" in keys

    def test_user_cfg_fields_are_kept(self):
        """用户配置里有但 defaults/required 里没有的字段，也要显示，避免丢数据。"""
        keys = _collect_field_keys(
            "openai",
            {"api_key": "x", "custom_field": "y"},
            DEFAULT_ENGINE_CONFIGS["openai"],
        )
        assert "custom_field" in keys

    def test_no_duplicates(self):
        keys = _collect_field_keys(
            "openai",
            {"api_key": "x", "base_url": "y", "model": "z"},
            DEFAULT_ENGINE_CONFIGS["openai"],
        )
        assert len(keys) == len(set(keys))

    def test_empty_engine_falls_back_to_api_key(self):
        keys = _collect_field_keys("__unknown__", {}, {})
        assert keys == ["api_key"]


class TestRequiredFieldsCoverage:
    def test_every_required_field_has_a_label(self):
        """必填字段都应该在 FIELD_LABELS 里有中文标签，否则 UI 上显示英文 key。"""
        from mc_mod_translator.gui.engine_dialog import FIELD_LABELS

        for fields in ENGINE_REQUIRED_FIELDS.values():
            for f in fields:
                assert f in FIELD_LABELS, f"{f} 缺少 FIELD_LABELS 标签"