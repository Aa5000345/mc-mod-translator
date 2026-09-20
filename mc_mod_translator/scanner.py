from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from .langfile import (
    JSON_FORMAT,
    LANG_FORMAT,
    lang_filename_candidates,
    parse_lang_content,
)


_EN_US_NAMES = {"en_us.json", "en_us.lang"}


@dataclass
class LangEntry:
    jar_path: Path
    mod_id: str
    lang_path: str
    fmt: str  # "json" | "lang"
    source: Dict[str, str] = field(default_factory=dict)
    existing: Dict[str, str] = field(default_factory=dict)


def _pick_source(names: set[str], mod_id: str) -> Optional[tuple[str, str]]:
    """在给定 zip 内挑选该 mod 的源语言文件，优先 json。

    返回 (zip 内路径, fmt)，未找到返回 None。
    """
    prefix = f"assets/{mod_id}/lang/"
    json_path: Optional[str] = None
    lang_path: Optional[str] = None
    for name in names:
        if not name.startswith(prefix):
            continue
        fname = name[len(prefix):]
        if fname.lower() not in _EN_US_NAMES:
            continue
        if fname.lower().endswith(".json"):
            json_path = name
        else:
            lang_path = name
    if json_path is not None:
        return json_path, JSON_FORMAT
    if lang_path is not None:
        return lang_path, LANG_FORMAT
    return None


def _read_existing(
    zf: zipfile.ZipFile,
    names: set[str],
    mod_id: str,
    fmt: str,
    target_lang: str,
) -> Dict[str, str]:
    """尝试读取目标语言已有翻译，兼容大小写变体。"""
    prefix = f"assets/{mod_id}/lang/"
    for cand in lang_filename_candidates(target_lang, fmt):
        path = f"{prefix}{cand}"
        if path in names:
            try:
                return parse_lang_content(
                    zf.read(path).decode("utf-8", errors="replace"), fmt
                )
            except Exception as e:
                logger.warning(f"读取已有翻译失败 {path}: {e}")
    return {}


def _scan_zip(
    zf: zipfile.ZipFile,
    jar_path: Path,
    target_lang: str,
) -> List[LangEntry]:
    entries: List[LangEntry] = []
    names = set(zf.namelist())

    mod_ids: set[str] = set()
    for name in names:
        parts = name.split("/")
        if len(parts) == 4 and parts[0] == "assets" and parts[2] == "lang":
            mod_ids.add(parts[1])

    for mod_id in sorted(mod_ids):
        pick = _pick_source(names, mod_id)
        if pick is None:
            continue
        lang_path, fmt = pick
        try:
            content = zf.read(lang_path).decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"读取语言文件失败 {jar_path}::{lang_path}: {e}")
            continue
        source = parse_lang_content(content, fmt)
        if not source:
            continue
        existing = _read_existing(zf, names, mod_id, fmt, target_lang)
        entries.append(
            LangEntry(
                jar_path=jar_path,
                mod_id=mod_id,
                lang_path=lang_path,
                fmt=fmt,
                source=source,
                existing=existing,
            )
        )
    return entries


def scan_jar(
    jar_path: Path,
    target_lang: str = "zh_cn",
    *,
    allow_jar_in_jar: bool = True,
) -> List[LangEntry]:
    entries: List[LangEntry] = []
    try:
        with zipfile.ZipFile(jar_path) as zf:
            entries.extend(_scan_zip(zf, jar_path, target_lang))
            if allow_jar_in_jar:
                for name in zf.namelist():
                    if not (
                        name.startswith("META-INF/jarjar/")
                        and name.endswith(".jar")
                    ):
                        continue
                    try:
                        data = zf.read(name)
                        with zipfile.ZipFile(io.BytesIO(data)) as nested:
                            entries.extend(_scan_zip(nested, jar_path, target_lang))
                    except Exception as e:
                        logger.warning(f"解析嵌套 jar 失败 {jar_path}::{name}: {e}")
    except zipfile.BadZipFile as e:
        logger.warning(f"坏 jar（跳过）{jar_path}: {e}")
    except Exception as e:
        logger.warning(f"扫描 jar 失败 {jar_path}: {e}")
    return entries


def scan_mods_dir(mods_dir: Path, target_lang: str = "zh_cn") -> List[LangEntry]:
    mods_dir = Path(mods_dir)
    all_entries: List[LangEntry] = []
    if not mods_dir.is_dir():
        return all_entries
    for jar in sorted(mods_dir.glob("*.jar")):
        all_entries.extend(scan_jar(jar, target_lang))
    return all_entries


def scan_preview(mods_dir: Path, target_lang: str = "zh_cn"):
    """便捷函数：扫描并返回 ``PreviewStats``。

    为避免循环导入，运行时从 ``scanner_preview`` 导入。
    """
    from .scanner_preview import preview

    return preview(mods_dir, target_lang=target_lang)


def resolve_mods_dir(path: Path) -> Optional[Path]:
    """传入整合包根目录或 mods 文件夹，返回实际 mods 文件夹。"""
    path = Path(path)
    if not path.is_dir():
        return None
    if (path / "mods").is_dir():
        return path / "mods"
    if path.name.lower() == "mods":
        return path
    if (path / ".minecraft" / "mods").is_dir():
        return path / ".minecraft" / "mods"
    return None