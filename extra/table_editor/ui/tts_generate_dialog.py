"""TTS 생성 — 종류 선택 후 topic/id 입력."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from extra.table_editor.services.topic_sources import (
    topics_for_conversation_preview,
    topics_for_vocabulary_preview,
)
from extra.table_editor.ui.window_placement import center_toplevel_on_parent

TTS_KINDS: tuple[tuple[str, str], ...] = (
    ("conv", "회화 sub KO TTS"),
    ("vocab", "단어장 KO TTS"),
    ("shorts_conv", "숏츠 회화 TTS"),
    ("shorts_vocab", "숏츠 단어 TTS"),
)

_KIND_LABELS = {key: label for key, label in TTS_KINDS}
_KIND_BY_LABEL = {label: key for key, label in TTS_KINDS}


class TtsGenerateDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, *, initial: str = "") -> None:
        super().__init__(parent)
        self.title("TTS 생성")
        self.transient(parent)
        self.grab_set()
        self.result: tuple[str, str] | None = None
        self._initial = (initial or "").strip()

        ttk.Label(
            self,
            text="TTS 종류를 선택하고 필요한 값을 입력하세요.",
            wraplength=380,
        ).pack(padx=16, pady=(14, 8), anchor="w")

        kind_row = ttk.Frame(self)
        kind_row.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Label(kind_row, text="종류:", width=8).pack(side=tk.LEFT)
        self._kind_var = tk.StringVar(value=_KIND_LABELS["conv"])
        kind_combo = ttk.Combobox(
            kind_row,
            textvariable=self._kind_var,
            values=[label for _, label in TTS_KINDS],
            state="readonly",
            width=32,
        )
        kind_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        kind_combo.bind("<<ComboboxSelected>>", lambda _e: self._rebuild_input())

        self._input_host = ttk.Frame(self)
        self._input_host.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._input_var = tk.StringVar(value=self._initial)
        self._input_widget: ttk.Combobox | ttk.Entry | None = None

        self._rebuild_input()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(4, 14))
        ttk.Button(btn_frame, text="실행", command=self._confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="취소", command=self._cancel).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after_idle(lambda: center_toplevel_on_parent(self, parent))

    def _current_kind(self) -> str:
        return _KIND_BY_LABEL.get(self._kind_var.get(), "conv")

    def _rebuild_input(self) -> None:
        for child in self._input_host.winfo_children():
            child.destroy()

        kind = self._current_kind()
        row = ttk.Frame(self._input_host)
        row.pack(fill=tk.X)

        if kind == "conv":
            ttk.Label(row, text="topic:", width=8).pack(side=tk.LEFT)
            topics = topics_for_conversation_preview()
            prompt = "base_sentences.topic"
        elif kind == "vocab":
            ttk.Label(row, text="topic:", width=8).pack(side=tk.LEFT)
            topics = topics_for_vocabulary_preview()
            prompt = "vocabulary_word_rows.topic"
        elif kind == "shorts_conv":
            ttk.Label(row, text="입력:", width=8).pack(side=tk.LEFT)
            ttk.Label(
                row,
                text="set_id(숫자) 또는 topic",
                foreground="#666",
            ).pack(side=tk.LEFT, padx=(0, 8))
            entry = ttk.Entry(row, textvariable=self._input_var, width=28)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._input_widget = entry
            return
        else:
            ttk.Label(row, text="입력:", width=8).pack(side=tk.LEFT)
            ttk.Label(
                row,
                text="topic 또는 clips id(숫자)",
                foreground="#666",
            ).pack(side=tk.LEFT, padx=(0, 8))
            entry = ttk.Entry(row, textvariable=self._input_var, width=28)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._input_widget = entry
            return

        values = list(topics)
        current = self._initial
        if current and current not in values:
            values = [current, *values]
        if not values:
            ttk.Label(
                self._input_host,
                text=f"{prompt} 목록 없음 — CSV를 확인하세요.",
                foreground="#a60",
                wraplength=360,
            ).pack(anchor="w", pady=(4, 0))
            values = [current] if current else [""]

        combo = ttk.Combobox(
            row,
            textvariable=self._input_var,
            values=values,
            state="readonly",
            width=32,
        )
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if values:
            combo.set(current if current in values else values[0])
        self._input_widget = combo

    def _confirm(self) -> None:
        value = (self._input_var.get() or "").strip()
        if not value:
            messagebox.showwarning("TTS 생성", "값을 입력하세요.", parent=self)
            return
        self.result = (self._current_kind(), value)
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, parent: tk.Misc, *, initial: str = "") -> tuple[str, str] | None:
        dialog = cls(parent, initial=initial)
        parent.wait_window(dialog)
        return dialog.result
