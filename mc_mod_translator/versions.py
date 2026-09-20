from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Tuple


# 参考 Minecraft Wiki (Resource pack version)
PACK_FORMAT_TABLE = [
    ((1, 6, 1), (1, 8, 9), 1),
    ((1, 9, 0), (1, 10, 2), 2),
    ((1, 11, 0), (1, 12, 2), 3),
    ((1, 13, 0), (1, 14, 4), 4),
    ((1, 15, 0), (1, 16, 1), 5),
    ((1, 16, 2), (1, 16, 5), 6),
    ((1, 17, 0), (1, 17, 1), 7),
    ((1, 18, 0), (1, 18, 2), 8),
    ((1, 19, 0), (1, 19, 2), 9),
    ((1, 19, 3), (1, 19, 3), 12),
    ((1, 19, 4), (1, 19, 4), 13),
    ((1, 20, 0), (1, 20, 1), 15),
    ((1, 20, 2), (1, 20, 2), 18),
    ((1, 20, 3), (1, 20, 4), 22),
    ((1, 20, 5), (1, 20, 6), 32),
    ((1, 21, 0), (1, 21, 1), 34),
    ((1, 21, 2), (1, 21, 3), 42),
    ((1, 21, 4), (1, 21, 4), 46),
    ((1, 21, 5), (1, 21, 5), 55),
]

# 允许 "1.20.1" 以及 "1.20.1-forge-47.2.0" 这类目录名；只取前缀纯版本号
_VERSION_RE = re.compile(r"^(\d+(?:\.\d+){1,3})")


def parse_version(v: str) -> Tuple[int, ...]:
    """把版本字符串解析为**固定 3 元组**，便于与 ``PACK_FORMAT_TABLE`` 比较。

    - ``"1.20.1"`` -> ``(1, 20, 1)``
    - ``"1.20"``   -> ``(1, 20, 0)``（补齐 patch 位）
    - ``"1"``      -> ``(1, 0, 0)``（补齐 minor/patch 位）
    - ``""``       -> ``()``（保留“无法解析”语义）
    - ``"abc"``    -> ``()``
    """
    if not v or not v.strip():
        return ()
    parts: List[int] = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    if not parts:
        return ()
    # 补齐到 3 位，与 PACK_FORMAT_TABLE 的 (major, minor, patch) 对齐
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def pack_format_for(version: str) -> int:
    v = parse_version(version)
    if not v:
        return PACK_FORMAT_TABLE[-1][2]
    for lo, hi, pf in PACK_FORMAT_TABLE:
        if lo <= v <= hi:
            return pf
    if v < PACK_FORMAT_TABLE[0][0]:
        return PACK_FORMAT_TABLE[0][2]
    return PACK_FORMAT_TABLE[-1][2]


def uses_json_lang(version: str) -> bool:
    """1.13 起语言文件从 .lang 切换到 .json。"""
    v = parse_version(version)
    return v >= (1, 13, 0)


def _extract_versions(dir_path: Path) -> List[str]:
    if not dir_path.is_dir():
        return []
    out: List[str] = []
    for d in dir_path.iterdir():
        if not d.is_dir():
            continue
        m = _VERSION_RE.match(d.name)
        if m:
            out.append(m.group(1))
    return out


def detect_mc_version(pack_root: Path) -> Optional[str]:
    pack_root = Path(pack_root)
    # CurseForge
    m = pack_root / "manifest.json"
    if m.exists():
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
            v = data.get("minecraft", {}).get("version")
            if v:
                return v
        except Exception:
            pass
    # Modrinth
    mi = pack_root / "modrinth.index.json"
    if mi.exists():
        try:
            data = json.loads(mi.read_text(encoding="utf-8"))
            v = data.get("dependencies", {}).get("minecraft")
            if v:
                return v
        except Exception:
            pass
    # versions 文件夹（含 forge/fabric 后缀）
    cands = _extract_versions(pack_root / "versions")
    if cands:
        cands.sort(key=parse_version)
        return cands[-1]
    # .minecraft/versions
    cands = _extract_versions(pack_root / ".minecraft" / "versions")
    if cands:
        cands.sort(key=parse_version)
        return cands[-1]
    return None