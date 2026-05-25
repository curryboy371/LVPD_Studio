"""회화 모드: topic별 sub_sentences.alt_translation → 한국어 TTS mp3."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from core.paths import (
    CONVERSATION_SUB_KO_SOUND_DIR,
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


def base_ids_for_topic(
    topic: str,
    *,
    base_csv: str | Path | None = None,
) -> set[int]:
    """base_sentences.topic 이 일치하는 base_id 집합."""
    topic_k = _topic_key(topic)
    if not topic_k:
        return set()
    load_base_sentences_from_csv(base_csv or DEFAULT_BASE_SENTENCES_CSV)
    from data.table_manager import get_base_sentences

    out: set[int] = set()
    for row in get_base_sentences() or []:
        if _topic_key(row.topic) == topic_k:
            out.add(int(row.id))
    return out


def purge_conversation_sub_ko_for_topic(
    topic: str,
    *,
    base_csv: str | Path | None = None,
) -> int:
    """topic 소속 base_id 의 ko_sub_{base_id}_*.mp3 만 삭제 (다른 topic 파일은 유지)."""
    base_ids = base_ids_for_topic(topic, base_csv=base_csv)
    if not base_ids:
        logger.warning("topic=%s: 삭제할 base_sentences 없음", topic)
        return 0

    deleted = 0
    for base_id in sorted(base_ids):
        pattern = f"ko_sub_{int(base_id)}_*.mp3"
        for path in CONVERSATION_SUB_KO_SOUND_DIR.glob(pattern):
            try:
                path.unlink()
                deleted += 1
                logger.info(
                    "삭제 %s",
                    path.relative_to(get_repo_root()),
                )
            except OSError as ex:
                logger.warning("삭제 실패 %s: %s", path, ex)
    return deleted


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
    rebuild: bool = True,
    base_csv: str | Path | None = None,
    sub_csv: str | Path | None = None,
) -> tuple[int, int, int]:
    """topic에 속한 sub_sentences.alt_translation TTS 배치. Returns (ok, skip, fail).

    기본(rebuild=True): 해당 topic base_id 의 ko_sub_{base_id}_*.mp3 삭제 후 전부 재생성.
    rebuild=False, force_tts=False: 기존 mp3 있으면 스킵.
    force_tts=True, rebuild=False: 삭제 없이 덮어쓰기만.
    """
    from audio.ko_narration import cached_cue_audio_usable, resolve_tts_provider

    if rebuild:
        n = purge_conversation_sub_ko_for_topic(topic, base_csv=base_csv)
        logger.info("topic=%s: 기존 mp3 %d개 삭제 후 재생성", topic, n)
        force_tts = True

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
        out = conversation_sub_ko_mp3_path(base_id, sub_id)
        if not force_tts and out.is_file() and cached_cue_audio_usable(out):
            skip += 1
            continue
        try:
            provider.synthesize(text, lang="ko", out_path=out)
            if cached_cue_audio_usable(out):
                ok += 1
                logger.info(
                    "base_id=%s sub_id=%s → %s (%s)",
                    base_id,
                    sub_id,
                    out.relative_to(get_repo_root()),
                    text[:48],
                )
            else:
                fail += 1
        except Exception as ex:
            fail += 1
            logger.exception("회화 sub TTS 실패 sub_id=%s: %s", sub_id, ex)

    return ok, skip, fail
