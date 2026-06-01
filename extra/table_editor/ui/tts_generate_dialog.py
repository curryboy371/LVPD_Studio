"""TTS 생성 — 종류·topic/배치·한국어/중국어/영어 선택·미리듣기."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from extra.table_editor.services.topic_sources import (
    topics_for_conversation_preview,
    topics_for_shorts_conversation_preview,
    topics_for_shorts_vocabulary_preview,
    topics_for_vocabulary_preview,
)
from extra.table_editor.services.tts_voice_options import (
    DEFAULT_EN_TTS_VOICE,
    EN_EDGE_VOICES,
    KIND_LANG_META,
    KO_EDGE_VOICES,
    PREVIEW_SAMPLE_EN,
    PREVIEW_SAMPLE_KO,
    PREVIEW_SAMPLE_ZH,
    TtsGenerateResult,
    TtsLangOptions,
    ZH_EDGE_VOICES,
)
from extra.table_editor.services.word_memorize_layouts import (
    list_layout_files,
    normalize_layout_filename,
)
from extra.table_editor.ui.tts_lang_row_widget import LangTtsRow
from extra.table_editor.ui.window_placement import center_toplevel_on_parent

TTS_KINDS: tuple[tuple[str, str], ...] = (
    ("conv", "회화 sub KO TTS"),
    ("vocab", "단어장 KO TTS"),
    ("shorts_conv", "숏츠 회화 TTS"),
    ("shorts_vocab", "숏츠 단어 TTS"),
    ("word_memorize", "단어 외우기"),
)

_KIND_LABELS = {key: label for key, label in TTS_KINDS}
_KIND_BY_LABEL = {label: key for key, label in TTS_KINDS}


class TtsGenerateDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        initial: str = "",
        initial_kind: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("TTS 생성")
        self.transient(parent)
        self.grab_set()
        self.result: TtsGenerateResult | None = None
        self._initial = (initial or "").strip()
        self._layout_paths: dict[str, str] = {}
        if initial_kind and initial_kind in _KIND_LABELS:
            self._kind_var = tk.StringVar(value=_KIND_LABELS[initial_kind])
        else:
            self._kind_var = tk.StringVar(value=_KIND_LABELS["conv"])
            self._apply_initial_kind_if_layout_file()

        ttk.Label(
            self,
            text="TTS 종류와 대상을 고른 뒤, 생성할 언어(한국어·중국어·영어)와 목소리를 설정하세요.",
            wraplength=440,
        ).pack(padx=16, pady=(14, 8), anchor="w")

        kind_row = ttk.Frame(self)
        kind_row.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Label(kind_row, text="종류:", width=8).pack(side=tk.LEFT)
        kind_combo = ttk.Combobox(
            kind_row,
            textvariable=self._kind_var,
            values=[label for _, label in TTS_KINDS],
            state="readonly",
            width=32,
        )
        kind_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        kind_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_kind_changed())

        self._input_host = ttk.Frame(self)
        self._input_host.pack(fill=tk.X, padx=16, pady=(0, 4))
        self._input_var = tk.StringVar(value=self._initial)

        self._lang_frame = ttk.LabelFrame(
            self, text="보낼 TTS (종류 · 목소리 · 미리듣기)"
        )
        self._lang_frame.pack(fill=tk.X, padx=16, pady=(4, 4))

        inner = ttk.Frame(self._lang_frame)
        inner.pack(fill=tk.X, padx=8, pady=6)
        self._row_ko = LangTtsRow(
            inner,
            label="한국어",
            voices=KO_EDGE_VOICES,
            default_voice=KO_EDGE_VOICES[0],
            sample_text=PREVIEW_SAMPLE_KO,
            preview_lang="ko",
        )
        self._row_zh = LangTtsRow(
            inner,
            label="중국어",
            voices=ZH_EDGE_VOICES,
            default_voice=ZH_EDGE_VOICES[0],
            sample_text=PREVIEW_SAMPLE_ZH,
            preview_lang="zh",
        )
        self._row_en = LangTtsRow(
            inner,
            label="영어",
            voices=EN_EDGE_VOICES,
            default_voice=DEFAULT_EN_TTS_VOICE,
            sample_text=PREVIEW_SAMPLE_EN,
            preview_lang="en",
        )

        self._hint_var = tk.StringVar()
        ttk.Label(
            self,
            textvariable=self._hint_var,
            foreground="#666",
            wraplength=440,
            font=("Segoe UI", 8),
        ).pack(padx=16, pady=(0, 8), anchor="w")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(4, 14))
        ttk.Button(btn_frame, text="실행", command=self._confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="취소", command=self._cancel).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._on_kind_changed()
        self.after_idle(lambda: center_toplevel_on_parent(self, parent))

    def _apply_initial_kind_if_layout_file(self) -> None:
        norm = normalize_layout_filename(self._initial)
        if not norm:
            return
        for name, _ in list_layout_files():
            if name == norm:
                self._kind_var.set(_KIND_LABELS["word_memorize"])
                return

    def _current_kind(self) -> str:
        return _KIND_BY_LABEL.get(self._kind_var.get(), "conv")

    def _on_kind_changed(self) -> None:
        self._rebuild_input()
        kind = self._current_kind()
        labels, multi = KIND_LANG_META.get(
            kind, (("한국어", "중국어", "영어"), False)
        )
        self._row_ko.set_label(labels[0])
        self._row_zh.set_label(labels[1])
        self._row_en.set_label(labels[2])

        if multi:
            self._row_ko.set_enabled(True, default_generate=True)
            self._row_zh.set_enabled(True, default_generate=True)
            self._row_en.set_enabled(True, default_generate=True)
            self._hint_var.set(
                "단어 외우기: 한국어 뜻(ko_word_*) · 한자(wm_zh_word_*) · 영어(en_word_*). "
                "한자 경로는 words.sound_path 와 별도입니다."
            )
        else:
            self._row_ko.set_enabled(True, default_generate=True)
            self._row_zh.set_enabled(False, force_skip=True)
            self._row_en.set_enabled(False, force_skip=True)
            self._hint_var.set(
                "이 TTS 종류는 한국어만 생성합니다. 중국어·영어는 단어 외우기에서 선택하세요."
            )

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
            ttk.Label(row, text="topic:", width=8).pack(side=tk.LEFT)
            topics = topics_for_shorts_conversation_preview()
            prompt = "shorts_conversation_clips.topic"
        elif kind == "shorts_vocab":
            ttk.Label(row, text="topic:", width=8).pack(side=tk.LEFT)
            topics = topics_for_shorts_vocabulary_preview()
            prompt = "shorts_vocabulary_clips.topic"
        elif kind == "word_memorize":
            ttk.Label(row, text="단어 외우기:", width=10).pack(side=tk.LEFT)
            layouts = list_layout_files()
            self._layout_paths = {name: str(path) for name, path in layouts}
            topics = [name for name, _ in layouts]
            prompt = "resource/table/word_memorize_layouts"
        else:
            return

        values = list(topics)
        current = self._initial
        if kind == "word_memorize":
            current = normalize_layout_filename(current)
        if current and current not in values:
            values = [current, *values]
        if not values:
            hint = (
                f"{prompt} 목록 없음 — 배치 편집기에서 JSON을 저장하세요."
                if kind == "word_memorize"
                else f"{prompt} 목록 없음 — CSV를 확인하세요."
            )
            ttk.Label(
                self._input_host,
                text=hint,
                foreground="#a60",
                wraplength=400,
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

    def _collect_lang(self) -> TtsLangOptions:
        return TtsLangOptions(
            gen_ko=self._row_ko.should_generate(),
            gen_zh=self._row_zh.should_generate(),
            gen_en=self._row_en.should_generate(),
            voice_ko=self._row_ko.voice(),
            voice_zh=self._row_zh.voice(),
            voice_en=self._row_en.voice(),
        )

    def _confirm(self) -> None:
        kind = self._current_kind()
        value = (self._input_var.get() or "").strip()
        if kind != "word_memorize" and not value:
            messagebox.showwarning("TTS 생성", "값을 입력하세요.", parent=self)
            return

        lang = self._collect_lang()
        if not (lang.gen_ko or lang.gen_zh or lang.gen_en):
            messagebox.showwarning(
                "TTS 생성",
                "한국어·중국어·영어 중 최소 한 가지는 「생성」으로 선택하세요.",
                parent=self,
            )
            return

        _, multi = KIND_LANG_META.get(kind, (("", "", ""), False))
        if not multi and not lang.gen_ko:
            messagebox.showwarning(
                "TTS 생성",
                "이 종류는 한국어 TTS만 지원합니다. 한국어를 「생성」으로 선택하세요.",
                parent=self,
            )
            return
        if not multi and (lang.gen_zh or lang.gen_en):
            messagebox.showwarning(
                "TTS 생성",
                "이 종류는 한국어만 생성됩니다. 중국어·영어는 단어 외우기를 사용하세요.",
                parent=self,
            )
            return

        layout_path = ""
        if kind == "word_memorize":
            layout_path = self._layout_paths.get(value, "")
            if not layout_path:
                messagebox.showwarning(
                    "TTS 생성", "JSON 파일명을 선택하세요.", parent=self
                )
                return

        self.result = TtsGenerateResult(
            kind=kind,
            value=value,
            lang=lang,
            layout_path=layout_path,
        )
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    @classmethod
    def ask(
        cls,
        parent: tk.Misc,
        *,
        initial: str = "",
        initial_kind: str | None = None,
    ) -> TtsGenerateResult | None:
        dialog = cls(parent, initial=initial, initial_kind=initial_kind)
        parent.wait_window(dialog)
        return dialog.result
