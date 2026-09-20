from __future__ import annotations

import sys


def _run() -> int:
    from mc_mod_translator.gui.main import main

    return main()


if __name__ == "__main__":
    sys.exit(_run())