from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from .cache import TranslationCache
from .glossary import Glossary
from .translator import MANUAL_ENGINE, TranslatedEntry


FIELDS = [
    "mod_id",
    "key",
    "source",
    "machine_translation",
    "proofread_translation",
    "status",
]


def export_csv(
    path: Path,
    entries: List[TranslatedEntry],
    tgt_lang: str = "zh_cn",
    only_modified: bool = False,
) -> Path:
    """导出校对 CSV。

    - 参数 ``tgt_lang`` 仅用于文件名/元信息扩展；缓存导入时由 import_csv 显式传入。
    - ``only_modified=True`` 时只导出有译文的行，避免 CSV 巨大。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FIELDS)
        for te in entries:
            for key, src in te.entry.source.items():
                mt = te.merged.get(key, "")
                if only_modified and not mt:
                    continue
                writer.writerow([te.entry.mod_id, key, src, mt, "", ""])
    return path


def import_csv(
    path: Path,
    cache: TranslationCache,
    glossary: Glossary,
    engine_name: str = MANUAL_ENGINE,
    tgt_lang: str = "zh_cn",
    add_to_glossary: bool = True,
    glossary_max_len: int = 40,
) -> int:
    """导入校对文件，写入缓存 + 术语表。返回更新条数。

    默认写入 ``MANUAL_ENGINE``（"manual"）名下，Translator 会优先于引擎缓存查找。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    updated = 0
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src = (row.get("source") or "").strip()
            proof = (row.get("proofread_translation") or "").strip()
            final = proof or (row.get("machine_translation") or "").strip()
            if not src or not final:
                continue
            cache.update(src, engine_name, "en", tgt_lang, final)
            if add_to_glossary and len(src) <= glossary_max_len and "\n" not in src:
                glossary.add(src, final)
            updated += 1
    return updated