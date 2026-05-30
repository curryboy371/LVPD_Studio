"""숏츠 bg_path 콤보 미리듣기 / 정지."""
from __future__ import annotations

import random
import threading
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

from core.paths import get_repo_root
from extra.table_editor.services.shorts_editor_choices import (
    bg_path_from_combo,
    list_bg_path_choices,
)


class ShortsBgPathPreviewPlayer:
    """편집기 bg_path 미리듣기 — 동시에 하나만 재생."""

    _lock = threading.Lock()
    _active: ShortsBgPathPreviewPlayer | None = None

    def __init__(self) -> None:
        self._channel: object | None = None
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    def resolve_path(self, combo_value: str) -> Path | None:
        stored = bg_path_from_combo(combo_value)
        repo = get_repo_root()
        if stored:
            path = Path(stored)
            if not path.is_absolute():
                path = repo / stored.replace("\\", "/")
            return path if path.is_file() else None
        rel_choices = list_bg_path_choices()
        if not rel_choices:
            return None
        rel = random.choice(rel_choices)
        path = repo / rel.replace("\\", "/")
        return path if path.is_file() else None

    def play(self, combo_value: str) -> bool:
        path = self.resolve_path(combo_value)
        if path is None:
            return False
        self.stop()
        try:
            import pygame

            if pygame.mixer.get_init() is None:
                from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
            snd = pygame.mixer.Sound(str(path))
            ch = pygame.mixer.find_channel(True)
            if ch is None:
                ch = pygame.mixer.Channel(0)
            ch.play(snd, loops=-1)
            with self._lock:
                ShortsBgPathPreviewPlayer._active = self
            self._channel = ch
            self._playing = True
            return True
        except Exception:
            self._playing = False
            self._channel = None
            raise

    def stop(self) -> None:
        ch = self._channel
        self._channel = None
        self._playing = False
        if ch is not None:
            try:
                ch.stop()
            except Exception:
                pass
        with self._lock:
            if ShortsBgPathPreviewPlayer._active is self:
                ShortsBgPathPreviewPlayer._active = None

    @classmethod
    def stop_global(cls) -> None:
        with cls._lock:
            active = cls._active
        if active is not None:
            active.stop()


def attach_bg_path_preview(parent: ttk.Frame, combo: ttk.Combobox) -> ttk.Button:
    """bg_path 콤보 옆 미리듣기/정지 토글 버튼."""
    player = ShortsBgPathPreviewPlayer()
    btn_var = tk.StringVar(value="미리듣기")

    def _set_idle() -> None:
        btn_var.set("미리듣기")

    def _toggle() -> None:
        if player.is_playing:
            player.stop()
            _set_idle()
            return
        ShortsBgPathPreviewPlayer.stop_global()
        try:
            ok = player.play(combo.get())
        except Exception as ex:
            messagebox.showwarning(
                "미리듣기",
                f"재생할 수 없습니다.\n{ex}",
                parent=parent.winfo_toplevel(),
            )
            _set_idle()
            return
        if not ok:
            messagebox.showwarning(
                "미리듣기",
                "재생할 bg_short 파일이 없습니다.\n"
                "resource/sound/bg_short 에 오디오를 추가하거나 경로를 선택하세요.",
                parent=parent.winfo_toplevel(),
            )
            _set_idle()
            return
        btn_var.set("정지")

    def _on_combo_change(_event: tk.Event | None = None) -> None:
        if player.is_playing:
            player.stop()
            _set_idle()

    combo.bind("<<ComboboxSelected>>", _on_combo_change, add="+")

    top = combo.winfo_toplevel()

    def _on_destroy(_event: tk.Event | None = None) -> None:
        if _event is not None and _event.widget is not top:
            return
        player.stop()

    top.bind("<Destroy>", _on_destroy, add="+")

    return ttk.Button(parent, textvariable=btn_var, command=_toggle, width=9)
