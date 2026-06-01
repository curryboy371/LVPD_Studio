"""단어 외우기 — 한국어 뜻 + 한자(중국어) + 영문 en_meaning TTS 배치."""

from __future__ import annotations

import logging
from pathlib import Path

from audio.vocab_meaning_ko import batch_build_vocab_meaning_ko_for_word_ids
from audio.word_memorize_en import (
    DEFAULT_EN_TTS_VOICE,
    batch_build_word_memorize_en_for_word_ids,
    load_en_meaning_by_id,
)
from audio.word_memorize_zh import batch_build_word_memorize_zh_for_word_ids

logger = logging.getLogger(__name__)


def batch_build_word_memorize_tts_for_word_ids(
    word_ids: list[int],
    *,
    layout_label: str = "",
    gen_ko: bool = True,
    gen_zh: bool = True,
    gen_en: bool = True,
    tts_ko: str = "edge",
    tts_voice_ko: str = "ko-KR-SunHiNeural",
    tts_zh: str = "edge",
    tts_voice_zh: str = "zh-CN-XiaoxiaoNeural",
    tts_en: str = "edge",
    tts_voice_en: str = DEFAULT_EN_TTS_VOICE,
    force_tts: bool = False,
) -> tuple[int, int, int]:
    """word_id마다 선택한 KO/ZH/EN TTS. Returns (ok, skip, fail)."""
    if not word_ids:
        logger.warning("word_id 목록이 비어 있습니다.")
        return 0, 0, 1
    if not (gen_ko or gen_zh or gen_en):
        logger.warning("생성할 TTS 종류가 없습니다.")
        return 0, 0, 1

    en_by_id = load_en_meaning_by_id() if gen_en else {}
    label = layout_label or f"{len(word_ids)} words"

    ko_ok = ko_skip = ko_fail = 0
    zh_ok = zh_skip = zh_fail = 0
    en_ok = en_skip = en_fail = 0

    if gen_ko:
        ko_ok, ko_skip, ko_fail = batch_build_vocab_meaning_ko_for_word_ids(
            word_ids,
            tts=tts_ko,
            tts_voice=tts_voice_ko,
            force_tts=force_tts,
        )
    if gen_zh:
        zh_ok, zh_skip, zh_fail = batch_build_word_memorize_zh_for_word_ids(
            word_ids,
            tts=tts_zh,
            tts_voice=tts_voice_zh,
            force_tts=force_tts,
        )
    if gen_en:
        en_ok, en_skip, en_fail = batch_build_word_memorize_en_for_word_ids(
            word_ids,
            en_by_id,
            tts=tts_en,
            tts_voice=tts_voice_en,
            force_tts=force_tts,
        )

    ok = ko_ok + zh_ok + en_ok
    skip = ko_skip + zh_skip + en_skip
    fail = ko_fail + zh_fail + en_fail
    logger.info(
        "단어 외우기 TTS [%s] word_id %d개 — "
        "KO 생성=%d 스킵=%d 실패=%d | "
        "ZH 생성=%d 스킵=%d 실패=%d | "
        "EN 생성=%d 스킵=%d 실패=%d",
        label,
        len(word_ids),
        ko_ok,
        ko_skip,
        ko_fail,
        zh_ok,
        zh_skip,
        zh_fail,
        en_ok,
        en_skip,
        en_fail,
    )
    return ok, skip, fail


def batch_build_word_memorize_tts_for_layout(
    layout_path: str | Path,
    **kwargs,
) -> tuple[int, int, int]:
    """배치 JSON 경로 → word_id 수집 후 TTS."""
    from extra.table_editor.services.word_memorize_layouts import word_ids_from_layout

    path = Path(layout_path)
    word_ids = word_ids_from_layout(path)
    return batch_build_word_memorize_tts_for_word_ids(
        word_ids,
        layout_label=path.stem,
        **kwargs,
    )
