from __future__ import annotations

from mc_mod_translator.langfile import (
    JSON_FORMAT,
    LANG_FORMAT,
    lang_filename_candidates,
    normalize_lang_code,
    parse_lang_content,
    serialize_lang,
    target_lang_filename,
)


class TestNormalizeLangCode:
    def test_json_lowercase(self):
        assert normalize_lang_code("zh_cn", JSON_FORMAT) == "zh_cn"
        assert normalize_lang_code("zh-CN", JSON_FORMAT) == "zh_cn"
        assert normalize_lang_code("ZH_CN", JSON_FORMAT) == "zh_cn"

    def test_lang_uppercase_region(self):
        assert normalize_lang_code("zh_cn", LANG_FORMAT) == "zh_CN"
        assert normalize_lang_code("zh-CN", LANG_FORMAT) == "zh_CN"
        assert normalize_lang_code("ZH_CN", LANG_FORMAT) == "zh_CN"

    def test_zh_tw(self):
        assert normalize_lang_code("zh_tw", JSON_FORMAT) == "zh_tw"
        assert normalize_lang_code("zh_tw", LANG_FORMAT) == "zh_TW"

    def test_en_us(self):
        assert normalize_lang_code("en_us", JSON_FORMAT) == "en_us"
        assert normalize_lang_code("en_us", LANG_FORMAT) == "en_US"

    def test_unknown_lang(self):
        # 未登记的语言：仍然按规则转换
        assert normalize_lang_code("xx_yy", JSON_FORMAT) == "xx_yy"
        assert normalize_lang_code("xx_yy", LANG_FORMAT) == "xx_YY"

    def test_empty(self):
        assert normalize_lang_code("", JSON_FORMAT) == ""


class TestTargetLangFilename:
    def test_json(self):
        assert target_lang_filename("zh_cn", JSON_FORMAT) == "zh_cn.json"

    def test_lang_uppercase(self):
        assert target_lang_filename("zh_cn", LANG_FORMAT) == "zh_CN.lang"
        assert target_lang_filename("zh-CN", LANG_FORMAT) == "zh_CN.lang"
        assert target_lang_filename("zh_tw", LANG_FORMAT) == "zh_TW.lang"

    def test_en_us_lang(self):
        assert target_lang_filename("en_us", LANG_FORMAT) == "en_US.lang"


class TestLangFilenameCandidates:
    def test_json_candidates(self):
        cands = lang_filename_candidates("zh_cn", JSON_FORMAT)
        assert "zh_cn.json" in cands
        # JSON 格式不应包含 .lang
        assert all(c.endswith(".json") for c in cands)

    def test_lang_candidates_include_variants(self):
        cands = lang_filename_candidates("zh_cn", LANG_FORMAT)
        # 应同时包含标准 zh_CN.lang 和小写变体
        assert "zh_CN.lang" in cands
        assert "zh_cn.lang" in cands

    def test_en_us(self):
        cands = lang_filename_candidates("en_us", LANG_FORMAT)
        assert "en_US.lang" in cands
        assert "en_us.lang" in cands


class TestParseSerialize:
    def test_parse_json(self):
        data = parse_lang_content('{"a": "b"}', JSON_FORMAT)
        assert data == {"a": "b"}

    def test_parse_json_invalid(self):
        assert parse_lang_content("not json", JSON_FORMAT) == {}

    def test_parse_lang(self):
        content = "# comment\na=b\nc = d\n\n"
        data = parse_lang_content(content, LANG_FORMAT)
        assert data == {"a": "b", "c": "d"}

    def test_roundtrip_json(self):
        data = {"a": "b", "中文": "值"}
        text = serialize_lang(data, JSON_FORMAT)
        assert parse_lang_content(text, JSON_FORMAT) == data

    def test_roundtrip_lang(self):
        data = {"a": "b", "c": "d"}
        text = serialize_lang(data, LANG_FORMAT)
        assert parse_lang_content(text, LANG_FORMAT) == data