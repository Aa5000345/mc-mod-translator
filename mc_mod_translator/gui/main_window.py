from __future__ import annotations

import asyncio
import csv
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..cache import TranslationCache
from ..config import (
    CACHE_PATH,
    CONFIG_DIR,
    GLOSSARY_PATH,
    Config,
    load_config,
    save_config,
)
from ..engines.registry import ENGINE_NAMES, create_engine
from ..glossary import Glossary
from ..packager import build_merged_pack, build_per_mod_packs
from ..proofread import import_csv
from ..scanner import resolve_mods_dir, scan_mods_dir
from ..scanner_preview import preview as preview_scan
from ..translator import MANUAL_ENGINE, TranslatedEntry, Translator
from ..versions import detect_mc_version, pack_format_for
from .drop_edit import DropLineEdit
from .engine_dialog import EngineConfigDialog
from .proofread_dialog import ProofreadDialog
from .settings import (
    GuiState,
    default_output_for,
    load_gui_state,
    save_gui_state,
)


TARGET_LANGS = [
    ("zh_cn", "简体中文 (zh_cn)"),
    ("zh_tw", "繁體中文 (zh_tw)"),
]

PROOFREAD_DRAFT_PATH = CONFIG_DIR / "proofread_draft.json"


class TranslateWorker(QObject):
    log = Signal(str)
    text_progress = Signal(int, int)
    file_progress = Signal(int, int)
    finished = Signal(object, object)  # (results, packs)
    failed = Signal(str)

    def __init__(self, cfg: Config, pack_root: Path | None, mods_path: Path):
        super().__init__()
        self.cfg = cfg
        self.pack_root = pack_root
        self.mods_path = mods_path
        self._cancel_event = None

    def request_cancel(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        cache: TranslationCache | None = None
        eng = None
        try:
            entries = scan_mods_dir(self.mods_path, target_lang=self.cfg.target_language)
            if not entries:
                self.failed.emit("未找到可翻译的语言文件")
                return
            self.log.emit(f"扫描到 {len(entries)} 个语言文件")
            self.file_progress.emit(0, len(entries))

            detected_version = self.cfg.mc_version
            if detected_version is None and self.pack_root is not None:
                detected_version = detect_mc_version(self.pack_root)
            if detected_version is None:
                detected_version = "1.20.1"
                self.log.emit(f"未检测到版本，使用默认 {detected_version}")

            pf = (
                self.cfg.pack_format
                if self.cfg.pack_format is not None
                else pack_format_for(detected_version)
            )
            self.log.emit(f"目标版本 {detected_version} (pack_format={pf})")

            engine_cfg = self.cfg.engines.get(self.cfg.engine, {})
            eng = create_engine(self.cfg.engine, engine_cfg)
            self.log.emit(f"使用引擎 {self.cfg.engine}")

            cache = TranslationCache(CACHE_PATH) if self.cfg.cache_enabled else None
            glossary = Glossary()
            if self.cfg.glossary_enabled:
                glossary.load(GLOSSARY_PATH)

            import threading

            self._cancel_event = threading.Event()
            tr = Translator(
                engine=eng,
                cache=cache,
                glossary=glossary,
                concurrency=self.cfg.concurrency,
                merge_existing=self.cfg.merge_existing,
                log_cb=lambda m: self.log.emit(m),
                progress_cb=lambda d, t: self.text_progress.emit(d, t),
                cancel_event=self._cancel_event,
            )

            async def _run_translation():
                try:
                    return await tr.translate_entries(
                        entries, target_lang=self.cfg.target_language
                    )
                finally:
                    await eng.aclose()

            results: list[TranslatedEntry] = asyncio.run(_run_translation())

            # 文件进度收尾：所有条目均已合并完成
            self.file_progress.emit(len(entries), len(entries))

            out_dir = Path(self.cfg.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            packs: list[Path] = []
            if self.cfg.output_mode == "merged":
                out = out_dir / f"{self.cfg.resourcepack_name}.zip"
                build_merged_pack(
                    out,
                    results,
                    pf,
                    target_lang=self.cfg.target_language,
                )
                packs.append(out)
            else:
                packs = build_per_mod_packs(
                    out_dir,
                    results,
                    pf,
                    target_lang=self.cfg.target_language,
                )

            if self.cfg.auto_install and self.pack_root is not None:
                import shutil

                rp = self.pack_root / "resourcepacks"
                rp.mkdir(parents=True, exist_ok=True)
                for p in packs:
                    shutil.copy2(p, rp / Path(p).name)
                self.log.emit(f"已安装 {len(packs)} 个资源包到 {rp}")

            self.finished.emit(results, packs)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{e}\n{traceback.format_exc()}")
        finally:
            if cache is not None:
                try:
                    cache.close()
                except Exception:
                    pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MC Mod Translator")

        self.state: GuiState = load_gui_state()
        self.cfg: Config = load_config()

        # 恢复窗口几何
        self.resize(
            self.state.window_width or 1180,
            self.state.window_height or 820,
        )
        if self.state.window_x is not None and self.state.window_y is not None:
            self.move(self.state.window_x, self.state.window_y)

        self.current_results: list[TranslatedEntry] = []
        self.worker_thread: QThread | None = None
        self.worker: TranslateWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ---------- 输入 ----------
        path_box = QGroupBox("输入")
        path_layout = QFormLayout(path_box)

        self.pack_root_edit = DropLineEdit(want_dir_only=True)
        self.pack_root_edit.setText(self.state.pack_root or "")
        self.pack_root_edit.pathDropped.connect(self._on_pack_root_dropped)

        self.mods_dir_edit = DropLineEdit(want_dir_only=True)
        self.mods_dir_edit.setText(self.state.mods_dir or "")

        btn_root = QPushButton("选择整合包根目录")
        btn_mods = QPushButton("选择 mods 文件夹")
        btn_root.clicked.connect(self._pick_pack_root)
        btn_mods.clicked.connect(self._pick_mods_dir)

        row1 = QHBoxLayout()
        row1.addWidget(self.pack_root_edit)
        row1.addWidget(btn_root)
        row2 = QHBoxLayout()
        row2.addWidget(self.mods_dir_edit)
        row2.addWidget(btn_mods)
        path_layout.addRow("整合包根目录", row1)
        path_layout.addRow("mods 文件夹", row2)

        self.mc_version_edit = QLineEdit_safe(self.cfg.mc_version or "")
        self.mc_version_edit.setPlaceholderText("留空自动检测，例如 1.20.1")
        self.pack_format_edit = QLineEdit_safe(
            "" if self.cfg.pack_format is None else str(self.cfg.pack_format)
        )
        self.pack_format_edit.setPlaceholderText("留空自动计算")
        path_layout.addRow("MC 版本", self.mc_version_edit)
        path_layout.addRow("pack_format", self.pack_format_edit)

        # ---------- 输出 ----------
        out_box = QGroupBox("输出")
        out_layout = QFormLayout(out_box)

        # 若 cfg 或 state 都有值，优先 state
        output_text = self.state.output_dir or self.cfg.output_dir
        if self.state.pack_root and output_text in ("", "./output"):
            output_text = default_output_for(self.state.pack_root, "")

        self.output_dir_edit = DropLineEdit(want_dir_only=True)
        self.output_dir_edit.setText(output_text or "./output")

        btn_out = QPushButton("选择输出目录")
        btn_out.clicked.connect(self._pick_output_dir)
        row3 = QHBoxLayout()
        row3.addWidget(self.output_dir_edit)
        row3.addWidget(btn_out)
        out_layout.addRow("输出目录", row3)

        self.mode_merged = QRadioButton("合并为一个资源包")
        self.mode_per_mod = QRadioButton("每个 mod 单独资源包")
        if self.cfg.output_mode == "per_mod":
            self.mode_per_mod.setChecked(True)
        else:
            self.mode_merged.setChecked(True)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_merged)
        mode_row.addWidget(self.mode_per_mod)
        out_layout.addRow("输出模式", mode_row)

        self.target_lang_combo = QComboBox()
        for code, label in TARGET_LANGS:
            self.target_lang_combo.addItem(label, code)
        idx = self.target_lang_combo.findData(self.cfg.target_language)
        if idx >= 0:
            self.target_lang_combo.setCurrentIndex(idx)
        out_layout.addRow("目标语言", self.target_lang_combo)

        self.auto_install_cb = QCheckBox("翻译完成后自动安装到整合包 resourcepacks")
        self.auto_install_cb.setChecked(self.cfg.auto_install)
        out_layout.addRow("", self.auto_install_cb)

        self.merge_existing_cb = QCheckBox("保留已有 zh_cn 翻译，仅补全缺失 key")
        self.merge_existing_cb.setChecked(self.cfg.merge_existing)
        out_layout.addRow("", self.merge_existing_cb)

        # ---------- 引擎 ----------
        eng_box = QGroupBox("翻译引擎")
        eng_layout = QFormLayout(eng_box)
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(ENGINE_NAMES)
        if self.cfg.engine in ENGINE_NAMES:
            self.engine_combo.setCurrentText(self.cfg.engine)
        btn_eng_cfg = QPushButton("配置引擎...")
        btn_eng_cfg.clicked.connect(self._open_engine_dialog)
        eng_row = QHBoxLayout()
        eng_row.addWidget(self.engine_combo)
        eng_row.addWidget(btn_eng_cfg)
        eng_layout.addRow("引擎", eng_row)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 64)
        self.concurrency_spin.setValue(self.cfg.concurrency)
        eng_layout.addRow("并发数", self.concurrency_spin)

        # ---------- 操作按钮 ----------
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("开始翻译")
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QPushButton("取消翻译")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_proof = QPushButton("打开校对")
        self.btn_proof.clicked.connect(self._open_proofread)
        self.btn_import = QPushButton("导入校对文件")
        self.btn_import.clicked.connect(self._import_proofread)
        self.btn_save_cfg = QPushButton("保存配置")
        self.btn_save_cfg.clicked.connect(self._save_cfg)
        self.btn_export_log = QPushButton("导出日志")
        self.btn_export_log.clicked.connect(self._export_log)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_proof)
        btn_row.addWidget(self.btn_import)
        btn_row.addWidget(self.btn_save_cfg)
        btn_row.addWidget(self.btn_export_log)

        # ---------- 进度 ----------
        prog_box = QGroupBox("进度")
        prog_layout = QFormLayout(prog_box)
        self.file_progress = QProgressBar()
        self.file_progress.setFormat("文件 %v/%m")
        self.text_progress = QProgressBar()
        self.text_progress.setFormat("文本 %v/%m")
        prog_layout.addRow("文件进度", self.file_progress)
        prog_layout.addRow("文本进度", self.text_progress)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        # ---------- Mod 列表 ----------
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            [
                "Mod",
                "语言文件",
                "已有 key",
                "缺失 key",
                "新增翻译",
                "缓存命中",
                "失败",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        root.addWidget(path_box)
        root.addWidget(out_box)
        root.addWidget(eng_box)
        root.addLayout(btn_row)
        root.addWidget(prog_box)
        root.addWidget(QLabel("翻译结果（双击某行 Mod 可只对该 mod 校对）"))
        root.addWidget(self.table, 2)
        root.addWidget(QLabel("日志"))
        root.addWidget(self.log_view, 2)

    # ---------- 选择路径 ----------
    def _pick_pack_root(self):
        d = QFileDialog.getExistingDirectory(self, "选择整合包根目录")
        if d:
            self.pack_root_edit.setText(d)
            self._maybe_fill_output(d)

    def _pick_mods_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择 mods 文件夹")
        if d:
            self.mods_dir_edit.setText(d)

    def _pick_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.output_dir_edit.setText(d)

    def _on_pack_root_dropped(self, path: str) -> None:
        self._maybe_fill_output(path)

    def _maybe_fill_output(self, pack_root: str) -> None:
        """若输出目录还是默认值，按整合包目录推荐。"""
        cur = self.output_dir_edit.text().strip()
        if cur in ("", "./output"):
            self.output_dir_edit.setText(default_output_for(pack_root, ""))

    # ---------- 引擎配置 ----------
    def _open_engine_dialog(self):
        dlg = EngineConfigDialog(self.cfg.engines, self)
        if dlg.exec():
            self.cfg.engines = dlg.result_engines()
            QMessageBox.information(
                self,
                "提示",
                "引擎配置已更新到内存。还需要在主窗口点“保存配置”写入磁盘。",
            )

    # ---------- 保存配置 ----------
    def _sync_ui_to_cfg(self) -> None:
        self.cfg.engine = self.engine_combo.currentText()
        self.cfg.output_mode = "per_mod" if self.mode_per_mod.isChecked() else "merged"
        self.cfg.output_dir = self.output_dir_edit.text().strip() or "./output"
        self.cfg.auto_install = self.auto_install_cb.isChecked()
        self.cfg.merge_existing = self.merge_existing_cb.isChecked()
        self.cfg.concurrency = self.concurrency_spin.value()
        self.cfg.target_language = self.target_lang_combo.currentData() or "zh_cn"
        v = self.mc_version_edit.text().strip()
        self.cfg.mc_version = v or None
        pf = self.pack_format_edit.text().strip()
        self.cfg.pack_format = int(pf) if pf.isdigit() else None

    def _save_cfg(self):
        self._sync_ui_to_cfg()
        save_config(self.cfg)
        self._log("配置已保存")

    # ---------- 日志 ----------
    def _log(self, msg: str):
        from datetime import datetime

        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{ts}] {msg}")

    def _export_log(self):
        f, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "mcmt.log", "Log (*.log);;Text (*.txt)"
        )
        if not f:
            return
        try:
            Path(f).write_text(self.log_view.toPlainText(), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "导出失败", str(e))
            return
        self._log(f"日志已导出: {f}")

    # ---------- 预览 ----------
    def _preview_and_confirm(self, mods_path: Path) -> bool:
        self._log("扫描预览中...")
        stats = preview_scan(mods_path, target_lang=self.cfg.target_language)
        if stats.errors:
            for e in stats.errors:
                self._log(f"[扫描错误] {e}")
        self._log(f"预览: {stats.summary()}")

        if stats.unique_missing_texts == 0:
            QMessageBox.information(
                self,
                "无需翻译",
                f"共 {stats.total_keys} 个 key，全部已有翻译。\n"
                f"（如果想重新翻译已有内容，请取消勾选“保留已有 zh_cn 翻译”）",
            )
            return False

        msg = (
            f"jar 文件: {stats.total_jars}\n"
            f"语言文件: {stats.total_lang_entries}\n"
            f"key 总数: {stats.total_keys}\n"
            f"已有翻译: {stats.existing_keys}\n"
            f"缺失 key: {stats.missing_keys}\n"
            f"唯一待翻译文本: {stats.unique_missing_texts}\n\n"
            f"引擎: {self.engine_combo.currentText()}\n"
            f"目标语言: {self.target_lang_combo.currentData()}\n"
            f"输出模式: "
            f"{'每个 mod 单独' if self.mode_per_mod.isChecked() else '合并一个'}\n\n"
            f"是否开始翻译？"
        )
        ans = QMessageBox.question(
            self,
            "翻译预览",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return ans == QMessageBox.Yes

    # ---------- 开始 / 取消 ----------
    def _start(self):
        if self.worker_thread is not None:
            QMessageBox.warning(self, "提示", "翻译正在进行中")
            return

        pack_root_text = self.pack_root_edit.text().strip()
        mods_text = self.mods_dir_edit.text().strip()

        pack_root = Path(pack_root_text) if pack_root_text else None
        mods_path = None
        if mods_text:
            mods_path = resolve_mods_dir(Path(mods_text))
        elif pack_root:
            mods_path = resolve_mods_dir(pack_root)
        else:
            QMessageBox.warning(self, "提示", "请选择整合包根目录或 mods 文件夹")
            return

        if mods_path is None:
            QMessageBox.critical(self, "错误", "无法定位 mods 目录")
            return

        engine_cfg = self.cfg.engines.get(self.engine_combo.currentText(), {})
        api_key = engine_cfg.get("api_key", "")
        if self.engine_combo.currentText() in {
            "openai",
            "deepseek",
            "moonshot",
            "qwen",
            "openrouter",
            "claude",
            "gemini",
        } and not api_key:
            QMessageBox.warning(
                self,
                "提示",
                f"引擎 {self.engine_combo.currentText()} 未配置 api_key，"
                f"请先点击“配置引擎...”填写。",
            )
            return

        self._sync_ui_to_cfg()

        if not self._preview_and_confirm(mods_path):
            return

        save_config(self.cfg)

        self.log_view.clear()
        self.file_progress.setMaximum(1)
        self.file_progress.setValue(0)
        self.text_progress.setMaximum(1)
        self.text_progress.setValue(0)
        self.table.setRowCount(0)

        self.worker_thread = QThread()
        self.worker = TranslateWorker(self.cfg, pack_root, mods_path)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self._log)
        self.worker.text_progress.connect(self._on_text_progress)
        self.worker.file_progress.connect(self._on_file_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_thread)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.worker_thread.start()

    def _cancel(self):
        if self.worker is not None:
            self.worker.request_cancel()
            self._log("已请求取消，等待当前任务收尾...")

    def _cleanup_thread(self):
        self.worker_thread = None
        self.worker = None
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)

    def _on_text_progress(self, done: int, total: int):
        self.text_progress.setMaximum(max(total, 1))
        self.text_progress.setValue(done)

    def _on_file_progress(self, done: int, total: int):
        self.file_progress.setMaximum(max(total, 1))
        self.file_progress.setValue(done)

    def _on_finished(self, results: list, packs: list):
        self.current_results = results
        self._log(f"完成。生成 {len(packs)} 个资源包。")
        for p in packs:
            self._log(str(p))

        self.table.setRowCount(len(results))
        for r, te in enumerate(results):
            existing_cnt = len(te.entry.existing)
            missing_cnt = sum(
                1 for k in te.entry.source if k not in te.entry.existing
            )
            self.table.setItem(r, 0, QTableWidgetItem(te.entry.mod_id))
            self.table.setItem(r, 1, QTableWidgetItem(te.entry.lang_path))
            self.table.setItem(r, 2, QTableWidgetItem(str(existing_cnt)))
            self.table.setItem(r, 3, QTableWidgetItem(str(missing_cnt)))
            self.table.setItem(r, 4, QTableWidgetItem(str(te.new_keys)))
            self.table.setItem(r, 5, QTableWidgetItem(str(te.cached_keys)))
            self.table.setItem(r, 6, QTableWidgetItem(str(te.failed_keys)))

        failed_all = [
            (te.entry.mod_id, key, src)
            for te in results
            for key, src in te.failed_pairs
        ]
        if failed_all:
            self._log(f"共有 {len(failed_all)} 条翻译失败（示例前 10）：")
            for mod_id, key, src in failed_all[:10]:
                self._log(f"  - [{mod_id}] {key}: {src[:60]!r}")

    def _on_failed(self, msg: str):
        self._log("[失败] " + msg)
        QMessageBox.critical(self, "失败", msg)

    # ---------- 校对 ----------
    def _open_proofread(self):
        if not self.current_results:
            QMessageBox.information(self, "提示", "还没有可校对的结果")
            return
        self._open_proofread_for(self.current_results)

    def _on_cell_double_clicked(self, row: int, col: int):
        if not self.current_results:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        mod_id = item.text()
        filtered = [te for te in self.current_results if te.entry.mod_id == mod_id]
        if not filtered:
            return
        self._log(f"仅对 mod {mod_id} 打开校对（{len(filtered)} 个语言文件）")
        self._open_proofread_for(filtered)

    def _open_proofread_for(self, entries: list):
        dlg = ProofreadDialog(entries, self, draft_path=PROOFREAD_DRAFT_PATH)
        if dlg.exec():
            edits = dlg.collect_edits()
            if not edits:
                QMessageBox.information(self, "提示", "没有任何修改")
                return
            self._save_proofread_csv(edits)
            QMessageBox.information(
                self, "完成", f"已保存 {len(edits)} 条校对结果"
            )

    def _save_proofread_csv(self, rows):
        out = Path(self.cfg.output_dir) / "proofread.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "mod_id",
                    "key",
                    "source",
                    "machine_translation",
                    "proofread_translation",
                    "status",
                ]
            )
            for mod_id, key, src, mt, proof in rows:
                w.writerow([mod_id, key, src, mt, proof, "approved" if proof else ""])
        self._log(f"校对文件已保存: {out}")

        cache = TranslationCache(CACHE_PATH)
        glossary = Glossary()
        glossary.load(GLOSSARY_PATH)
        try:
            n = import_csv(
                out,
                cache,
                glossary,
                engine_name=MANUAL_ENGINE,
                tgt_lang=self.cfg.target_language,
            )
            glossary.save(GLOSSARY_PATH)
            self._log(f"缓存/术语表更新 {n} 条")
        finally:
            cache.close()

    def _import_proofread(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择校对文件", "", "CSV (*.csv)"
        )
        if not f:
            return
        cache = TranslationCache(CACHE_PATH)
        glossary = Glossary()
        glossary.load(GLOSSARY_PATH)
        try:
            n = import_csv(
                Path(f),
                cache,
                glossary,
                engine_name=MANUAL_ENGINE,
                tgt_lang=self.cfg.target_language,
            )
            glossary.save(GLOSSARY_PATH)
            QMessageBox.information(self, "完成", f"已导入 {n} 条")
        finally:
            cache.close()

    # ---------- 生命周期 ----------
    def closeEvent(self, event):  # noqa: N802
        try:
            self._sync_ui_to_cfg()
            state = GuiState(
                pack_root=self.pack_root_edit.text().strip(),
                mods_dir=self.mods_dir_edit.text().strip(),
                output_dir=self.output_dir_edit.text().strip(),
                window_width=self.width(),
                window_height=self.height(),
                window_x=self.x(),
                window_y=self.y(),
            )
            save_gui_state(state)
        except Exception:
            pass
        super().closeEvent(event)


# 延迟导入 QLineEdit，避免顶部 import 被 PySide6 名字占满导致可读性下降
from PySide6.QtWidgets import QLineEdit as QLineEdit_safe  # noqa: E402