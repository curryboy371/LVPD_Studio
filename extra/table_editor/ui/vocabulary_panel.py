"""Words.xlsx editor: sheets, pos filter, id/hanzi search."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from extra.table_editor.config import (
    DEFAULT_WORDS_TABLE_CSV,
    DEFAULT_WORDS_TABLE_EXCEL,
    POS_FILTER_ALL,
)
from extra.table_editor.data.fields import WORDS_FIELDNAMES
from extra.table_editor.data.workbook import MultiSheetWorkbookStore
from extra.table_editor.services.csv_export import export_words_csv
from extra.table_editor.services.post_save_csv import export_csv_paths
from extra.table_editor.services.global_table_cache import invalidate_global_table_cache
from extra.table_editor.services.search import (
    allocate_next_word_id,
    filter_rows_by_pos,
    filter_rows_by_type,
    find_row_by_id,
    find_rows_by_type,
    find_rows_by_word,
    parse_search_query,
    unique_pos_values,
    unique_type_values,
)
from extra.table_editor.services.word_autofill import apply_new_word_defaults
from extra.table_editor.ui.id_picker_dialog import IdPickerDialog
from extra.table_editor.ui.row_editor_dialog import RowEditorDialog
from extra.table_editor.ui.table_panel import TablePanel

_WORDS_DISPLAY_COLUMNS = [
    "id",
    "word",
    "meaning",
    "pinyin",
    "type",
    "pos",
]

_WORDS_COLUMN_WIDTHS = {
    "id": 56,
    "word": 72,
    "meaning": 140,
    "pinyin": 96,
    "type": 56,
    "pos": 56,
}

_WORDS_COLUMN_HEADINGS = {
    "word": "한자",
    "meaning": "뜻",
    "type": "종류",
}


class VocabularyPanel(ttk.Frame):
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
        self._store = MultiSheetWorkbookStore(WORDS_FIELDNAMES)
        self._all_rows: list[dict[str, str]] = []
        self._current_sheet = ""
        self._build_ui()

    def load_defaults(self) -> None:
        """Load resource/table/words.xlsx when present (call after main window is ready)."""
        if DEFAULT_WORDS_TABLE_EXCEL.exists():
            try:
                self.load_file(DEFAULT_WORDS_TABLE_EXCEL)
            except (OSError, ValueError) as ex:
                self._on_status(f"기본 words 로드 실패: {ex}")

    @property
    def is_dirty(self) -> bool:
        return self._store.dirty

    @property
    def file_path(self) -> Path | None:
        return self._store.path

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text="시트:").pack(side=tk.LEFT)
        self._sheet_var = tk.StringVar()
        self._sheet_combo = ttk.Combobox(
            top, textvariable=self._sheet_var, state="readonly", width=24
        )
        self._sheet_combo.pack(side=tk.LEFT, padx=(4, 12))
        self._sheet_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_sheet_changed())

        ttk.Label(top, text="pos:").pack(side=tk.LEFT)
        self._pos_var = tk.StringVar(value=POS_FILTER_ALL)
        self._pos_combo = ttk.Combobox(
            top, textvariable=self._pos_var, state="readonly", width=16
        )
        self._pos_combo.pack(side=tk.LEFT, padx=(4, 12))
        self._pos_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Label(top, text="type:").pack(side=tk.LEFT)
        self._type_var = tk.StringVar(value=POS_FILTER_ALL)
        self._type_combo = ttk.Combobox(
            top, textvariable=self._type_var, state="readonly", width=16
        )
        self._type_combo.pack(side=tk.LEFT, padx=(4, 12))
        self._type_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Button(top, text="삭제", command=self._delete_row).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="새로 만들기", command=self._new_row).pack(side=tk.RIGHT, padx=4)

        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(search_frame, text="검색 (id / 한자 / type):").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(search_frame, textvariable=self._search_var, width=40)
        self._search_entry.pack(side=tk.LEFT, padx=6, fill=tk.X, expand=True)
        self._search_entry.bind("<Return>", lambda _e: self._run_search())

        self._table = TablePanel(
            self,
            WORDS_FIELDNAMES,
            display_columns=_WORDS_DISPLAY_COLUMNS,
            column_widths=_WORDS_COLUMN_WIDTHS,
            column_headings=_WORDS_COLUMN_HEADINGS,
            on_double_click=self._edit_row,
        )
        self._table.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._table.bind_tree("<Delete>", self._delete_row)
        self._table.bind_row_context_copy(
            lambda row: (row.get("word") or "").strip(),
            label="한자 복사",
            on_status=self._on_status,
        )

    def load_file(self, path: Path) -> None:
        self._store.load(path)
        names = self._store.sheet_names
        if not names:
            raise ValueError("시트가 없습니다.")
        self._sheet_combo["values"] = names
        self._current_sheet = names[0]
        self._sheet_var.set(self._current_sheet)
        self._reload_sheet()
        self._on_dirty_change(False)
        self._on_status(f"로드: {path}")

    def open_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="words.xlsx 열기",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All", "*.*")],
            initialdir=str(DEFAULT_WORDS_TABLE_EXCEL.parent),
        )
        if path:
            self.load_file(Path(path))

    def _write_csv_paths(self) -> str:
        if self._store.path is None:
            raise ValueError("저장된 Excel 경로가 없습니다.")
        return export_words_csv(self._store.path, DEFAULT_WORDS_TABLE_CSV)

    def _export_csv(self, *, show_dialog: bool) -> bool:
        if self._store.path is None:
            if show_dialog:
                messagebox.showinfo("CSV", "먼저 파일을 저장하세요.", parent=self)
            return False
        return export_csv_paths(
            self,
            self._on_status,
            self._write_csv_paths,
            show_dialog=show_dialog,
            dialog_title="CSV 보내기",
            status_prefix="저장·CSV" if not show_dialog else "CSV",
        )

    def save(self) -> bool:
        if self._store.path is None:
            return self.save_as()
        self._flush_current_sheet()
        try:
            self._store.save()
            self._on_dirty_change(False)
            invalidate_global_table_cache(words=True)
            self._on_status(f"저장: {self._store.path}")
            self._export_csv(show_dialog=False)
            return True
        except OSError as ex:
            messagebox.showerror("저장 실패", str(ex), parent=self)
            return False

    def save_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            title="words.xlsx 저장",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="words.xlsx",
            initialdir=str(DEFAULT_WORDS_TABLE_EXCEL.parent),
        )
        if not path:
            return False
        self._flush_current_sheet()
        try:
            self._store.save(path)
            self._on_dirty_change(False)
            invalidate_global_table_cache(words=True)
            self._on_status(f"저장: {path}")
            self._export_csv(show_dialog=False)
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
            return
        self._export_csv(show_dialog=True)

    def _flush_current_sheet(self) -> None:
        if self._current_sheet:
            self._store.set_sheet_rows(self._current_sheet, self._all_rows)

    def _reload_sheet(self) -> None:
        self._all_rows = self._store.get_sheet_rows(self._current_sheet)
        self._update_pos_combo()
        self._update_type_combo()
        self._apply_filter()

    def _update_pos_combo(self) -> None:
        values = [POS_FILTER_ALL] + unique_pos_values(self._all_rows)
        self._pos_combo["values"] = values
        if self._pos_var.get() not in values:
            self._pos_var.set(POS_FILTER_ALL)

    def _update_type_combo(self) -> None:
        values = [POS_FILTER_ALL] + unique_type_values(self._all_rows)
        self._type_combo["values"] = values
        if self._type_var.get() not in values:
            self._type_var.set(POS_FILTER_ALL)

    def _on_sheet_changed(self) -> None:
        self._flush_current_sheet()
        self._current_sheet = self._sheet_var.get()
        self._reload_sheet()

    def _apply_filter(self) -> None:
        filtered = filter_rows_by_pos(self._all_rows, self._pos_var.get())
        filtered = filter_rows_by_type(filtered, self._type_var.get())
        self._table.set_rows(filtered)

    def _run_search(self) -> None:
        query = self._search_var.get()
        kind, value = parse_search_query(query)
        if not value:
            self._apply_filter()
            return
        sheet_rows = self._all_rows
        if kind == "id":
            row = find_row_by_id(sheet_rows, value)
            if row is None:
                self._on_status(f"id {value} 없음 (현재 시트)")
                messagebox.showinfo("검색", f"id {value} 를 찾을 수 없습니다.", parent=self)
                return
            self._pos_var.set(POS_FILTER_ALL)
            self._type_var.set(POS_FILTER_ALL)
            self._apply_filter()
            self._table.select_row_by_id(value)
            self._on_status(f"id {value} 선택")
            return
        matches = find_rows_by_word(sheet_rows, value)
        if not matches:
            matches = find_rows_by_type(sheet_rows, value)
        if not matches:
            self._on_status(f"'{value}' 없음 (한자·type)")
            messagebox.showinfo(
                "검색",
                f"'{value}' 와 일치하는 한자·type 항목이 없습니다.",
                parent=self,
            )
            return
        if len(matches) == 1:
            rid = matches[0].get("id", "")
            self._pos_var.set(POS_FILTER_ALL)
            self._type_var.set(POS_FILTER_ALL)
            self._apply_filter()
            self._table.select_row_by_id(rid)
            self._on_status(f"한자 '{value}' → id {rid}")
            return

        def on_pick(row: dict[str, str]) -> None:
            rid = row.get("id", "")
            self._pos_var.set(POS_FILTER_ALL)
            self._type_var.set(POS_FILTER_ALL)
            self._apply_filter()
            self._table.select_row_by_id(rid)
            self._on_status(f"한자 '{value}' → id {rid}")

        IdPickerDialog(self, matches, on_pick)

    def _all_sheet_rows_snapshot(self) -> dict[str, list[dict[str, str]]]:
        """시트별 행(현재 편집 중인 시트는 메모리 반영)."""
        snapshot: dict[str, list[dict[str, str]]] = {}
        for name in self._store.sheet_names:
            if name == self._current_sheet:
                snapshot[name] = list(self._all_rows)
            else:
                snapshot[name] = self._store.get_sheet_rows(name)
        return snapshot

    def _sheet_existing_ids(self) -> set[str]:
        return {
            (r.get("id") or "").strip()
            for r in self._all_rows
            if (r.get("id") or "").strip()
        }

    def _new_row(self) -> None:
        if not self._current_sheet:
            messagebox.showinfo("새로 만들기", "먼저 시트를 선택하거나 파일을 열어주세요.", parent=self)
            return
        new_id = allocate_next_word_id(
            self._all_rows,
            self._all_sheet_rows_snapshot(),
            sheet_name=self._current_sheet,
        )
        defaults: dict[str, str] = {c: "" for c in WORDS_FIELDNAMES}
        defaults["id"] = new_id
        pos = self._pos_var.get()
        if pos and pos != POS_FILTER_ALL:
            defaults["pos"] = pos
        defaults = apply_new_word_defaults(
            defaults,
            pos=defaults.get("pos", ""),
        )
        self._open_editor(defaults, is_new=True)
        self._on_status(f"새 단어 (시트: {self._current_sheet}, id={new_id})")

    def _delete_row(self) -> None:
        if not self._current_sheet:
            messagebox.showinfo("삭제", "먼저 시트를 선택하거나 파일을 열어주세요.", parent=self)
            return
        row = self._table.get_selected_row()
        if row is None:
            messagebox.showinfo("삭제", "삭제할 행을 그리드에서 선택하세요.", parent=self)
            return
        rid = (row.get("id") or "").strip()
        if not rid:
            messagebox.showinfo("삭제", "id가 없는 행은 삭제할 수 없습니다.", parent=self)
            return
        word = (row.get("word") or "").strip()
        meaning = (row.get("meaning") or "").strip()
        detail = f"id={rid}"
        if word:
            detail += f"\n한자: {word}"
        if meaning:
            detail += f"\n뜻: {meaning}"
        if not messagebox.askyesno(
            "단어 삭제",
            f"현재 시트 「{self._current_sheet}」에서 아래 항목을 삭제할까요?\n\n{detail}",
            parent=self,
        ):
            return
        before = len(self._all_rows)
        self._all_rows = [
            r for r in self._all_rows if (r.get("id") or "").strip() != rid
        ]
        if len(self._all_rows) == before:
            messagebox.showwarning("삭제", "시트 데이터에서 해당 id를 찾지 못했습니다.", parent=self)
            return
        self._store.set_sheet_rows(self._current_sheet, self._all_rows)
        self._on_dirty_change(True)
        self._update_pos_combo()
        self._update_type_combo()
        self._apply_filter()
        self._on_status(f"삭제: id={rid} (시트: {self._current_sheet})")

    def _edit_row(self, row: dict[str, str]) -> None:
        self._open_editor(dict(row), is_new=False, original_id=row.get("id", ""))

    def _open_editor(
        self,
        row: dict[str, str],
        *,
        is_new: bool,
        original_id: str | None = None,
    ) -> None:
        def on_save(values: dict[str, str], new: bool) -> None:
            if new:
                self._all_rows.append(values)
            else:
                oid = (original_id or "").strip()
                for i, r in enumerate(self._all_rows):
                    if (r.get("id") or "").strip() == oid:
                        self._all_rows[i] = values
                        break
            self._store.set_sheet_rows(self._current_sheet, self._all_rows)
            self._on_dirty_change(True)
            self._update_pos_combo()
            self._update_type_combo()
            self._apply_filter()
            self._table.update_row(values, original_id=original_id)
            self._on_status(f"{'추가' if new else '수정'}: id {values.get('id', '')}")

        RowEditorDialog(
            self,
            WORDS_FIELDNAMES,
            row,
            title="새 단어" if is_new else "단어 편집",
            is_new=is_new,
            existing_ids=self._sheet_existing_ids(),
            original_id=original_id,
            on_save=on_save,
        )
