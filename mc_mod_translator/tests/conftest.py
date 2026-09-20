from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest


# 让 tests 目录能直接 import mc_mod_translator.*
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_jar(tmp_path: Path):
    """返回一个工厂函数：根据提供的语言文件内容生成 jar。"""

    def _make(
        name: str,
        files: dict,  # {zip内路径: 文本}
        sub_jar: bool = False,
        sub_name: str = "META-INF/jarjar/nested.jar",
    ) -> Path:
        jar_path = tmp_path / name
        if sub_jar:
            # 先构造内层 jar
            inner = tmp_path / "_inner.jar"
            with zipfile.ZipFile(inner, "w") as zf:
                for k, v in files.items():
                    zf.writestr(k, v)
            with zipfile.ZipFile(jar_path, "w") as zf:
                zf.write(inner, sub_name)
        else:
            with zipfile.ZipFile(jar_path, "w") as zf:
                for k, v in files.items():
                    zf.writestr(k, v)
        return jar_path

    return _make


@pytest.fixture
def make_json_lang():
    def _make(data: dict) -> str:
        return json.dumps(data, ensure_ascii=False)

    return _make


@pytest.fixture
def make_lang_lang():
    def _make(data: dict) -> str:
        return "\n".join(f"{k}={v}" for k, v in data.items()) + "\n"

    return _make