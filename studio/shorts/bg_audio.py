"""숏츠 학습 구간 배경음 (resource/sound/background)."""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Callable, Optional

import pygame

from core.paths import STUDIO_PRACTICE_BG_AUDIO_LINEAR_GAIN, get_repo_root

logger = logging.getLogger(__name__)

_BG_SOUND_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
_BG_CHANNEL_INDEX = 0
_BG_FADE_MS = 400


def load_background_sounds() -> list[tuple[str, pygame.mixer.Sound]]:
    bg_dir = get_repo_root() / "resource" / "sound" / "background"
    if not bg_dir.is_dir():
        return []
    out: list[tuple[str, pygame.mixer.Sound]] = []
    for path in sorted(bg_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _BG_SOUND_EXTS:
            continue
        try:
            _ensure_mixer()
            out.append((str(path.resolve()), pygame.mixer.Sound(str(path))))
        except Exception as ex:
            logger.debug("bg 로드 스킵 %s: %s", path, ex)
    return out


def _ensure_mixer() -> None:
    if pygame.mixer.get_init() is None:
        from core.paths import STUDIO_AUDIO_SAMPLE_RATE

        pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)


class ShortsBackgroundPlayer:
    def __init__(
        self,
        *,
        on_bg_started: Optional[Callable[[str, float], None]] = None,
        is_recording: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._sounds = load_background_sounds()
        self._on_bg_started = on_bg_started
        self._is_recording = is_recording
        self._channel: Optional[pygame.mixer.Channel] = None
        self._last_index = -1
        self._playing = False
        self._active_path = ""

    @property
    def is_playing(self) -> bool:
        return self._playing

    def stop(self) -> None:
        ch = self._channel
        if ch is not None:
            try:
                ch.fadeout(_BG_FADE_MS)
            except Exception:
                try:
                    ch.stop()
                except Exception:
                    pass
        self._channel = None
        self._playing = False
        self._active_path = ""

    def start_loop(self, *, duration_hint_sec: float = 120.0) -> None:
        if not self._sounds or self._playing:
            return
        try:
            if len(self._sounds) == 1:
                idx = 0
            else:
                candidates = [i for i in range(len(self._sounds)) if i != self._last_index]
                idx = random.choice(candidates) if candidates else 0
            path, snd = self._sounds[idx]
            self._last_index = idx
            self._active_path = path
            dur_hint = max(1.0, float(duration_hint_sec))
            if self._recording_mode():
                self._playing = True
                if self._on_bg_started is not None:
                    self._on_bg_started(path, dur_hint)
                return
            _ensure_mixer()
            ch = pygame.mixer.Channel(_BG_CHANNEL_INDEX)
            ch.set_volume(float(STUDIO_PRACTICE_BG_AUDIO_LINEAR_GAIN))
            ch.play(snd, loops=-1, fade_ms=_BG_FADE_MS)
            self._channel = ch
            self._playing = True
            if self._on_bg_started is not None:
                self._on_bg_started(path, dur_hint)
        except Exception as ex:
            logger.warning("숏츠 bg 재생 실패: %s", ex)
            self._playing = False

    def _recording_mode(self) -> bool:
        if self._is_recording is None:
            return False
        try:
            return bool(self._is_recording())
        except Exception:
            return False
