"""단어 외우기 — words.xlsx 시트·품사에서 보관함으로 가져오기."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from extra.table_editor.config import POS_FILTER_ALL
from extra.table_editor.services.word_sheet_browser import (
    clear_word_sheet_browser_cache,
    default_words_sheet,
    get_pos_values,
    get_sheet_names,
    get_type_values,
    query_words,
)
from extra.table_editor.ui.window_placement import schedule_center_toplevel_on_parent


class WordMemorizeVocabImportDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        exclude_ids: set[str],
        on_import: Callable[[list[str]], None],
    ) -> None:
        super().__init__(parent)
        self.title("단어장에서 가져오기")
        self.transient(parent)
        self.grab_set()
        self._exclude_ids = set(exclude_ids)
        self._on_import = on_import
        self._rows: list[dict[str, str]] = []

        clear_word_sheet_browser_cache()

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=(
                "시트·품사·종류를 고른 뒤 목록에서 선택합니다. "
                "더블클릭 또는 [가져오기] → 보관함(미표시). "
                "Ctrl·Shift로 복수 선택 가능."
            ),
            foreground="#555",
            wraplength=480,
        ).pack(anchor="w", pady=(0, 8))

        filter_row = ttk.Frame(frame)
        filter_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(filter_row, text="시트:").pack(side=tk.LEFT)
        self._sheet_var = tk.StringVar()
        sheets = get_sheet_names()
        self._sheet_combo = ttk.Combobox(
            filter_row,
            textvariable=self._sheet_var,
            values=sheets,
            state="readonly",
            width=14,
        )
        self._sheet_combo.pack(side=tk.LEFT, padx=(4, 12))
        self._sheet_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_sheet_changed())

        ttk.Label(filter_row, text="품사:").pack(side=tk.LEFT)
        self._pos_var = tk.StringVar(value=POS_FILTER_ALL)
        self._pos_combo = ttk.Combobox(
            filter_row,
            textvariable=self._pos_var,
            state="readonly",
            width=12,
        )
        self._pos_combo.pack(side=tk.LEFT, padx=(4, 12))
        self._pos_combo.bind("<<ComboboxSelected>>", lambda _e: self._reload_list())

        ttk.Label(filter_row, text="종류:").pack(side=tk.LEFT)
        self._type_var = tk.StringVar(value=POS_FILTER_ALL)
        self._type_combo = ttk.Combobox(
            filter_row,
            textvariable=self._type_var,
            state="readonly",
            width=12,
        )
        self._type_combo.pack(side=tk.LEFT, padx=4)
        self._type_combo.bind("<<ComboboxSelected>>", lambda _e: self._reload_list())

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self._list = tk.Listbox(
            list_frame,
            height=16,
            exportselection=False,
            selectmode=tk.EXTENDED,
            font=("Segoe UI", 11),
        )
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._list.yview)
        self._list.configure(yscrollcommand=scroll.set)
        self._list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._list.bind("<Double-Button-1>", lambda _e: self._import_selected(close=False))

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="가져오기", command=lambda: self._import_selected(close=False)).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(btn_row, text="가져오기 후 닫기", command=lambda: self._import_selected(close=True)).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(btn_row, text="닫기", command=self.destroy).pack(side=tk.RIGHT)

        if sheets:
            self._sheet_var.set(default_words_sheet(sheets))
            self._on_sheet_changed()
        else:
            messagebox.showwarning(
                "단어장 없음",
                "words.xlsx / words.csv 를 찾을 수 없습니다.",
                parent=self,
            )

        self.bind("<Escape>", lambda _e: self.destroy())
        schedule_center_toplevel_on_parent(self, parent, width=520, height=520)

    def _on_sheet_changed(self) -> None:
        sheet = self._sheet_var.get()
        pos_values = get_pos_values(sheet) if sheet else [POS_FILTER_ALL]
        type_values = get_type_values(sheet) if sheet else [POS_FILTER_ALL]
        self._pos_combo["values"] = pos_values
        self._type_combo["values"] = type_values
        if pos_values:
            self._pos_var.set(pos_values[0])
        if type_values:
            self._type_var.set(type_values[0])
        self._reload_list()

    def _reload_list(self) -> None:
        sheet = self._sheet_var.get()
        pos = self._pos_var.get()
        word_type = self._type_var.get()
        self._rows = query_words(sheet, pos, word_type) if sheet else []
        self._list.delete(0, tk.END)
        for row in self._rows:
            wid = row["id"]
            hanzi = row.get("word", "")
            meaning = (row.get("meaning") or "")[:20]
            pos_label = (row.get("pos") or "").strip()
            type_label = (row.get("type") or "").strip()
            tag = "  (이미 추가됨)" if wid in self._exclude_ids else ""
            label = f"{wid:>6}  {hanzi}  {meaning}"
            meta: list[str] = []
            if type_label:
                meta.append(type_label)
            if pos_label and pos_label not in meta:
                meta.append(pos_label)
            if meta:
                label += f"  [{', '.join(meta)}]"
            label += tag
            self._list.insert(tk.END, label)

    def _selected_word_ids(self) -> list[str]:
        ids: list[str] = []
        for idx in self._list.curselection():
            if 0 <= idx < len(self._rows):
                ids.append(self._rows[idx]["id"])
        return ids

    def _import_selected(self, *, close: bool) -> None:
        ids = self._selected_word_ids()
        if not ids:
            messagebox.showinfo(
                "선택 없음",
                "가져올 단어를 목록에서 선택하세요.",
                parent=self,
            )
            return
        new_ids = [wid for wid in ids if wid not in self._exclude_ids]
        skipped = len(ids) - len(new_ids)
        if not new_ids:
            messagebox.showinfo(
                "가져오기",
                "선택한 단어는 이미 보관함 또는 표시 목록에 있습니다.",
                parent=self,
            )
            return
        self._on_import(new_ids)
        self._exclude_ids.update(new_ids)
        self._reload_list()
        if skipped:
            messagebox.showinfo(
                "일부 건너뜀",
                f"{len(new_ids)}개 보관함에 추가, {skipped}개는 이미 있어 건너뜀.",
                parent=self,
            )
        if close:
            self.destroy()
