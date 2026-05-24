"""회화 모드 세션 배경음 (resource/sound/bg)."""
from __future__ import annotations

import logging
import random
from typing import Callable, Optional

import pygame

from core.paths import STUDIO_PRACTICE_BG_AUDIO_LINEAR_GAIN, get_repo_root

logger = logging.getLogger(__name__)

_BG_SOUND_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
_BG_CHANNEL_INDEX = 5
_BG_FADE_MS = 1000


def load_conversation_background_sounds() -> list[tuple[str, pygame.mixer.Sound]]:
    """`resource/sound/bg` 아래 오디오 파일을 로드한다."""
    bg_dir = get_repo_root() / "resource" / "sound" / "bg"
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
            logger.debug("회화 bg 로드 스킵 %s: %s", path, ex)
    return out


def _ensure_mixer() -> None:
    if pygame.mixer.get_init() is None:
        from core.paths import STUDIO_AUDIO_SAMPLE_RATE

        pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)


class ConversationBackgroundPlayer:
    """회화 스튜디오 실행 중 랜덤 bg를 fade in/out으로 반복 재생한다."""

    def __init__(
        self,
        *,
        on_bg_started: Optional[Callable[[str, float], None]] = None,
        is_recording: Optional[Callable[[], bool]] = None,
        volume: float | None = None,
    ) -> None:
        self._sounds = load_conversation_background_sounds()
        self._on_bg_started = on_bg_started
        self._is_recording = is_recording
        self._volume = float(volume if volume is not None else STUDIO_PRACTICE_BG_AUDIO_LINEAR_GAIN)
        self._channel: Optional[pygame.mixer.Channel] = None
        self._last_index: int | None = None
        self._active_path = ""
        self._session_active = False
        self._paused = False
        self._recording_logged = False

    @property
    def is_active(self) -> bool:
        return self._session_active

    def reload_sounds(self) -> None:
        """display·mixer 준비 후 사운드를 다시 로드한다(debug F5 등)."""
        self._sounds = load_conversation_background_sounds()

    def start_session(
        self,
        *,
        duration_hint_sec: float = 3600.0,
        reload: bool = False,
        restart: bool = True,
    ) -> None:
        """스튜디오 시작 시 한 번 호출. 세션이 끝날 때까지 bg를 유지한다.

        restart=False: 이미 재생 중이면 끊지 않고 유지(숏츠 따라해보세요 구간 등).
        """
        if reload or not self._sounds:
            self.reload_sounds()
        if not self._sounds:
            logger.warning("회화 배경음 없음: %s", get_repo_root() / "resource" / "sound" / "bg")
            return
        if reload:
            self._recording_logged = False
        dur = max(1.0, float(duration_hint_sec))
        if self._session_active and not restart:
            if self._recording_mode():
                if not self._recording_logged:
                    idx = self._pick_random_index() if self._last_index is None else self._last_index
                    self._play_index(idx, duration_hint_sec=dur)
                return
            ch = self._channel
            if ch is not None and ch.get_busy():
                return
        if restart and self._session_active:
            self._stop_channel_immediate()
        if reload or self._last_index is None:
            idx = self._pick_random_index()
        else:
            idx = self._last_index
        self._session_active = True
        self._paused = False
        self._play_index(idx, duration_hint_sec=dur)

    def stop_session(self) -> None:
        """스튜디오 종료·단어 단계 전환 시 fade out."""
        self._session_active = False
        self._paused = False
        self._recording_logged = False
        ch = self._channel
        self._channel = None
        self._active_path = ""
        if ch is None:
            return
        try:
            if ch.get_busy():
                ch.fadeout(_BG_FADE_MS)
        except Exception:
            try:
                ch.stop()
            except Exception:
                pass

    def set_paused(self, paused: bool) -> None:
        """비디오 일시정지와 동기."""
        paused = bool(paused)
        if paused == self._paused:
            return
        self._paused = paused
        ch = self._channel
        if ch is None:
            return
        try:
            if paused:
                ch.pause()
            else:
                ch.unpause()
        except Exception:
            pass

    def tick(self, *, duration_hint_sec: float = 3600.0) -> None:
        """매 프레임: 재생이 끊기면 동일 곡을 처음부터 다시 재생한다."""
        if not self._session_active or self._paused or not self._sounds:
            return
        if self._recording_mode():
            return
        ch = self._channel
        if ch is not None and ch.get_busy():
            return
        idx = self._last_index if self._last_index is not None else 0
        self._play_index(idx, duration_hint_sec=max(1.0, float(duration_hint_sec)))

    def _stop_channel_immediate(self) -> None:
        ch = self._channel
        if ch is None:
            return
        try:
            ch.stop()
        except Exception:
            pass

    def _pick_random_index(self) -> int:
        if len(self._sounds) == 1:
            return 0
        candidates = [i for i in range(len(self._sounds)) if i != self._last_index]
        return random.choice(candidates) if candidates else 0

    def _play_index(self, idx: int, *, duration_hint_sec: float) -> None:
        try:
            idx = max(0, min(int(idx), len(self._sounds) - 1))
            path, snd = self._sounds[idx]
            self._last_index = idx
            self._active_path = path

            if self._recording_mode():
                if not self._recording_logged:
                    self._recording_logged = True
                    if self._on_bg_started is not None:
                        self._on_bg_started(path, duration_hint_sec)
                return

            _ensure_mixer()
            ch = pygame.mixer.Channel(_BG_CHANNEL_INDEX)
            ch.set_volume(max(0.0, min(2.0, self._volume)))
            ch.play(snd, loops=-1, fade_ms=_BG_FADE_MS)
            self._channel = ch
            if self._on_bg_started is not None:
                self._on_bg_started(path, duration_hint_sec)
        except Exception as ex:
            logger.warning("회화 bg 재생 실패: %s", ex)
            self._channel = None

    def _recording_mode(self) -> bool:
        if self._is_recording is None:
            return False
        try:
            return bool(self._is_recording())
        except Exception:
            return False
