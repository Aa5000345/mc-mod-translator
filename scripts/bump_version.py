#!/usr/bin/env python3
"""版本号快速修改脚本。

一次性更新：
  - pyproject.toml           version = "x.y.z"
  - mc_mod_translator/__init__.py   __version__ = "x.y.z"
  - README.md                徽章 version-x.y.z-blue.svg

用法：
    # 直接指定版本
    python scripts/bump_version.py 0.4.0

    # 自动递增
    python scripts/bump_version.py --bump patch
    python scripts/bump_version.py --bump minor
    python scripts/bump_version.py --bump major

    # 顺带 git tag（用于触发 GitHub Actions Release）
    python scripts/bump_version.py --bump minor --tag

    # 只预览，不写入
    python scripts/bump_version.py 0.4.0 --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# 路径定位
# ---------------------------------------------------------------------------

def _find_repo_root(start: Path) -> Path:
    """从 start 向上查找含 pyproject.toml 的目录。"""
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists():
            return p
    return start


REPO_ROOT = _find_repo_root(Path(__file__).resolve())

PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PY = REPO_ROOT / "mc_mod_translator" / "__init__.py"
README = REPO_ROOT / "README.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"


# ---------------------------------------------------------------------------
# 版本号解析
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


@dataclass
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, s: str) -> "Version":
        m = _VERSION_RE.match(s.strip())
        if not m:
            raise ValueError(
                f"版本号格式错误: {s!r}（期望 x.y.z，例如 0.4.0）"
            )
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def bump(self, level: str) -> "Version":
        if level == "major":
            return Version(self.major + 1, 0, 0)
        if level == "minor":
            return Version(self.major, self.minor + 1, 0)
        if level == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise ValueError(f"未知递增级别: {level}")


# ---------------------------------------------------------------------------
# 读取 / 写入
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        return
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# 各文件的正则
# ---------------------------------------------------------------------------

# pyproject.toml 里项目自己的 version（避免误伤 [build-system] 里的 setuptools 版本）
# 只匹配顶层 [project] 段的 version 行
_PYPROJECT_VERSION_RE = re.compile(
    r'^(version\s*=\s*)"[^"]*"',
    re.MULTILINE,
)

# __init__.py 里的 __version__
_INIT_VERSION_RE = re.compile(
    r'^(__version__\s*=\s*)"[^"]*"',
    re.MULTILINE,
)

# README 徽章
_README_BADGE_RE = re.compile(
    r"version-(\d+\.\d+\.\d+)-blue\.svg"
)


# ---------------------------------------------------------------------------
# 更新逻辑
# ---------------------------------------------------------------------------

def _current_version_from_pyproject() -> Optional[Version]:
    if not PYPROJECT.exists():
        return None
    content = _read(PYPROJECT)
    # 找到 [project] 段之后第一个 version = "x.y.z"
    in_project = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project:
            m = re.match(r'^version\s*=\s*"([^"]+)"', stripped)
            if m:
                try:
                    return Version.parse(m.group(1))
                except ValueError:
                    return None
    return None


def _update_pyproject(new: Version, dry_run: bool) -> Tuple[bool, str]:
    if not PYPROJECT.exists():
        return False, f"[跳过] {PYPROJECT} 不存在"

    content = _read(PYPROJECT)

    # 精确替换 [project] 段里的 version 行
    lines = content.splitlines(keepends=True)
    in_project = False
    changed = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project:
            m = re.match(r'^(version\s*=\s*)"([^"]*)"(.*)$', line.rstrip("\n"))
            if m:
                new_line = f'{m.group(1)}"{new}"{m.group(3)}'
                # 保留原始换行符
                if line.endswith("\r\n"):
                    new_line += "\r\n"
                elif line.endswith("\n"):
                    new_line += "\n"
                lines[i] = new_line
                changed = True
                break

    if not changed:
        return False, f"[失败] {PYPROJECT} 中未找到 [project] 段的 version"

    _write(PYPROJECT, "".join(lines), dry_run)
    return True, f"[更新] {PYPROJECT.relative_to(REPO_ROOT)} -> {new}"


def _update_init_py(new: Version, dry_run: bool) -> Tuple[bool, str]:
    if not INIT_PY.exists():
        return False, f"[跳过] {INIT_PY} 不存在"

    content = _read(INIT_PY)
    new_content, n = _INIT_VERSION_RE.subn(
        lambda m: f'{m.group(1)}"{new}"', content, count=1
    )
    if n == 0:
        return False, f"[失败] {INIT_PY} 中未找到 __version__"

    _write(INIT_PY, new_content, dry_run)
    return True, f"[更新] {INIT_PY.relative_to(REPO_ROOT)} -> {new}"


def _update_readme(new: Version, dry_run: bool) -> Tuple[bool, str]:
    if not README.exists():
        return False, f"[跳过] {README} 不存在"

    content = _read(README)
    if not _README_BADGE_RE.search(content):
        return False, f"[跳过] {README} 中未找到版本徽章"

    new_content = _README_BADGE_RE.sub(
        f"version-{new}-blue.svg", content, count=1
    )
    _write(README, new_content, dry_run)
    return True, f"[更新] {README.relative_to(REPO_ROOT)} 徽章 -> {new}"


# ---------------------------------------------------------------------------
# git tag
# ---------------------------------------------------------------------------

def _git_tag(version: Version, dry_run: bool) -> Tuple[bool, str]:
    tag = f"v{version}"

    # 检查是否在 git 仓库
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False, "[跳过] 当前目录不是 git 仓库"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "[跳过] 未找到 git 命令"

    # 检查 tag 是否已存在
    r = subprocess.run(
        ["git", "tag", "--list", tag],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.stdout.strip():
        return False, f"[跳过] tag {tag} 已存在"

    if dry_run:
        return True, f"[预览] 将创建 tag: {tag}"

    r = subprocess.run(
        ["git", "tag", tag],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode != 0:
        return False, f"[失败] git tag 错误: {r.stderr.strip()}"

    return True, (
        f"[更新] 已创建 tag: {tag}\n"
        f"       推送命令: git push origin {tag}"
    )


# ---------------------------------------------------------------------------
# CHANGELOG 提示
# ---------------------------------------------------------------------------

def _changelog_hint(new: Version) -> str:
    if not CHANGELOG.exists():
        return ""
    return (
        f"\n提示：别忘了更新 {CHANGELOG.relative_to(REPO_ROOT)}。\n"
        f"建议在文件顶部（在第一个 ## [..] 之前）插入一段：\n"
        f"\n"
        f"    ## [{new}] - {_today()}\n"
        f"\n"
        f"    ### Added\n"
        f"    - （新功能）\n"
        f"\n"
        f"    ### Fixed\n"
        f"    - （修复内容）\n"
    )


def _today() -> str:
    from datetime import date

    return date.today().isoformat()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="快速修改项目版本号（pyproject.toml / __init__.py / README 徽章）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python scripts/bump_version.py 0.4.0\n"
            "  python scripts/bump_version.py --bump patch\n"
            "  python scripts/bump_version.py --bump minor --tag\n"
            "  python scripts/bump_version.py 0.4.0 --dry-run\n"
        ),
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="目标版本号，例如 0.4.0",
    )
    parser.add_argument(
        "--bump",
        choices=["major", "minor", "patch"],
        help="在当前版本基础上递增",
    )
    parser.add_argument(
        "--tag",
        action="store_true",
        help="写入成功后自动创建 git tag（vX.Y.Z）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示会改成什么，不实际写入",
    )

    args = parser.parse_args(argv)

    # 参数互斥检查
    if not args.version and not args.bump:
        parser.error("必须指定版本号（位置参数）或 --bump {major,minor,patch}")
    if args.version and args.bump:
        parser.error("不能同时指定版本号和 --bump")

    # 计算新版本
    if args.version:
        try:
            new_version = Version.parse(args.version)
        except ValueError as e:
            print(f"[错误] {e}", file=sys.stderr)
            return 1
    else:
        current = _current_version_from_pyproject()
        if current is None:
            print(
                "[错误] 无法从 pyproject.toml 读取当前版本，无法使用 --bump",
                file=sys.stderr,
            )
            return 1
        new_version = current.bump(args.bump)

    # 显示摘要
    current = _current_version_from_pyproject()
    print(f"仓库: {REPO_ROOT}")
    if current:
        print(f"当前版本: {current}")
    print(f"目标版本: {new_version}")
    if args.dry_run:
        print("模式: --dry-run（不会写入任何文件）")
    print()

    # 执行更新
    results = [
        _update_pyproject(new_version, args.dry_run),
        _update_init_py(new_version, args.dry_run),
        _update_readme(new_version, args.dry_run),
    ]

    failed = False
    for ok, msg in results:
        print(msg)
        if not ok and msg.startswith("[失败]"):
            failed = True

    if failed:
        print("\n[中止] 有文件更新失败，未执行后续步骤。", file=sys.stderr)
        return 1

    # git tag
    if args.tag:
        print()
        ok, msg = _git_tag(new_version, args.dry_run)
        print(msg)
        if not ok and msg.startswith("[失败]"):
            return 1

    # CHANGELOG 提示
    hint = _changelog_hint(new_version)
    if hint:
        print(hint)

    # 下一步提示
    if not args.dry_run:
        print("\n下一步：")
        print(f"  git add -A")
        print(f"  git commit -m \"chore: release v{new_version}\"")
        print(f"  git push")
        if args.tag:
            print(f"  git push origin v{new_version}   # 触发 GitHub Actions Release")

    return 0


if __name__ == "__main__":
    sys.exit(main())