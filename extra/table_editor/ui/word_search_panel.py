"""Sidebar word lookup (id / hanzi) for slot editors."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from extra.table_editor.services.word_lookup import search_words


class WordSearchPanel(ttk.LabelFrame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_pick: Callable[[str], None],
        hint: str = "word id 입력란에 포커스 후 검색·선택",
        pick_button_text: str = "슬롯에 넣기",
    ) -> None:
        super().__init__(master, text="단어 검색")
        self._on_pick = on_pick
        self._matches: list[dict[str, str]] = []

        ttk.Label(
            self,
            text=hint,
            foreground="#555",
            wraplength=240,
        ).pack(fill=tk.X, padx=8, pady=(6, 4))

        search_row = ttk.Frame(self)
        search_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._search_var = tk.StringVar()
        entry = ttk.Entry(search_row, textvariable=self._search_var, width=18)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda _e: self._run_search())
        ttk.Button(search_row, text="검색", command=self._run_search, width=6).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        columns = ("id", "word", "pos")
        self._tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=14,
            selectmode="browse",
        )
        self._tree.heading("id", text="id")
        self._tree.heading("word", text="한자")
        self._tree.heading("pos", text="pos")
        self._tree.column("id", width=52, minwidth=40, stretch=False)
        self._tree.column("word", width=72, minwidth=48, stretch=False)
        self._tree.column("pos", width=56, minwidth=40, stretch=True)

        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._meaning_var = tk.StringVar(value="")
        ttk.Label(
            self,
            textvariable=self._meaning_var,
            wraplength=240,
            foreground="#333",
        ).pack(fill=tk.X, padx=8, pady=(0, 4))

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-Button-1>", lambda _e: self._pick_selected())
        self._tree.bind("<Return>", lambda _e: self._pick_selected())

        btn_row = ttk.Frame(self)
        btn_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(btn_row, text=pick_button_text, command=self._pick_selected).pack(
            side=tk.LEFT
        )

    def _run_search(self) -> None:
        query = self._search_var.get()
        matches = search_words(query)
        self._matches = matches
        self._meaning_var.set("")

        for item in self._tree.get_children():
            self._tree.delete(item)

        if not matches:
            if (query or "").strip():
                messagebox.showinfo(
                    "단어 검색",
                    f"'{query.strip()}' 와 일치하는 단어가 없습니다.",
                    parent=self.winfo_toplevel(),
                )
            return

        for i, row in enumerate(matches):
            self._tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(
                    row.get("id", ""),
                    row.get("word", ""),
                    row.get("pos", ""),
                ),
            )

        first = str(0)
        self._tree.selection_set(first)
        self._tree.focus(first)
        self._tree.see(first)
        self._show_meaning(matches[0])

    def _on_tree_select(self, _event: tk.Event | None = None) -> None:
        sel = self._tree.selection()
        if not sel:
            self._meaning_var.set("")
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._matches):
            self._show_meaning(self._matches[idx])

    def _show_meaning(self, row: dict[str, str]) -> None:
        meaning = (row.get("meaning") or "").strip()
        sheet = (row.get("sheet") or "").strip()
        if sheet:
            text = f"[{sheet}] {meaning}" if meaning else f"[{sheet}]"
        else:
            text = meaning
        self._meaning_var.set(text)

    def _pick_selected(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._matches):
            return
        word_id = (self._matches[idx].get("id") or "").strip()
        if word_id:
            self._on_pick(word_id)
