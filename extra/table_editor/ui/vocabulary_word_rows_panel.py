"""vocabulary_word_rows.xlsx editor: topic filter, id/topic search."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from extra.table_editor.config import (
    DEFAULT_VOCABULARY_WORD_ROWS_CSV,
    DEFAULT_VOCABULARY_WORD_ROWS_EXCEL,
    TOPIC_FILTER_ALL,
)
from extra.table_editor.data.fields import VOCABULARY_WORD_ROWS_FIELDNAMES
from extra.table_editor.data.workbook import ExcelWorkbookStore
from extra.table_editor.services.csv_export import export_vocabulary_word_rows_csv
from extra.table_editor.services.search import (
    allocate_next_row_id,
    filter_rows_by_topic,
    find_row_by_id,
    ids_equal,
    parse_search_query,
    unique_topic_values,
)
from extra.table_editor.services.word_lookup import (
    clear_words_index_cache,
    lookup_word_details,
)
from extra.table_editor.ui.row_editor_dialog import RowEditorDialog
from extra.table_editor.ui.table_panel import TablePanel

_VOCAB_ROWS_DISPLAY_COLUMNS = [
    "id",
    "topic",
    "word_id",
    "한자",
    "뜻",
    "시트",
    "품사",
    "desc",
]


def _word_display(row: dict[str, str], field: str) -> str:
    info = lookup_word_details(row.get("word_id", ""))
    value = (info.get(field) or "").strip()
    return value if value else "—"


class VocabularyWordRowsPanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_status: Callable[[str], None],
        on_dirty_change: Callable[[bool], None],
    ) -> None:
        super().__init__(master)
        self._on_status = on_status
        self._on_dirty_change = on_dirty_change
        self._store = ExcelWorkbookStore(VOCABULARY_WORD_ROWS_FIELDNAMES)
        self._all_rows: list[dict[str, str]] = []
        self._build_ui()

    def load_defaults(self) -> None:
        clear_words_index_cache()
        if DEFAULT_VOCABULARY_WORD_ROWS_EXCEL.exists():
            try:
                self.load_file(DEFAULT_VOCABULARY_WORD_ROWS_EXCEL)
            except (OSError, ValueError) as ex:
                self._on_status(f"기본 vocabulary_word_rows 로드 실패: {ex}")

    @property
    def is_dirty(self) -> bool:
        return self._store.dirty

    @property
    def file_path(self) -> Path | None:
        return self._store.path

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text="topic:").pack(side=tk.LEFT)
        self._topic_var = tk.StringVar(value=TOPIC_FILTER_ALL)
        self._topic_combo = ttk.Combobox(
            top, textvariable=self._topic_var, state="readonly", width=28
        )
        self._topic_combo.pack(side=tk.LEFT, padx=(4, 12))
        self._topic_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Button(top, text="삭제", command=self._delete_row).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="새로 만들기", command=self._new_row).pack(side=tk.RIGHT, padx=4)

        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(search_frame, text="검색 (id / topic / word_id):").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(search_frame, textvariable=self._search_var, width=40)
        self._search_entry.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        self._search_entry.bind("<Return>", lambda _e: self._run_search())

        self._table = TablePanel(
            self,
            VOCABULARY_WORD_ROWS_FIELDNAMES,
            display_columns=_VOCAB_ROWS_DISPLAY_COLUMNS,
            computed_columns={
                "한자": lambda row: _word_display(row, "word"),
                "뜻": lambda row: _word_display(row, "meaning"),
                "시트": lambda row: _word_display(row, "sheet"),
                "품사": lambda row: _word_display(row, "pos"),
            },
            on_double_click=self._edit_row,
        )
        self._table.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._table.bind_tree("<Delete>", self._delete_row)

    def load_file(self, path: Path) -> None:
        clear_words_index_cache()
        self._store.load(path)
        self._all_rows = self._store.get_rows()
        self._update_topic_combo()
        self._apply_filter()
        self._on_dirty_change(False)
        self._on_status(f"로드: {path}")

    def open_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="vocabulary_word_rows.xlsx 열기",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All", "*.*")],
            initialdir=str(DEFAULT_VOCABULARY_WORD_ROWS_EXCEL.parent),
        )
        if path:
            self.load_file(Path(path))

    def save(self) -> bool:
        if self._store.path is None:
            return self.save_as()
        self._flush_rows()
        try:
            self._store.save()
            self._on_dirty_change(False)
            self._on_status(f"저장: {self._store.path}")
            return True
        except OSError as ex:
            messagebox.showerror("저장 실패", str(ex), parent=self)
            return False

    def save_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            title="vocabulary_word_rows.xlsx 저장",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="vocabulary_word_rows.xlsx",
            initialdir=str(DEFAULT_VOCABULARY_WORD_ROWS_EXCEL.parent),
        )
        if not path:
            return False
        self._flush_rows()
        try:
            self._store.save(path)
            self._on_dirty_change(False)
            self._on_status(f"저장: {path}")
            return True
        except OSError as ex:
            messagebox.showerror("저장 실패", str(ex), parent=self)
            return False

    def export_csv(self) -> None:
        if self._store.path is None:
            messagebox.showinfo("CSV", "먼저 파일을 저장하세요.", parent=self)
            return
        if self.is_dirty:
            if not messagebox.askyesno(
                "CSV 보내기",
                "저장되지 않은 변경이 있습니다. 저장 후 CSV를 생성할까요?",
                parent=self,
            ):
                return
            if not self.save():
                return
        try:
            out = export_vocabulary_word_rows_csv(
                self._store.path, DEFAULT_VOCABULARY_WORD_ROWS_CSV
            )
            messagebox.showinfo("CSV 보내기", f"생성 완료:\n{out}", parent=self)
            self._on_status(f"CSV: {out}")
        except Exception as ex:
            messagebox.showerror("CSV 실패", str(ex), parent=self)

    def _flush_rows(self) -> None:
        self._store.set_rows(self._all_rows)

    def _update_topic_combo(self) -> None:
        values = [TOPIC_FILTER_ALL] + unique_topic_values(self._all_rows)
        self._topic_combo["values"] = values
        if self._topic_var.get() not in values:
            self._topic_var.set(TOPIC_FILTER_ALL)

    def _apply_filter(self) -> None:
        filtered = filter_rows_by_topic(self._all_rows, self._topic_var.get())
        self._table.set_rows(filtered)

    def _run_search(self) -> None:
        query = self._search_var.get()
        kind, value = parse_search_query(query)
        if not value:
            self._apply_filter()
            return
        if kind == "id":
            row = find_row_by_id(self._all_rows, value)
            if row is None:
                matches = [
                    r for r in self._all_rows if ids_equal(r.get("word_id", ""), value)
                ]
                if len(matches) == 1:
                    row = matches[0]
                elif len(matches) > 1:
                    self._topic_var.set(TOPIC_FILTER_ALL)
                    self._apply_filter()
                    self._table.select_row_by_id(matches[0].get("id", ""))
                    self._on_status(f"word_id {value} → id {matches[0].get('id', '')} (첫 일치)")
                    return
            if row is None:
                self._on_status(f"id/word_id {value} 없음")
                messagebox.showinfo(
                    "검색",
                    f"id 또는 word_id {value} 를 찾을 수 없습니다.",
                    parent=self,
                )
                return
            self._topic_var.set(TOPIC_FILTER_ALL)
            self._apply_filter()
            self._table.select_row_by_id(row.get("id", ""))
            self._on_status(f"id {row.get('id', '')} 선택")
            return
        topics = unique_topic_values(self._all_rows)
        if value not in topics:
            self._on_status(f"topic '{value}' 없음")
            messagebox.showinfo(
                "검색",
                f"topic '{value}' 와 일치하는 항목이 없습니다.",
                parent=self,
            )
            return
        self._topic_var.set(value)
        self._apply_filter()
        self._on_status(f"topic '{value}' 필터")

    def _existing_ids(self) -> set[str]:
        return {
            (r.get("id") or "").strip()
            for r in self._all_rows
            if (r.get("id") or "").strip()
        }

    def _new_row(self) -> None:
        new_id = allocate_next_row_id(self._all_rows)
        defaults: dict[str, str] = {c: "" for c in VOCABULARY_WORD_ROWS_FIELDNAMES}
        defaults["id"] = new_id
        topic = self._topic_var.get()
        if topic and topic != TOPIC_FILTER_ALL:
            defaults["topic"] = topic
        self._open_editor(defaults, is_new=True)
        self._on_status(f"새 행 (id={new_id})")

    def _delete_row(self) -> None:
        row = self._table.get_selected_row()
        if row is None:
            messagebox.showinfo("삭제", "삭제할 행을 그리드에서 선택하세요.", parent=self)
            return
        rid = (row.get("id") or "").strip()
        if not rid:
            messagebox.showinfo("삭제", "id가 없는 행은 삭제할 수 없습니다.", parent=self)
            return
        topic = (row.get("topic") or "").strip()
        word_id = (row.get("word_id") or "").strip()
        detail = f"id={rid}"
        if topic:
            detail += f"\ntopic: {topic}"
        if word_id:
            detail += f"\nword_id: {word_id}"
        if not messagebox.askyesno(
            "행 삭제",
            f"아래 항목을 삭제할까요?\n\n{detail}",
            parent=self,
        ):
            return
        before = len(self._all_rows)
        self._all_rows = [
            r for r in self._all_rows if (r.get("id") or "").strip() != rid
        ]
        if len(self._all_rows) == before:
            messagebox.showwarning("삭제", "데이터에서 해당 id를 찾지 못했습니다.", parent=self)
            return
        self._store.set_rows(self._all_rows)
        self._on_dirty_change(True)
        self._update_topic_combo()
        self._apply_filter()
        self._on_status(f"삭제: id={rid}")

    def _edit_row(self, row: dict[str, str]) -> None:
        self._open_editor(dict(row), is_new=False, original_id=row.get("id", ""))

    def _validate_row(self, values: dict[str, str]) -> bool:
        topic = (values.get("topic") or "").strip()
        if not topic:
            messagebox.showwarning("검증", "topic을 입력하세요.", parent=self)
            return False
        raw_wid = (values.get("word_id") or "").strip()
        if not raw_wid:
            messagebox.showwarning("검증", "word_id를 입력하세요.", parent=self)
            return False
        try:
            wid = int(float(raw_wid))
        except (ValueError, TypeError):
            messagebox.showwarning("검증", "word_id는 1 이상의 숫자여야 합니다.", parent=self)
            return False
        if wid < 1:
            messagebox.showwarning("검증", "word_id는 1 이상이어야 합니다.", parent=self)
            return False
        values["word_id"] = str(wid)
        return True

    def _open_editor(
        self,
        row: dict[str, str],
        *,
        is_new: bool,
        original_id: str | None = None,
    ) -> None:
        def on_save(values: dict[str, str], new: bool) -> bool | None:
            if not self._validate_row(values):
                return False
            if new:
                self._all_rows.append(values)
            else:
                oid = (original_id or "").strip()
                for i, r in enumerate(self._all_rows):
                    if (r.get("id") or "").strip() == oid:
                        self._all_rows[i] = values
                        break
            self._store.set_rows(self._all_rows)
            self._on_dirty_change(True)
            self._update_topic_combo()
            self._apply_filter()
            self._table.update_row(values, original_id=original_id)
            self._on_status(f"{'추가' if new else '수정'}: id {values.get('id', '')}")
            return None

        RowEditorDialog(
            self,
            VOCABULARY_WORD_ROWS_FIELDNAMES,
            row,
            title="새 단어장 행" if is_new else "단어장 행 편집",
            is_new=is_new,
            existing_ids=self._existing_ids(),
            original_id=original_id,
            on_save=on_save,
        )
