from __future__ import annotations

import sys
from typing import Optional


class SimpleProgress:
    """单行刷新进度条。零依赖，不用 tqdm。

    用法::

        sp = SimpleProgress()
        sp.update(done, total)
        ...
        sp.finish()

    输出会被写到 ``file``（默认 stderr），这样不会污染 stdout 里的结构化结果。
    """

    def __init__(self, width: int = 40, prefix: str = "进度", file=None):
        self.width = max(10, width)
        self.prefix = prefix
        self.file = file if file is not None else sys.stderr
        self._last_len = 0
        self._last_done = -1

    def update(self, done: int, total: int) -> None:
        if total <= 0:
            return
        if done == self._last_done:
            return
        self._last_done = done

        frac = max(0.0, min(1.0, done / total))
        filled = int(self.width * frac)
        bar = "=" * filled + "-" * (self.width - filled)
        line = f"\r{self.prefix} [{bar}] {done}/{total} ({frac * 100:5.1f}%)"

        pad = max(0, self._last_len - len(line))
        self.file.write(line + " " * pad)
        self.file.flush()
        self._last_len = len(line)

    def finish(self, message: Optional[str] = None) -> None:
        if self._last_len:
            self.file.write("\n")
            self.file.flush()
            self._last_len = 0
        if message:
            self.file.write(message + "\n")
            self.file.flush()


class NullProgress:
    """在不需要进度输出时使用的空实现。"""

    def update(self, done: int, total: int) -> None:
        return

    def finish(self, message: Optional[str] = None) -> None:
        return