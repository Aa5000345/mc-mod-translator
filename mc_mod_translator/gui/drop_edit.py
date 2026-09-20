from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit


class DropLineEdit(QLineEdit):
    """支持把文件/文件夹拖进来的 QLineEdit。

    - 接受 ``text/uri-list``（资源管理器拖拽的标准 MIME）
    - 默认只取第一个条目
    - 如果设置了 ``want_dir_only``，非目录会被忽略
    """

    pathDropped = Signal(str)

    def __init__(self, parent=None, want_dir_only: bool = True):
        super().__init__(parent)
        self.want_dir_only = want_dir_only
        self.setAcceptDrops(True)
        self.setPlaceholderText("也可以把文件夹拖到这里")

    # ---- Qt 事件 ----
    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        urls = event.mimeData().urls()
        if not urls:
            super().dropEvent(event)
            return
        target = urls[0].toLocalFile()
        if not target:
            return
        p = Path(target)
        if self.want_dir_only and not p.is_dir():
            return
        self.setText(str(p))
        self.pathDropped.emit(str(p))
        event.acceptProposedAction()