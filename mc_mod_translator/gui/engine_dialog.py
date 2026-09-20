from __future__ import annotations

import asyncio
from typing import Dict, List

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..engines.registry import (
    DEFAULT_ENGINE_CONFIGS,
    ENGINE_NAMES,
    ENGINE_REQUIRED_FIELDS,
    create_engine,
    missing_required_fields,
)


# 真正的秘密字段。region 不是秘密。
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
    "email": "邮箱（可选，提升 MyMemory 额度）",
}

ENGINE_HINTS = {
    "auto_free": (
        "推荐给普通玩家。自动尝试免费的翻译服务，无需注册、无需配置。\n"
        "冷门模组、小整合包直接可用；大型整合包建议改用 DeepSeek 等付费引擎。"
    ),
    "mymemory": (
        "免费，无需 API Key。匿名每日约 10000 字符。\n"
        "可在下方填邮箱，额度提升到每日约 50000 字符（不会被公开）。"
    ),
    "baidu": "百度翻译需要到 https://fanyi-api.baidu.com/ 申请 App ID 和 App Key。",
    "deepl": "DeepL API Key 从 https://www.deepl.com/pro-api 获取。",
    "microsoft": "Azure Translator 需要 Key 和 Region（例如 eastasia / global）。",
    "openai": "OpenAI API Key 从 https://platform.openai.com/ 获取。",
    "deepseek": "DeepSeek API Key 从 https://platform.deepseek.com/ 获取（推荐，便宜好用）。",
    "claude": "Anthropic API Key 从 https://console.anthropic.com/ 获取。",
    "gemini": "Google AI Studio API Key 从 https://aistudio.google.com/ 获取。",
    "google": "Google 翻译免费接口，无需 Key。中国大陆需要配置代理或镜像。",
    "ollama": "本地模型。需要先安装 https://ollama.ai/ 并下载模型。",
    "nllb": "本地 NLLB 模型。首次使用会下载约 2~3 GB 模型文件。",
    "libretranslate": "需要本地或自建的 LibreTranslate 服务地址。",
}


def _collect_field_keys(name: str, cfg: Dict, defaults: Dict) -> List[str]:
    """决定某个引擎在对话框中应显示哪些字段。

    顺序：
      1. ``DEFAULT_ENGINE_CONFIGS`` 里的字段
      2. ``ENGINE_REQUIRED_FIELDS`` 里标记为必填的字段
      3. 用户配置里已有的字段

    如果该引擎是已知的但不需要任何字段，返回空列表（不显示任何输入框）。
    """
    keys: List[str] = []

    def _add(k: str) -> None:
        if k and k not in keys:
            keys.append(k)

    for k in (defaults or {}).keys():
        _add(k)
    for k in ENGINE_REQUIRED_FIELDS.get(name, []):
        _add(k)
    for k in (cfg or {}).keys():
        _add(k)

    # 只有完全未知的引擎才 fallback
    known = name in ENGINE_REQUIRED_FIELDS or name in DEFAULT_ENGINE_CONFIGS
    if not keys and not known:
        keys = ["api_key"]
    return keys


class EngineConfigDialog(QDialog):
    def __init__(self, engines: Dict[str, Dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("翻译引擎配置")
        self.resize(660, 560)
        self.engines: Dict[str, Dict] = {
            k: dict(v) for k, v in (engines or {}).items()
        }
        self.current_name: str = ""
        self.fields: Dict[str, QWidget] = {}

        self.engine_combo = QComboBox()
        self.engine_combo.addItems(ENGINE_NAMES)
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)

        self.form = QFormLayout()

        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #555;")

        self.empty_label = QLabel("此引擎无需任何配置，直接点“保存”即可。")
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("color: #888; font-style: italic;")

        layout = QVBoxLayout(self)
        layout.addWidget(self.engine_combo)
        layout.addWidget(self.hint_label)
        layout.addLayout(self.form)
        layout.addWidget(self.empty_label)

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

    # ---------- 切换 / 保存 ----------
    def _on_engine_changed(self, name: str) -> None:
        if self.current_name:
            self._save_current_to_memory()
        self._load_engine(name)

    def _save_current_to_memory(self) -> None:
        """把当前表单内容合并回 ``self.engines[current_name]``。

        用 merge 而非整体替换，避免丢失表单未显示但配置里已有的字段。
        """
        if not self.current_name:
            return
        existing = dict(self.engines.get(self.current_name, {}) or {})
        for key, widget in self.fields.items():
            if isinstance(widget, QPlainTextEdit):
                existing[key] = widget.toPlainText().strip()
            elif isinstance(widget, QLineEdit):
                existing[key] = widget.text().strip()
            else:
                existing[key] = ""
        self.engines[self.current_name] = existing

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
        defaults = DEFAULT_ENGINE_CONFIGS.get(name, {}) or {}
        keys = _collect_field_keys(name, cfg, defaults)

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

        hint = ENGINE_HINTS.get(name, "")
        self.hint_label.setText(hint)
        self.hint_label.setVisible(bool(hint))

        # 无字段时显示说明
        self.empty_label.setVisible(len(self.fields) == 0)

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
        cfg = self.engines.get(name, {}) or {}

        # 前置校验：如果必填项没填，直接告诉用户，不去打网络请求
        missing = missing_required_fields(name, cfg)
        if missing:
            QMessageBox.warning(
                self,
                "配置不完整",
                f"引擎 “{name}” 缺少以下必填项：\n\n"
                + "\n".join(f"  • {FIELD_LABELS.get(m, m)} ({m})" for m in missing),
            )
            return

        eng = create_engine(name, cfg)

        async def _run():
            try:
                text = await eng.translate("hello", "en", "zh")
                return True, text
            except Exception as e:  # noqa: BLE001
                return False, f"{type(e).__name__}: {e}"
            finally:
                await eng.aclose()

        ok, info = asyncio.run(_run())
        if ok:
            QMessageBox.information(self, "测试连接", f"成功。示例返回：{info!r}")
        else:
            QMessageBox.warning(self, "测试连接失败", str(info))