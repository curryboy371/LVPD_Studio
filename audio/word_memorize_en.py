"""단어 외우기: words.csv en_meaning → 영어 TTS 캐시."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

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
from audio.vocab_meaning_ko import _normalize_word_tts_type
from core.paths import DEFAULT_WORDS_TABLE_CSV, get_repo_root
from data.table_manager import get_word, load_words_table_from_csv

logger = logging.getLogger(__name__)

DEFAULT_EN_TTS_VOICE = "en-US-GuyNeural"


def load_en_meaning_by_id(csv_path: Path | None = None) -> dict[int, str]:
    path = Path(csv_path or DEFAULT_WORDS_TABLE_CSV)
    out: dict[int, str] = {}
    if not path.is_file():
        return out
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                wid = int(float(row.get("id", 0)))
            except (TypeError, ValueError):
                continue
            text = (row.get("en_meaning") or "").strip()
            if text:
                out[wid] = text
    return out


def english_meaning_text_for_word_id(
    word_id: int,
    en_by_id: dict[int, str] | None = None,
) -> str:
    if en_by_id is None:
        en_by_id = load_en_meaning_by_id()
    return (en_by_id.get(int(word_id)) or "").strip()


def word_memorize_en_cue_audio_path(word_id: int, cue_index: int = 0) -> Path:
    from audio.ko_narration import KO_SOUND_DIR

    return KO_SOUND_DIR / f"en_word_{int(word_id)}_{int(cue_index)}.mp3"


def word_memorize_en_timeline_path(word_id: int) -> Path:
    from audio.ko_narration import KO_SOUND_DIR

    return KO_SOUND_DIR / f"en_word_{int(word_id)}_timeline.json"


def resolve_word_memorize_en_audio_path(word_id: int) -> Path | None:
    p = word_memorize_en_cue_audio_path(int(word_id))
    return p if p.is_file() else None


def _repo_relative_audio_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(get_repo_root())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def resolve_word_en_tts_config(
    word_id: int,
    *,
    tts_cli: str = "edge",
    tts_voice_cli: str = DEFAULT_EN_TTS_VOICE,
) -> tuple[str, str]:
    """words.tts_type 우선, 영어 목소리는 CLI 기본(한국어 tts_voice는 사용하지 않음)."""
    engine = (tts_cli or "edge").strip().lower()
    voice = (tts_voice_cli or DEFAULT_EN_TTS_VOICE).strip()
    word = get_word(int(word_id))
    if word is not None:
        wt = _normalize_word_tts_type(getattr(word, "tts_type", "") or "")
        if wt:
            engine = wt
    if not voice and engine in ("edge", "edge-tts", "edge_tts"):
        voice = DEFAULT_EN_TTS_VOICE
    return engine, voice


def try_load_cached_word_memorize_en_plan(word_id: int) -> Optional[KoNarrationPlan]:
    path = word_memorize_en_timeline_path(word_id)
    plan = load_ko_narration_plan_from_json(path)
    if plan is not None and plan_cue_audios_ready(plan):
        return normalize_plan_cue_audio_paths(plan)
    return None


def build_word_memorize_en_plan_for_word(
    word_id: int,
    text: str,
    *,
    tts: str | None = None,
    tts_voice: str | None = None,
    force_tts: bool = False,
) -> Optional[KoNarrationPlan]:
    from audio.ko_narration import KO_SOUND_DIR, cached_cue_audio_usable

    line = (text or "").strip()
    wid = int(word_id)
    if wid < 1 or not line:
        return None

    engine, voice = resolve_word_en_tts_config(
        wid,
        tts_cli=(tts or "edge"),
        tts_voice_cli=(tts_voice or DEFAULT_EN_TTS_VOICE),
    )
    KO_SOUND_DIR.mkdir(parents=True, exist_ok=True)
    provider = resolve_tts_provider(engine, voice=voice)

    paths: list[Path] = []
    for i, cue_text in enumerate([line]):
        out = word_memorize_en_cue_audio_path(wid, i)
        if not force_tts and out.is_file() and cached_cue_audio_usable(out):
            paths.append(out)
            continue
        try:
            provider.synthesize(cue_text, lang="en", out_path=out)
            if cached_cue_audio_usable(out):
                paths.append(out)
        except Exception as ex:
            logger.exception("단어 영문 TTS 실패 word_id=%s: %s", wid, ex)
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

    timeline_json = word_memorize_en_timeline_path(wid)
    plan = KoNarrationPlan(
        set_id=wid,
        clip_type="word_memorize_en",
        clip_id=wid,
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


def batch_build_word_memorize_en_for_word_ids(
    word_ids: list[int],
    en_by_id: dict[int, str] | None = None,
    *,
    tts: str = "edge",
    tts_voice: str = DEFAULT_EN_TTS_VOICE,
    force_tts: bool = False,
) -> tuple[int, int, int]:
    """en_meaning → en_word_{id}_*.mp3. Returns (ok, skip, fail)."""
    load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
    if en_by_id is None:
        en_by_id = load_en_meaning_by_id()

    ok = skip = fail = 0
    for word_id in word_ids:
        wid = int(word_id)
        if wid < 1:
            continue
        text = english_meaning_text_for_word_id(wid, en_by_id)
        if not text:
            logger.warning("word_id=%s: en_meaning 없음, 스킵", wid)
            skip += 1
            continue
        if not force_tts:
            cached = try_load_cached_word_memorize_en_plan(wid)
            if cached is not None:
                logger.info("word_id=%s 영문 캐시 (%s)", wid, text[:40])
                skip += 1
                continue
        engine, voice = resolve_word_en_tts_config(
            wid, tts_cli=tts, tts_voice_cli=tts_voice
        )
        plan = build_word_memorize_en_plan_for_word(
            wid,
            text,
            tts=engine,
            tts_voice=voice,
            force_tts=force_tts,
        )
        if plan is None or not plan_cue_audios_ready(plan):
            fail += 1
            logger.warning(
                "word_id=%s 영문 TTS 실패 (%s)",
                wid,
                format_tts_log_label(engine, voice),
            )
        else:
            ok += 1
            logger.info(
                "word_id=%s 영문 [%s] → %s",
                wid,
                format_tts_log_label(engine, voice),
                plan.timeline_json_path,
            )
    if not word_ids:
        return 0, 0, 1
    return ok, skip, fail
