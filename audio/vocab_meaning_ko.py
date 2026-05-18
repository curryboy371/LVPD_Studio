"""숏츠 단어 모드: words.csv 뜻 → 한국어 TTS 캐시 (topic 배치)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from audio.ko_narration import (
    KoNarrationPlan,
    build_timeline,
    load_ko_narration_plan_from_json,
    plan_cue_audios_ready,
    resolve_tts_provider,
    write_timeline_json,
)
from core.paths import (
    DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV,
    DEFAULT_VOCABULARY_WORD_ROWS_CSV,
    DEFAULT_WORDS_TABLE_CSV,
)
from data.table_manager import (
    get_word,
    load_vocabulary_word_rows_from_csv,
    load_words_table_from_csv,
    select_vocabulary_word_rows_for_session_topics,
)

logger = logging.getLogger(__name__)


def _cache_stem_for_vocab_word(word_id: int) -> str:
    return f"word_{int(word_id)}"


def vocab_meaning_timeline_path(word_id: int) -> Path:
    from audio.ko_narration import KO_SOUND_DIR

    return KO_SOUND_DIR / f"ko_{_cache_stem_for_vocab_word(word_id)}_timeline.json"


def korean_meaning_text_from_word(word: Any) -> str:
    """words.meaning 첫 항목(| 구분) — TTS·자막용."""
    meaning_raw = (getattr(word, "meaning", None) or "").strip()
    if not meaning_raw:
        return ""
    return meaning_raw.split("|")[0].strip()


def korean_meaning_text_for_word_id(word_id: int) -> str:
    word = get_word(int(word_id))
    if word is None:
        return ""
    return korean_meaning_text_from_word(word)


def try_load_cached_vocab_meaning_plan(
    clip: dict[str, Any],
) -> Optional[KoNarrationPlan]:
    """배치 산출 ko_word_{word_id}_timeline.json + mp3."""
    try:
        word_id = int(clip.get("word_id") or 0)
    except (TypeError, ValueError):
        return None
    if word_id < 1:
        return None
    path = vocab_meaning_timeline_path(word_id)
    plan = load_ko_narration_plan_from_json(path)
    if plan is not None and plan_cue_audios_ready(plan):
        return plan
    return None


def build_vocab_meaning_plan_for_word(
    word_id: int,
    text: str,
    *,
    clip_id: int = 0,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    force_tts: bool = False,
) -> Optional[KoNarrationPlan]:
    """단어 1개 뜻 TTS·timeline JSON 생성."""
    from audio.ko_narration import KO_SOUND_DIR

    line = (text or "").strip()
    wid = int(word_id)
    if wid < 1 or not line:
        return None

    stem = _cache_stem_for_vocab_word(wid)
    KO_SOUND_DIR.mkdir(parents=True, exist_ok=True)
    provider = resolve_tts_provider(tts, voice=tts_voice)

    paths: list[Path] = []
    for i, cue_text in enumerate([line]):
        out = KO_SOUND_DIR / f"ko_{stem}_{i}.mp3"
        if not force_tts and out.is_file():
            from audio.ko_narration import cached_cue_audio_usable

            if cached_cue_audio_usable(out):
                paths.append(out)
                continue
        try:
            provider.synthesize(cue_text, lang="ko", out_path=out)
            from audio.ko_narration import cached_cue_audio_usable

            if cached_cue_audio_usable(out):
                paths.append(out)
        except Exception as ex:
            logger.exception("단어 뜻 TTS 실패 word_id=%s: %s", wid, ex)
            return None

    if not paths:
        return None

    cues = build_timeline([line], paths)
    if not cues:
        return None

    timeline_json = vocab_meaning_timeline_path(wid)
    plan = KoNarrationPlan(
        set_id=wid,
        clip_type="vocabulary_word",
        clip_id=int(clip_id),
        cues=cues,
        composite_audio_path="",
        adjusted_srt_path="",
        timeline_json_path=str(timeline_json.resolve()),
        total_duration_sec=cues[-1].end_sec if cues else 0.0,
    )
    write_timeline_json(plan)
    return load_ko_narration_plan_from_json(timeline_json) or plan


def collect_vocab_word_ids_from_vocabulary_rows(topic: str) -> list[tuple[int, int]]:
    """shorts_vocabulary_clips 없을 때 vocabulary_word_rows(topic, word_id) 폴백."""
    load_vocabulary_word_rows_from_csv(DEFAULT_VOCABULARY_WORD_ROWS_CSV)
    rows = select_vocabulary_word_rows_for_session_topics([topic.strip()])
    seen: set[int] = set()
    out: list[tuple[int, int]] = []
    for row in rows:
        wid = int(row.word_id)
        if wid < 1 or wid in seen:
            continue
        seen.add(wid)
        clip_id = int(row.id) if int(row.id) > 0 else wid
        out.append((clip_id, wid))
    return out


def list_vocab_topics_in_word_rows() -> list[str]:
    """vocabulary_word_rows에 등장하는 topic 목록(정렬)."""
    load_vocabulary_word_rows_from_csv(DEFAULT_VOCABULARY_WORD_ROWS_CSV)
    from data.table_manager import get_vocabulary_word_rows

    topics: set[str] = set()
    for row in get_vocabulary_word_rows() or []:
        t = (row.topic or "").strip()
        if t:
            topics.add(t)
    return sorted(topics)


def collect_vocab_word_ids_for_topic(
    topic: str,
    *,
    csv_path: str | Path | None = None,
) -> list[tuple[int, int]]:
    """topic → (clip_id, word_id). shorts_vocabulary_clips 우선, 없으면 vocabulary_word_rows."""
    from studio.shorts.data_loading import _read_shorts_csv, _topic_matches

    path = Path(csv_path) if csv_path else DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV
    topic_key = topic.strip().lower()
    topic_set = {topic_key}
    seen: set[int] = set()
    out: list[tuple[int, int]] = []
    for row in _read_shorts_csv(path, label="shorts_vocabulary_clips"):
        if not _topic_matches((row.get("topic") or "").strip(), topic_set):
            continue
        try:
            clip_id = int(float(row.get("id") or "0"))
            word_id = int(float(row.get("word_id") or "0"))
        except (TypeError, ValueError):
            continue
        if clip_id < 1 or word_id < 1 or word_id in seen:
            continue
        seen.add(word_id)
        out.append((clip_id, word_id))
    if out:
        return out
    fallback = collect_vocab_word_ids_from_vocabulary_rows(topic)
    if fallback:
        logger.info(
            "shorts_vocabulary_clips에 topic=%s 없음 → vocabulary_word_rows %d개 word_id",
            topic.strip(),
            len(fallback),
        )
    return fallback


def batch_build_vocab_meaning_ko_for_topic(
    topic: str,
    *,
    csv_path: str | Path | None = None,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    force_tts: bool = False,
) -> tuple[int, int, int]:
    """topic 숏츠 단어 클립의 word_id 뜻 TTS 배치. Returns (ok, skip, fail)."""
    load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
    pairs = collect_vocab_word_ids_for_topic(topic, csv_path=csv_path)
    if not pairs:
        hints = ", ".join(list_vocab_topics_in_word_rows()[:15])
        logger.warning(
            "topic=%s: 단어 클립·단어장 행 모두 없음. vocabulary_word_rows topic 예: %s",
            topic,
            hints or "(없음)",
        )
        return 0, 0, 1

    ok = skip = fail = 0
    for clip_id, word_id in pairs:
        text = korean_meaning_text_for_word_id(word_id)
        if not text:
            logger.warning("word_id=%s: 뜻 없음, 스킵", word_id)
            skip += 1
            continue
        if not force_tts:
            cached = try_load_cached_vocab_meaning_plan(
                {"word_id": word_id, "clip_id": clip_id, "clip_type": "vocabulary"}
            )
            if cached is not None:
                logger.info("word_id=%s 캐시 사용 (%s)", word_id, text[:40])
                skip += 1
                continue
        plan = build_vocab_meaning_plan_for_word(
            word_id,
            text,
            clip_id=clip_id,
            tts=tts,
            tts_voice=tts_voice,
            force_tts=force_tts,
        )
        if plan is None or not plan_cue_audios_ready(plan):
            fail += 1
            logger.warning("word_id=%s TTS 실패", word_id)
        else:
            ok += 1
            logger.info("word_id=%s → %s", word_id, plan.timeline_json_path)
    return ok, skip, fail
