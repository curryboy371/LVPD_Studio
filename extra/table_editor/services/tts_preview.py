"""Edge/gTTS 샘플 합성 후 재생 (GUI 미리듣기)."""
from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_preview_lock = threading.Lock()
_playing = False


def is_tts_preview_playing() -> bool:
    return _playing


def play_tts_preview(
    *,
    text: str,
    lang: str,
    voice: str,
    engine: str = "edge",
    on_done: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[BaseException], None]] = None,
) -> None:
    """백그라운드에서 합성·재생. 동시 요청은 무시."""

    def _worker() -> None:
        global _playing
        with _preview_lock:
            if _playing:
                return
            _playing = True
        path: Path | None = None
        try:
            from audio.ko_narration import resolve_tts_provider

            line = (text or "").strip()
            if not line:
                raise ValueError("미리듣기 텍스트가 비어 있습니다.")
            eng = (engine or "edge").strip().lower()
            provider = resolve_tts_provider(eng, voice=(voice or "").strip())
            fd, raw = tempfile.mkstemp(suffix=".mp3", prefix="lvpd_tts_preview_")
            import os

            os.close(fd)
            path = Path(raw)
            provider.synthesize(line, lang=lang, out_path=path)
            _play_mp3(path)
            if on_done:
                on_done()
        except Exception as ex:
            logger.exception("TTS 미리듣기 실패")
            if on_error:
                on_error(ex)
        finally:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            with _preview_lock:
                _playing = False

    threading.Thread(target=_worker, daemon=True).start()


def _play_mp3(path: Path) -> None:
    import time

    import pygame

    if pygame.mixer.get_init() is None:
        from core.paths import STUDIO_AUDIO_SAMPLE_RATE

        pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
    pygame.mixer.music.load(str(path))
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)
    pygame.mixer.music.unload()
