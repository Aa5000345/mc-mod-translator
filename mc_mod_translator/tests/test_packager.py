from __future__ import annotations

import json
import zipfile
from pathlib import Path

from mc_mod_translator.packager import (
    build_merged_pack,
    make_pack_mcmeta,
)
from mc_mod_translator.scanner import LangEntry
from mc_mod_translator.translator import TranslatedEntry


def _entry(mod_id: str, fmt: str = "json", source=None, merged=None) -> TranslatedEntry:
    lang = LangEntry(
        jar_path=Path("/fake.jar"),
        mod_id=mod_id,
        lang_path=f"assets/{mod_id}/lang/en_us.{fmt}",
        fmt=fmt,
        source=source or {"a": "b"},
        existing={},
    )
    return TranslatedEntry(entry=lang, merged=merged or {"a": "中文"})


class TestMcmeta:
    def test_basic(self):
        s = make_pack_mcmeta(15, "test")
        data = json.loads(s)
        assert data["pack"]["pack_format"] == 15
        assert data["pack"]["description"] == "test"

    def test_supported_formats_int(self):
        s = make_pack_mcmeta(15, "test", supported_formats=15)
        data = json.loads(s)
        assert data["pack"]["supported_formats"] == [15]

    def test_supported_formats_range(self):
        s = make_pack_mcmeta(22, "test", supported_formats=(20, 25))
        data = json.loads(s)
        assert data["pack"]["supported_formats"] == [20, 25]


class TestMergedPack:
    def test_json_path_zh_cn(self, tmp_path: Path):
        out = tmp_path / "out.zip"
        build_merged_pack(out, [_entry("mod_a")], 15, target_lang="zh_cn")
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert "pack.mcmeta" in names
            assert "assets/mod_a/lang/zh_cn.json" in names

    def test_lang_path_zh_CN_uppercase(self, tmp_path: Path):
        """老版本用 .lang 时必须是 zh_CN.lang（大写），不能是 zh_cn.lang。"""
        out = tmp_path / "out.zip"
        build_merged_pack(
            out,
            [_entry("old_mod", fmt="lang")],
            3,
            target_lang="zh_cn",
        )
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert "assets/old_mod/lang/zh_CN.lang" in names
            assert "assets/old_mod/lang/zh_cn.lang" not in names

    def test_zh_tw_lang_uppercase(self, tmp_path: Path):
        out = tmp_path / "out.zip"
        build_merged_pack(
            out,
            [_entry("m", fmt="lang")],
            3,
            target_lang="zh_tw",
        )
        with zipfile.ZipFile(out) as zf:
            assert "assets/m/lang/zh_TW.lang" in zf.namelist()

    def test_same_mod_same_fmt_merged(self, tmp_path: Path):
        """同一 mod 同一 fmt 两个 entry 不应互相覆盖。"""
        out = tmp_path / "out.zip"
        e1 = _entry("mod_a", source={"a": "b"}, merged={"a": "甲"})
        e2 = _entry("mod_a", source={"c": "d"}, merged={"c": "丙"})
        # 修改 e2 的 lang_path，避免合并前逻辑误认
        e2.entry = LangEntry(
            jar_path=Path("/fake2.jar"),
            mod_id="mod_a",
            lang_path="assets/mod_a/lang/en_us.json",
            fmt="json",
            source={"c": "d"},
            existing={},
        )
        build_merged_pack(out, [e1, e2], 15, target_lang="zh_cn")
        with zipfile.ZipFile(out) as zf:
            content = zf.read("assets/mod_a/lang/zh_cn.json").decode("utf-8")
        data = json.loads(content)
        # 两个 key 都存在
        assert data == {"a": "甲", "c": "丙"}