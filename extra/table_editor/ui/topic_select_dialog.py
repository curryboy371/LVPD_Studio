"""미리보기 실행 전 topic 선택."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class TopicSelectDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        prompt: str,
        topics: list[str],
        initial: str = "",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.result: str | None = None

        ttk.Label(self, text=prompt, wraplength=360).pack(
            padx=16, pady=(14, 8), anchor="w"
        )

        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Label(row, text="topic:", width=8).pack(side=tk.LEFT)
        self._topic_var = tk.StringVar()
        values = list(topics)
        current = (initial or "").strip()
        if current and current not in values:
            values = [current, *values]
        if not values:
            values = [current] if current else [""]
        combo = ttk.Combobox(
            row,
            textvariable=self._topic_var,
            values=values,
            state="readonly",
            width=32,
        )
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        combo.set(current if current in values else values[0])

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(4, 14))
        ttk.Button(btn_frame, text="실행", command=self._confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="취소", command=self._cancel).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _confirm(self) -> None:
        value = (self._topic_var.get() or "").strip()
        if not value:
            return
        self.result = value
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    @classmethod
    def ask(
        cls,
        parent: tk.Misc,
        *,
        title: str,
        prompt: str,
        topics: list[str],
        initial: str = "",
    ) -> str | None:
        dialog = cls(
            parent,
            title=title,
            prompt=prompt,
            topics=topics,
            initial=initial,
        )
        parent.wait_window(dialog)
        return dialog.result
