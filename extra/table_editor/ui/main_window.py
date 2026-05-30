"""Main application window."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Literal

from extra.table_editor.config import APP_TITLE
from extra.table_editor.ui.clipboard_bindings import bind_clipboard_on_class
from extra.table_editor.ui.main_panel import MainPanel

if TYPE_CHECKING:
    from extra.table_editor.ui.conversation_panel import ConversationPanel
    from extra.table_editor.ui.shorts_conversation_clips_panel import (
        ShortsConversationClipsPanel,
    )
    from extra.table_editor.ui.shorts_vocabulary_clips_panel import (
        ShortsVocabularyClipsPanel,
    )
    from extra.table_editor.ui.tts_panel import TtsPanel
    from extra.table_editor.ui.vocabulary_panel import VocabularyPanel
    from extra.table_editor.ui.vocabulary_word_rows_panel import VocabularyWordRowsPanel

Mode = Literal[
    "main",
    "conversation",
    "vocabulary",
    "vocab_rows",
    "shorts_conv",
    "shorts_vocab",
    "tts",
]


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x800")
        self.minsize(800, 600)
        self._main_geometry = "1100x880"
        self._vocab_geometry = "1100x800"
        self._vocab_rows_geometry = "1100x800"
        self._shorts_conv_geometry = "1100x800"
        self._shorts_vocab_geometry = "1100x800"
        self._conv_geometry = "1100x1020"
        self._tts_geometry = "1100x960"

        bind_clipboard_on_class(self)

        self._mode = tk.StringVar(value="main")
        self._status_var = tk.StringVar(value="준비")
        self._path_var = tk.StringVar(value="")

        self._build_toolbar()
        self._build_mode_selector()

        self._content = ttk.Frame(self)
        self._content.pack(fill=tk.BOTH, expand=True)

        self._ui_ready = False
        self._vocab: VocabularyPanel | None = None
        self._vocab_rows: VocabularyWordRowsPanel | None = None
        self._shorts_conv: ShortsConversationClipsPanel | None = None
        self._shorts_vocab: ShortsVocabularyClipsPanel | None = None
        self._conv: ConversationPanel | None = None
        self._tts: TtsPanel | None = None
        self._panel_defaults_loaded: set[Mode] = set()
        self._main = MainPanel(
            self._content,
            on_status=self._set_status,
        )
        self._ui_ready = True
        self._show_mode("main")

        status = ttk.Label(self, textvariable=self._status_var, relief=tk.SUNKEN, anchor="w")
        status.pack(fill=tk.X, side=tk.BOTTOM)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _ensure_vocab(self) -> "VocabularyPanel":
        if self._vocab is None:
            from extra.table_editor.ui.vocabulary_panel import VocabularyPanel

            self._vocab = VocabularyPanel(
                self._content,
                on_status=self._set_status,
                on_dirty_change=self._on_panel_dirty,
            )
        return self._vocab

    def _ensure_vocab_rows(self) -> "VocabularyWordRowsPanel":
        if self._vocab_rows is None:
            from extra.table_editor.ui.vocabulary_word_rows_panel import (
                VocabularyWordRowsPanel,
            )

            self._vocab_rows = VocabularyWordRowsPanel(
                self._content,
                on_status=self._set_status,
                on_dirty_change=self._on_panel_dirty,
            )
        return self._vocab_rows

    def _ensure_shorts_conv(self) -> "ShortsConversationClipsPanel":
        if self._shorts_conv is None:
            from extra.table_editor.ui.shorts_conversation_clips_panel import (
                ShortsConversationClipsPanel,
            )

            self._shorts_conv = ShortsConversationClipsPanel(
                self._content,
                on_status=self._set_status,
                on_dirty_change=self._on_panel_dirty,
            )
        return self._shorts_conv

    def _ensure_shorts_vocab(self) -> "ShortsVocabularyClipsPanel":
        if self._shorts_vocab is None:
            from extra.table_editor.ui.shorts_vocabulary_clips_panel import (
                ShortsVocabularyClipsPanel,
            )

            self._shorts_vocab = ShortsVocabularyClipsPanel(
                self._content,
                on_status=self._set_status,
                on_dirty_change=self._on_panel_dirty,
            )
        return self._shorts_vocab

    def _ensure_conv(self) -> "ConversationPanel":
        if self._conv is None:
            from extra.table_editor.ui.conversation_panel import ConversationPanel

            self._conv = ConversationPanel(
                self._content,
                on_status=self._set_status,
                on_dirty_change=self._on_panel_dirty,
            )
        return self._conv

    def _ensure_tts(self) -> "TtsPanel":
        if self._tts is None:
            from extra.table_editor.ui.tts_panel import TtsPanel

            self._tts = TtsPanel(
                self._content,
                on_status=self._set_status,
                on_dirty_change=self._on_panel_dirty,
            )
        return self._tts

    def _ensure_panel_defaults(self, mode: Mode) -> None:
        if mode in self._panel_defaults_loaded:
            return
        if mode == "vocabulary":
            label, loader = "단어장", self._ensure_vocab().load_defaults
        elif mode == "vocab_rows":
            label, loader = (
                "단어장 행",
                self._ensure_vocab_rows().load_defaults,
            )
        elif mode == "shorts_conv":
            label, loader = (
                "숏츠 회화 클립",
                self._ensure_shorts_conv().load_defaults,
            )
        elif mode == "shorts_vocab":
            label, loader = (
                "숏츠 단어 클립",
                self._ensure_shorts_vocab().load_defaults,
            )
        elif mode == "conversation":
            label, loader = "회화", self._ensure_conv().load_defaults
        elif mode == "tts":
            label, loader = "TTS", self._ensure_tts().load_defaults
        else:
            return
        self._set_status(f"{label} 데이터 로딩 중…")
        try:
            loader()
            self._panel_defaults_loaded.add(mode)
            self._set_status("준비")
        except Exception as ex:
            self._set_status(f"{label} 로드 실패: {ex}")

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=4)
        self._toolbar = bar

        self._open_btn = ttk.Button(bar, text="파일 열기", command=self._open_file)
        self._open_btn.pack(side=tk.LEFT, padx=2)
        self._save_btn = ttk.Button(bar, text="저장", command=self._save)
        self._save_btn.pack(side=tk.LEFT, padx=2)
        self._save_as_btn = ttk.Button(
            bar, text="다른 이름으로 저장", command=self._save_as
        )
        self._save_as_btn.pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        self._export_csv_btn = ttk.Button(
            bar, text="현재 탭 CSV", command=self._export_current_csv
        )
        self._export_csv_btn.pack(side=tk.LEFT, padx=2)
        self._export_all_btn = ttk.Button(
            bar, text="회화 전체 CSV", command=self._export_all_csv
        )
        self._export_all_btn.pack(side=tk.LEFT, padx=2)

        ttk.Label(bar, textvariable=self._path_var).pack(side=tk.RIGHT, padx=8)

    def _build_mode_selector(self) -> None:
        frame = ttk.LabelFrame(self, text="모드")
        frame.pack(fill=tk.X, padx=8, pady=4)
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X)
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X)
        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X)

        modes_row1 = [
            ("메인 (빠른 작업)", "main"),
            ("단어장 (words.xlsx)", "vocabulary"),
            ("단어장 행 (vocabulary_word_rows.xlsx)", "vocab_rows"),
            ("회화모드 (base / sub)", "conversation"),
        ]
        modes_row2 = [
            ("숏츠 회화 (shorts_conversation_clips.xlsx)", "shorts_conv"),
            ("숏츠 단어 (shorts_vocabulary_clips.xlsx)", "shorts_vocab"),
        ]
        modes_row3 = [
            ("TTS (ko_narration sets / lines)", "tts"),
        ]
        for text, value in modes_row1:
            ttk.Radiobutton(
                row1,
                text=text,
                variable=self._mode,
                value=value,
                command=lambda v=value: self._switch_mode(v),  # type: ignore[arg-type]
            ).pack(side=tk.LEFT, padx=12, pady=4)
        for text, value in modes_row2:
            ttk.Radiobutton(
                row2,
                text=text,
                variable=self._mode,
                value=value,
                command=lambda v=value: self._switch_mode(v),  # type: ignore[arg-type]
            ).pack(side=tk.LEFT, padx=12, pady=4)
        for text, value in modes_row3:
            ttk.Radiobutton(
                row3,
                text=text,
                variable=self._mode,
                value=value,
                command=lambda v=value: self._switch_mode(v),  # type: ignore[arg-type]
            ).pack(side=tk.LEFT, padx=12, pady=4)

    def _active_panel(
        self,
    ) -> (
        "MainPanel | VocabularyPanel | VocabularyWordRowsPanel | "
        "ShortsConversationClipsPanel | ShortsVocabularyClipsPanel | "
        "ConversationPanel | TtsPanel"
    ):
        if not getattr(self, "_ui_ready", False):
            return self._main
        mode = self._mode.get()
        if mode == "main":
            return self._main
        if mode == "conversation":
            return self._ensure_conv()
        if mode == "tts":
            return self._ensure_tts()
        if mode == "vocab_rows":
            return self._ensure_vocab_rows()
        if mode == "shorts_conv":
            return self._ensure_shorts_conv()
        if mode == "shorts_vocab":
            return self._ensure_shorts_vocab()
        return self._ensure_vocab()

    def _persist_visible_edits(self) -> None:
        if not getattr(self, "_ui_ready", False):
            return
        if self._vocab is not None and self._vocab.winfo_ismapped():
            self._vocab._flush_current_sheet()
        if self._vocab_rows is not None and self._vocab_rows.winfo_ismapped():
            self._vocab_rows._flush_rows()
        if self._shorts_conv is not None and self._shorts_conv.winfo_ismapped():
            self._shorts_conv._flush_rows()
        if self._shorts_vocab is not None and self._shorts_vocab.winfo_ismapped():
            self._shorts_vocab._flush_rows()
        if self._conv is not None and self._conv.winfo_ismapped():
            self._conv.flush_all()
        if self._tts is not None and self._tts.winfo_ismapped():
            self._tts.flush_all()

    def _update_toolbar_for_mode(self, mode: Mode) -> None:
        if mode == "main":
            self._open_btn.pack_forget()
            self._save_btn.pack_forget()
            self._save_as_btn.pack_forget()
            self._export_all_btn.pack_forget()
            if not self._export_csv_btn.winfo_ismapped():
                self._export_csv_btn.pack(side=tk.LEFT, padx=2)
        else:
            if not self._open_btn.winfo_ismapped():
                self._open_btn.pack(side=tk.LEFT, padx=2)
            if not self._save_btn.winfo_ismapped():
                self._save_btn.pack(side=tk.LEFT, padx=2)
            if not self._save_as_btn.winfo_ismapped():
                self._save_as_btn.pack(side=tk.LEFT, padx=2)
            if not self._export_csv_btn.winfo_ismapped():
                self._export_csv_btn.pack(side=tk.LEFT, padx=2)

    def _show_mode(self, mode: Mode) -> None:
        self._persist_visible_edits()
        self._main.pack_forget()
        if self._vocab is not None:
            self._vocab.pack_forget()
        if self._vocab_rows is not None:
            self._vocab_rows.pack_forget()
        if self._shorts_conv is not None:
            self._shorts_conv.pack_forget()
        if self._shorts_vocab is not None:
            self._shorts_vocab.pack_forget()
        if self._conv is not None:
            self._conv.pack_forget()
        if self._tts is not None:
            self._tts.pack_forget()
        self._export_all_btn.pack_forget()
        self._update_toolbar_for_mode(mode)
        if mode == "main":
            self._main.pack(fill=tk.BOTH, expand=True)
            self.geometry(self._main_geometry)
            self.minsize(900, 660)
        elif mode == "conversation":
            self._ensure_conv().pack(fill=tk.BOTH, expand=True)
            self._export_all_btn.pack(side=tk.LEFT, padx=2)
            self.geometry(self._conv_geometry)
            self.minsize(800, 820)
        elif mode == "tts":
            self._ensure_tts().pack(fill=tk.BOTH, expand=True)
            self.geometry(self._tts_geometry)
            self.minsize(800, 780)
        elif mode == "vocab_rows":
            self._ensure_vocab_rows().pack(fill=tk.BOTH, expand=True)
            self.geometry(self._vocab_rows_geometry)
            self.minsize(800, 600)
        elif mode == "shorts_conv":
            self._ensure_shorts_conv().pack(fill=tk.BOTH, expand=True)
            self.geometry(self._shorts_conv_geometry)
            self.minsize(800, 600)
        elif mode == "shorts_vocab":
            self._ensure_shorts_vocab().pack(fill=tk.BOTH, expand=True)
            self.geometry(self._shorts_vocab_geometry)
            self.minsize(800, 600)
        else:
            self._ensure_vocab().pack(fill=tk.BOTH, expand=True)
            self.geometry(self._vocab_geometry)
            self.minsize(800, 600)
        if mode != "main":
            self.after(1, lambda m=mode: self._ensure_panel_defaults(m))
        self._update_path_label()

    def _switch_mode(self, mode: Mode) -> None:
        if self._main.winfo_ismapped():
            current: Mode = "main"
        elif self._conv is not None and self._conv.winfo_ismapped():
            current = "conversation"
        elif self._tts is not None and self._tts.winfo_ismapped():
            current = "tts"
        elif self._vocab_rows is not None and self._vocab_rows.winfo_ismapped():
            current = "vocab_rows"
        elif self._shorts_conv is not None and self._shorts_conv.winfo_ismapped():
            current = "shorts_conv"
        elif self._shorts_vocab is not None and self._shorts_vocab.winfo_ismapped():
            current = "shorts_vocab"
        else:
            current = "vocabulary"
        if mode == current:
            return
        if not self._confirm_leave_panel(current):
            self._mode.set(current)
            return
        self._show_mode(mode)

    def _confirm_leave_panel(self, leaving: Mode) -> bool:
        if leaving == "main":
            return True
        if leaving == "vocabulary" and self._vocab is not None and self._vocab.is_dirty:
            return messagebox.askyesno(
                "저장 확인",
                "단어장에 저장되지 않은 변경이 있습니다. 계속할까요?",
                parent=self,
            )
        if (
            leaving == "vocab_rows"
            and self._vocab_rows is not None
            and self._vocab_rows.is_dirty
        ):
            return messagebox.askyesno(
                "저장 확인",
                "단어장 행에 저장되지 않은 변경이 있습니다. 계속할까요?",
                parent=self,
            )
        if (
            leaving == "shorts_conv"
            and self._shorts_conv is not None
            and self._shorts_conv.is_dirty
        ):
            return messagebox.askyesno(
                "저장 확인",
                "숏츠 회화 클립에 저장되지 않은 변경이 있습니다. 계속할까요?",
                parent=self,
            )
        if (
            leaving == "shorts_vocab"
            and self._shorts_vocab is not None
            and self._shorts_vocab.is_dirty
        ):
            return messagebox.askyesno(
                "저장 확인",
                "숏츠 단어 클립에 저장되지 않은 변경이 있습니다. 계속할까요?",
                parent=self,
            )
        if leaving == "conversation" and self._conv is not None and self._conv.is_dirty:
            return messagebox.askyesno(
                "저장 확인",
                "회화 데이터에 저장되지 않은 변경이 있습니다. 계속할까요?",
                parent=self,
            )
        if leaving == "tts" and self._tts is not None and self._tts.is_dirty:
            return messagebox.askyesno(
                "저장 확인",
                "TTS 데이터에 저장되지 않은 변경이 있습니다. 계속할까요?",
                parent=self,
            )
        return True

    def _on_panel_dirty(self, _dirty: bool) -> None:
        if getattr(self, "_ui_ready", False):
            self._update_path_label()

    def _update_path_label(self) -> None:
        if not getattr(self, "_ui_ready", False):
            return
        mode = self._mode.get()
        if mode == "main":
            dirty = False
            path_str = self._main.path_summary()
        elif mode == "vocabulary" and self._vocab is not None:
            p = self._vocab.file_path
            dirty = self._vocab.is_dirty
            path_str = str(p) if p else "(파일 없음)"
        elif mode == "vocab_rows" and self._vocab_rows is not None:
            p = self._vocab_rows.file_path
            dirty = self._vocab_rows.is_dirty
            path_str = str(p) if p else "(파일 없음)"
        elif mode == "shorts_conv" and self._shorts_conv is not None:
            p = self._shorts_conv.file_path
            dirty = self._shorts_conv.is_dirty
            path_str = str(p) if p else "(파일 없음)"
        elif mode == "shorts_vocab" and self._shorts_vocab is not None:
            p = self._shorts_vocab.file_path
            dirty = self._shorts_vocab.is_dirty
            path_str = str(p) if p else "(파일 없음)"
        elif mode == "tts" and self._tts is not None:
            dirty = self._tts.is_dirty
            path_str = self._tts.path_summary()
        elif mode == "conversation" and self._conv is not None:
            dirty = self._conv.is_dirty
            path_str = self._conv.path_summary()
        else:
            dirty = False
            path_str = "(파일 없음)"
        self._path_var.set(f"{'* ' if dirty else ''}{path_str}")

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)
        self._update_path_label()

    def _open_file(self) -> None:
        if self._mode.get() == "main":
            return
        self._active_panel().open_file_dialog()
        self._update_path_label()

    def _save(self) -> None:
        if self._mode.get() == "main":
            return
        self._active_panel().save()
        self._update_path_label()

    def _save_as(self) -> None:
        if self._mode.get() == "main":
            return
        self._active_panel().save_as()
        self._update_path_label()

    def _export_current_csv(self) -> None:
        mode = self._mode.get()
        if mode == "main":
            self._main.export_current_csv()
            return
        panel = self._active_panel()
        if mode == "vocabulary":
            panel.export_csv()
        elif mode == "vocab_rows":
            panel.export_csv()
        elif mode == "shorts_conv":
            panel.export_csv()
        elif mode == "shorts_vocab":
            panel.export_csv()
        elif mode == "tts":
            panel.export_all_csv()
        else:
            panel.export_current_csv()

    def _export_all_csv(self) -> None:
        if self._conv is not None:
            self._conv.export_all_csv()

    def _on_close(self) -> None:
        self._persist_visible_edits()
        dirty = (
            (self._vocab is not None and self._vocab.is_dirty)
            or (self._vocab_rows is not None and self._vocab_rows.is_dirty)
            or (self._shorts_conv is not None and self._shorts_conv.is_dirty)
            or (self._shorts_vocab is not None and self._shorts_vocab.is_dirty)
            or (self._conv is not None and self._conv.is_dirty)
            or (self._tts is not None and self._tts.is_dirty)
        )
        if dirty:
            if not messagebox.askyesno(
                "종료",
                "저장되지 않은 변경이 있습니다. 종료할까요?",
                parent=self,
            ):
                return
        self.destroy()
