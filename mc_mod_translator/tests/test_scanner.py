from __future__ import annotations

from pathlib import Path

from mc_mod_translator.scanner import (
    resolve_mods_dir,
    scan_jar,
    scan_mods_dir,
)


class TestScanJar:
    def test_en_us_json(self, tmp_jar, make_json_lang):
        jar = tmp_jar(
            "mod_a.jar",
            {
                "assets/mod_a/lang/en_us.json": make_json_lang(
                    {"item.a": "Sword", "item.b": "Pickaxe"}
                )
            },
        )
        entries = scan_jar(jar, target_lang="zh_cn")
        assert len(entries) == 1
        e = entries[0]
        assert e.mod_id == "mod_a"
        assert e.fmt == "json"
        assert e.source == {"item.a": "Sword", "item.b": "Pickaxe"}
        assert e.existing == {}

    def test_en_US_lang_uppercase(self, tmp_jar, make_lang_lang):
        # 老版本 1.12 及以前的标准：en_US.lang
        jar = tmp_jar(
            "old_mod.jar",
            {
                "assets/old_mod/lang/en_US.lang": make_lang_lang(
                    {"item.a": "Sword"}
                )
            },
        )
        entries = scan_jar(jar, target_lang="zh_cn")
        assert len(entries) == 1
        assert entries[0].fmt == "lang"
        assert entries[0].source == {"item.a": "Sword"}

    def test_en_us_lang_lowercase(self, tmp_jar, make_lang_lang):
        # 也有一些 mod 用小写，仍应识别
        jar = tmp_jar(
            "odd.jar",
            {
                "assets/odd/lang/en_us.lang": make_lang_lang({"a": "b"}),
            },
        )
        entries = scan_jar(jar)
        assert len(entries) == 1

    def test_existing_zh_cn_uppercase(self, tmp_jar, make_json_lang):
        # 已有 zh_cn.json 应被读到 existing
        jar = tmp_jar(
            "mod_a.jar",
            {
                "assets/mod_a/lang/en_us.json": make_json_lang({"a": "b"}),
                "assets/mod_a/lang/zh_cn.json": make_json_lang({"a": "中文"}),
            },
        )
        entries = scan_jar(jar, target_lang="zh_cn")
        assert entries[0].existing == {"a": "中文"}

    def test_existing_zh_cn_lower_lang(self, tmp_jar, make_json_lang, make_lang_lang):
        # 已有 zh_cn.lang（小写）也应被读到
        jar = tmp_jar(
            "mod_b.jar",
            {
                "assets/mod_b/lang/en_us.lang": make_lang_lang({"a": "b"}),
                "assets/mod_b/lang/zh_cn.lang": make_lang_lang({"a": "中"}),
            },
        )
        entries = scan_jar(jar, target_lang="zh_cn")
        assert entries[0].existing == {"a": "中"}

    def test_existing_zh_CN_uppercase_lang(self, tmp_jar, make_lang_lang):
        # 已有 zh_CN.lang（大写）也应被读到
        jar = tmp_jar(
            "mod_c.jar",
            {
                "assets/mod_c/lang/en_us.lang": make_lang_lang({"a": "b"}),
                "assets/mod_c/lang/zh_CN.lang": make_lang_lang({"a": "中"}),
            },
        )
        entries = scan_jar(jar, target_lang="zh_cn")
        assert entries[0].existing == {"a": "中"}

    def test_bad_jar_does_not_raise(self, tmp_path: Path):
        bad = tmp_path / "bad.jar"
        bad.write_bytes(b"not a zip")
        entries = scan_jar(bad)
        assert entries == []

    def test_nested_jar(self, tmp_jar, make_json_lang):
        jar = tmp_jar(
            "outer.jar",
            {
                "assets/inner/lang/en_us.json": make_json_lang({"a": "b"}),
            },
            sub_jar=True,
        )
        entries = scan_jar(jar, allow_jar_in_jar=True)
        assert any(e.mod_id == "inner" for e in entries)


class TestScanModsDir:
    def test_dir_with_multiple_jars(self, tmp_path, tmp_jar, make_json_lang):
        # 构造两个 jar 放到同一目录
        j1 = tmp_jar("a.jar", {"assets/ma/lang/en_us.json": make_json_lang({"k": "v"})})
        j2 = tmp_jar("b.jar", {"assets/mb/lang/en_us.json": make_json_lang({"k": "v"})})
        mods = tmp_path / "mods"
        mods.mkdir()
        j1.rename(mods / j1.name)
        j2.rename(mods / j2.name)

        entries = scan_mods_dir(mods)
        mod_ids = sorted({e.mod_id for e in entries})
        assert mod_ids == ["ma", "mb"]

    def test_non_existent_dir(self, tmp_path: Path):
        assert scan_mods_dir(tmp_path / "nope") == []


class TestResolveModsDir:
    def test_pack_root(self, tmp_path: Path):
        (tmp_path / "mods").mkdir()
        assert resolve_mods_dir(tmp_path) == tmp_path / "mods"

    def test_mods_dir_directly(self, tmp_path: Path):
        mods = tmp_path / "mods"
        mods.mkdir()
        assert resolve_mods_dir(mods) == mods

    def test_minecraft_subdir(self, tmp_path: Path):
        mc = tmp_path / ".minecraft"
        mc.mkdir()
        (mc / "mods").mkdir()
        assert resolve_mods_dir(tmp_path) == mc / "mods"

    def test_none(self, tmp_path: Path):
        assert resolve_mods_dir(tmp_path) is None