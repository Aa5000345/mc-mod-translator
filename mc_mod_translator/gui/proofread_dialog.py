from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..placeholder import protect
from ..translator import TranslatedEntry


PAGE_SIZE_CHOICES = [100, 200, 500, 1000]
DEFAULT_PAGE_SIZE = 200
DEFAULT_DRAFT_PATH = Path.home() / ".mc_mod_translator" / "proofread_draft.json"


@dataclass
class _Row:
    mod_id: str
    key: str
    source: str
    machine: str
    proof: str = ""
    modified: bool = False


def _extract_placeholders(text: str) -> List[str]:
    """提取占位符（与 placeholder.protect 的规则一致）。"""
    _, ph = protect(text)
    return ph


def _placeholder_diff(src_phs: List[str], out_phs: List[str]) -> Tuple[List[str], List[str]]:
    """返回 (缺失, 多余)。"""
    src_c = Counter(src_phs)
    out_c = Counter(out_phs)
    missing_c = src_c - out_c
    extra_c = out_c - src_c
    missing: List[str] = []
    for ph, n in missing_c.items():
        missing.extend([ph] * n)
    extra: List[str] = []
    for ph, n in extra_c.items():
        extra.extend([ph] * n)
    return missing, extra


class ProofreadDialog(QDialog):
    def __init__(
        self,
        entries: List[TranslatedEntry],
        parent=None,
        draft_path: Optional[Path] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("人工校对")
        self.resize(1200, 740)

        self.entries = entries
        self.draft_path = Path(draft_path) if draft_path else DEFAULT_DRAFT_PATH

        self.all_rows: List[_Row] = []
        self.filtered_idx: List[int] = []
        self.page: int = 0
        self.page_size: int = DEFAULT_PAGE_SIZE
        self._loading: bool = False

        self._build_rows()
        self._build_ui()
        self._load_draft()
        self._apply_filters()

        # 30 秒自动保存草稿
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(30_000)
        self._autosave_timer.timeout.connect(self._save_draft)
        self._autosave_timer.start()

    # ------------------------------------------------------------------
    # 构建数据
    # ------------------------------------------------------------------
    def _build_rows(self) -> None:
        for te in self.entries:
            for key, src in te.entry.source.items():
                mt = te.merged.get(key, "")
                self.all_rows.append(
                    _Row(
                        mod_id=te.entry.mod_id,
                        key=key,
                        source=src,
                        machine=mt,
                    )
                )

    # ------------------------------------------------------------------
    # 构建 UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ---- 工具栏 ----
        bar = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索 Mod / Key / 原文 / 机翻 / 译文")
        self.search_edit.textChanged.connect(self._on_search_changed)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._apply_filters)

        self.filter_missing_cb = QCheckBox("只看缺失翻译")
        self.filter_modified_cb = QCheckBox("只看已修改")
        self.filter_empty_mt_cb = QCheckBox("只看机翻为空")
        for cb in (
            self.filter_missing_cb,
            self.filter_modified_cb,
            self.filter_empty_mt_cb,
        ):
            cb.stateChanged.connect(self._on_filter_changed)

        self.mod_combo = QComboBox()
        self.mod_combo.addItem("全部 mod", "")
        seen = []
        for r in self.all_rows:
            if r.mod_id not in seen:
                seen.append(r.mod_id)
        for m in sorted(seen):
            self.mod_combo.addItem(m, m)
        self.mod_combo.currentIndexChanged.connect(self._on_filter_changed)

        bar.addWidget(QLabel("搜索"))
        bar.addWidget(self.search_edit, 2)
        bar.addWidget(QLabel("Mod"))
        bar.addWidget(self.mod_combo, 1)
        bar.addWidget(self.filter_missing_cb)
        bar.addWidget(self.filter_modified_cb)
        bar.addWidget(self.filter_empty_mt_cb)
        layout.addLayout(bar)

        # ---- 表格 ----
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Mod", "Key", "原文", "机翻", "校对后（可编辑）"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        # ---- 分页栏 ----
        page_bar = QHBoxLayout()
        self.btn_prev = QPushButton("上一页")
        self.btn_next = QPushButton("下一页")
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_next.clicked.connect(self._go_next)
        self.page_label = QLabel("第 1 / 1 页")
        self.page_size_spin = QSpinBox()
        self.page_size_spin.setRange(50, 5000)
        self.page_size_spin.setSingleStep(50)
        self.page_size_spin.setValue(self.page_size)
        self.page_size_spin.valueChanged.connect(self._on_page_size_changed)
        self.count_label = QLabel("共 0 条")

        page_bar.addWidget(self.btn_prev)
        page_bar.addWidget(self.btn_next)
        page_bar.addWidget(self.page_label)
        page_bar.addStretch(1)
        page_bar.addWidget(self.count_label)
        page_bar.addWidget(QLabel("每页"))
        page_bar.addWidget(self.page_size_spin)
        layout.addLayout(page_bar)

        # ---- 底部按钮 ----
        bottom = QHBoxLayout()
        self.btn_batch = QPushButton("批量替换...")
        self.btn_batch.clicked.connect(self._batch_replace)
        self.btn_clear = QPushButton("清空本页校对")
        self.btn_clear.clicked.connect(self._clear_page)
        bottom.addWidget(self.btn_batch)
        bottom.addWidget(self.btn_clear)
        bottom.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self._on_cancel)
        bottom.addWidget(buttons)
        layout.addLayout(bottom)

    # ------------------------------------------------------------------
    # 过滤 + 分页
    # ------------------------------------------------------------------
    def _on_search_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _on_filter_changed(self, *_args) -> None:
        self._apply_filters()

    def _apply_filters(self) -> None:
        q = self.search_edit.text().strip().lower()
        mod_filter = self.mod_combo.currentData() or ""
        only_missing = self.filter_missing_cb.isChecked()
        only_modified = self.filter_modified_cb.isChecked()
        only_empty_mt = self.filter_empty_mt_cb.isChecked()

        self.filtered_idx = []
        for i, r in enumerate(self.all_rows):
            if mod_filter and r.mod_id != mod_filter:
                continue
            if only_missing and (r.proof or r.machine):
                continue
            if only_modified and not r.modified:
                continue
            if only_empty_mt and r.machine:
                continue
            if q:
                hay = (
                    f"{r.mod_id}\t{r.key}\t{r.source}\t{r.machine}\t{r.proof}"
                ).lower()
                if q not in hay:
                    continue
            self.filtered_idx.append(i)

        self.page = 0
        self._refresh_table()

    def _refresh_table(self) -> None:
        self._loading = True
        try:
            total = len(self.filtered_idx)
            max_page = max(0, (total - 1) // self.page_size) if total else 0
            if self.page > max_page:
                self.page = max_page
            start = self.page * self.page_size
            end = min(start + self.page_size, total)
            page_rows = self.filtered_idx[start:end]

            self.table.setRowCount(len(page_rows))
            for r, idx in enumerate(page_rows):
                row = self.all_rows[idx]
                self._set_cell(r, 0, row.mod_id, editable=False)
                self._set_cell(r, 1, row.key, editable=False)
                self._set_cell(r, 2, row.source, editable=False)
                self._set_cell(r, 3, row.machine, editable=False)
                self._set_cell(r, 4, row.proof, editable=True)

            self.page_label.setText(f"第 {self.page + 1} / {max_page + 1} 页")
            self.count_label.setText(f"共 {total} 条（总 {len(self.all_rows)}）")
            self.btn_prev.setEnabled(self.page > 0)
            self.btn_next.setEnabled(self.page < max_page)
        finally:
            self._loading = False

    def _set_cell(self, r: int, c: int, text: str, editable: bool) -> None:
        item = QTableWidgetItem(text)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, c, item)

    def _go_prev(self) -> None:
        if self.page > 0:
            self.page -= 1
            self._refresh_table()

    def _go_next(self) -> None:
        total = len(self.filtered_idx)
        max_page = max(0, (total - 1) // self.page_size) if total else 0
        if self.page < max_page:
            self.page += 1
            self._refresh_table()

    def _on_page_size_changed(self, value: int) -> None:
        self.page_size = max(1, value)
        self.page = 0
        self._refresh_table()

    # ------------------------------------------------------------------
    # 编辑
    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        if item.column() != 4:
            return
        r = item.row()
        pos = self.page * self.page_size + r
        if pos >= len(self.filtered_idx):
            return
        idx = self.filtered_idx[pos]
        row = self.all_rows[idx]
        new_val = item.text()
        if new_val != row.proof:
            row.proof = new_val
            row.modified = True

    def _clear_page(self) -> None:
        start = self.page * self.page_size
        end = min(start + self.page_size, len(self.filtered_idx))
        cleared = 0
        for pos in range(start, end):
            idx = self.filtered_idx[pos]
            row = self.all_rows[idx]
            if row.proof:
                row.proof = ""
                row.modified = True
                cleared += 1
        if cleared:
            self._refresh_table()

    # ------------------------------------------------------------------
    # 批量替换
    # ------------------------------------------------------------------
    def _batch_replace(self) -> None:
        find, ok = QInputDialog.getText(self, "批量替换", "查找：")
        if not ok or not find:
            return
        repl, ok = QInputDialog.getText(self, "批量替换", "替换为：")
        if not ok:
            return

        scope, ok = QInputDialog.getItem(
            self,
            "批量替换",
            "作用范围：",
            ["当前筛选结果", "所有行"],
            editable=False,
        )
        if not ok:
            return

        if scope == "当前筛选结果":
            target_indices = list(self.filtered_idx)
        else:
            target_indices = list(range(len(self.all_rows)))

        replaced = 0
        for idx in target_indices:
            row = self.all_rows[idx]
            # 有校对文本就替换校对文本，否则替换机翻
            base = row.proof if row.proof else row.machine
            if find in base:
                row.proof = base.replace(find, repl)
                row.modified = True
                replaced += 1

        self._refresh_table()
        QMessageBox.information(self, "批量替换", f"已替换 {replaced} 条")

    # ------------------------------------------------------------------
    # 占位符校验
    # ------------------------------------------------------------------
    def _validate_placeholders(self) -> List[str]:
        problems: List[str] = []
        for r in self.all_rows:
            if not r.modified or not r.proof:
                continue
            src_phs = _extract_placeholders(r.source)
            out_phs = _extract_placeholders(r.proof)
            missing, extra = _placeholder_diff(src_phs, out_phs)
            if missing:
                problems.append(f"[{r.mod_id}] {r.key}: 缺少占位符 {missing}")
            if extra:
                problems.append(f"[{r.mod_id}] {r.key}: 出现多余占位符 {extra}")
        return problems

    # ------------------------------------------------------------------
    # 草稿
    # ------------------------------------------------------------------
    def _save_draft(self) -> None:
        try:
            edits = [
                {
                    "mod_id": r.mod_id,
                    "key": r.key,
                    "source": r.source,
                    "machine": r.machine,
                    "proof": r.proof,
                    "modified": r.modified,
                }
                for r in self.all_rows
                if r.modified or r.proof
            ]
            self.draft_path.parent.mkdir(parents=True, exist_ok=True)
            self.draft_path.write_text(
                json.dumps({"edits": edits}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            # 草稿失败不打断主流程
            pass

    def _load_draft(self) -> None:
        if not self.draft_path.exists():
            return
        try:
            data = json.loads(self.draft_path.read_text(encoding="utf-8"))
        except Exception:
            return
        items = data.get("edits") or []
        if not isinstance(items, list):
            return
        by_key = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            k = (item.get("mod_id"), item.get("key"))
            proof = item.get("proof") or ""
            if proof:
                by_key[k] = proof
        if not by_key:
            return
        for r in self.all_rows:
            v = by_key.get((r.mod_id, r.key))
            if v and v != r.proof:
                r.proof = v
                r.modified = True

    # ------------------------------------------------------------------
    # 保存 / 取消
    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        problems = self._validate_placeholders()
        if problems:
            preview = "\n".join(problems[:10])
            more = f"\n... 共 {len(problems)} 条" if len(problems) > 10 else ""
            ans = QMessageBox.warning(
                self,
                "占位符校验",
                f"检测到占位符问题：\n{preview}{more}\n\n仍要保存吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return
        self._save_draft()
        self.accept()

    def _on_cancel(self) -> None:
        self._save_draft()
        self.reject()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def collect_edits(self) -> List[tuple]:
        """返回 (mod_id, key, source, machine, proofread) 列表，仅含被修改的行。"""
        out: List[tuple] = []
        for r in self.all_rows:
            if r.modified:
                out.append((r.mod_id, r.key, r.source, r.machine, r.proof))
        return out