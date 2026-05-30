"""스튜디오 실행 — topic 선택 후 미리보기/녹화."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from extra.table_editor.ui.window_placement import center_toplevel_on_parent

_RUN_MODES: tuple[tuple[str, str], ...] = (
    ("debug", "미리보기 (F5 debug)"),
    ("record", "녹화 (record)"),
)
_MODE_LABELS = {key: label for key, label in _RUN_MODES}
_MODE_BY_LABEL = {label: key for key, label in _RUN_MODES}


class StudioRunDialog(tk.Toplevel):
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
        self.result: tuple[str, str] | None = None

        ttk.Label(self, text=prompt, wraplength=380).pack(
            padx=16, pady=(14, 8), anchor="w"
        )

        topic_row = ttk.Frame(self)
        topic_row.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Label(topic_row, text="topic:", width=8).pack(side=tk.LEFT)
        self._topic_var = tk.StringVar()
        values = list(topics)
        current = (initial or "").strip()
        if current and current not in values:
            values = [current, *values]
        if not values:
            values = [current] if current else [""]
        combo = ttk.Combobox(
            topic_row,
            textvariable=self._topic_var,
            values=values,
            state="readonly",
            width=32,
        )
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        combo.set(current if current in values else values[0])

        mode_frame = ttk.LabelFrame(self, text="실행 방식")
        mode_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._mode_var = tk.StringVar(value=_MODE_LABELS["debug"])
        for key, label in _RUN_MODES:
            ttk.Radiobutton(
                mode_frame,
                text=label,
                variable=self._mode_var,
                value=label,
            ).pack(anchor="w", padx=10, pady=2)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(4, 14))
        ttk.Button(btn_frame, text="실행", command=self._confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="취소", command=self._cancel).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after_idle(lambda: center_toplevel_on_parent(self, parent))

    def _confirm(self) -> None:
        topic = (self._topic_var.get() or "").strip()
        if not topic:
            messagebox.showwarning("실행", "topic을 선택하세요.", parent=self)
            return
        mode = _MODE_BY_LABEL.get(self._mode_var.get(), "debug")
        self.result = (mode, topic)
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
    ) -> tuple[str, str] | None:
        dialog = cls(
            parent,
            title=title,
            prompt=prompt,
            topics=topics,
            initial=initial,
        )
        parent.wait_window(dialog)
        return dialog.result
