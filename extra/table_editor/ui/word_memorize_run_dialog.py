"""단어 외우기 — 배치 JSON 선택 후 미리보기/녹화."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from extra.table_editor.services.word_memorize_layout import (
    layout_uses_compose,
    load_layout,
)
from extra.table_editor.services.word_memorize_layouts import normalize_layout_filename
from extra.table_editor.ui.window_placement import center_toplevel_on_parent

_WORD_KIND_LABELS: dict[str, str] = {
    "normal": "일반 단어",
    "combo": "조합 단어",
}
_WORD_KIND_BY_LABEL = {v: k for k, v in _WORD_KIND_LABELS.items()}


def _layout_is_combo(path: Path) -> bool:
    try:
        return layout_uses_compose(load_layout(path))
    except Exception:
        return False


_WORD_MEMORIZE_RUN_MODES: tuple[tuple[str, str], ...] = (
    ("debug", "미리보기 (F5 debug)"),
    ("record", "녹화 (record)"),
    ("summary", "정리 (텍스트)"),
)
_MODE_LABELS = {key: label for key, label in _WORD_MEMORIZE_RUN_MODES}
_MODE_BY_LABEL = {label: key for key, label in _WORD_MEMORIZE_RUN_MODES}

_MEANING_LANG_LABELS: dict[str, str] = {
    "ko": "한국어",
    "en": "영어",
    "zh": "중국어",
}
_MEANING_LANG_BY_LABEL = {v: k for k, v in _MEANING_LANG_LABELS.items()}

_QUIZ_MODE_BY_LABEL = {
    "퀴즈 모드 (타일·디졸브)": True,
    "일반 모드 (타일 없음·레이저 선명)": False,
}


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
        self.result: tuple[str, str, str, bool] | None = None

        ttk.Label(
            self,
            text="저장된 배치(JSON)를 고른 뒤 미리보기·녹화·정리를 실행합니다.",
            wraplength=400,
        ).pack(padx=16, pady=(14, 8), anchor="w")

        self._layout_paths = {name: path for name, path in layouts}
        self._names_by_kind: dict[str, list[str]] = {"normal": [], "combo": []}
        for name, path in layouts:
            kind = "combo" if _layout_is_combo(path) else "normal"
            self._names_by_kind[kind].append(name)

        initial = normalize_layout_filename(initial_layout)
        initial_kind = "combo" if initial in self._names_by_kind["combo"] else "normal"

        kind_frame = ttk.LabelFrame(self, text="단어 종류")
        kind_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._kind_var = tk.StringVar(value=_WORD_KIND_LABELS[initial_kind])
        for key in ("combo", "normal"):
            ttk.Radiobutton(
                kind_frame,
                text=_WORD_KIND_LABELS[key],
                variable=self._kind_var,
                value=_WORD_KIND_LABELS[key],
                command=self._on_kind_changed,
            ).pack(side=tk.LEFT, padx=12, pady=6)

        layout_row = ttk.Frame(self)
        layout_row.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Label(layout_row, text="파일명:", width=8).pack(side=tk.LEFT)
        self._layout_var = tk.StringVar()
        self._layout_combo = ttk.Combobox(
            layout_row,
            textvariable=self._layout_var,
            state="readonly",
            width=34,
        )
        self._layout_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._refresh_layout_combo(preferred=initial)

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

        quiz_frame = ttk.LabelFrame(self, text="퀴즈 모드")
        quiz_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._quiz_var = tk.StringVar(value="퀴즈 모드 (타일·디졸브)")
        for label in _QUIZ_MODE_BY_LABEL:
            ttk.Radiobutton(
                quiz_frame,
                text=label,
                variable=self._quiz_var,
                value=label,
            ).pack(anchor="w", padx=12, pady=2)

        mode_frame = ttk.LabelFrame(self, text="실행 방식")
        mode_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._mode_var = tk.StringVar(value=_MODE_LABELS["debug"])
        for _key, label in _WORD_MEMORIZE_RUN_MODES:
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

    def _selected_kind(self) -> str:
        return _WORD_KIND_BY_LABEL.get(self._kind_var.get(), "normal")

    def _on_kind_changed(self) -> None:
        self._refresh_layout_combo()

    def _refresh_layout_combo(self, *, preferred: str = "") -> None:
        names = self._names_by_kind[self._selected_kind()]
        values = names if names else [""]
        self._layout_combo.configure(
            values=values, state="readonly" if names else "disabled"
        )
        if preferred in names:
            self._layout_var.set(preferred)
        elif names:
            self._layout_var.set(names[0])
        else:
            self._layout_var.set("")

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
        quiz_mode = _QUIZ_MODE_BY_LABEL.get(self._quiz_var.get(), True)
        self.result = (mode, str(path), meaning_lang, quiz_mode)
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
    ) -> tuple[str, str, str, bool] | None:
        dialog = cls(parent, layouts=layouts, initial_layout=initial_layout)
        parent.wait_window(dialog)
        return dialog.result
