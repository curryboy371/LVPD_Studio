"""숏츠 학습 3단계 안내 음성 (follow_along.mp3 → SHORTS_FOLLOW_ALONG_LABEL)."""
from __future__ import annotations

import logging
from pathlib import Path

from core.paths import DEFAULT_KO_NARRATION_SOUND_DIR
from studio.shorts.constants import SHORTS_FOLLOW_ALONG_LABEL

logger = logging.getLogger(__name__)

SHORTS_FOLLOW_ALONG_TEXT = SHORTS_FOLLOW_ALONG_LABEL
SHORTS_FOLLOW_ALONG_MP3 = DEFAULT_KO_NARRATION_SOUND_DIR / "follow_along.mp3"
_FOLLOW_ALONG_TEXT_STAMP = SHORTS_FOLLOW_ALONG_MP3.with_suffix(".txt")


def ensure_follow_along_mp3() -> Path:
    """resource/sound/shorts/follow_along.mp3 없으면 TTS 생성."""
    from audio.ko_narration import cached_cue_audio_usable, resolve_tts_provider

    out = SHORTS_FOLLOW_ALONG_MP3
    out.parent.mkdir(parents=True, exist_ok=True)
    stamp = (_FOLLOW_ALONG_TEXT_STAMP.read_text(encoding="utf-8").strip()
             if _FOLLOW_ALONG_TEXT_STAMP.is_file() else "")
    if stamp != SHORTS_FOLLOW_ALONG_TEXT and out.is_file():
        try:
            out.unlink()
        except OSError:
            pass
    if cached_cue_audio_usable(out) and stamp == SHORTS_FOLLOW_ALONG_TEXT:
        return out
    try:
        provider = resolve_tts_provider("edge")
        provider.synthesize(SHORTS_FOLLOW_ALONG_TEXT, out_path=out)
    except Exception as ex:
        logger.warning("follow_along edge TTS 실패, gtts 시도: %s", ex)
        resolve_tts_provider("gtts").synthesize(SHORTS_FOLLOW_ALONG_TEXT, out_path=out)
    if not cached_cue_audio_usable(out):
        raise RuntimeError(f"follow_along TTS 생성 실패: {out}")
    _FOLLOW_ALONG_TEXT_STAMP.write_text(SHORTS_FOLLOW_ALONG_TEXT, encoding="utf-8")
    logger.info("follow_along TTS: %s", out)
    return out
