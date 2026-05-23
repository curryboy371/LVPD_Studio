"""회화 PRACTICE 말하기(따라해보세요) 구간 효과음 (resource/sound/follow)."""
from __future__ import annotations

import logging
import random
from typing import Callable, Optional

import pygame

from core.paths import STUDIO_PRACTICE_BG_AUDIO_LINEAR_GAIN, get_repo_root

logger = logging.getLogger(__name__)

_FOLLOW_SOUND_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
_FOLLOW_CHANNEL_INDEX = 6
_FOLLOW_FADE_MS = 1000


def load_practice_follow_sounds() -> list[tuple[str, pygame.mixer.Sound]]:
    """`resource/sound/follow` 아래 오디오를 로드한다."""
    follow_dir = get_repo_root() / "resource" / "sound" / "follow"
    if not follow_dir.is_dir():
        return []
    out: list[tuple[str, pygame.mixer.Sound]] = []
    for path in sorted(follow_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _FOLLOW_SOUND_EXTS:
            continue
        try:
            _ensure_mixer()
            out.append((str(path.resolve()), pygame.mixer.Sound(str(path))))
        except Exception as ex:
            logger.debug("follow 로드 스킵 %s: %s", path, ex)
    return out


def _ensure_mixer() -> None:
    if pygame.mixer.get_init() is None:
        from core.paths import STUDIO_AUDIO_SAMPLE_RATE

        pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)


class PracticeFollowSoundPlayer:
    """말하기(주황 게이지) 구간에만 랜덤 follow mp3를 fade in/out으로 재생한다."""

    def __init__(
        self,
        *,
        on_follow_started: Optional[Callable[[str, float], None]] = None,
        is_recording: Optional[Callable[[], bool]] = None,
        volume: float | None = None,
    ) -> None:
        self._sounds = load_practice_follow_sounds()
        self._on_follow_started = on_follow_started
        self._is_recording = is_recording
        self._volume = float(volume if volume is not None else STUDIO_PRACTICE_BG_AUDIO_LINEAR_GAIN)
        self._channel: Optional[pygame.mixer.Channel] = None
        self._last_index: int | None = None
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    def reload_sounds(self) -> None:
        self._sounds = load_practice_follow_sounds()

    def stop(self) -> None:
        self._playing = False
        ch = self._channel
        self._channel = None
        if ch is None:
            return
        try:
            if ch.get_busy():
                ch.fadeout(_FOLLOW_FADE_MS)
        except Exception:
            try:
                ch.stop()
            except Exception:
                pass

    def play_random(self, *, duration_hint_sec: float) -> None:
        if not self._sounds:
            return
        if self._playing:
            # 녹화: 채널 없이 _playing만 켜지므로 매 프레임 InsertSound가 중복되지 않게 한다.
            if self._recording_mode():
                return
            ch = self._channel
            if ch is not None and ch.get_busy():
                return
        try:
            if len(self._sounds) == 1:
                idx = 0
            else:
                candidates = [i for i in range(len(self._sounds)) if i != self._last_index]
                idx = random.choice(candidates) if candidates else 0
            path, snd = self._sounds[idx]
            self._last_index = idx
            dur = max(0.0, float(duration_hint_sec))

            if self._recording_mode():
                self._channel = None
                self._playing = True
                if self._on_follow_started is not None:
                    self._on_follow_started(path, dur)
                return

            _ensure_mixer()
            ch = pygame.mixer.Channel(_FOLLOW_CHANNEL_INDEX)
            ch.set_volume(max(0.0, min(2.0, self._volume)))
            ch.play(snd, loops=-1, fade_ms=_FOLLOW_FADE_MS)
            self._channel = ch
            self._playing = True
            if self._on_follow_started is not None:
                self._on_follow_started(path, dur)
        except Exception as ex:
            logger.warning("follow 사운드 재생 실패: %s", ex)
            self._channel = None
            self._playing = False

    def _recording_mode(self) -> bool:
        if self._is_recording is None:
            return False
        try:
            return bool(self._is_recording())
        except Exception:
            return False
