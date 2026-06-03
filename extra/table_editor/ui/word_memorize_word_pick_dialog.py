"""단어 외우기 배치 — word id 검색·선택 (한국어 뜻 · 영어 뜻)."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from extra.table_editor.services.word_lookup import search_words
from extra.table_editor.ui.window_placement import schedule_center_toplevel_on_parent


class WordMemorizeWordPickDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        on_select: Callable[[str], None],
        *,
        exclude_ids: set[str] | frozenset[str] | None = None,
        title: str = "word 추가",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self._on_select = on_select
        self._exclude_ids = {
            (wid or "").strip() for wid in (exclude_ids or ()) if (wid or "").strip()
        }
        self._matches: list[dict[str, str]] = []

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=(
                "word id · 한자 · 종류(type) 입력 → [검색] 또는 Enter → [선택]. "
                "종류(예: 과일)는 해당 단어 목록을 보여줍니다."
            ),
            foreground="#555",
        ).pack(anchor="w", pady=(0, 8))

        search_row = ttk.Frame(frame)
        search_row.pack(fill=tk.X, pady=(0, 8))
        self._search_var = tk.StringVar()
        entry = ttk.Entry(search_row, textvariable=self._search_var, width=36)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda _e: self._on_entry_return())
        entry.focus_set()
        ttk.Button(search_row, text="검색", command=self._run_search, width=8).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        columns = ("id", "word", "type", "meaning")
        self._tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=10,
            selectmode="browse",
        )
        self._tree.heading("id", text="id")
        self._tree.heading("word", text="한자")
        self._tree.heading("type", text="종류")
        self._tree.heading("meaning", text="뜻")
        self._tree.column("id", width=56, minwidth=48, stretch=False)
        self._tree.column("word", width=88, minwidth=56, stretch=False)
        self._tree.column("type", width=56, minwidth=40, stretch=False)
        self._tree.column("meaning", width=120, minwidth=56, stretch=True)

        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-Button-1>", lambda _e: self._confirm())
        self._tree.bind("<Return>", lambda _e: self._confirm())

        detail = ttk.LabelFrame(frame, text="뜻")
        detail.pack(fill=tk.X, pady=(0, 8))

        self._meaning_var = tk.StringVar(value="—")
        self._en_meaning_var = tk.StringVar(value="—")
        ttk.Label(detail, text="한국어:", width=8).grid(
            row=0, column=0, sticky="nw", padx=8, pady=4
        )
        ttk.Label(
            detail,
            textvariable=self._meaning_var,
            wraplength=420,
            foreground="#222",
        ).grid(row=0, column=1, sticky="w", padx=(0, 8), pady=4)
        ttk.Label(detail, text="영어:", width=8).grid(
            row=1, column=0, sticky="nw", padx=8, pady=(0, 8)
        )
        ttk.Label(
            detail,
            textvariable=self._en_meaning_var,
            wraplength=420,
            foreground="#333",
        ).grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 8))

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="선택", command=self._confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="취소", command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.bind("<Escape>", lambda _e: self.destroy())
        schedule_center_toplevel_on_parent(self, parent, width=520, height=520)

    def _run_search(self) -> None:
        query = self._search_var.get()
        all_matches = search_words(query)
        matches = [
            row
            for row in all_matches
            if (row.get("id") or "").strip() not in self._exclude_ids
        ]
        self._matches = matches
        self._meaning_var.set("—")
        self._en_meaning_var.set("—")

        for item in self._tree.get_children():
            self._tree.delete(item)

        if not matches:
            if (query or "").strip():
                if all_matches:
                    messagebox.showinfo(
                        "단어 검색",
                        f"'{query.strip()}' 검색 결과가 모두 이미 배치에 추가된 단어입니다.",
                        parent=self,
                    )
                else:
                    messagebox.showinfo(
                        "단어 검색",
                        f"'{query.strip()}' 와 일치하는 id·한자·종류가 없습니다.",
                        parent=self,
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
                    row.get("type", ""),
                    row.get("meaning", ""),
                ),
            )

        first = str(0)
        self._tree.selection_set(first)
        self._tree.focus(first)
        self._tree.see(first)
        self._show_meanings(matches[0])
        self.update_idletasks()

    def _on_entry_return(self) -> None:
        if self._matches:
            self._confirm()
        else:
            self._run_search()
            if len(self._matches) == 1:
                self._confirm()

    def _selected_match(self) -> dict[str, str] | None:
        if not self._matches:
            return None
        sel = self._tree.selection()
        if sel:
            try:
                idx = int(sel[0])
            except ValueError:
                idx = -1
            if 0 <= idx < len(self._matches):
                return self._matches[idx]
        if len(self._matches) == 1:
            return self._matches[0]
        return None

    def _on_tree_select(self, _event: tk.Event | None = None) -> None:
        sel = self._tree.selection()
        if not sel:
            self._meaning_var.set("—")
            self._en_meaning_var.set("—")
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._matches):
            self._show_meanings(self._matches[idx])

    def _show_meanings(self, row: dict[str, str]) -> None:
        meaning = (row.get("meaning") or "").strip()
        en = (row.get("en_meaning") or "").strip()
        sheet = (row.get("sheet") or "").strip()
        prefix = f"[{sheet}] " if sheet else ""
        self._meaning_var.set(prefix + meaning if meaning else "—")
        self._en_meaning_var.set(en if en else "—")

    def _confirm(self) -> None:
        query = (self._search_var.get() or "").strip()
        if not self._matches and query:
            self._run_search()
        row = self._selected_match()
        if row is None:
            if not query:
                messagebox.showinfo(
                    "검색 필요",
                    "word id · 한자 · 종류를 입력한 뒤 [검색] 또는 Enter를 누르세요.",
                    parent=self,
                )
            elif self._matches:
                messagebox.showinfo(
                    "선택 필요",
                    "목록에서 단어를 선택한 뒤 [선택]을 누르세요.",
                    parent=self,
                )
            return
        word_id = (row.get("id") or "").strip()
        if not word_id:
            messagebox.showwarning(
                "id 없음",
                "선택한 항목에 word id가 없습니다.",
                parent=self,
            )
            return
        self._on_select(word_id)
        self.destroy()
