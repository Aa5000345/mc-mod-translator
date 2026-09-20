from __future__ import annotations

import asyncio
from typing import Dict

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..engines.registry import DEFAULT_ENGINE_CONFIGS, ENGINE_NAMES, create_engine


# 真正的秘密字段。region 不是秘密，不再加密/掩码。
SECRET_FIELDS = {"api_key", "app_key", "app_id", "token"}

FIELD_LABELS = {
    "api_key": "API Key",
    "app_id": "App ID",
    "app_key": "App Key",
    "region": "Region",
    "base_url": "Base URL",
    "model": "Model",
    "model_path": "模型路径",
    "device": "设备 (cpu/cuda)",
    "system_prompt": "系统提示词",
    "max_tokens": "Max Tokens",
}


class EngineConfigDialog(QDialog):
    def __init__(self, engines: Dict[str, Dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("翻译引擎配置")
        self.resize(660, 540)
        self.engines: Dict[str, Dict] = {
            k: dict(v) for k, v in (engines or {}).items()
        }
        self.current_name: str = ""
        self.fields: Dict[str, QWidget] = {}

        self.engine_combo = QComboBox()
        self.engine_combo.addItems(ENGINE_NAMES)
        # 初始化时以当前引擎为主（避免触发 _on_engine_changed 再覆盖）
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)

        self.form = QFormLayout()

        layout = QVBoxLayout(self)
        layout.addWidget(self.engine_combo)
        layout.addLayout(self.form)

        btn_test = QPushButton("测试连接")
        btn_test.clicked.connect(self._test_connection)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(btn_test)
        bottom.addStretch(1)
        bottom.addWidget(buttons)
        layout.addLayout(bottom)

        self._load_engine(ENGINE_NAMES[0])

    # ---------- 切换/保存 ----------
    def _on_engine_changed(self, name: str) -> None:
        if self.current_name:
            self._save_current_to_memory()
        self._load_engine(name)

    def _save_current_to_memory(self) -> None:
        if not self.current_name:
            return
        cfg: Dict[str, str] = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QPlainTextEdit):
                cfg[key] = widget.toPlainText().strip()
            elif isinstance(widget, QLineEdit):
                cfg[key] = widget.text().strip()
            else:
                cfg[key] = ""
        self.engines[self.current_name] = cfg

    # ---------- 加载 ----------
    def _clear_form(self) -> None:
        while self.form.count():
            item = self.form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.fields.clear()

    def _load_engine(self, name: str) -> None:
        self._clear_form()
        self.current_name = name
        cfg = self.engines.get(name, {}) or {}
        defaults = DEFAULT_ENGINE_CONFIGS.get(name, {})
        keys = list(defaults.keys())
        for k in cfg.keys():
            if k not in keys:
                keys.append(k)
        if not keys:
            keys = ["api_key"]
        for key in keys:
            value = str(cfg.get(key, defaults.get(key, "")) or "")
            if key == "system_prompt":
                w: QWidget = QPlainTextEdit()
                assert isinstance(w, QPlainTextEdit)
                w.setPlainText(value)
                w.setMinimumHeight(96)
            else:
                le = QLineEdit()
                le.setText(value)
                if key in SECRET_FIELDS:
                    le.setEchoMode(QLineEdit.Password)
                w = le
            self.fields[key] = w
            self.form.addRow(FIELD_LABELS.get(key, key), w)

    # ---------- 保存 ----------
    def _save(self) -> None:
        self._save_current_to_memory()
        self.accept()

    def result_engines(self) -> Dict[str, Dict]:
        return self.engines

    # ---------- 测试连接 ----------
    def _test_connection(self) -> None:
        self._save_current_to_memory()
        name = self.current_name
        eng = create_engine(name, self.engines.get(name, {}))

        async def _run():
            try:
                r = await eng.translate("hello", "en", "zh")
                return True, r
            except Exception as e:  # noqa: BLE001
                return False, f"{type(e).__name__}: {e}"
            finally:
                await eng.aclose()

        ok, info = asyncio.run(_run())
        if ok:
            QMessageBox.information(
                self, "测试连接", f"成功。示例返回：{info!r}"
            )
        else:
            QMessageBox.warning(self, "测试连接失败", str(info))