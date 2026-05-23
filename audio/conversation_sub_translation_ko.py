"""회화 모드: topic별 sub_sentences.alt_translation → 한국어 TTS mp3."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from core.paths import (
    DEFAULT_BASE_SENTENCES_CSV,
    DEFAULT_SUB_SENTENCES_CSV,
    conversation_sub_ko_mp3_path,
    get_repo_root,
)
from data.table_manager import load_base_sentences_from_csv

logger = logging.getLogger(__name__)


def _topic_key(topic: str) -> str:
    return (topic or "").strip().lower()


def collect_sub_translation_jobs_for_topic(
    topic: str,
    *,
    base_csv: str | Path | None = None,
    sub_csv: str | Path | None = None,
) -> list[tuple[int, int, str]]:
    """topic → (sub_sentences.id, base_id, alt_translation) 목록."""
    topic_k = _topic_key(topic)
    if not topic_k:
        return []

    load_base_sentences_from_csv(base_csv or DEFAULT_BASE_SENTENCES_CSV)
    from data.table_manager import get_base_sentences

    base_ids: set[int] = set()
    for row in get_base_sentences() or []:
        if _topic_key(row.topic) == topic_k:
            base_ids.add(int(row.id))

    if not base_ids:
        logger.warning("topic=%s 에 해당하는 base_sentences 없음", topic)
        return []

    path = Path(sub_csv or DEFAULT_SUB_SENTENCES_CSV)
    if not path.is_file():
        logger.warning("sub_sentences CSV 없음: %s", path)
        return []

    jobs: list[tuple[int, int, str]] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                base_id = int(float(str(row.get("base_id") or "").strip()))
            except (TypeError, ValueError):
                continue
            if base_id not in base_ids:
                continue
            try:
                sub_id = int(float(str(row.get("id") or "").strip()))
            except (TypeError, ValueError):
                continue
            if sub_id < 1:
                continue
            text = str(row.get("alt_translation") or "").strip()
            if not text:
                logger.debug("sub_id=%s: alt_translation 비어 있음, 스킵", sub_id)
                continue
            jobs.append((sub_id, base_id, text))

    jobs.sort(key=lambda x: x[0])
    return jobs


def list_conversation_topics_in_base_sentences() -> list[str]:
    load_base_sentences_from_csv(DEFAULT_BASE_SENTENCES_CSV)
    from data.table_manager import get_base_sentences

    topics: set[str] = set()
    for row in get_base_sentences() or []:
        t = (row.topic or "").strip()
        if t:
            topics.add(t)
    return sorted(topics)


def batch_build_conversation_sub_ko_for_topic(
    topic: str,
    *,
    tts: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    force_tts: bool = False,
    base_csv: str | Path | None = None,
    sub_csv: str | Path | None = None,
) -> tuple[int, int, int]:
    """topic에 속한 sub_sentences.alt_translation TTS 배치. Returns (ok, skip, fail)."""
    from audio.ko_narration import cached_cue_audio_usable, resolve_tts_provider

    jobs = collect_sub_translation_jobs_for_topic(
        topic, base_csv=base_csv, sub_csv=sub_csv
    )
    if not jobs:
        return 0, 0, 0

    out_dir = get_repo_root() / "resource" / "sound" / "sentense"
    out_dir.mkdir(parents=True, exist_ok=True)
    provider = resolve_tts_provider(tts, voice=tts_voice)

    ok = skip = fail = 0
    for sub_id, base_id, text in jobs:
        out = conversation_sub_ko_mp3_path(sub_id)
        if not force_tts and out.is_file() and cached_cue_audio_usable(out):
            skip += 1
            continue
        try:
            provider.synthesize(text, lang="ko", out_path=out)
            if cached_cue_audio_usable(out):
                ok += 1
                logger.info(
                    "sub_id=%s base_id=%s → %s (%s)",
                    sub_id,
                    base_id,
                    out.relative_to(get_repo_root()),
                    text[:48],
                )
            else:
                fail += 1
        except Exception as ex:
            fail += 1
            logger.exception("회화 sub TTS 실패 sub_id=%s: %s", sub_id, ex)

    return ok, skip, fail
