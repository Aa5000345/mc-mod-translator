from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, Optional


DEFAULT_TERMS: Dict[str, str] = {
    "creeper": "苦力怕",
    "redstone": "红石",
    "ender dragon": "末影龙",
    "enderman": "末影人",
    "nether": "下界",
    "the end": "末地",
    "overworld": "主世界",
    "diamond": "钻石",
    "emerald": "绿宝石",
    "iron ingot": "铁锭",
    "gold ingot": "金锭",
    "coal": "煤炭",
    "stick": "木棍",
    "crafting table": "工作台",
    "furnace": "熔炉",
    "chest": "箱子",
    "sword": "剑",
    "pickaxe": "镐",
    "axe": "斧",
    "shovel": "锹",
    "hoe": "锄",
    "helmet": "头盔",
    "chestplate": "胸甲",
    "leggings": "护腿",
    "boots": "靴子",
    "water bucket": "水桶",
    "lava bucket": "熔岩桶",
}


class Glossary:
    def __init__(self, load_default: bool = True):
        self.entries: Dict[str, str] = {}
        if load_default:
            self.entries.update(DEFAULT_TERMS)

    def load(self, path: Path) -> None:
        p = Path(path)
        if not p.exists():
            return
        with p.open(encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header and header[0].lower() == "en":
                pass
            else:
                # 无表头时按行处理
                if header and len(header) >= 2:
                    self.entries[header[0].strip().lower()] = header[1].strip()
            for row in reader:
                if len(row) >= 2 and row[0].strip():
                    self.entries[row[0].strip().lower()] = row[1].strip()

    def save(self, path: Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["en", "zh_cn"])
            for k, v in sorted(self.entries.items()):
                writer.writerow([k, v])

    def lookup(self, text: str) -> Optional[str]:
        if not text:
            return None
        return self.entries.get(text.strip().lower())

    def apply_inline(self, text: str) -> str:
        """在译文中替换已知术语，用于简单场景。"""
        if not text:
            return text
        result = text
        for en, zh in sorted(self.entries.items(), key=lambda x: -len(x[0])):
            pattern = r"\b" + re.escape(en) + r"\b"
            result = re.sub(pattern, zh, result, flags=re.IGNORECASE)
        return result

    def add(self, en: str, zh: str) -> None:
        if en and zh:
            self.entries[en.strip().lower()] = zh.strip()