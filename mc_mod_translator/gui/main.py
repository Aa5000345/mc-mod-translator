from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication


# 兼容两种运行方式：
#   1) 作为包内模块被导入：``from mc_mod_translator.gui.main import main``
#      —— 此时 ``__package__`` 为 "mc_mod_translator.gui"，相对导入可用。
#   2) 直接执行脚本：``python mc_mod_translator/gui/main.py``
#      —— 此时 ``__package__`` 为空，相对导入失败，需要退回到绝对导入。
#
# PyInstaller 打包请使用仓库根的 ``launcher.py`` 作为入口，
# 而不是直接打包本文件。
try:
    from .main_window import MainWindow
except ImportError:  # pragma: no cover - 仅直接执行脚本时触发
    _repo_root = Path(__file__).resolve().parents[2]
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))
    from mc_mod_translator.gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MC Mod Translator")
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())