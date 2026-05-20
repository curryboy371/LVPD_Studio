"""숏츠 단어 모드: words.csv 뜻 → 한국어 TTS 캐시 (topic 배치)."""

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


def _repo_relative_audio_path(path: Path) -> str:
    """timeline JSON 저장용 — repo 기준 상대 경로 우선."""
    try:
        return str(path.resolve().relative_to(get_repo_root())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


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


def _normalize_word_tts_type(raw: str) -> str:
    """words.tts_type → resolve_tts_provider 키."""
    key = (raw or "").strip().lower()
    if key in ("edge", "edge-tts", "edge_tts"):
        return "edge"
    if key in ("gtts", "google"):
        return "gtts"
    return ""


def resolve_word_meaning_tts_config(
    word_id: int,
    *,
    tts_cli: str = "edge",
    tts_voice_cli: str = "ko-KR-SunHiNeural",
) -> tuple[str, str]:
    """words.csv tts_type·tts_voice 우선, 비어 있으면 CLI/기본값."""
    engine = (tts_cli or "edge").strip().lower()
    voice = (tts_voice_cli or "").strip()
    word = get_word(int(word_id))
    if word is not None:
        wt = _normalize_word_tts_type(getattr(word, "tts_type", "") or "")
        wv = (getattr(word, "tts_voice", "") or "").strip()
        if wt:
            engine = wt
        if wv:
            voice = wv
    if not voice and engine in ("edge", "edge-tts", "edge_tts"):
        voice = "ko-KR-SunHiNeural"
    return engine, voice


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
        return normalize_plan_cue_audio_paths(plan)
    return None


def build_vocab_meaning_plan_for_word(
    word_id: int,
    text: str,
    *,
    clip_id: int = 0,
    tts: str | None = None,
    tts_voice: str | None = None,
    force_tts: bool = False,
) -> Optional[KoNarrationPlan]:
    """단어 1개 뜻 TTS·timeline JSON 생성 (words.csv tts_type·tts_voice)."""
    from audio.ko_narration import KO_SOUND_DIR

    line = (text or "").strip()
    wid = int(word_id)
    if wid < 1 or not line:
        return None

    engine, voice = resolve_word_meaning_tts_config(
        wid,
        tts_cli=(tts or "edge"),
        tts_voice_cli=(tts_voice or "ko-KR-SunHiNeural"),
    )

    stem = _cache_stem_for_vocab_word(wid)
    KO_SOUND_DIR.mkdir(parents=True, exist_ok=True)
    provider = resolve_tts_provider(engine, voice=voice)

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
    loaded = load_ko_narration_plan_from_json(timeline_json)
    if loaded is not None and plan_cue_audios_ready(loaded):
        return normalize_plan_cue_audio_paths(loaded)
    if plan_cue_audios_ready(plan):
        return normalize_plan_cue_audio_paths(plan)
    return None


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
    from studio.shorts.data_loading import (
        _vocab_word_clip_id,
        parse_vocab_word_ids_field,
    )

    for row in _read_shorts_csv(path, label="shorts_vocabulary_clips"):
        if not _topic_matches((row.get("topic") or "").strip(), topic_set):
            continue
        try:
            topic_row_id = int(float(row.get("id") or "0"))
        except (TypeError, ValueError):
            continue
        if topic_row_id < 1:
            continue
        for wi, word_id in enumerate(
            parse_vocab_word_ids_field(row.get("word_id") or ""), start=1
        ):
            if word_id in seen:
                continue
            seen.add(word_id)
            out.append((_vocab_word_clip_id(topic_row_id, wi), word_id))
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


def collect_vocab_word_ids_by_clip_row_id(
    clip_row_id: int,
    *,
    csv_path: str | Path | None = None,
) -> list[tuple[int, int]]:
    """shorts_vocabulary_clips.csv 행 id → (내부 clip_id, word_id) 목록."""
    from studio.shorts.data_loading import (
        _read_shorts_csv,
        _vocab_word_clip_id,
        parse_vocab_word_ids_field,
    )

    path = Path(csv_path) if csv_path else DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV
    want = int(clip_row_id)
    if want < 1:
        return []
    out: list[tuple[int, int]] = []
    seen: set[int] = set()
    for row in _read_shorts_csv(path, label="shorts_vocabulary_clips"):
        try:
            rid = int(float(row.get("id") or "0"))
        except (TypeError, ValueError):
            continue
        if rid != want:
            continue
        topic = (row.get("topic") or "").strip()
        for wi, word_id in enumerate(
            parse_vocab_word_ids_field(row.get("word_id") or ""), start=1
        ):
            if word_id in seen:
                continue
            seen.add(word_id)
            out.append((_vocab_word_clip_id(want, wi), word_id))
        if out:
            logger.info(
                "shorts_vocabulary_clips id=%s topic=%s → word_id %d개",
                want,
                topic or "(없음)",
                len(out),
            )
            return out
        logger.warning("shorts_vocabulary_clips id=%s: word_id 없음", want)
        return []
    logger.warning(
        "shorts_vocabulary_clips id=%s 없음 (csv=%s)",
        want,
        path,
    )
    return []


def _batch_build_vocab_meaning_ko_for_pairs(
    pairs: list[tuple[int, int]],
    *,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    force_tts: bool = False,
) -> tuple[int, int, int]:
    """(clip_id, word_id) 목록 뜻 TTS 배치. Returns (ok, skip, fail)."""
    load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
    if not pairs:
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
        engine, voice = resolve_word_meaning_tts_config(
            word_id, tts_cli=tts, tts_voice_cli=tts_voice
        )
        plan = build_vocab_meaning_plan_for_word(
            word_id,
            text,
            clip_id=clip_id,
            tts=engine,
            tts_voice=voice,
            force_tts=force_tts,
        )
        if plan is None or not plan_cue_audios_ready(plan):
            fail += 1
            logger.warning(
                "word_id=%s TTS 실패 (%s)",
                word_id,
                format_tts_log_label(engine, voice),
            )
        else:
            ok += 1
            logger.info(
                "word_id=%s [%s] → %s",
                word_id,
                format_tts_log_label(engine, voice),
                plan.timeline_json_path,
            )
    return ok, skip, fail


def parse_word_id_list_field(raw: str) -> list[int]:
    """`30123` 또는 `30123|30124|30125` → word_id 목록."""
    out: list[int] = []
    seen: set[int] = set()
    for part in (raw or "").replace("|", ",").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            wid = int(token)
        except ValueError:
            continue
        if wid < 1 or wid in seen:
            continue
        seen.add(wid)
        out.append(wid)
    return out


def batch_build_vocab_meaning_ko_for_word_ids(
    word_ids: list[int],
    *,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    force_tts: bool = False,
) -> tuple[int, int, int]:
    """words.csv word_id 직접 지정 — 숏츠 CSV 없이 뜻 TTS 배치."""
    pairs = [(wid, wid) for wid in word_ids if int(wid) > 0]
    return _batch_build_vocab_meaning_ko_for_pairs(
        pairs,
        tts=tts,
        tts_voice=tts_voice,
        force_tts=force_tts,
    )


def batch_build_vocab_meaning_ko_for_clip_row_id(
    clip_row_id: int,
    *,
    csv_path: str | Path | None = None,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    force_tts: bool = False,
) -> tuple[int, int, int]:
    """shorts_vocabulary_clips 행 id → word_id 목록 뜻 TTS 배치."""
    pairs = collect_vocab_word_ids_by_clip_row_id(clip_row_id, csv_path=csv_path)
    return _batch_build_vocab_meaning_ko_for_pairs(
        pairs,
        tts=tts,
        tts_voice=tts_voice,
        force_tts=force_tts,
    )


def batch_build_vocab_meaning_ko_for_topic(
    topic: str,
    *,
    csv_path: str | Path | None = None,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    force_tts: bool = False,
) -> tuple[int, int, int]:
    """topic 숏츠 단어 클립의 word_id 뜻 TTS 배치. Returns (ok, skip, fail)."""
    pairs = collect_vocab_word_ids_for_topic(topic, csv_path=csv_path)
    if not pairs:
        hints = ", ".join(list_vocab_topics_in_word_rows()[:15])
        logger.warning(
            "topic=%s: 단어 클립·단어장 행 모두 없음. vocabulary_word_rows topic 예: %s",
            topic,
            hints or "(없음)",
        )
        return 0, 0, 1
    return _batch_build_vocab_meaning_ko_for_pairs(
        pairs,
        tts=tts,
        tts_voice=tts_voice,
        force_tts=force_tts,
    )


def ensure_vocab_meaning_plan_for_clip(
    clip: dict[str, Any],
    *,
    build_if_missing: bool = True,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
) -> Optional[KoNarrationPlan]:
    """재생용: 캐시 로드, 없으면 1회 TTS 생성(배치 권장)."""
    plan = try_load_cached_vocab_meaning_plan(clip)
    if plan is not None:
        return normalize_plan_cue_audio_paths(plan)
    if not build_if_missing:
        return None
    try:
        word_id = int(clip.get("word_id") or 0)
    except (TypeError, ValueError):
        return None
    if word_id < 1:
        return None
    text = korean_meaning_text_for_word_id(word_id)
    if not text:
        return None
    try:
        clip_id = int(clip.get("clip_id") or 0)
    except (TypeError, ValueError):
        clip_id = 0
    engine, voice = resolve_word_meaning_tts_config(
        word_id, tts_cli=tts, tts_voice_cli=tts_voice
    )
    logger.info(
        "단어 뜻 TTS 캐시 없음 → 재생 시 생성 word_id=%s [%s] (배치: lvpd.bat tts)",
        word_id,
        format_tts_log_label(engine, voice),
    )
    return build_vocab_meaning_plan_for_word(
        word_id,
        text,
        clip_id=clip_id,
        tts=engine,
        tts_voice=voice,
        force_tts=False,
    )
