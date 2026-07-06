"""단어 외우기 조합형 — 결과 단어 활용 문장(중국어) + 번역(한국어) TTS 캐시.

words.csv의 example_sentence(중국어 문장)/example_translation(한국어 뜻) →
resource/sound/shorts:
  wm_sentence_ko_{word_id}_0.mp3   — 한국어 번역 문장
  wm_sentence_zh_{word_id}_0.mp3   — 중국어 문장

words.csv의 example_sentence/example_translation은 component1_id/2_id와 같은 방식으로
추가된 컬럼이라 Word 모델(get_word())에는 없다 — CSV를 직접 읽는다.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from audio.ko_narration import (
    KoCue,
    KoNarrationPlan,
    build_timeline,
    cached_cue_audio_usable,
    format_tts_log_label,
    load_ko_narration_plan_from_json,
    normalize_plan_cue_audio_paths,
    plan_cue_audios_ready,
    resolve_tts_provider,
    write_timeline_json,
)
from audio.vocab_meaning_ko import _normalize_word_tts_type
from core.paths import DEFAULT_WORDS_TABLE_CSV, get_repo_root

logger = logging.getLogger(__name__)

DEFAULT_SENTENCE_KO_TTS_VOICE = "ko-KR-SunHiNeural"
DEFAULT_SENTENCE_ZH_TTS_VOICE = "zh-CN-XiaoxiaoNeural"
# 단어 한자(wm_zh_word)와 동일하게 정상 속도(1.0) 고정.
SENTENCE_ZH_TTS_RATE = 1.0

_KO_PREFIX = "wm_sentence_ko"
_ZH_PREFIX = "wm_sentence_zh"


def _sentence_cue_audio_path(prefix: str, word_id: int, cue_index: int = 0) -> Path:
    from audio.ko_narration import KO_SOUND_DIR

    return KO_SOUND_DIR / f"{prefix}_{int(word_id)}_{int(cue_index)}.mp3"


def _sentence_timeline_path(prefix: str, word_id: int) -> Path:
    from audio.ko_narration import KO_SOUND_DIR

    return KO_SOUND_DIR / f"{prefix}_{int(word_id)}_timeline.json"


def resolve_compose_sentence_ko_audio_path(word_id: int) -> Path | None:
    p = _sentence_cue_audio_path(_KO_PREFIX, int(word_id))
    return p if p.is_file() else None


def resolve_compose_sentence_zh_audio_path(word_id: int) -> Path | None:
    p = _sentence_cue_audio_path(_ZH_PREFIX, int(word_id))
    return p if p.is_file() else None


def load_example_sentences_by_id(
    csv_path: str | Path | None = None,
) -> dict[int, tuple[str, str]]:
    """word_id → (example_sentence 중국어 문장, example_translation 한국어 뜻)."""
    path = Path(csv_path) if csv_path else DEFAULT_WORDS_TABLE_CSV
    out: dict[int, tuple[str, str]] = {}
    if not path.is_file():
        return out
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                wid = int(float(row.get("id", 0)))
            except (TypeError, ValueError):
                continue
            sentence = (row.get("example_sentence") or "").strip()
            if not sentence:
                continue
            translation = (row.get("example_translation") or "").strip()
            out[wid] = (sentence, translation)
    return out


def _repo_relative_audio_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(get_repo_root())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _normalize_tts_config(
    tts_cli: str, tts_voice_cli: str, default_voice: str
) -> tuple[str, str]:
    engine = _normalize_word_tts_type(tts_cli) or "edge"
    voice = (tts_voice_cli or "").strip()
    if not voice and engine in ("edge", "edge-tts", "edge_tts"):
        voice = default_voice
    return engine, voice


def _build_sentence_plan(
    word_id: int,
    text: str,
    *,
    prefix: str,
    lang: str,
    clip_type: str,
    default_voice: str,
    rate_multiplier: float | None,
    tts: str | None,
    tts_voice: str | None,
    force_tts: bool,
) -> Optional[KoNarrationPlan]:
    from audio.ko_narration import KO_SOUND_DIR

    line = (text or "").strip()
    wid = int(word_id)
    if wid < 1 or not line:
        return None

    engine, voice = _normalize_tts_config(tts or "edge", tts_voice or default_voice, default_voice)
    KO_SOUND_DIR.mkdir(parents=True, exist_ok=True)
    provider = resolve_tts_provider(engine, voice=voice, rate_multiplier=rate_multiplier)

    out = _sentence_cue_audio_path(prefix, wid, 0)
    if not force_tts and out.is_file() and cached_cue_audio_usable(out):
        paths = [out]
    else:
        try:
            provider.synthesize(line, lang=lang, out_path=out)
        except Exception as ex:
            logger.exception("조합형 문장 TTS 실패 word_id=%s (%s): %s", wid, prefix, ex)
            return None
        paths = [out] if cached_cue_audio_usable(out) else []

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

    timeline_json = _sentence_timeline_path(prefix, wid)
    plan = KoNarrationPlan(
        set_id=wid,
        clip_type=clip_type,
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


def batch_build_compose_sentence_tts_for_word_ids(
    word_ids: list[int],
    *,
    gen_ko: bool = True,
    gen_zh: bool = True,
    tts_ko: str = "edge",
    tts_voice_ko: str = DEFAULT_SENTENCE_KO_TTS_VOICE,
    tts_zh: str = "edge",
    tts_voice_zh: str = DEFAULT_SENTENCE_ZH_TTS_VOICE,
    force_tts: bool = False,
    csv_path: str | Path | None = None,
) -> tuple[int, int, int]:
    """word_id(결과 단어)마다 example_sentence(ZH)/example_translation(KO) TTS.

    Returns (ok, skip, fail) — ko/zh 합산.
    """
    if not word_ids:
        logger.warning("word_id 목록이 비어 있습니다.")
        return 0, 0, 1
    if not (gen_ko or gen_zh):
        logger.warning("생성할 TTS 종류가 없습니다.")
        return 0, 0, 1

    sentences_by_id = load_example_sentences_by_id(csv_path)
    ok = skip = fail = 0
    for word_id in word_ids:
        wid = int(word_id)
        pair = sentences_by_id.get(wid)
        if pair is None:
            logger.info("word_id=%s: example_sentence 없음, 스킵", wid)
            skip += 1
            continue
        sentence_zh, translation_ko = pair

        if gen_zh:
            if sentence_zh:
                if not force_tts and resolve_compose_sentence_zh_audio_path(wid) is not None:
                    skip += 1
                else:
                    plan = _build_sentence_plan(
                        wid,
                        sentence_zh,
                        prefix=_ZH_PREFIX,
                        lang="zh-cn" if _normalize_word_tts_type(tts_zh) == "gtts" else "zh",
                        clip_type="word_memorize_compose_sentence_zh",
                        default_voice=DEFAULT_SENTENCE_ZH_TTS_VOICE,
                        rate_multiplier=SENTENCE_ZH_TTS_RATE,
                        tts=tts_zh,
                        tts_voice=tts_voice_zh,
                        force_tts=force_tts,
                    )
                    if plan is None:
                        fail += 1
                        logger.warning("word_id=%s 문장(ZH) TTS 실패", wid)
                    else:
                        ok += 1
                        logger.info(
                            "word_id=%s 문장(ZH) [%s] → %s",
                            wid,
                            format_tts_log_label(tts_zh, tts_voice_zh),
                            plan.timeline_json_path,
                        )
            else:
                skip += 1

        if gen_ko:
            if translation_ko:
                if not force_tts and resolve_compose_sentence_ko_audio_path(wid) is not None:
                    skip += 1
                else:
                    plan = _build_sentence_plan(
                        wid,
                        translation_ko,
                        prefix=_KO_PREFIX,
                        lang="ko",
                        clip_type="word_memorize_compose_sentence_ko",
                        default_voice=DEFAULT_SENTENCE_KO_TTS_VOICE,
                        rate_multiplier=None,
                        tts=tts_ko,
                        tts_voice=tts_voice_ko,
                        force_tts=force_tts,
                    )
                    if plan is None:
                        fail += 1
                        logger.warning("word_id=%s 번역(KO) TTS 실패", wid)
                    else:
                        ok += 1
                        logger.info(
                            "word_id=%s 번역(KO) [%s] → %s",
                            wid,
                            format_tts_log_label(tts_ko, tts_voice_ko),
                            plan.timeline_json_path,
                        )
            else:
                skip += 1

    return ok, skip, fail


def batch_build_compose_sentence_tts_for_layout(
    layout_path: str | Path,
    **kwargs,
) -> tuple[int, int, int]:
    """조합형 배치 JSON 경로 → boxes의 word_id(결과 단어) 수집 후 문장 TTS."""
    from extra.table_editor.services.word_memorize_layouts import word_ids_from_layout

    path = Path(layout_path)
    word_ids = word_ids_from_layout(path)
    return batch_build_compose_sentence_tts_for_word_ids(word_ids, **kwargs)
