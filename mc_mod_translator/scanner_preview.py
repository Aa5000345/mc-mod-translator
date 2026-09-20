from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .scanner import LangEntry, scan_mods_dir


@dataclass
class PreviewStats:
    """翻译前预览统计，供 GUI/CLI 显示。"""

    total_jars: int = 0
    total_lang_entries: int = 0
    total_keys: int = 0
    existing_keys: int = 0
    missing_keys: int = 0
    unique_missing_texts: int = 0
    by_mod: Dict[str, Dict[str, int]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"jar={self.total_jars} 语言文件={self.total_lang_entries} "
            f"key 总数={self.total_keys} 已有={self.existing_keys} "
            f"缺失={self.missing_keys} 唯一缺失文本={self.unique_missing_texts}"
        )


def _count_jars(mods_dir: Path) -> int:
    if not mods_dir.is_dir():
        return 0
    return sum(1 for _ in mods_dir.glob("*.jar"))


def preview(
    mods_dir: Path,
    target_lang: str = "zh_cn",
    entries: List[LangEntry] | None = None,
) -> PreviewStats:
    """扫描并统计。

    参数 ``entries`` 允许调用方传入已扫描结果，避免重复扫描。
    """
    mods_dir = Path(mods_dir)
    stats = PreviewStats()
    stats.total_jars = _count_jars(mods_dir)

    if entries is None:
        try:
            entries = scan_mods_dir(mods_dir, target_lang=target_lang)
        except Exception as e:  # noqa: BLE001
            stats.errors.append(f"{type(e).__name__}: {e}")
            return stats

    stats.total_lang_entries = len(entries)
    missing_texts: set = set()

    for e in entries:
        src_keys = set(e.source.keys())
        existing_keys = set(e.existing.keys())
        missing = src_keys - existing_keys

        stats.total_keys += len(src_keys)
        stats.existing_keys += len(src_keys & existing_keys)
        stats.missing_keys += len(missing)

        for k in missing:
            v = e.source.get(k)
            if v and v.strip():
                missing_texts.add(v)

        stats.by_mod[e.mod_id] = {
            "lang_entries": stats.by_mod.get(e.mod_id, {}).get("lang_entries", 0) + 1,
            "total_keys": len(src_keys),
            "existing_keys": len(src_keys & existing_keys),
            "missing_keys": len(missing),
        }

    stats.unique_missing_texts = len(missing_texts)
    return stats