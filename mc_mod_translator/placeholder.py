from __future__ import annotations

import re
from collections import Counter
from typing import List, Tuple


_PATTERNS = [
    # %1$s / %s / %d / %f 等
    re.compile(r"%(\d+\$)?[sdifoxXeEgGc]"),
    # {0} / {name} / {player.name}
    re.compile(r"\{[^{}]*\}"),
    # §a §l §r 等
    re.compile(r"§[0-9a-fk-orA-FK-OR]"),
    # \n \t \r
    re.compile(r"\\[ntr]"),
    # &a &l 等（部分 mod 使用）
    re.compile(r"&[0-9a-fk-orA-FK-OR]"),
]

# 引擎偶尔会加空格：__PH_ 0 __ 等
_RESIDUE_RE = re.compile(r"__PH_\s*\d+\s*__")


def protect(text: str) -> Tuple[str, List[str]]:
    placeholders: List[str] = []

    def _sub(m: "re.Match[str]") -> str:
        placeholders.append(m.group(0))
        return f"__PH_{len(placeholders) - 1}__"

    result = text
    for pat in _PATTERNS:
        result = pat.sub(_sub, result)
    return result, placeholders


def restore(text: str, placeholders: List[str]) -> str:
    for i, p in enumerate(placeholders):
        text = text.replace(f"__PH_{i}__", p)
        # 容忍引擎加了空格
        text = text.replace(f"__PH_ {i} __", p)
        text = text.replace(f"__PH_{i} __", p)
        text = text.replace(f"__PH_ {i}__", p)
    return text


def validate_restore(text: str, placeholders: List[str]) -> bool:
    """校验占位符是否被完整还原。

    返回 False 表示：
      - 译文中仍残留 ``__PH_N__``
      - 某个原始占位符在译文中缺失（数量少于原文）
    """
    if _RESIDUE_RE.search(text):
        return False
    if not placeholders:
        return True
    expected = Counter(placeholders)
    for ph, cnt in expected.items():
        if text.count(ph) < cnt:
            return False
    return True