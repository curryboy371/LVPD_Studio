"""Dialog to pick one id when multiple rows match hanzi search."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class IdPickerDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        matches: list[dict[str, str]],
        on_select: Callable[[dict[str, str]], None],
    ) -> None:
        super().__init__(parent)
        self.title("id 선택")
        self.transient(parent)
        self.grab_set()
        self._on_select = on_select
        self._matches = matches

        ttk.Label(
            self,
            text=f"한자에 일치하는 항목이 {len(matches)}개 있습니다. id를 선택하세요.",
        ).pack(padx=12, pady=(12, 6), anchor="w")

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        self._listbox = tk.Listbox(frame, height=min(12, len(matches) + 1), width=60)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=scroll.set)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for row in matches:
            rid = row.get("id", "")
            word = row.get("word", "")
            meaning = row.get("meaning", "")
            pos = row.get("pos", "")
            label = f"id={rid}  {word}  [{pos}]  {meaning}"
            self._listbox.insert(tk.END, label)

        self._listbox.bind("<Double-Button-1>", lambda _e: self._confirm())
        self._listbox.selection_set(0)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(6, 12))
        ttk.Button(btn_frame, text="확인", command=self._confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _confirm(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = int(sel[0])
        self._on_select(self._matches[idx])
        self.destroy()
