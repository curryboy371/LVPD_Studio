"""단어 외우기 — 배치 JSON 선택 후 미리보기/녹화."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from extra.table_editor.ui.studio_run_dialog import (
    _MODE_BY_LABEL,
    _MODE_LABELS,
    _RUN_MODES,
)
from extra.table_editor.services.word_memorize_layouts import normalize_layout_filename
from extra.table_editor.ui.window_placement import center_toplevel_on_parent

_MEANING_LANG_LABELS: dict[str, str] = {
    "ko": "한국어",
    "en": "영어",
    "zh": "중국어",
}
_MEANING_LANG_BY_LABEL = {v: k for k, v in _MEANING_LANG_LABELS.items()}


class WordMemorizeRunDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        layouts: list[tuple[str, Path]],
        initial_layout: str = "",
    ) -> None:
        super().__init__(parent)
        self.title("단어 외우기")
        self.transient(parent)
        self.grab_set()
        self.result: tuple[str, str, str] | None = None

        ttk.Label(
            self,
            text="저장된 배치(JSON)를 고른 뒤 미리보기 또는 녹화를 실행합니다.",
            wraplength=400,
        ).pack(padx=16, pady=(14, 8), anchor="w")

        layout_row = ttk.Frame(self)
        layout_row.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Label(layout_row, text="파일명:", width=8).pack(side=tk.LEFT)
        self._layout_var = tk.StringVar()
        labels = [name for name, _ in layouts]
        if not labels:
            labels = [""]
        combo = ttk.Combobox(
            layout_row,
            textvariable=self._layout_var,
            values=labels,
            state="readonly" if layouts else "disabled",
            width=34,
        )
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        initial = normalize_layout_filename(initial_layout)
        if initial in labels:
            combo.set(initial)
        elif labels and labels[0]:
            combo.set(labels[0])

        self._layout_paths = {name: path for name, path in layouts}

        lang_frame = ttk.LabelFrame(self, text="언어 (카드 뜻 · TTS 순서)")
        lang_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._lang_var = tk.StringVar(value=_MEANING_LANG_LABELS["ko"])
        for key in ("ko", "en", "zh"):
            ttk.Radiobutton(
                lang_frame,
                text=_MEANING_LANG_LABELS[key],
                variable=self._lang_var,
                value=_MEANING_LANG_LABELS[key],
            ).pack(side=tk.LEFT, padx=12, pady=6)

        mode_frame = ttk.LabelFrame(self, text="실행 방식")
        mode_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._mode_var = tk.StringVar(value=_MODE_LABELS["debug"])
        for _key, label in _RUN_MODES:
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
        name = (self._layout_var.get() or "").strip()
        path = self._layout_paths.get(name)
        if not path or not path.is_file():
            messagebox.showwarning(
                "실행",
                "JSON 파일명을 선택하세요.\n"
                "resource/table/word_memorize_layouts/ 에 저장했는지 확인하세요.",
                parent=self,
            )
            return
        mode = _MODE_BY_LABEL.get(self._mode_var.get(), "debug")
        meaning_lang = _MEANING_LANG_BY_LABEL.get(self._lang_var.get(), "ko")
        self.result = (mode, str(path), meaning_lang)
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    @classmethod
    def ask(
        cls,
        parent: tk.Misc,
        *,
        layouts: list[tuple[str, Path]],
        initial_layout: str = "",
    ) -> tuple[str, str, str] | None:
        dialog = cls(parent, layouts=layouts, initial_layout=initial_layout)
        parent.wait_window(dialog)
        return dialog.result
