"""ko_narration_sets + ko_narration_lines editor (vertical split)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from extra.table_editor.config import (
    DEFAULT_KO_NARRATION_LINES_CSV,
    DEFAULT_KO_NARRATION_LINES_EXCEL,
    DEFAULT_KO_NARRATION_SETS_CSV,
    DEFAULT_KO_NARRATION_SETS_EXCEL,
    DEFAULT_KO_NARRATION_TTS_TYPE,
    DEFAULT_KO_NARRATION_TTS_VOICE,
)
from extra.table_editor.data.fields import (
    KO_NARRATION_LINES_FIELDNAMES,
    KO_NARRATION_SETS_FIELDNAMES,
)
from extra.table_editor.data.workbook import ExcelWorkbookStore, normalize_id_display
from extra.table_editor.services.global_table_cache import invalidate_global_table_cache
from extra.table_editor.services.csv_export import (
    export_ko_narration_lines_csv,
    export_ko_narration_sets_csv,
)
from extra.table_editor.services.ko_narration_lines_normalize import (
    ko_line_rows_for_editor,
    read_ko_line_rows_from_excel,
    rows_need_ko_line_merge,
)
from extra.table_editor.services.post_save_csv import export_csv_paths
from extra.table_editor.services.search import (
    allocate_next_ko_line_id,
    allocate_next_row_id,
    filter_rows_by_set_id,
    find_ko_line_row_index,
    find_row_by_id,
    find_row_index_by_id,
    ids_equal,
    ko_line_id_exists,
    parse_search_query,
    sort_ko_narration_lines_by_id,
)
from extra.table_editor.ui.table_panel import TablePanel


class TtsPanel(ttk.Frame):
    """위: ko_narration_sets / 아래: 선택 set 의 lines (id 1행, text는 \\n 구분)."""

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

        self._sets_store = ExcelWorkbookStore(KO_NARRATION_SETS_FIELDNAMES)
        self._lines_store = ExcelWorkbookStore(KO_NARRATION_LINES_FIELDNAMES)
        self._all_set_rows: list[dict[str, str]] = []
        self._all_line_rows: list[dict[str, str]] = []
        self._selected_set_id = ""
        self._syncing_selection = False
        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text="검색 (set id):").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self._search_var, width=32)
        entry.pack(side=tk.LEFT, padx=6)
        entry.bind("<Return>", lambda _e: self._run_search())

        self._new_line_btn = ttk.Button(
            top, text="line 새로 만들기", command=self._new_line_row, state=tk.DISABLED
        )
        self._new_line_btn.pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="set 새로 만들기", command=self._new_set_row).pack(
            side=tk.RIGHT, padx=4
        )

        file_row = ttk.Frame(self)
        file_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Button(file_row, text="sets 열기", command=self._open_sets_dialog).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(file_row, text="lines 열기", command=self._open_lines_dialog).pack(
            side=tk.LEFT, padx=2
        )

        self._paned = ttk.Panedwindow(self, orient=tk.VERTICAL)
        self._paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._sets_frame = ttk.LabelFrame(self._paned, text="ko_narration_sets")
        self._paned.add(self._sets_frame, weight=3)

        self._sets_table = TablePanel(
            self._sets_frame,
            KO_NARRATION_SETS_FIELDNAMES,
            display_columns=["id", "title", "tts", "tts_voice"],
            on_double_click=self._edit_set_row,
            on_select=self._on_set_selected,
        )
        self._sets_table.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self._lines_frame: ttk.LabelFrame | None = None
        self._lines_table: TablePanel | None = None
        self._detail_visible = False

    def _ensure_detail_ui(self) -> None:
        if self._lines_frame is not None:
            return

        self._lines_frame = ttk.LabelFrame(
            self._paned,
            text="ko_narration_lines (set 선택)",
        )
        self._lines_table = TablePanel(
            self._lines_frame,
            KO_NARRATION_LINES_FIELDNAMES,
            display_columns=["id", "text"],
            row_sort=sort_ko_narration_lines_by_id,
            on_double_click=self._edit_line_row,
        )
        self._lines_table.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    def load_defaults(self) -> None:
        if DEFAULT_KO_NARRATION_SETS_EXCEL.exists():
            try:
                self._load_sets(DEFAULT_KO_NARRATION_SETS_EXCEL)
            except (OSError, ValueError) as ex:
                self._on_status(f"sets 로드 실패: {ex}")
        if DEFAULT_KO_NARRATION_LINES_EXCEL.exists():
            try:
                self._load_lines(DEFAULT_KO_NARRATION_LINES_EXCEL)
            except (OSError, ValueError) as ex:
                self._on_status(f"lines 로드 실패: {ex}")

    @property
    def is_dirty(self) -> bool:
        return self._sets_store.dirty or self._lines_store.dirty

    def path_summary(self) -> str:
        parts: list[str] = []
        if self._sets_store.path:
            parts.append(f"sets: {self._sets_store.path.name}")
        if self._lines_store.path:
            parts.append(f"lines: {self._lines_store.path.name}")
        return " | ".join(parts) if parts else "(파일 없음)"

    def _on_child_dirty(self) -> None:
        self._on_dirty_change(self.is_dirty)

    def _load_sets(self, path: Path) -> None:
        self._sets_store.load(path)
        self._all_set_rows = self._sets_store.get_rows()
        self._syncing_selection = True
        try:
            self._sets_table.set_rows(self._all_set_rows)
            self._hide_detail_panel()
            self._selected_set_id = ""
            if self._lines_table is not None:
                self._lines_table.set_rows([])
            if self._lines_frame is not None:
                self._lines_frame.configure(text="ko_narration_lines (set 선택)")
            self._new_line_btn.configure(state=tk.DISABLED)
            self._sets_table.clear_selection()
        finally:
            self._syncing_selection = False
        self._on_child_dirty()
        self._on_status(f"sets 로드: {path}")

    def _load_lines(self, path: Path) -> None:
        path = Path(path)
        raw_rows = read_ko_line_rows_from_excel(path)
        merged = ko_line_rows_for_editor(raw_rows)
        self._lines_store.load(path)
        self._lines_store.set_rows(merged)
        self._all_line_rows = list(merged)
        if rows_need_ko_line_merge(raw_rows):
            self._on_status(
                f"lines 로드: {path} (legacy seq 행 → id당 1행, text \\n 병합)"
            )
        else:
            self._on_status(f"lines 로드: {path}")
        self._refresh_lines_view()
        self._on_child_dirty()

    def _open_sets_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="ko_narration_sets 열기",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All", "*.*")],
            initialdir=str(DEFAULT_KO_NARRATION_SETS_EXCEL.parent),
            initialfile=DEFAULT_KO_NARRATION_SETS_EXCEL.name,
        )
        if path:
            self._load_sets(Path(path))

    def _open_lines_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="ko_narration_lines 열기",
            filetypes=[("Excel", "*.xlsx *.xls"), ("All", "*.*")],
            initialdir=str(DEFAULT_KO_NARRATION_LINES_EXCEL.parent),
            initialfile=DEFAULT_KO_NARRATION_LINES_EXCEL.name,
        )
        if path:
            self._load_lines(Path(path))

    def open_file_dialog(self) -> None:
        self._open_sets_dialog()

    def _flush_sets(self) -> None:
        self._sets_store.set_rows(self._all_set_rows)

    def _flush_lines(self) -> None:
        self._all_line_rows = ko_line_rows_for_editor(self._all_line_rows)
        self._lines_store.set_rows(self._all_line_rows)

    def flush_all(self) -> None:
        self._flush_sets()
        self._flush_lines()

    def _save_sets(self) -> bool:
        if self._sets_store.path is None:
            return self._save_sets_as()
        self._flush_sets()
        try:
            self._sets_store.save()
            self._on_child_dirty()
            invalidate_global_table_cache(ko_sets=True)
            return True
        except OSError as ex:
            messagebox.showerror("sets 저장 실패", str(ex), parent=self)
            return False

    def _save_lines(self) -> bool:
        if (
            self._lines_store.path is None
            and not self._all_line_rows
            and not self._lines_store.dirty
        ):
            return True
        if self._lines_store.path is None:
            return self._save_lines_as()
        self._flush_lines()
        try:
            self._lines_store.save()
            self._on_child_dirty()
            invalidate_global_table_cache(ko_lines=True)
            return True
        except OSError as ex:
            messagebox.showerror("lines 저장 실패", str(ex), parent=self)
            return False

    def _write_csv_paths(self) -> list[str]:
        if self._sets_store.path is None or self._lines_store.path is None:
            raise ValueError("sets·lines Excel 경로가 필요합니다.")
        sets_out = export_ko_narration_sets_csv(
            self._sets_store.path, DEFAULT_KO_NARRATION_SETS_CSV
        )
        lines_out = export_ko_narration_lines_csv(
            self._lines_store.path, DEFAULT_KO_NARRATION_LINES_CSV
        )
        return [sets_out, lines_out]

    def _export_csv(self, *, show_dialog: bool) -> bool:
        if self._sets_store.path is None:
            if show_dialog:
                messagebox.showinfo(
                    "TTS CSV",
                    "ko_narration_sets 파일을 먼저 열거나 저장하세요.",
                    parent=self,
                )
            return False
        if self._lines_store.path is None:
            if show_dialog:
                messagebox.showinfo(
                    "TTS CSV",
                    "ko_narration_lines 파일을 먼저 열거나 저장하세요.",
                    parent=self,
                )
            return False
        return export_csv_paths(
            self,
            self._on_status,
            self._write_csv_paths,
            show_dialog=show_dialog,
            dialog_title="TTS CSV",
            status_prefix="저장·CSV" if not show_dialog else "CSV",
        )

    def save(self) -> bool:
        ok_sets = self._save_sets()
        ok_lines = self._save_lines()
        if ok_sets and ok_lines:
            self._on_status("sets·lines 저장 완료")
            self._export_csv(show_dialog=False)
        return ok_sets and ok_lines

    def _save_sets_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            title="ko_narration_sets 저장",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=DEFAULT_KO_NARRATION_SETS_EXCEL.name,
            initialdir=str(DEFAULT_KO_NARRATION_SETS_EXCEL.parent),
        )
        if not path:
            return False
        self._flush_sets()
        try:
            self._sets_store.save(path)
            self._on_child_dirty()
            invalidate_global_table_cache(ko_sets=True)
            return True
        except OSError as ex:
            messagebox.showerror("sets 저장 실패", str(ex), parent=self)
            return False

    def _save_lines_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            title="ko_narration_lines 저장",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=DEFAULT_KO_NARRATION_LINES_EXCEL.name,
            initialdir=str(DEFAULT_KO_NARRATION_LINES_EXCEL.parent),
        )
        if not path:
            return False
        self._flush_lines()
        try:
            self._lines_store.save(path)
            self._on_child_dirty()
            invalidate_global_table_cache(ko_lines=True)
            return True
        except OSError as ex:
            messagebox.showerror("lines 저장 실패", str(ex), parent=self)
            return False

    def save_as(self) -> bool:
        ok_sets = self._save_sets_as()
        ok_lines = self._save_lines_as()
        if ok_sets and ok_lines:
            self._on_status("sets·lines 다른 이름으로 저장 완료")
            self._export_csv(show_dialog=False)
        return ok_sets and ok_lines

    def export_current_csv(self) -> None:
        self.export_all_csv()

    def export_all_csv(self) -> None:
        self.flush_all()
        if self.is_dirty:
            if not messagebox.askyesno(
                "TTS CSV",
                "저장되지 않은 변경이 있습니다. 저장 후 CSV를 생성할까요?",
                parent=self,
            ):
                return
            if not self.save():
                return
            return
        self._export_csv(show_dialog=True)

    def _set_title_for(self, set_id: str) -> str:
        row = find_row_by_id(self._all_set_rows, set_id)
        if row is None:
            return ""
        return (row.get("title") or "").strip()

    def _show_detail_panel(self) -> None:
        self._ensure_detail_ui()
        assert self._lines_frame is not None
        if not self._detail_visible:
            self._paned.add(self._lines_frame, weight=2)
            self._detail_visible = True

    def _hide_detail_panel(self) -> None:
        if self._detail_visible and self._lines_frame is not None:
            self._paned.forget(self._lines_frame)
            self._detail_visible = False

    def _clear_set_selection(self) -> None:
        self._selected_set_id = ""
        if self._lines_table is not None:
            self._lines_table.set_rows([])
        if self._lines_frame is not None:
            self._lines_frame.configure(text="ko_narration_lines (set 선택)")
        self._new_line_btn.configure(state=tk.DISABLED)
        self._syncing_selection = True
        try:
            self._sets_table.clear_selection()
        finally:
            self._syncing_selection = False

    def _apply_set_selection(
        self,
        set_id: str,
        *,
        skip_sync: str | None = None,
    ) -> None:
        sid = (set_id or "").strip()
        if not sid:
            self._clear_set_selection()
            return
        self._selected_set_id = sid
        self._new_line_btn.configure(state=tk.NORMAL)
        self._syncing_selection = True
        try:
            self._show_detail_panel()
            if skip_sync != "sets":
                self._sets_table.select_row_by_id(sid)
        finally:
            self._syncing_selection = False
        self._refresh_lines_view()
        n = len(filter_rows_by_set_id(self._all_line_rows, sid))
        self._on_status(f"set id {sid} 선택 — line {n}건")

    def _refresh_lines_view(self) -> None:
        if self._lines_table is None or self._lines_frame is None:
            return
        if not self._selected_set_id:
            self._lines_table.set_rows([])
            self._lines_frame.configure(text="ko_narration_lines (set 선택)")
            return
        filtered = filter_rows_by_set_id(self._all_line_rows, self._selected_set_id)
        title = self._set_title_for(self._selected_set_id)
        label = f"ko_narration_lines — set_id {self._selected_set_id}"
        if title:
            label += f" · {title}"
        self._lines_frame.configure(text=label)
        self._lines_table.set_rows(filtered)

    def _on_set_selected(self, row: dict[str, str] | None) -> None:
        if self._syncing_selection:
            return
        if row is None:
            if not self._selected_set_id:
                return
            self._clear_set_selection()
            return
        set_id = (row.get("id") or "").strip()
        if ids_equal(set_id, self._selected_set_id):
            return
        self._apply_set_selection(set_id, skip_sync="sets")

    def _run_search(self) -> None:
        kind, value = parse_search_query(self._search_var.get())
        if not value:
            return
        if kind != "id":
            messagebox.showinfo(
                "검색",
                "TTS 모드에서는 set id(숫자)만 검색할 수 있습니다.",
                parent=self,
            )
            return
        row = find_row_by_id(self._all_set_rows, value)
        if row is None:
            self._on_status(f"set id {value} 없음")
            messagebox.showinfo("검색", f"set id {value} 를 찾을 수 없습니다.", parent=self)
            return
        self._apply_set_selection(value)

    def _normalize_ids(self, row: dict[str, str]) -> dict[str, str]:
        out = dict(row)
        for col in ("id", "set_id"):
            if col in out:
                out[col] = normalize_id_display(out.get(col, ""))
        return out

    def _set_existing_ids(self) -> set[str]:
        return {
            (r.get("id") or "").strip()
            for r in self._all_set_rows
            if (r.get("id") or "").strip()
        }

    def _line_existing_ids(self, set_id: str) -> set[str]:
        sid = (set_id or "").strip()
        return {
            (r.get("id") or "").strip()
            for r in self._all_line_rows
            if ids_equal(r.get("set_id", ""), sid) and (r.get("id") or "").strip()
        }

    def _new_set_row(self) -> None:
        defaults = {c: "" for c in KO_NARRATION_SETS_FIELDNAMES}
        defaults["id"] = allocate_next_row_id(self._all_set_rows)
        defaults["tts"] = DEFAULT_KO_NARRATION_TTS_TYPE
        defaults["tts_voice"] = DEFAULT_KO_NARRATION_TTS_VOICE
        self._open_set_editor(defaults, is_new=True, title="새 set 행")

    def _new_line_row(self) -> None:
        if not self._selected_set_id:
            messagebox.showinfo(
                "line 새로 만들기",
                "먼저 set id를 선택하세요 (위 sets 표).",
                parent=self,
            )
            return
        defaults = {c: "" for c in KO_NARRATION_LINES_FIELDNAMES}
        defaults["id"] = allocate_next_ko_line_id(
            self._all_line_rows, self._selected_set_id
        )
        defaults["set_id"] = self._selected_set_id
        self._open_line_editor(defaults, is_new=True, title="새 line 행")

    def _edit_set_row(self, row: dict[str, str]) -> None:
        self._open_set_editor(
            dict(row),
            is_new=False,
            title="set 행 편집",
            original_id=row.get("id", ""),
            original_row=dict(row),
        )

    def _edit_line_row(self, row: dict[str, str]) -> None:
        self._open_line_editor(
            dict(row),
            is_new=False,
            title="line 행 편집",
            original_id=row.get("id", ""),
            original_row=dict(row),
        )

    def _open_set_editor(
        self,
        row: dict[str, str],
        *,
        is_new: bool,
        title: str,
        original_id: str | None = None,
        original_row: dict[str, str] | None = None,
    ) -> None:
        row_snapshot = dict(original_row or row)

        def on_delete() -> bool:
            sid = (original_id or row_snapshot.get("id") or "").strip()
            if not sid:
                messagebox.showwarning("삭제", "id가 없는 행은 삭제할 수 없습니다.", parent=self)
                return False
            title = (row_snapshot.get("title") or "").strip()
            lines = filter_rows_by_set_id(self._all_line_rows, sid)
            detail = f"id={sid}"
            if title:
                detail += f"\ntitle: {title}"
            prompt = f"set 행을 삭제할까요?\n\n{detail}"
            if lines:
                prompt += f"\n\n연결된 line {len(lines)}건도 함께 삭제됩니다."
            if not messagebox.askyesno("set 삭제", prompt, parent=self):
                return False
            idx = find_row_index_by_id(
                self._all_set_rows,
                sid,
                match=row_snapshot,
                fieldnames=KO_NARRATION_SETS_FIELDNAMES,
            )
            if idx is None:
                messagebox.showwarning(
                    "삭제",
                    f"set id {sid} 행을 찾을 수 없습니다.",
                    parent=self,
                )
                return False
            del self._all_set_rows[idx]
            if lines:
                self._all_line_rows = [
                    r
                    for r in self._all_line_rows
                    if not ids_equal(r.get("set_id", ""), sid)
                ]
                self._lines_store.set_rows(self._all_line_rows)
            self._sets_store.set_rows(self._all_set_rows)
            self._sets_table.set_rows(self._all_set_rows)
            if ids_equal(self._selected_set_id, sid):
                self._clear_set_selection()
            else:
                self._refresh_lines_view()
            self._on_child_dirty()
            line_note = f", line {len(lines)}건" if lines else ""
            self._on_status(f"삭제: set id {sid}{line_note}")
            return True

        def on_save(values: dict[str, str], new: bool) -> bool | None:
            values = self._normalize_ids(values)
            if new:
                if find_row_index_by_id(self._all_set_rows, values.get("id", "")) is not None:
                    messagebox.showwarning(
                        "검증",
                        f"id {values.get('id', '')} 가 이미 존재합니다.",
                        parent=self,
                    )
                    return False
                self._all_set_rows.append(values)
            else:
                idx = find_row_index_by_id(
                    self._all_set_rows,
                    original_id or "",
                    match=row_snapshot,
                    fieldnames=KO_NARRATION_SETS_FIELDNAMES,
                )
                if idx is None:
                    messagebox.showwarning(
                        "저장",
                        f"set id {original_id} 행을 찾을 수 없습니다.",
                        parent=self,
                    )
                    return False
                old_id = (original_id or "").strip()
                new_id = (values.get("id") or "").strip()
                self._all_set_rows[idx] = values
                if old_id and new_id and not ids_equal(old_id, new_id):
                    for line in self._all_line_rows:
                        if ids_equal(line.get("set_id", ""), old_id):
                            line["set_id"] = new_id
                    if ids_equal(self._selected_set_id, old_id):
                        self._selected_set_id = new_id
                    self._flush_lines()
            self._sets_store.set_rows(self._all_set_rows)
            self._sets_table.set_rows(self._all_set_rows)
            self._apply_set_selection(values.get("id", ""))
            self._on_child_dirty()
            self._on_status(f"{'추가' if new else '수정'}: set id {values.get('id', '')}")
            return True

        from extra.table_editor.ui.row_editor_dialog import RowEditorDialog

        RowEditorDialog(
            self,
            KO_NARRATION_SETS_FIELDNAMES,
            row,
            title=title,
            is_new=is_new,
            existing_ids=self._set_existing_ids(),
            original_id=original_id,
            on_save=on_save,
            on_delete=None if is_new else on_delete,
        )

    def _open_line_editor(
        self,
        row: dict[str, str],
        *,
        is_new: bool,
        title: str,
        original_id: str | None = None,
        original_row: dict[str, str] | None = None,
    ) -> None:
        row_snapshot = dict(original_row or row)

        def on_delete() -> bool:
            lid = (original_id or row_snapshot.get("id") or "").strip()
            if not lid:
                messagebox.showwarning("삭제", "id가 없는 행은 삭제할 수 없습니다.", parent=self)
                return False
            set_id = (row_snapshot.get("set_id") or "").strip() or self._selected_set_id
            text_preview = (row_snapshot.get("text") or "").strip().replace("\n", " ")[:80]
            detail = f"set_id={set_id}  id={lid}"
            if text_preview:
                detail += f"\ntext: {text_preview}"
            if not messagebox.askyesno("line 삭제", f"line 행을 삭제할까요?\n\n{detail}", parent=self):
                return False
            idx = find_ko_line_row_index(
                self._all_line_rows,
                set_id,
                lid,
                match=row_snapshot,
                fieldnames=KO_NARRATION_LINES_FIELDNAMES,
            )
            if idx is None:
                messagebox.showwarning(
                    "삭제",
                    f"line id {lid} (set {set_id}) 행을 찾을 수 없습니다.",
                    parent=self,
                )
                return False
            del self._all_line_rows[idx]
            self._lines_store.set_rows(self._all_line_rows)
            self._refresh_lines_view()
            self._on_child_dirty()
            self._on_status(f"삭제: line id {lid} (set {set_id})")
            return True

        def on_save(values: dict[str, str], new: bool) -> bool | None:
            values = self._normalize_ids(values)
            set_id = (values.get("set_id") or "").strip() or self._selected_set_id
            if not (values.get("set_id") or "").strip() and self._selected_set_id:
                values["set_id"] = self._selected_set_id
            if not (values.get("text") or "").strip():
                messagebox.showwarning("검증", "text를 입력하세요.", parent=self)
                return False
            if new:
                if ko_line_id_exists(self._all_line_rows, set_id, values.get("id", "")):
                    messagebox.showwarning(
                        "검증",
                        f"set {set_id} 에 id {values.get('id', '')} 가 이미 있습니다.",
                        parent=self,
                    )
                    return False
                self._all_line_rows.append(values)
            else:
                edit_set_id = (row_snapshot.get("set_id") or "").strip() or set_id
                idx = find_ko_line_row_index(
                    self._all_line_rows,
                    edit_set_id,
                    original_id or "",
                    match=row_snapshot,
                    fieldnames=KO_NARRATION_LINES_FIELDNAMES,
                )
                if idx is None:
                    messagebox.showwarning(
                        "저장",
                        f"line id {original_id} (set {edit_set_id}) 행을 찾을 수 없습니다.",
                        parent=self,
                    )
                    return False
                self._all_line_rows[idx] = values
            self._lines_store.set_rows(self._all_line_rows)
            self._refresh_lines_view()
            self._on_child_dirty()
            self._on_status(f"{'추가' if new else '수정'}: line id {values.get('id', '')}")
            return True

        from extra.table_editor.ui.row_editor_dialog import RowEditorDialog

        RowEditorDialog(
            self,
            KO_NARRATION_LINES_FIELDNAMES,
            row,
            title=title,
            is_new=is_new,
            existing_ids=self._line_existing_ids(
                (row.get("set_id") or "").strip() or self._selected_set_id
            ),
            original_id=original_id,
            on_save=on_save,
            on_delete=None if is_new else on_delete,
        )
