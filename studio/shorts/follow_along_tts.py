"""숏츠 2회차 안내 음성: 따라해보세요 (TTS mp3)."""
from __future__ import annotations

import logging
from pathlib import Path

from core.paths import DEFAULT_KO_NARRATION_SOUND_DIR

logger = logging.getLogger(__name__)

SHORTS_FOLLOW_ALONG_TEXT = "따라해보세요"
SHORTS_FOLLOW_ALONG_MP3 = DEFAULT_KO_NARRATION_SOUND_DIR / "follow_along.mp3"


def ensure_follow_along_mp3() -> Path:
    """resource/sound/shorts/follow_along.mp3 없으면 TTS 생성."""
    from audio.ko_narration import cached_cue_audio_usable, resolve_tts_provider

    out = SHORTS_FOLLOW_ALONG_MP3
    out.parent.mkdir(parents=True, exist_ok=True)
    if cached_cue_audio_usable(out):
        return out
    try:
        provider = resolve_tts_provider("edge")
        provider.synthesize(SHORTS_FOLLOW_ALONG_TEXT, out_path=out)
    except Exception as ex:
        logger.warning("follow_along edge TTS 실패, gtts 시도: %s", ex)
        resolve_tts_provider("gtts").synthesize(SHORTS_FOLLOW_ALONG_TEXT, out_path=out)
    if not cached_cue_audio_usable(out):
        raise RuntimeError(f"따라해보세요 TTS 생성 실패: {out}")
    logger.info("따라해보세요 TTS: %s", out)
    return out
