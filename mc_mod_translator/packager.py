from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from .langfile import serialize_lang, target_lang_filename
from .translator import TranslatedEntry


SupportedFormats = Union[int, List[int], Tuple[int, int]]


def make_pack_mcmeta(
    pack_format: int,
    description: str,
    supported_formats: Optional[SupportedFormats] = None,
) -> str:
    pack: Dict[str, object] = {
        "pack_format": pack_format,
        "description": description,
    }
    if supported_formats is not None:
        if isinstance(supported_formats, int):
            pack["supported_formats"] = [supported_formats]
        elif isinstance(supported_formats, tuple):
            pack["supported_formats"] = list(supported_formats)
        else:
            pack["supported_formats"] = list(supported_formats)
    return json.dumps({"pack": pack}, ensure_ascii=False, indent=2)


def _merge_by_path(
    entries: List[TranslatedEntry], target_lang: str
) -> Dict[str, Tuple[TranslatedEntry, Dict[str, str]]]:
    """同一资源包内、同一 mod + 同一 fmt 的多个条目合并为一个 lang 文件。"""
    merged: Dict[str, Tuple[TranslatedEntry, Dict[str, str]]] = {}
    for te in entries:
        fname = target_lang_filename(target_lang, te.entry.fmt)
        path = f"assets/{te.entry.mod_id}/lang/{fname}"
        if path in merged:
            base_te, base_data = merged[path]
            combined = dict(base_data)
            combined.update(te.merged)
            merged[path] = (base_te, combined)
        else:
            merged[path] = (te, dict(te.merged))
    return merged


def _build_zip(
    output_path: Path,
    entries: List[TranslatedEntry],
    pack_format: int,
    description: str,
    target_lang: str,
    supported_formats: Optional[SupportedFormats] = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "pack.mcmeta",
            make_pack_mcmeta(pack_format, description, supported_formats),
        )
        for path, (te, data) in _merge_by_path(entries, target_lang).items():
            zf.writestr(path, serialize_lang(data, te.entry.fmt))


def build_merged_pack(
    output_path: Path,
    entries: List[TranslatedEntry],
    pack_format: int,
    description: str = "Mods 简体中文翻译",
    target_lang: str = "zh_cn",
    supported_formats: Optional[SupportedFormats] = None,
) -> Path:
    _build_zip(
        output_path, entries, pack_format, description, target_lang, supported_formats
    )
    return output_path


def build_per_mod_packs(
    output_dir: Path,
    entries: List[TranslatedEntry],
    pack_format: int,
    target_lang: str = "zh_cn",
    supported_formats: Optional[SupportedFormats] = None,
) -> List[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    by_mod: Dict[str, List[TranslatedEntry]] = {}
    for te in entries:
        by_mod.setdefault(te.entry.mod_id, []).append(te)

    paths: List[Path] = []
    for mod_id, mod_entries in by_mod.items():
        path = output_dir / f"{mod_id}-{target_lang}.zip"
        _build_zip(
            path,
            mod_entries,
            pack_format,
            f"{mod_id} 简体中文翻译",
            target_lang,
            supported_formats,
        )
        paths.append(path)
    return paths