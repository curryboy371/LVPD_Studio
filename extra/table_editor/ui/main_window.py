"""Main application window."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Literal

from extra.table_editor.config import APP_TITLE
from extra.table_editor.ui.clipboard_bindings import bind_clipboard_on_class
from extra.table_editor.ui.conversation_panel import ConversationPanel
from extra.table_editor.ui.vocabulary_panel import VocabularyPanel

Mode = Literal["conversation", "vocabulary"]


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x700")
        self.minsize(800, 500)
        self._vocab_geometry = "1100x700"
        self._conv_geometry = "1100x920"

        bind_clipboard_on_class(self)

        self._mode = tk.StringVar(value="vocabulary")
        self._status_var = tk.StringVar(value="준비")
        self._path_var = tk.StringVar(value="")

        self._build_toolbar()
        self._build_mode_selector()

        self._content = ttk.Frame(self)
        self._content.pack(fill=tk.BOTH, expand=True)

        self._ui_ready = False
        self._vocab = VocabularyPanel(
            self._content,
            on_status=self._set_status,
            on_dirty_change=self._on_panel_dirty,
        )
        self._conv = ConversationPanel(
            self._content,
            on_status=self._set_status,
            on_dirty_change=self._on_panel_dirty,
        )
        self._ui_ready = True
        self._vocab.load_defaults()
        self._conv.load_defaults()

        self._show_mode("vocabulary")

        status = ttk.Label(self, textvariable=self._status_var, relief=tk.SUNKEN, anchor="w")
        status.pack(fill=tk.X, side=tk.BOTTOM)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=4)

        ttk.Button(bar, text="파일 열기", command=self._open_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="저장", command=self._save).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="다른 이름으로 저장", command=self._save_as).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(bar, text="현재 탭 CSV", command=self._export_current_csv).pack(
            side=tk.LEFT, padx=2
        )
        self._export_all_btn = ttk.Button(
            bar, text="회화 전체 CSV", command=self._export_all_csv
        )
        self._export_all_btn.pack(side=tk.LEFT, padx=2)

        ttk.Label(bar, textvariable=self._path_var).pack(side=tk.RIGHT, padx=8)

    def _build_mode_selector(self) -> None:
        frame = ttk.LabelFrame(self, text="모드")
        frame.pack(fill=tk.X, padx=8, pady=4)
        ttk.Radiobutton(
            frame,
            text="단어장 (words.xlsx)",
            variable=self._mode,
            value="vocabulary",
            command=lambda: self._switch_mode("vocabulary"),
        ).pack(side=tk.LEFT, padx=12, pady=4)
        ttk.Radiobutton(
            frame,
            text="회화모드 (base / sub)",
            variable=self._mode,
            value="conversation",
            command=lambda: self._switch_mode("conversation"),
        ).pack(side=tk.LEFT, padx=12, pady=4)

    def _active_panel(self) -> VocabularyPanel | ConversationPanel:
        if not getattr(self, "_ui_ready", False):
            return self._vocab
        return self._conv if self._mode.get() == "conversation" else self._vocab

    def _persist_visible_edits(self) -> None:
        if not getattr(self, "_ui_ready", False):
            return
        if self._vocab.winfo_ismapped():
            self._vocab._flush_current_sheet()
        if self._conv.winfo_ismapped():
            self._conv.flush_all()

    def _show_mode(self, mode: Mode) -> None:
        self._persist_visible_edits()
        self._vocab.pack_forget()
        self._conv.pack_forget()
        self._export_all_btn.pack_forget()
        if mode == "conversation":
            self._conv.pack(fill=tk.BOTH, expand=True)
            self._export_all_btn.pack(side=tk.LEFT, padx=2)
            self.geometry(self._conv_geometry)
            self.minsize(800, 720)
        else:
            self._vocab.pack(fill=tk.BOTH, expand=True)
            self.geometry(self._vocab_geometry)
            self.minsize(800, 500)
        self._update_path_label()

    def _switch_mode(self, mode: Mode) -> None:
        current: Mode = (
            "conversation" if self._conv.winfo_ismapped() else "vocabulary"
        )
        if mode == current:
            return
        if not self._confirm_leave_panel(current):
            self._mode.set(current)
            return
        self._show_mode(mode)

    def _confirm_leave_panel(self, leaving: Mode) -> bool:
        if leaving == "vocabulary" and self._vocab.is_dirty:
            return messagebox.askyesno(
                "저장 확인",
                "단어장에 저장되지 않은 변경이 있습니다. 계속할까요?",
                parent=self,
            )
        if leaving == "conversation" and self._conv.is_dirty:
            return messagebox.askyesno(
                "저장 확인",
                "회화 데이터에 저장되지 않은 변경이 있습니다. 계속할까요?",
                parent=self,
            )
        return True

    def _on_panel_dirty(self, _dirty: bool) -> None:
        if getattr(self, "_ui_ready", False):
            self._update_path_label()

    def _update_path_label(self) -> None:
        if not getattr(self, "_ui_ready", False):
            return
        panel = self._active_panel()
        if isinstance(panel, VocabularyPanel):
            p = panel.file_path
            dirty = panel.is_dirty
            path_str = str(p) if p else "(파일 없음)"
        else:
            dirty = panel.is_dirty
            path_str = panel.path_summary()
        self._path_var.set(f"{'* ' if dirty else ''}{path_str}")

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)
        self._update_path_label()

    def _open_file(self) -> None:
        self._active_panel().open_file_dialog()
        self._update_path_label()

    def _save(self) -> None:
        self._active_panel().save()
        self._update_path_label()

    def _save_as(self) -> None:
        self._active_panel().save_as()
        self._update_path_label()

    def _export_current_csv(self) -> None:
        panel = self._active_panel()
        if isinstance(panel, VocabularyPanel):
            panel.export_csv()
        else:
            panel.export_current_csv()

    def _export_all_csv(self) -> None:
        if isinstance(self._conv, ConversationPanel):
            self._conv.export_all_csv()

    def _on_close(self) -> None:
        self._persist_visible_edits()
        dirty = self._vocab.is_dirty or self._conv.is_dirty
        if dirty:
            if not messagebox.askyesno(
                "종료",
                "저장되지 않은 변경이 있습니다. 종료할까요?",
                parent=self,
            ):
                return
        self.destroy()
