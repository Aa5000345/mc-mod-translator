from __future__ import annotations

from pathlib import Path

from mc_mod_translator.versions import (
    detect_mc_version,
    pack_format_for,
    parse_version,
    uses_json_lang,
)


def test_parse_version():
    # 三位补齐：便于与 PACK_FORMAT_TABLE 的三元组比较
    assert parse_version("1.20.1") == (1, 20, 1)
    assert parse_version("1.20") == (1, 20, 0)
    assert parse_version("1") == (1, 0, 0)
    # 空 / 非法保留“无法解析”语义
    assert parse_version("") == ()
    assert parse_version("abc") == ()


def test_pack_format_for():
    assert pack_format_for("1.6.1") == 1
    assert pack_format_for("1.12.2") == 3
    assert pack_format_for("1.13") == 4
    assert pack_format_for("1.20.1") == 15
    assert pack_format_for("1.20.2") == 18
    assert pack_format_for("1.21.4") == 46


def test_uses_json_lang():
    assert not uses_json_lang("1.12.2")
    assert uses_json_lang("1.13")
    assert uses_json_lang("1.20.1")


def test_detect_from_manifest(tmp_path: Path):
    (tmp_path / "manifest.json").write_text(
        '{"minecraft": {"version": "1.19.4"}}', encoding="utf-8"
    )
    assert detect_mc_version(tmp_path) == "1.19.4"


def test_detect_from_modrinth(tmp_path: Path):
    (tmp_path / "modrinth.index.json").write_text(
        '{"dependencies": {"minecraft": "1.20.1"}}', encoding="utf-8"
    )
    assert detect_mc_version(tmp_path) == "1.20.1"


def test_detect_from_versions_dir(tmp_path: Path):
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "1.19.4").mkdir()
    (versions / "1.20.1").mkdir()
    assert detect_mc_version(tmp_path) == "1.20.1"


def test_detect_versions_dir_with_modloader_suffix(tmp_path: Path):
    """目录名带 forge/fabric 后缀，也要提取出前缀版本号。"""
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "1.20.1-forge-47.2.0").mkdir()
    (versions / "1.20.4-fabric-0.15.0").mkdir()
    assert detect_mc_version(tmp_path) == "1.20.4"


def test_detect_none(tmp_path: Path):
    assert detect_mc_version(tmp_path) is None