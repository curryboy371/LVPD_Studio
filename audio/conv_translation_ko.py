"""숏츠 회화 모드: base_sentences.translation → 한국어 TTS (중국어 mp3 직전)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from audio.ko_narration import (
    KoCue,
    KoNarrationPlan,
    build_timeline,
    format_tts_log_label,
    load_ko_narration_plan_from_json,
    normalize_plan_cue_audio_paths,
    plan_cue_audios_ready,
    resolve_tts_provider,
    write_timeline_json,
)
from core.paths import get_repo_root

logger = logging.getLogger(__name__)


def _cache_stem_for_conv_base(base_id: int) -> str:
    return f"conv_base_{int(base_id)}"


def conv_translation_timeline_path(base_id: int) -> Path:
    from audio.ko_narration import KO_SOUND_DIR

    return KO_SOUND_DIR / f"ko_{_cache_stem_for_conv_base(base_id)}_timeline.json"


def _repo_relative_audio_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(get_repo_root())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def korean_translation_text_from_clip(clip: dict[str, Any]) -> str:
    """clip.translation 첫 줄 — base_sentences.translation."""
    trans = clip.get("translation") or []
    if isinstance(trans, list):
        if not trans:
            return ""
        return str(trans[0] or "").strip()
    return str(trans or "").strip()


def try_load_cached_conv_translation_plan(
    clip: dict[str, Any],
) -> Optional[KoNarrationPlan]:
    try:
        base_id = int(clip.get("base_id") or 0)
    except (TypeError, ValueError):
        return None
    if base_id < 1:
        return None
    path = conv_translation_timeline_path(base_id)
    plan = load_ko_narration_plan_from_json(path)
    if plan is not None and plan_cue_audios_ready(plan):
        return normalize_plan_cue_audio_paths(plan)
    return None


def build_conv_translation_plan_for_base(
    base_id: int,
    text: str,
    *,
    clip_id: int = 0,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    force_tts: bool = False,
) -> Optional[KoNarrationPlan]:
    """회화 base 1개 번역 TTS·timeline JSON 생성."""
    from audio.ko_narration import KO_SOUND_DIR, cached_cue_audio_usable

    line = (text or "").strip()
    bid = int(base_id)
    if bid < 1 or not line:
        return None

    stem = _cache_stem_for_conv_base(bid)
    KO_SOUND_DIR.mkdir(parents=True, exist_ok=True)
    provider = resolve_tts_provider(tts, voice=tts_voice)

    paths: list[Path] = []
    out = KO_SOUND_DIR / f"ko_{stem}_0.mp3"
    if not force_tts and out.is_file() and cached_cue_audio_usable(out):
        paths.append(out)
    else:
        try:
            provider.synthesize(line, lang="ko", out_path=out)
            if cached_cue_audio_usable(out):
                paths.append(out)
        except Exception as ex:
            logger.exception("회화 번역 TTS 실패 base_id=%s: %s", bid, ex)
            return None

    if not paths:
        return None

    cues = build_timeline([line], paths)
    if not cues:
        return None
    cues = [
        KoCue(
            index=c.index,
            text=c.text,
            start_sec=c.start_sec,
            end_sec=c.end_sec,
            audio_path=_repo_relative_audio_path(Path(c.audio_path)),
        )
        for c in cues
    ]

    timeline_json = conv_translation_timeline_path(bid)
    plan = KoNarrationPlan(
        set_id=bid,
        clip_type="conversation_base",
        clip_id=int(clip_id),
        cues=cues,
        composite_audio_path="",
        adjusted_srt_path="",
        timeline_json_path=str(timeline_json.resolve()),
        total_duration_sec=cues[-1].end_sec if cues else 0.0,
    )
    write_timeline_json(plan)
    loaded = load_ko_narration_plan_from_json(timeline_json)
    if loaded is not None and plan_cue_audios_ready(loaded):
        return normalize_plan_cue_audio_paths(loaded)
    if plan_cue_audios_ready(plan):
        return normalize_plan_cue_audio_paths(plan)
    return None


def ensure_conv_translation_plan_for_clip(
    clip: dict[str, Any],
    *,
    build_if_missing: bool = True,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
) -> Optional[KoNarrationPlan]:
    """재생용: 캐시 로드, 없으면 1회 TTS 생성."""
    plan = try_load_cached_conv_translation_plan(clip)
    if plan is not None:
        return normalize_plan_cue_audio_paths(plan)
    if not build_if_missing:
        return None
    try:
        base_id = int(clip.get("base_id") or 0)
    except (TypeError, ValueError):
        return None
    if base_id < 1:
        return None
    text = korean_translation_text_from_clip(clip)
    if not text:
        return None
    try:
        clip_id = int(clip.get("clip_id") or 0)
    except (TypeError, ValueError):
        clip_id = 0
    logger.info(
        "회화 번역 TTS 캐시 없음 → 재생 시 생성 base_id=%s clip_id=%s [%s]",
        base_id,
        clip_id,
        format_tts_log_label(tts, tts_voice),
    )
    return build_conv_translation_plan_for_base(
        base_id,
        text,
        clip_id=clip_id,
        tts=tts,
        tts_voice=tts_voice,
        force_tts=False,
    )
