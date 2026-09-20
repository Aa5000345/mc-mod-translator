from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


JSON_FORMAT = "json"
LANG_FORMAT = "lang"

# 已知语言码映射：key 为 "小写+下划线" 归一化形式
# value = (json 资源包代码, 旧 .lang 代码)
_LANG_CODE_MAP = {
    "zh_cn": ("zh_cn", "zh_CN"),
    "zh_tw": ("zh_tw", "zh_TW"),
    "zh_hk": ("zh_hk", "zh_HK"),
    "en_us": ("en_us", "en_US"),
    "en_gb": ("en_gb", "en_GB"),
    "ja_jp": ("ja_jp", "ja_JP"),
    "ko_kr": ("ko_kr", "ko_KR"),
    "fr_fr": ("fr_fr", "fr_FR"),
    "de_de": ("de_de", "de_DE"),
    "ru_ru": ("ru_ru", "ru_RU"),
    "es_es": ("es_es", "es_ES"),
    "pt_br": ("pt_br", "pt_BR"),
}


def _normalize_key(lang: str) -> str:
    return lang.replace("-", "_").strip().lower()


def normalize_lang_code(lang: str, fmt: str) -> str:
    """把任意语言码规范为文件名中使用的形式。

    - json 资源包：全小写 + 下划线，如 ``zh_cn``
    - 旧 .lang：语言小写 + 地区大写，如 ``zh_CN``
    """
    if not lang:
        return lang
    key = _normalize_key(lang)
    if key in _LANG_CODE_MAP:
        json_code, lang_code = _LANG_CODE_MAP[key]
    else:
        json_code = key
        parts = key.split("_")
        if len(parts) >= 2:
            lang_code = f"{parts[0]}_{parts[1].upper()}"
        else:
            lang_code = key
    return json_code if fmt == JSON_FORMAT else lang_code


def target_lang_filename(target_lang: str, fmt: str) -> str:
    """返回目标语言在给定格式下的文件名。

    - ``target_lang_filename("zh_cn", "json")`` -> ``"zh_cn.json"``
    - ``target_lang_filename("zh_cn", "lang")`` -> ``"zh_CN.lang"``
    """
    code = normalize_lang_code(target_lang, fmt)
    ext = "json" if fmt == JSON_FORMAT else "lang"
    return f"{code}.{ext}"


def lang_filename_candidates(lang: str, fmt: str) -> List[str]:
    """返回同一语言码在 .json/.lang 中可能出现的所有文件名。

    用于识别旧 mod 里大小写不规范的 ``en_US.lang``、``zh_cn.lang`` 等。
    """
    key = _normalize_key(lang)
    json_code, lang_code = _LANG_CODE_MAP.get(key, (key, key))
    json_base = json_code.replace("_", "_")
    lang_base = lang_code if "_" in lang_code else lang_code
    # 同时包含大小写变体
    names = {
        f"{json_base}.json",
        f"{json_base}.lang",
        f"{lang_base}.lang",
        f"{lang_base.lower()}.lang",
    }
    if fmt == JSON_FORMAT:
        return [n for n in names if n.endswith(".json")] or [f"{json_base}.json"]
    return sorted(names)


def parse_lang_content(content: str, fmt: str) -> Dict[str, str]:
    if fmt == JSON_FORMAT:
        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                return {}
            return {str(k): str(v) for k, v in data.items()}
        except Exception:
            return {}
    result: Dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def serialize_lang(data: Dict[str, str], fmt: str) -> str:
    if fmt == JSON_FORMAT:
        return json.dumps(data, ensure_ascii=False, indent=2)
    return "\n".join(f"{k}={v}" for k, v in data.items()) + "\n"


def read_lang(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    fmt = JSON_FORMAT if path.suffix == ".json" else LANG_FORMAT
    return parse_lang_content(path.read_text(encoding="utf-8"), fmt)


def write_lang(path: Path, data: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = JSON_FORMAT if path.suffix == ".json" else LANG_FORMAT
    path.write_text(serialize_lang(data, fmt), encoding="utf-8")