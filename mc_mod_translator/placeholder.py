from __future__ import annotations

import re
from collections import Counter
from typing import List, Tuple


# 原始占位符（保护阶段的匹配）
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

# 保护后的占位符标记：__PH_0__、__PH_1__...
# 引擎有时会在下划线、PH、数字之间插入空格，例如：
#   __ PH_0 __
#   __PH_ 0 __
#   __ PH_ 0__
# 统一用这个正则匹配**所有**变形。
_RESTORE_RE = re.compile(r"__\s*PH_\s*(\d+)\s*__")

# 残留检测：与 _RESTORE_RE 同构
_RESIDUE_RE = re.compile(r"__\s*PH_\s*\d+\s*__")


def protect(text: str) -> Tuple[str, List[str]]:
    """把占位符替换为 __PH_N__，返回 (保护后的文本, 原占位符列表)。"""
    placeholders: List[str] = []

    def _sub(m: "re.Match[str]") -> str:
        placeholders.append(m.group(0))
        return f"__PH_{len(placeholders) - 1}__"

    result = text
    for pat in _PATTERNS:
        result = pat.sub(_sub, result)
    return result, placeholders


def restore(text: str, placeholders: List[str]) -> str:
    """把 __PH_N__（含空格变形）还原为原始占位符。

    用正则一次性替换所有变形：
      - ``__PH_0__``
      - ``__ PH_0 __``
      - ``__PH_ 0 __``
      - ``__ PH_ 0__``
      - ... 任意 __ 与 PH_ 之间、数字两侧的空白组合
    """

    def _sub(m: "re.Match[str]") -> str:
        try:
            idx = int(m.group(1))
        except (TypeError, ValueError):
            return m.group(0)
        if 0 <= idx < len(placeholders):
            return placeholders[idx]
        # 索引越界：保留原样，交给 validate_restore 判失败
        return m.group(0)

    return _RESTORE_RE.sub(_sub, text)


def validate_restore(text: str, placeholders: List[str]) -> bool:
    """校验占位符是否被完整还原。

    返回 False 表示：
      - 译文中仍残留 ``__PH_N__``（含空格变形）
      - 某个原始占位符在译文中缺失（数量少于原文）
    """
    # 1. 残留检测
    if _RESIDUE_RE.search(text):
        return False

    # 2. 数量检测：每个原始占位符必须在译文中至少出现同样次数
    if not placeholders:
        return True
    expected = Counter(placeholders)
    for ph, cnt in expected.items():
        if text.count(ph) < cnt:
            return False
    return True