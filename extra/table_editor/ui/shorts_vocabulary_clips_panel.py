"""shorts_vocabulary_clips.xlsx editor."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from extra.table_editor.config import (
    DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV,
    DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL,
    TOPIC_FILTER_ALL,
)
from extra.table_editor.data.fields import SHORTS_VOCABULARY_CLIPS_FIELDNAMES
from extra.table_editor.data.workbook import ExcelWorkbookStore
from extra.table_editor.services.csv_export import export_shorts_vocabulary_clips_csv
from extra.table_editor.services.post_save_csv import export_csv_paths
from extra.table_editor.services.search import (
    allocate_next_row_id,
    filter_rows_by_topic,
    find_row_by_id,
    ids_equal,
    parse_search_query,
    unique_topic_values,
)
from extra.table_editor.services.shorts_vocab_data import parse_pipe_ids, warm_shorts_vocab_editor_cache
from extra.table_editor.services.word_lookup import lookup_word_details
from extra.table_editor.ui.shorts_vocabulary_clip_editor_dialog import (
    ShortsVocabularyClipEditorDialog,
)
from extra.table_editor.ui.table_panel import TablePanel

_DISPLAY_COLUMNS = [
    "id",
    "topic",
    "word_id",
    "단어수",
    "단어 미리보기",
    "hook_title",
    "ko_narration_id",
    "video_path",
    "bg_path",
]


def _word_count(row: dict[str, str]) -> str:
    n = len(parse_pipe_ids(row.get("word_id", "")))
    return str(n) if n else "0"


def _word_preview(row: dict[str, str]) -> str:
    parts: list[str] = []
    for wid in parse_pipe_ids(row.get("word_id", ""))[:4]:
        info = lookup_word_details(wid)
        hanzi = (info.get("word") or "").strip()
        parts.append(hanzi or wid)
    if not parts:
        return "—"
    extra = len(parse_pipe_ids(row.get("word_id", ""))) - len(parts)
    text = ", ".join(parts)
    if extra > 0:
        text += f" 외 {extra}개"
    return text


class ShortsVocabularyClipsPanel(ttk.Frame):
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
        self._store = ExcelWorkbookStore(SHORTS_VOCABULARY_CLIPS_FIELDNAMES)
        self._all_rows: list[dict[str, str]] = []
        self._build_ui()

    def load_defaults(self) -> None:
        warm_shorts_vocab_editor_cache()
        if DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL.exists():
            try:
                self.load_file(DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL)
            except (OSError, ValueError) as ex:
                self._on_status(f"기본 shorts_vocabulary_clips 로드 실패: {ex}")

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
            SHORTS_VOCABULARY_CLIPS_FIELDNAMES,
            display_columns=_DISPLAY_COLUMNS,
            computed_columns={
                "단어수": _word_count,
                "단어 미리보기": _word_preview,
            },
            on_double_click=self._edit_row,
        )
        self._table.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._table.bind_tree("<Delete>", self._delete_row)

    def load_file(self, path: Path) -> None:
        self._store.load(path)
        self._all_rows = self._store.get_rows()
        self._update_topic_combo()
        self._apply_filter()
        self._on_dirty_change(False)
        self._on_status(f"로드: {path}")

    def open_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="shorts_vocabulary_clips.xlsx 열기",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All", "*.*")],
            initialdir=str(DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL.parent),
        )
        if path:
            self.load_file(Path(path))

    def _write_csv_paths(self) -> str:
        if self._store.path is None:
            raise ValueError("저장된 Excel 경로가 없습니다.")
        return export_shorts_vocabulary_clips_csv(
            self._store.path, DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV
        )

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
        self._flush_rows()
        try:
            self._store.save()
            self._on_dirty_change(False)
            self._on_status(f"저장: {self._store.path}")
            self._export_csv(show_dialog=False)
            return True
        except OSError as ex:
            messagebox.showerror("저장 실패", str(ex), parent=self)
            return False

    def save_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            title="shorts_vocabulary_clips.xlsx 저장",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile="shorts_vocabulary_clips.xlsx",
            initialdir=str(DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL.parent),
        )
        if not path:
            return False
        self._flush_rows()
        try:
            self._store.save(path)
            self._on_dirty_change(False)
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
                    r
                    for r in self._all_rows
                    if value in parse_pipe_ids(r.get("word_id", ""))
                    or ids_equal(r.get("word_id", ""), value)
                ]
                if len(matches) == 1:
                    row = matches[0]
                elif len(matches) > 1:
                    self._topic_var.set(TOPIC_FILTER_ALL)
                    self._apply_filter()
                    self._table.select_row_by_id(matches[0].get("id", ""))
                    self._on_status(f"word_id {value} 포함 (첫 일치)")
                    return
            if row is None:
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
        defaults: dict[str, str] = {c: "" for c in SHORTS_VOCABULARY_CLIPS_FIELDNAMES}
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
            return
        topic = (row.get("topic") or "").strip()
        detail = f"id={rid}"
        if topic:
            detail += f"\ntopic: {topic}"
        if not messagebox.askyesno("행 삭제", f"아래 항목을 삭제할까요?\n\n{detail}", parent=self):
            return
        before = len(self._all_rows)
        self._all_rows = [r for r in self._all_rows if (r.get("id") or "").strip() != rid]
        if len(self._all_rows) == before:
            return
        self._store.set_rows(self._all_rows)
        self._on_dirty_change(True)
        self._update_topic_combo()
        self._apply_filter()
        self._on_status(f"삭제: id={rid}")

    def _edit_row(self, row: dict[str, str]) -> None:
        self._open_editor(dict(row), is_new=False, original_id=row.get("id", ""))

    def _validate_row(self, values: dict[str, str]) -> bool:
        try:
            clip_id = int(float(values.get("id", "")))
        except (ValueError, TypeError):
            messagebox.showwarning("검증", "id는 1 이상의 숫자여야 합니다.", parent=self)
            return False
        if clip_id < 1:
            messagebox.showwarning("검증", "id는 1 이상이어야 합니다.", parent=self)
            return False
        values["id"] = str(clip_id)

        if not (values.get("word_id") or "").strip():
            messagebox.showwarning("검증", "word_id를 1개 이상 지정하세요.", parent=self)
            return False
        if not (values.get("hook_title") or "").strip():
            messagebox.showwarning("검증", "hook_title을 입력하세요.", parent=self)
            return False

        ko_raw = (values.get("ko_narration_id") or "").strip()
        if ko_raw:
            try:
                ko_id = int(float(ko_raw))
                if ko_id < 1:
                    raise ValueError
                values["ko_narration_id"] = str(ko_id)
            except (ValueError, TypeError):
                messagebox.showwarning(
                    "검증", "ko_narration_id는 비우거나 1 이상이어야 합니다.", parent=self
                )
                return False
        else:
            values["ko_narration_id"] = ""

        last_hold = (values.get("last_hold_sec") or "").strip()
        if last_hold:
            try:
                float(last_hold)
            except (ValueError, TypeError):
                messagebox.showwarning(
                    "검증", "last_hold_sec는 숫자(초)여야 합니다.", parent=self
                )
                return False
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

        topics = unique_topic_values(self._all_rows)
        ShortsVocabularyClipEditorDialog(
            self,
            row,
            title="새 숏츠 단어 클립" if is_new else "숏츠 단어 클립 편집",
            is_new=is_new,
            existing_ids=self._existing_ids(),
            original_id=original_id,
            topic_choices=topics,
            on_save=on_save,
        )
