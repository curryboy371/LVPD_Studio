"""Treeview grid for table rows."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from extra.table_editor.services.search import ids_equal, sort_rows_by_id


class TablePanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        fieldnames: list[str],
        *,
        display_columns: list[str] | None = None,
        computed_columns: dict[str, Callable[[dict[str, str]], str]] | None = None,
        on_double_click: Callable[[dict[str, str]], None] | None = None,
        on_select: Callable[[dict[str, str] | None], None] | None = None,
        row_sort: Callable[[list[dict[str, str]]], list[dict[str, str]]] | None = None,
    ) -> None:
        super().__init__(master)
        self._fieldnames = list(fieldnames)
        self._display_columns = list(display_columns) if display_columns else None
        self._computed_columns = dict(computed_columns or {})
        self._on_double_click = on_double_click
        self._on_select = on_select
        self._row_sort = row_sort
        self._rows: list[dict[str, str]] = []
        self._iid_to_index: dict[str, int] = {}
        self._suppress_select = 0

        self._build_tree()

    def _notify_select_enabled(self) -> bool:
        return self._suppress_select <= 0

    def _visible_columns(self) -> list[str]:
        if self._display_columns is not None:
            return list(self._display_columns)
        return self._fieldnames[:6] if len(self._fieldnames) > 6 else list(self._fieldnames)

    def _cell_value(self, row: dict[str, str], col: str) -> str:
        if col in self._computed_columns:
            return self._computed_columns[col](row)
        return row.get(col, "")

    def _build_tree(self) -> None:
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        display_cols = self._visible_columns()
        self._tree = ttk.Treeview(
            container,
            columns=display_cols,
            show="headings",
            selectmode="browse",
        )
        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        for col in display_cols:
            self._tree.heading(col, text=col)
            width = (
                160
                if col in (
                    "word",
                    "raw_sentence",
                    "meaning",
                    "translation",
                    "완성형",
                    "alt_translation",
                    "text",
                    "한자",
                    "뜻",
                    "desc",
                )
                else 72
            )
            self._tree.column(col, width=width, minwidth=48, stretch=True)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        if self._on_double_click:
            self._tree.bind("<Double-1>", self._handle_double_click)
        if self._on_select:
            self._tree.bind("<<TreeviewSelect>>", self._handle_select)

    def set_rows(self, rows: list[dict[str, str]]) -> None:
        ordered = list(rows)
        if self._row_sort is not None:
            ordered = self._row_sort(ordered)
        else:
            ordered = sort_rows_by_id(ordered)
        self._rows = ordered
        self._refresh_tree()

    def get_rows(self) -> list[dict[str, str]]:
        return list(self._rows)

    def get_selected_row(self) -> dict[str, str] | None:
        sel = self._tree.selection()
        if not sel:
            return None
        idx = self._iid_to_index.get(sel[0])
        if idx is None or idx < 0 or idx >= len(self._rows):
            return None
        return dict(self._rows[idx])

    def select_row_by_id(self, row_id: str) -> bool:
        target = row_id.strip()
        children = self._tree.get_children()
        for i, row in enumerate(self._rows):
            if ids_equal(row.get("id", ""), target):
                if i < len(children):
                    iid = children[i]
                    self._suppress_select += 1
                    try:
                        self._tree.selection_set(iid)
                        self._tree.focus(iid)
                        self._tree.see(iid)
                    finally:
                        self._suppress_select -= 1
                return True
        return False

    def scroll_to_row(
        self,
        predicate: Callable[[dict[str, str]], bool],
        *,
        select: bool = True,
    ) -> bool:
        children = self._tree.get_children()
        for i, row in enumerate(self._rows):
            if not predicate(row):
                continue
            if i >= len(children):
                return False
            iid = children[i]
            if select:
                self._suppress_select += 1
                try:
                    self._tree.selection_set(iid)
                    self._tree.focus(iid)
                finally:
                    self._suppress_select -= 1
            self._tree.see(iid)
            return True
        return False

    def _refresh_tree(self) -> None:
        self._suppress_select += 1
        try:
            self._tree.delete(*self._tree.get_children())
            self._iid_to_index.clear()
            display_cols = self._visible_columns()
            for i, row in enumerate(self._rows):
                values = [self._cell_value(row, c) for c in display_cols]
                iid = self._tree.insert("", tk.END, values=values)
                self._iid_to_index[iid] = i
        finally:
            self._suppress_select -= 1

    def _handle_double_click(self, _event: tk.Event) -> None:
        row = self.get_selected_row()
        if row and self._on_double_click:
            self._on_double_click(row)

    def _handle_select(self, _event: tk.Event) -> None:
        if not self._notify_select_enabled():
            return
        if self._on_select:
            self._on_select(self.get_selected_row())

    def clear_selection(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        self._suppress_select += 1
        try:
            self._tree.selection_remove(sel)
        finally:
            self._suppress_select -= 1
        if self._on_select and self._notify_select_enabled():
            self._on_select(None)

    def update_row(self, row: dict[str, str], *, original_id: str | None = None) -> None:
        oid = (original_id or row.get("id", "")).strip()
        for i, existing in enumerate(self._rows):
            if ids_equal(existing.get("id", ""), oid):
                self._rows[i] = dict(row)
                self._refresh_tree()
                self.select_row_by_id(row.get("id", ""))
                return
        self._rows.append(dict(row))
        self._refresh_tree()
        self.select_row_by_id(row.get("id", ""))

    def existing_ids(self) -> set[str]:
        return {
            (r.get("id") or "").strip()
            for r in self._rows
            if (r.get("id") or "").strip()
        }

    def bind_tree(self, sequence: str, callback: Callable[[], None]) -> None:
        self._tree.bind(sequence, lambda _e: callback())
