"""TTS 언어별 — 생성/건너뛰기·목소리·미리듣기 행."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from extra.table_editor.services.tts_preview import is_tts_preview_playing, play_tts_preview
from extra.table_editor.services.tts_voice_options import GENERATE_LABEL, SKIP_LABEL, TYPE_CHOICES


class LangTtsRow:
    def __init__(
        self,
        parent: ttk.Frame,
        *,
        label: str,
        voices: tuple[str, ...],
        default_voice: str,
        sample_text: str,
        preview_lang: str,
        enabled: bool = True,
        default_generate: bool = True,
    ) -> None:
        self.sample_text = sample_text
        self.preview_lang = preview_lang
        self._enabled = enabled

        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        self._label = ttk.Label(row, text=label, width=12)
        self._label.pack(side=tk.LEFT)

        self.type_var = tk.StringVar(
            value=GENERATE_LABEL if (enabled and default_generate) else SKIP_LABEL
        )
        self._type_combo = ttk.Combobox(
            row,
            textvariable=self.type_var,
            values=list(TYPE_CHOICES),
            state="readonly" if enabled else "disabled",
            width=8,
        )
        self._type_combo.pack(side=tk.LEFT, padx=(0, 6))
        self._type_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_voice_state())

        ttk.Label(row, text="목소리:").pack(side=tk.LEFT, padx=(4, 2))
        self.voice_var = tk.StringVar()
        voice_values = list(voices)
        if default_voice and default_voice not in voice_values:
            voice_values = [default_voice, *voice_values]
        self._voice_combo = ttk.Combobox(
            row,
            textvariable=self.voice_var,
            values=voice_values,
            width=24,
        )
        self._voice_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if default_voice:
            self.voice_var.set(default_voice)

        self._preview_btn = ttk.Button(
            row, text="미리듣기", width=9, command=self._on_preview
        )
        self._preview_btn.pack(side=tk.LEFT, padx=(6, 0))
        self._sync_voice_state()

    def set_enabled(
        self,
        enabled: bool,
        *,
        force_skip: bool = False,
        default_generate: bool = True,
    ) -> None:
        self._enabled = enabled
        state = "readonly" if enabled else "disabled"
        self._type_combo.configure(state=state)
        if not enabled or force_skip:
            self.type_var.set(SKIP_LABEL)
        elif default_generate:
            self.type_var.set(GENERATE_LABEL)
        self._sync_voice_state()

    def set_label(self, text: str) -> None:
        self._label.configure(text=text)

    def should_generate(self) -> bool:
        return self._enabled and self.type_var.get() == GENERATE_LABEL

    def voice(self) -> str:
        return (self.voice_var.get() or "").strip()

    def _sync_voice_state(self) -> None:
        gen = self.should_generate()
        if self._enabled:
            self._voice_combo.configure(state="readonly" if gen else "disabled")
            self._preview_btn.configure(state=tk.NORMAL if gen else tk.DISABLED)
        else:
            self._voice_combo.configure(state=tk.DISABLED)
            self._preview_btn.configure(state=tk.DISABLED)

    def _on_preview(self) -> None:
        if not self.should_generate():
            return
        voice = self.voice()
        if not voice:
            messagebox.showwarning(
                "미리듣기", "목소리를 선택하세요.", parent=self._preview_btn.winfo_toplevel()
            )
            return
        if is_tts_preview_playing():
            messagebox.showinfo(
                "미리듣기",
                "다른 미리듣기가 재생 중입니다. 잠시 후 다시 시도하세요.",
                parent=self._preview_btn.winfo_toplevel(),
            )
            return
        parent = self._preview_btn.winfo_toplevel()
        self._preview_btn.configure(state=tk.DISABLED)

        def _done() -> None:
            parent.after(
                0,
                lambda: self._preview_btn.configure(
                    state=tk.NORMAL if self.should_generate() else tk.DISABLED
                ),
            )

        def _err(ex: BaseException) -> None:
            def _show() -> None:
                self._sync_voice_state()
                messagebox.showerror(
                    "미리듣기",
                    f"TTS 재생에 실패했습니다.\n\n{ex}\n\n"
                    "edge-tts 설치: pip install edge-tts",
                    parent=parent,
                )

            parent.after(0, _show)

        play_tts_preview(
            text=self.sample_text,
            lang=self.preview_lang,
            voice=voice,
            engine="edge",
            on_done=_done,
            on_error=_err,
        )
