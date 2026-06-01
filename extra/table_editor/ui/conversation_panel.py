"""base_sentences + sub_sentences editor (vertical split)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from extra.table_editor.config import (
    CONVERSATION_DISPLAY_COL,
    DEFAULT_BASE_SENTENCES_CSV,
    DEFAULT_BASE_SENTENCES_EXCEL,
    DEFAULT_SUB_SENTENCES_CSV,
    DEFAULT_SUB_SENTENCES_EXCEL,
    SUB_EDITOR_FIELDNAMES,
    TOPIC_FILTER_ALL,
)
from extra.table_editor.data.fields import BASE_FIELDNAMES, SUB_FIELDNAMES
from extra.table_editor.data.workbook import ExcelWorkbookStore, normalize_id_display
from extra.table_editor.services.csv_export import export_base_csv, export_sub_csv
from extra.table_editor.services.post_save_csv import export_csv_paths
from extra.table_editor.services.raw_sentence_slots import raw_to_display
from extra.table_editor.services.search import (
    allocate_next_sub_row_id,
    filter_rows_by_base_id,
    filter_rows_by_topic,
    find_row_by_id,
    find_row_index_by_id,
    find_sub_row_index,
    ids_equal,
    parse_search_query,
    sub_row_id_exists,
    unique_topic_values,
)
from extra.table_editor.services.global_table_cache import invalidate_global_table_cache
from extra.table_editor.services.sub_sentence_preview_cache import SubSentencePreviewCache
from extra.table_editor.ui.row_editor_dialog import RowEditorDialog
from extra.table_editor.ui.table_panel import TablePanel


class ConversationPanel(ttk.Frame):
    """위: base 전체 / 아래: 선택한 base id 에 맞는 sub (선택 전에는 sub 미표시)."""

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

        self._base_store = ExcelWorkbookStore(BASE_FIELDNAMES)
        self._sub_store = ExcelWorkbookStore(SUB_FIELDNAMES)
        self._all_base_rows: list[dict[str, str]] = []
        self._all_sub_rows: list[dict[str, str]] = []
        self._selected_base_id = ""
        self._sub_preview_cache = SubSentencePreviewCache()

        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text="topic:").pack(side=tk.LEFT)
        self._topic_var = tk.StringVar(value=TOPIC_FILTER_ALL)
        self._topic_combo = ttk.Combobox(
            top, textvariable=self._topic_var, state="readonly", width=20
        )
        self._topic_combo.pack(side=tk.LEFT, padx=(4, 12))
        self._topic_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_topic_filter_changed())

        ttk.Label(top, text="검색 (base id):").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self._search_var, width=32)
        entry.pack(side=tk.LEFT, padx=6)
        entry.bind("<Return>", lambda _e: self._run_search())

        self._new_sub_btn = ttk.Button(
            top, text="sub 새로 만들기", command=self._new_sub_row, state=tk.DISABLED
        )
        self._new_sub_btn.pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="base 새로 만들기", command=self._new_base_row).pack(
            side=tk.RIGHT, padx=4
        )

        file_row = ttk.Frame(self)
        file_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Button(file_row, text="base 열기", command=self._open_base_dialog).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(file_row, text="sub 열기", command=self._open_sub_dialog).pack(
            side=tk.LEFT, padx=2
        )

        self._paned = ttk.Panedwindow(self, orient=tk.VERTICAL)
        self._paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._base_frame = ttk.LabelFrame(self._paned, text="base_sentences")
        self._paned.add(self._base_frame, weight=3)

        self._base_table = TablePanel(
            self._base_frame,
            BASE_FIELDNAMES,
            display_columns=[
                "id",
                "topic",
                CONVERSATION_DISPLAY_COL,
                "translation",
                "raw_sentence",
            ],
            computed_columns={
                CONVERSATION_DISPLAY_COL: lambda row: raw_to_display(
                    row.get("raw_sentence", "")
                ),
            },
            on_double_click=self._edit_base_row,
            on_select=self._on_base_selected,
        )
        self._base_table.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._base_table.bind_row_context_copy(
            lambda row: raw_to_display(row.get("raw_sentence", "")),
            on_status=self._on_status,
        )

        self._sub_frame = ttk.LabelFrame(self._paned, text="sub_sentences")
        self._sub_table = TablePanel(
            self._sub_frame,
            SUB_FIELDNAMES,
            display_columns=[
                "id",
                "base_id",
                CONVERSATION_DISPLAY_COL,
                "main_slot",
                "alt_translation",
                "target_slot_order",
                "alt_word_id",
            ],
            computed_columns={
                CONVERSATION_DISPLAY_COL: self._sub_display_for_table_row,
            },
            on_double_click=self._edit_sub_row,
        )
        self._sub_table.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._sub_table.bind_row_context_copy(
            self._sub_display_for_table_row,
            on_status=self._on_status,
        )
        self._sub_visible = False

    def load_defaults(self) -> None:
        if DEFAULT_BASE_SENTENCES_EXCEL.exists():
            try:
                self._load_base(DEFAULT_BASE_SENTENCES_EXCEL)
            except OSError as ex:
                self._on_status(f"base 로드 실패: {ex}")
        if DEFAULT_SUB_SENTENCES_EXCEL.exists():
            try:
                self._load_sub(DEFAULT_SUB_SENTENCES_EXCEL)
            except OSError as ex:
                self._on_status(f"sub 로드 실패: {ex}")

    @property
    def is_dirty(self) -> bool:
        return self._base_store.dirty or self._sub_store.dirty

    @property
    def file_path(self) -> Path | None:
        return self._base_store.path or self._sub_store.path

    def path_summary(self) -> str:
        parts: list[str] = []
        if self._base_store.path:
            parts.append(f"base: {self._base_store.path.name}")
        if self._sub_store.path:
            parts.append(f"sub: {self._sub_store.path.name}")
        return " | ".join(parts) if parts else "(파일 없음)"

    def _on_child_dirty(self) -> None:
        self._on_dirty_change(self.is_dirty)

    def _load_base(self, path: Path) -> None:
        self._base_store.load(path)
        self._all_base_rows = self._base_store.get_rows()
        self._update_topic_combo()
        self._apply_base_filter()
        self._hide_sub_panel()
        self._on_child_dirty()
        self._on_status(f"base 로드: {path}")

    def _update_topic_combo(self) -> None:
        values = [TOPIC_FILTER_ALL] + unique_topic_values(self._all_base_rows)
        self._topic_combo["values"] = values
        if self._topic_var.get() not in values:
            self._topic_var.set(TOPIC_FILTER_ALL)

    def _apply_base_filter(self) -> None:
        filtered = filter_rows_by_topic(self._all_base_rows, self._topic_var.get())
        self._base_table.set_rows(filtered)

    def _on_topic_filter_changed(self) -> None:
        self._apply_base_filter()
        if self._base_table.get_selected_row() is None:
            self._hide_sub_panel()

    def _load_sub(self, path: Path) -> None:
        self._sub_store.load(path)
        self._all_sub_rows = self._sub_store.get_rows()
        self._refresh_sub_view()
        self._on_child_dirty()
        self._on_status(f"sub 로드: {path}")

    def _open_base_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="base_sentences 열기",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All", "*.*")],
            initialdir=str(DEFAULT_BASE_SENTENCES_EXCEL.parent),
            initialfile=DEFAULT_BASE_SENTENCES_EXCEL.name,
        )
        if path:
            self._load_base(Path(path))

    def _open_sub_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="sub_sentences 열기",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All", "*.*")],
            initialdir=str(DEFAULT_SUB_SENTENCES_EXCEL.parent),
            initialfile=DEFAULT_SUB_SENTENCES_EXCEL.name,
        )
        if path:
            self._load_sub(Path(path))

    def open_file_dialog(self) -> None:
        self._open_base_dialog()

    def _flush_base(self) -> None:
        self._base_store.set_rows(self._all_base_rows)

    def _flush_sub(self) -> None:
        self._sub_store.set_rows(self._all_sub_rows)

    def flush_all(self) -> None:
        self._flush_base()
        self._flush_sub()

    def _save_base(self) -> bool:
        if self._base_store.path is None:
            return self._save_base_as()
        self._flush_base()
        try:
            self._base_store.save()
            self._on_child_dirty()
            invalidate_global_table_cache(base=True)
            return True
        except OSError as ex:
            messagebox.showerror("base 저장 실패", str(ex), parent=self)
            return False

    def _save_sub(self) -> bool:
        if (
            self._sub_store.path is None
            and not self._all_sub_rows
            and not self._sub_store.dirty
        ):
            return True
        if self._sub_store.path is None:
            return self._save_sub_as()
        self._flush_sub()
        try:
            self._sub_store.save()
            self._on_child_dirty()
            invalidate_global_table_cache(sub=True)
            return True
        except OSError as ex:
            messagebox.showerror("sub 저장 실패", str(ex), parent=self)
            return False

    def _write_csv_paths(self) -> list[str]:
        if self._base_store.path is None or self._sub_store.path is None:
            raise ValueError("base·sub Excel 경로가 필요합니다.")
        base_out = export_base_csv(self._base_store.path, DEFAULT_BASE_SENTENCES_CSV)
        sub_out = export_sub_csv(self._sub_store.path, DEFAULT_SUB_SENTENCES_CSV)
        return [base_out, sub_out]

    def _export_csv(self, *, show_dialog: bool) -> bool:
        if self._base_store.path is None:
            if show_dialog:
                messagebox.showinfo(
                    "회화 CSV", "base_sentences 파일을 먼저 열거나 저장하세요.", parent=self
                )
            return False
        if self._sub_store.path is None:
            if show_dialog:
                messagebox.showinfo(
                    "회화 CSV", "sub_sentences 파일을 먼저 열거나 저장하세요.", parent=self
                )
            return False
        return export_csv_paths(
            self,
            self._on_status,
            self._write_csv_paths,
            show_dialog=show_dialog,
            dialog_title="회화 CSV",
            status_prefix="저장·CSV" if not show_dialog else "CSV",
        )

    def save(self) -> bool:
        ok_base = self._save_base()
        ok_sub = self._save_sub()
        if ok_base and ok_sub:
            self._on_status("base·sub 저장 완료")
            self._export_csv(show_dialog=False)
        return ok_base and ok_sub

    def _save_base_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            title="base_sentences 저장",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=DEFAULT_BASE_SENTENCES_EXCEL.name,
            initialdir=str(DEFAULT_BASE_SENTENCES_EXCEL.parent),
        )
        if not path:
            return False
        self._flush_base()
        try:
            self._base_store.save(path)
            self._on_child_dirty()
            invalidate_global_table_cache(base=True)
            return True
        except OSError as ex:
            messagebox.showerror("base 저장 실패", str(ex), parent=self)
            return False

    def _save_sub_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            title="sub_sentences 저장",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=DEFAULT_SUB_SENTENCES_EXCEL.name,
            initialdir=str(DEFAULT_SUB_SENTENCES_EXCEL.parent),
        )
        if not path:
            return False
        self._flush_sub()
        try:
            self._sub_store.save(path)
            self._on_child_dirty()
            invalidate_global_table_cache(sub=True)
            return True
        except OSError as ex:
            messagebox.showerror("sub 저장 실패", str(ex), parent=self)
            return False

    def save_as(self) -> bool:
        ok_base = self._save_base_as()
        ok_sub = self._save_sub_as()
        if ok_base and ok_sub:
            self._on_status("base·sub 다른 이름으로 저장 완료")
            self._export_csv(show_dialog=False)
        return ok_base and ok_sub

    def export_current_csv(self) -> None:
        self.export_all_csv()

    def export_all_csv(self) -> None:
        self.flush_all()
        if self.is_dirty:
            if not messagebox.askyesno(
                "회화 CSV",
                "저장되지 않은 변경이 있습니다. 저장 후 CSV를 생성할까요?",
                parent=self,
            ):
                return
            if not self.save():
                return
            return
        self._export_csv(show_dialog=True)

    def _show_sub_panel(self) -> None:
        if not self._sub_visible:
            self._paned.add(self._sub_frame, weight=2)
            self._sub_visible = True

    def _hide_sub_panel(self) -> None:
        self._selected_base_id = ""
        self._sub_table.set_rows([])
        self._new_sub_btn.configure(state=tk.DISABLED)
        if self._sub_visible:
            self._paned.forget(self._sub_frame)
            self._sub_visible = False

    def _on_base_selected(self, row: dict[str, str] | None) -> None:
        if row is None:
            self._hide_sub_panel()
            return
        base_id = (row.get("id") or "").strip()
        if not base_id:
            self._hide_sub_panel()
            return
        self._selected_base_id = base_id
        self._show_sub_panel()
        self._warm_sub_preview_cache_for_base(base_id)
        self._refresh_sub_view()
        n = len(filter_rows_by_base_id(self._all_sub_rows, base_id))
        self._new_sub_btn.configure(state=tk.NORMAL)
        self._on_status(f"base id {base_id} 선택 — sub {n}건")

    def _normalize_conversation_ids(self, row: dict[str, str]) -> dict[str, str]:
        out = dict(row)
        for col in ("id", "base_id"):
            if col in out:
                out[col] = normalize_id_display(out.get(col, ""))
        return out

    def _dedupe_rows_by_id(
        self, rows: list[dict[str, str]], *, keep_index: int, row_id: str
    ) -> list[dict[str, str]]:
        return [
            r
            for i, r in enumerate(rows)
            if i == keep_index or not ids_equal(r.get("id", ""), row_id)
        ]

    def _sub_display_for_table_row(self, row: dict[str, str]) -> str:
        base_id = (row.get("base_id") or "").strip() or self._selected_base_id
        base_raw = self._base_raw_sentence_for(base_id)
        return self._cached_sub_display_sentence(row, base_raw)

    def _refresh_sub_view(self) -> None:
        if not self._selected_base_id:
            self._sub_table.set_rows([])
            return
        filtered = filter_rows_by_base_id(self._all_sub_rows, self._selected_base_id)
        self._sub_table.set_rows(filtered)

    def _run_search(self) -> None:
        kind, value = parse_search_query(self._search_var.get())
        if not value:
            return
        if kind != "id":
            messagebox.showinfo(
                "검색",
                "회화 모드에서는 base id(숫자)만 검색할 수 있습니다.",
                parent=self,
            )
            return
        row = find_row_by_id(self._all_base_rows, value)
        if row is None:
            self._on_status(f"base id {value} 없음")
            messagebox.showinfo("검색", f"base id {value} 를 찾을 수 없습니다.", parent=self)
            return
        self._topic_var.set(TOPIC_FILTER_ALL)
        self._apply_base_filter()
        self._base_table.select_row_by_id(value)
        self._on_base_selected(row)

    def _new_base_row(self) -> None:
        defaults = {c: "" for c in BASE_FIELDNAMES}
        topic = self._topic_var.get()
        if topic and topic != TOPIC_FILTER_ALL:
            defaults["topic"] = topic
        self._open_base_row_editor(defaults, is_new=True, title="새 base 행")

    def _new_sub_row(self) -> None:
        if not self._selected_base_id:
            messagebox.showinfo(
                "sub 새로 만들기",
                "먼저 base 목록에서 행을 선택하세요.",
                parent=self,
            )
            return
        defaults = {c: "" for c in SUB_FIELDNAMES}
        defaults["id"] = allocate_next_sub_row_id(
            self._all_sub_rows,
            self._selected_base_id,
        )
        defaults["base_id"] = self._selected_base_id
        self._open_sub_editor(defaults, is_new=True, title="새 sub 행")

    def _edit_base_row(self, row: dict[str, str]) -> None:
        self._open_base_row_editor(
            dict(row),
            is_new=False,
            title="base 행 편집",
            original_id=row.get("id", ""),
            original_row=dict(row),
            on_after_save=self._on_base_row_saved,
        )

    def _edit_sub_row(self, row: dict[str, str]) -> None:
        self._open_sub_editor(
            dict(row),
            is_new=False,
            title="sub 행 편집",
            original_id=row.get("id", ""),
            original_row=dict(row),
        )

    def _on_base_row_saved(self, values: dict[str, str], _new: bool) -> None:
        old_sel = self._selected_base_id
        new_id = (values.get("id") or "").strip()
        if old_sel and new_id and not ids_equal(old_sel, new_id):
            for row in self._all_sub_rows:
                if ids_equal(row.get("base_id", ""), old_sel):
                    row["base_id"] = new_id
            self._selected_base_id = new_id
            self._flush_sub()
            self._refresh_sub_view()
        base_id = new_id or old_sel
        if base_id:
            self._sub_preview_cache.invalidate_for_base(
                base_id,
                self._all_sub_rows,
                self._base_raw_sentence_for(base_id),
            )
            self._refresh_sub_view()
        self._update_topic_combo()
        self._apply_base_filter()

    def _base_existing_ids(self) -> set[str]:
        return {
            (r.get("id") or "").strip()
            for r in self._all_base_rows
            if (r.get("id") or "").strip()
        }

    def _open_base_row_editor(
        self,
        row: dict[str, str],
        *,
        is_new: bool,
        title: str,
        original_id: str | None = None,
        original_row: dict[str, str] | None = None,
        on_after_save: Callable[[dict[str, str], bool], None] | None = None,
    ) -> None:
        row_snapshot = dict(original_row or row)
        def on_save(values: dict[str, str], new: bool) -> None:
            values = self._normalize_conversation_ids(values)
            if new:
                if find_row_index_by_id(self._all_base_rows, values.get("id", "")) is not None:
                    messagebox.showwarning(
                        "검증",
                        f"id {values.get('id', '')} 가 이미 존재합니다.",
                        parent=self,
                    )
                    return False
                self._all_base_rows.append(values)
            else:
                idx = find_row_index_by_id(
                    self._all_base_rows,
                    original_id or "",
                    match=row_snapshot,
                    fieldnames=BASE_FIELDNAMES,
                )
                if idx is None:
                    messagebox.showwarning(
                        "저장",
                        f"base id {original_id} 행을 찾을 수 없습니다.",
                        parent=self,
                    )
                    return False
                self._all_base_rows[idx] = values
                self._all_base_rows = self._dedupe_rows_by_id(
                    self._all_base_rows,
                    keep_index=idx,
                    row_id=values.get("id", ""),
                )
            self._base_store.set_rows(self._all_base_rows)
            if on_after_save:
                on_after_save(values, new)
            else:
                self._update_topic_combo()
                self._apply_base_filter()
            self._base_table.select_row_by_id(values.get("id", ""))
            self._on_child_dirty()
            self._on_status(f"{'추가' if new else '수정'}: id {values.get('id', '')}")
            return True

        def on_delete() -> bool:
            bid = (original_id or row_snapshot.get("id") or "").strip()
            if not bid:
                messagebox.showwarning("삭제", "id가 없는 행은 삭제할 수 없습니다.", parent=self)
                return False
            subs = filter_rows_by_base_id(self._all_sub_rows, bid)
            detail = f"id={bid}"
            topic = (row_snapshot.get("topic") or "").strip()
            translation = (row_snapshot.get("translation") or "").strip()
            if topic:
                detail += f"\ntopic: {topic}"
            if translation:
                detail += f"\ntranslation: {translation}"
            prompt = f"base 행을 삭제할까요?\n\n{detail}"
            if subs:
                prompt += f"\n\n연결된 sub {len(subs)}건도 함께 삭제됩니다."
            if not messagebox.askyesno("base 삭제", prompt, parent=self):
                return False
            idx = find_row_index_by_id(
                self._all_base_rows,
                bid,
                match=row_snapshot,
                fieldnames=BASE_FIELDNAMES,
            )
            if idx is None:
                messagebox.showwarning(
                    "삭제",
                    f"base id {bid} 행을 찾을 수 없습니다.",
                    parent=self,
                )
                return False
            del self._all_base_rows[idx]
            if subs:
                self._all_sub_rows = [
                    r
                    for r in self._all_sub_rows
                    if not ids_equal(r.get("base_id", ""), bid)
                ]
                self._sub_store.set_rows(self._all_sub_rows)
            self._base_store.set_rows(self._all_base_rows)
            if ids_equal(self._selected_base_id, bid):
                self._hide_sub_panel()
            self._update_topic_combo()
            self._apply_base_filter()
            self._schedule_warm_sub_preview_cache()
            self._on_child_dirty()
            sub_note = f", sub {len(subs)}건" if subs else ""
            self._on_status(f"삭제: base id {bid}{sub_note}")
            return True

        RowEditorDialog(
            self,
            BASE_FIELDNAMES,
            row,
            title=title,
            is_new=is_new,
            existing_ids=self._base_existing_ids(),
            original_id=original_id,
            on_save=on_save,
            on_delete=None if is_new else on_delete,
        )

    def _open_row_editor(
        self,
        store: ExcelWorkbookStore,
        table: TablePanel,
        fieldnames: list[str],
        row: dict[str, str],
        *,
        is_new: bool,
        title: str,
        original_id: str | None = None,
        on_after_save: Callable[[dict[str, str], bool], None] | None = None,
    ) -> None:
        def on_save(values: dict[str, str], new: bool) -> None:
            rows = table.get_rows()
            if new:
                rows.append(values)
            else:
                oid = (original_id or "").strip()
                for i, r in enumerate(rows):
                    if (r.get("id") or "").strip() == oid:
                        rows[i] = values
                        break
            store.set_rows(rows)
            table.set_rows(rows)
            table.select_row_by_id(values.get("id", ""))
            if on_after_save:
                on_after_save(values, new)
            self._on_child_dirty()
            self._on_status(f"{'추가' if new else '수정'}: id {values.get('id', '')}")

        RowEditorDialog(
            self,
            fieldnames,
            row,
            title=title,
            is_new=is_new,
            existing_ids=table.existing_ids(),
            original_id=original_id,
            on_save=on_save,
        )

    def _base_raw_sentence_for(self, base_id: str) -> str:
        bid = (base_id or "").strip()
        if not bid:
            return ""
        for r in self._all_base_rows:
            if (r.get("id") or "").strip() == bid:
                return (r.get("raw_sentence") or "").strip()
        return ""

    def _schedule_warm_sub_preview_cache(self) -> None:
        self.after_idle(self._warm_sub_preview_cache)

    def _warm_sub_preview_cache(self) -> None:
        if not self._all_sub_rows:
            return
        self._sub_preview_cache.warm_rows(
            self._all_sub_rows,
            self._base_raw_sentence_for,
        )
        if self._selected_base_id:
            self.after_idle(self._refresh_sub_view)

    def _warm_sub_preview_cache_for_base(self, base_id: str) -> None:
        bid = (base_id or "").strip()
        if not bid:
            return
        rows = filter_rows_by_base_id(self._all_sub_rows, bid)
        if not rows:
            return
        base_raw = self._base_raw_sentence_for(bid)
        self._sub_preview_cache.warm_rows(rows, lambda _bid=bid: base_raw)
        self._refresh_sub_view()

    def _cached_sub_display_sentence(
        self, row: dict[str, str], base_raw_sentence: str
    ) -> str:
        cached = self._sub_preview_cache.get(row, base_raw_sentence)
        if cached is not None:
            return cached
        return self._sub_preview_cache.build(row, base_raw_sentence)

    def _sub_existing_ids(self, base_id: str) -> set[str]:
        bid = (base_id or "").strip()
        return {
            (r.get("id") or "").strip()
            for r in self._all_sub_rows
            if ids_equal(r.get("base_id", ""), bid) and (r.get("id") or "").strip()
        }

    def _open_sub_editor(
        self,
        row: dict[str, str],
        *,
        is_new: bool,
        title: str,
        original_id: str | None = None,
        original_row: dict[str, str] | None = None,
    ) -> None:
        row_snapshot = dict(original_row or row)

        def on_save(values: dict[str, str], new: bool) -> None:
            values = self._normalize_conversation_ids(values)
            base_id = (
                (values.get("base_id") or "").strip()
                or self._selected_base_id
            )
            if not (values.get("base_id") or "").strip() and self._selected_base_id:
                values["base_id"] = self._selected_base_id
            if new:
                if sub_row_id_exists(self._all_sub_rows, base_id, values.get("id", "")):
                    messagebox.showwarning(
                        "검증",
                        f"base {base_id} 에 id {values.get('id', '')} 가 이미 있습니다.",
                        parent=self,
                    )
                    return False
                self._all_sub_rows.append(values)
            else:
                edit_base_id = (
                    (row_snapshot.get("base_id") or "").strip() or base_id
                )
                idx = find_sub_row_index(
                    self._all_sub_rows,
                    edit_base_id,
                    original_id or "",
                    match=row_snapshot,
                    fieldnames=SUB_FIELDNAMES,
                )
                if idx is None:
                    messagebox.showwarning(
                        "저장",
                        f"sub id {original_id} (base {edit_base_id}) 행을 찾을 수 없습니다.",
                        parent=self,
                    )
                    return False
                self._all_sub_rows[idx] = values
                self._all_sub_rows = [
                    r
                    for i, r in enumerate(self._all_sub_rows)
                    if i == idx
                    or not (
                        ids_equal(r.get("base_id", ""), base_id)
                        and ids_equal(r.get("id", ""), values.get("id", ""))
                    )
                ]
            self._sub_store.set_rows(self._all_sub_rows)
            base_raw = self._base_raw_sentence_for(
                (values.get("base_id") or "").strip() or self._selected_base_id
            )
            self._sub_preview_cache.build(values, base_raw)
            self._refresh_sub_view()
            self._on_child_dirty()
            self._on_status(f"{'추가' if new else '수정'}: sub id {values.get('id', '')}")
            return True

        def on_delete() -> bool:
            base_id = (row_snapshot.get("base_id") or "").strip() or self._selected_base_id
            sid = (original_id or row_snapshot.get("id") or "").strip()
            if not base_id or not sid:
                messagebox.showwarning("삭제", "id가 없는 행은 삭제할 수 없습니다.", parent=self)
                return False
            detail = f"base_id={base_id}, id={sid}"
            alt = (row_snapshot.get("alt_translation") or "").strip()
            if alt:
                detail += f"\nalt_translation: {alt}"
            if not messagebox.askyesno("sub 삭제", f"sub 행을 삭제할까요?\n\n{detail}", parent=self):
                return False
            idx = find_sub_row_index(
                self._all_sub_rows,
                base_id,
                sid,
                match=row_snapshot,
                fieldnames=SUB_FIELDNAMES,
            )
            if idx is None:
                messagebox.showwarning(
                    "삭제",
                    f"sub id {sid} (base {base_id}) 행을 찾을 수 없습니다.",
                    parent=self,
                )
                return False
            del self._all_sub_rows[idx]
            self._sub_store.set_rows(self._all_sub_rows)
            self._refresh_sub_view()
            self._on_child_dirty()
            self._on_status(f"삭제: sub id {sid} (base {base_id})")
            return True

        base_id = (row.get("base_id") or "").strip() or self._selected_base_id
        base_raw = self._base_raw_sentence_for(base_id)
        cached_display = self._cached_sub_display_sentence(row, base_raw)
        RowEditorDialog(
            self,
            SUB_EDITOR_FIELDNAMES,
            row,
            title=title,
            is_new=is_new,
            existing_ids=self._sub_existing_ids(base_id),
            original_id=original_id,
            on_save=on_save,
            on_delete=None if is_new else on_delete,
            base_raw_sentence=base_raw,
            sub_display_sentence=cached_display,
        )

