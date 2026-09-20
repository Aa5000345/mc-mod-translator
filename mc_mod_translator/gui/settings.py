from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


# 复用 config.CONFIG_DIR 的定位逻辑，避免循环导入
_SETTINGS_DIR = Path.home() / ".mc_mod_translator"
_SETTINGS_PATH = _SETTINGS_DIR / "gui_state.json"


@dataclass
class GuiState:
    """GUI 状态（不影响翻译行为，仅用于恢复界面）。

    与 Config 的区别：
      - Config 决定“做什么”（目标语言、输出模式、引擎等）
      - GuiState 决定“上次看到什么”（窗口大小、路径输入框、滚动位置）
    """

    pack_root: str = ""
    mods_dir: str = ""
    output_dir: str = ""
    window_width: int = 1180
    window_height: int = 820
    window_x: Optional[int] = None
    window_y: Optional[int] = None
    splitter_sizes: list = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _path() -> Path:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    return _SETTINGS_PATH


def load_gui_state() -> GuiState:
    p = _path()
    if not p.exists():
        return GuiState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return GuiState()
    if not isinstance(data, dict):
        return GuiState()
    allowed = set(GuiState.__dataclass_fields__.keys())
    kwargs = {k: v for k, v in data.items() if k in allowed}
    try:
        state = GuiState(**kwargs)
    except Exception:
        return GuiState()
    return state


def save_gui_state(state: GuiState) -> None:
    p = _path()
    try:
        p.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # 状态保存失败不致命
        pass


def default_output_for(pack_root: str, current: str = "") -> str:
    """给整合包根目录推荐一个输出目录：

    - 已有 current 且非默认空值时不覆盖
    - 有 pack_root 时优先 ``<pack_root>/resourcepacks``
    - 否则退回 ``<pack_root>/output``
    """
    if current:
        return current
    if not pack_root:
        return "./output"
    p = Path(pack_root)
    rp = p / "resourcepacks"
    if rp.is_dir():
        return str(rp)
    return str(p / "output")