"""Multi-line field editor: one Entry per line, joined with \\n on save."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def normalize_multiline_input(value: str) -> str:
    """엑셀/CSV의 실제 줄바꿈·문자열 ``\\n`` 을 편집용 줄바꿈으로 통일."""
    if not value:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text and "\\n" in text:
        text = text.replace("\\n", "\n")
    return text


def split_multiline_value(value: str) -> list[str]:
    text = normalize_multiline_input(value)
    if not text:
        return [""]
    return text.split("\n")


class MultilineLinesEditor(ttk.Frame):
    """각 줄: 입력란 · + · − (한 줄). 저장 시 ``\\n`` 으로 합친다."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        label: str,
        initial_value: str = "",
        label_on_top: bool = False,
        hint: str = "",
    ) -> None:
        super().__init__(master)
        self._label = label
        self._line_rows: list[ttk.Frame] = []
        self._entries: list[ttk.Entry] = []

        if label_on_top:
            ttk.Label(self, text=label, wraplength=560).pack(
                fill=tk.X, anchor=tk.W, pady=(0, 2)
            )
            if hint:
                ttk.Label(self, text=hint, foreground="#555", wraplength=560).pack(
                    fill=tk.X, anchor=tk.W, pady=(0, 4)
                )
            self._lines_host = ttk.Frame(self)
            self._lines_host.pack(fill=tk.X, expand=True)
        else:
            ttk.Label(self, text=label, width=18).pack(side=tk.LEFT, anchor=tk.N)
            self._lines_host = ttk.Frame(self)
            self._lines_host.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for line in split_multiline_value(initial_value):
            self._add_line(line, focus=False)
        if not self._entries:
            self._add_line("", focus=False)

    def _add_line(
        self,
        text: str = "",
        *,
        after_row: ttk.Frame | None = None,
        focus: bool = True,
    ) -> ttk.Frame:
        row = ttk.Frame(self._lines_host)
        if after_row is not None and after_row.winfo_exists():
            row.pack(fill=tk.X, pady=2, after=after_row)
        else:
            row.pack(fill=tk.X, pady=2)

        row.columnconfigure(0, weight=1)

        entry = ttk.Entry(row)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        if text:
            entry.insert(0, text)

        btn_frame = ttk.Frame(row)
        btn_frame.grid(row=0, column=1, sticky="e")

        ttk.Button(
            btn_frame,
            text="+",
            width=3,
            command=lambda r=row: self._insert_line_after(r),
        ).pack(side=tk.LEFT, padx=(0, 2))

        ttk.Button(
            btn_frame,
            text="−",
            width=3,
            command=lambda r=row, e=entry: self._remove_line(r, e),
        ).pack(side=tk.LEFT)

        insert_at = (
            self._line_rows.index(after_row) + 1
            if after_row is not None and after_row in self._line_rows
            else len(self._line_rows)
        )
        self._line_rows.insert(insert_at, row)
        self._entries.insert(insert_at, entry)

        if focus:
            entry.focus_set()
            entry.icursor(tk.END)
        return row

    def _insert_line_after(self, row: ttk.Frame) -> None:
        self._add_line("", after_row=row, focus=True)

    def _remove_line(self, row: ttk.Frame, entry: ttk.Entry) -> None:
        if len(self._entries) <= 1:
            entry.delete(0, tk.END)
            return
        if row in self._line_rows:
            self._line_rows.remove(row)
        if entry in self._entries:
            self._entries.remove(entry)
        row.destroy()

    def set_value(self, value: str) -> None:
        for row in self._line_rows:
            row.destroy()
        self._line_rows.clear()
        self._entries.clear()
        for line in split_multiline_value(value):
            self._add_line(line, focus=False)
        if not self._entries:
            self._add_line("", focus=False)

    def get_value(self) -> str:
        lines = [e.get() for e in self._entries]
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)
