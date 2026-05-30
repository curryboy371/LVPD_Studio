"""숏츠 회화: ko_narration_lines + sub_sentence_id 재생 단계."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from core.paths import (
    DEFAULT_BASE_SENTENCES_CSV,
    DEFAULT_SUB_SENTENCES_CSV,
    DEFAULT_WORDS_TABLE_CSV,
    get_repo_root,
)
from data.ko_narration_loader import (
    KoNarrationLine,
    get_ko_narration_lines_for_ment,
    ko_cue_index_for_line,
    load_ko_narration_tables,
)
from studio.conversation.data_loading import (
    _attach_sub_variants_to_base_rows,
    _load_base_sentences_csv,
    _load_sub_sentences_csv,
    _load_words_and_meanings_csv,
    _raw_sentence_to_display,
)

logger = logging.getLogger(__name__)


def parse_pipe_ints(raw: str) -> list[int]:
    """``1|2|3`` → [1, 2, 3]."""
    out: list[int] = []
    seen: set[int] = set()
    for part in str(raw or "").replace("，", "|").split("|"):
        s = part.strip()
        if not s:
            continue
        try:
            n = int(float(s))
        except (TypeError, ValueError):
            logger.warning("pipe 정수 파싱 실패: %s", part)
            continue
        if n < 1 or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def parse_sub_sentence_ids(row: dict[str, str]) -> list[int]:
    """클립 CSV ``sub_sentence_id`` (레거시 ``script`` 의 sub: 만)."""
    raw = (row.get("sub_sentence_id") or "").strip()
    if raw:
        return parse_pipe_ints(raw)
    legacy = (row.get("script") or "").strip()
    if not legacy:
        return []
    ids: list[int] = []
    for part in legacy.replace("，", "|").split("|"):
        token = part.strip().lower()
        if token.startswith("sub:"):
            try:
                ids.append(int(token.split(":", 1)[1].strip()))
            except (TypeError, ValueError, IndexError):
                pass
    return ids


def _ko_step_from_line(line: KoNarrationLine, *, set_id: int) -> dict[str, Any]:
    ment_id = int(line.id)
    seq = int(line.seq)
    return {
        "kind": "ko",
        "ment_id": ment_id,
        "seq": seq,
        "cue_index": ko_cue_index_for_line(set_id, ment_id=ment_id, seq=seq),
        "line_text": line.text,
    }


def _cn_steps_from_clip_row(row: dict[str, str]) -> list[dict[str, Any]]:
    """중국어: ``sub_sentence_id`` 목록만 (``base_id``는 주제·슬롯 조합용)."""
    return [
        {"kind": "sub", "sub_id": sub_id}
        for sub_id in parse_sub_sentence_ids(row)
    ]


def _resolve_ment_ids_for_subs(
    row: dict[str, str],
    *,
    sub_count: int,
) -> list[int]:
    """i번째 sub 에 붙일 ``ko_narration_lines.id`` 목록."""
    raw = (row.get("ko_narration_line_id") or "").strip()
    if raw:
        return parse_pipe_ints(raw)
    return list(range(1, max(1, int(sub_count)) + 1))


def _build_ko_then_sub_steps(
    *,
    set_id: int,
    sub_ids: list[int],
    ment_ids: list[int],
) -> list[dict[str, Any]]:
    """``sub_sentence_id`` 각각: 한국어 TTS(멘트 전체 seq) → 중국어 mp3."""
    out: list[dict[str, Any]] = []
    for i, sub_id in enumerate(sub_ids):
        mid = ment_ids[i] if i < len(ment_ids) else (i + 1)
        lines = get_ko_narration_lines_for_ment(set_id, ment_id=mid)
        if not lines:
            logger.warning(
                "ko_narration_lines set_id=%s: ment_id=%s 없음 — sub %s 는 중국어만",
                set_id,
                mid,
                sub_id,
            )
        for line in lines:
            out.append(_ko_step_from_line(line, set_id=set_id))
        out.append({"kind": "sub", "sub_id": int(sub_id)})
    return out


def _resolve_explicit_ko_script(
    row: dict[str, str],
    *,
    set_id: int,
) -> Optional[list[dict[str, Any]]]:
    """레거시 script=ko:1|base|ko:2|sub:2 — 있으면 그대로 사용."""
    legacy = (row.get("script") or "").strip()
    if not legacy or "ko:" not in legacy.lower():
        return None
    out: list[dict[str, Any]] = []
    for part in legacy.replace("，", "|").split("|"):
        token = part.strip().lower()
        if not token:
            continue
        if token == "base":
            out.append({"kind": "base"})
            continue
        if token.startswith("ko:"):
            try:
                ment_id = int(token.split(":", 1)[1].strip())
            except (TypeError, ValueError, IndexError):
                continue
            lines = get_ko_narration_lines_for_ment(set_id, ment_id)
            for line in lines:
                out.append(_ko_step_from_line(line, set_id=set_id))
            continue
        if token.startswith("sub:"):
            try:
                out.append({"kind": "sub", "sub_id": int(token.split(":", 1)[1].strip())})
            except (TypeError, ValueError, IndexError):
                pass
    return out if out else None


def _resolve_path(repo: Path, raw: str) -> str:
    p = (raw or "").strip()
    if not p:
        return ""
    if Path(p).is_absolute():
        return p
    return str(repo / p.replace("\\", "/"))


def _find_sub_row(base_id: int, sub_id: int) -> Optional[dict[str, Any]]:
    grouped = _load_sub_sentences_csv(str(DEFAULT_SUB_SENTENCES_CSV))
    for row in grouped.get(int(base_id), []):
        try:
            if int(row.get("id") or 0) == int(sub_id):
                return row
        except (TypeError, ValueError):
            continue
    return None


def _base_csv_row(base_id: int) -> Optional[dict[str, str]]:
    for row in _load_base_sentences_csv(str(DEFAULT_BASE_SENTENCES_CSV)):
        try:
            if int(float(row.get("id") or 0)) == int(base_id):
                return row
        except (TypeError, ValueError):
            continue
    return None


def build_sub_step_payload(
    *,
    base_id: int,
    sub_id: int,
    repo: Path,
) -> Optional[dict[str, Any]]:
    sub_row = _find_sub_row(int(base_id), int(sub_id))
    if sub_row is None:
        logger.warning("sub_sentences base_id=%s id=%s 없음", base_id, sub_id)
        return None

    base_row = _base_csv_row(base_id)
    if base_row is None:
        return None

    words_by_id, meanings_by_id, maskings_by_id, pinyins_by_id = _load_words_and_meanings_csv(
        str(DEFAULT_WORDS_TABLE_CSV)
    )
    attached = _attach_sub_variants_to_base_rows(
        [dict(base_row)],
        words_by_id=words_by_id,
        meanings_by_id=meanings_by_id,
        maskings_by_id=maskings_by_id,
        pinyins_by_id=pinyins_by_id,
        sub_rows_by_base_id={int(base_id): [sub_row]},
    )
    variants = attached[0].get("sub_variants") if attached else None
    if not variants:
        return None
    variant = variants[0] if isinstance(variants[0], dict) else {}
    display = str(variant.get("replaced_sentence") or "").strip()
    if not display:
        display = _raw_sentence_to_display(str(base_row.get("raw_sentence") or ""))
    translation = str(variant.get("alt_translation") or "").strip()
    pinyin = (
        str(variant.get("pinyin_marks") or variant.get("pinyin") or "").strip()
    )
    from core.paths import resolve_conversation_sub_cn_sound_path

    sound_raw = str(variant.get("alt_sound_path") or "").strip()
    resolved = resolve_conversation_sub_cn_sound_path(sound_raw)
    sound_path = _resolve_path(repo, str(resolved) if resolved else sound_raw)
    payload: dict[str, Any] = {
        "sentence": [display] if display else [],
        "translation": [translation] if translation else [],
        "pinyin": pinyin,
        "sound_path": sound_path,
    }
    for key in (
        "main_word_id",
        "main_word_img_path",
        "main_word_hanzi",
        "main_word_pinyin",
        "main_word_meaning",
    ):
        val = variant.get(key)
        if val:
            payload[key] = val
    return payload


def _materialize_cn_steps(
    steps: list[dict[str, Any]],
    *,
    base_id: int,
    repo: Path,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in steps:
        kind = step.get("kind")
        if kind == "ko":
            out.append(step)
        elif kind == "base":
            out.append({"kind": "base"})
        elif kind == "sub":
            sub_id = int(step["sub_id"])
            payload = build_sub_step_payload(base_id=base_id, sub_id=sub_id, repo=repo)
            if payload is None:
                logger.warning(
                    "sub_sentence_id %s 스킵 (clip base_id=%s)",
                    sub_id,
                    base_id,
                )
                continue
            out.append({"kind": "sub", "sub_id": sub_id, **payload})
    return out


def build_conv_playback_steps(
    row: dict[str, str],
    *,
    base_id: int,
    ko_narration_id: int,
    repo: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """클립 CSV → 재생 단계.

    - ``base_id`` = 주제·``sub_sentences`` 슬롯 조합용 (``base_sentences`` 직접 재생 안 함)
    - ``sub_sentence_id`` = ``1|2|3`` → 재생할 ``sub_sentences.id`` (``base_id``와 동일 base)
    - ``ko_narration_line_id`` = 멘트 id 목록. 비우면 **1..sub개수** 순서로 멘트 매칭
    - 재생(각 sub): 한국어 TTS(해당 멘트의 seq 전부) → ``sub_sentence_id`` 중국어 mp3
    """
    repo = repo or get_repo_root()
    load_ko_narration_tables()
    set_id = int(ko_narration_id or 0)

    if set_id < 1:
        logger.warning("conv: ko_narration_id 없음")
        return []

    legacy = _resolve_explicit_ko_script(row, set_id=set_id)
    if legacy is not None:
        return _materialize_cn_steps(legacy, base_id=base_id, repo=repo)

    cn_steps = _cn_steps_from_clip_row(row)
    if not cn_steps:
        logger.warning(
            "conv: sub_sentence_id 없음 (base_id=%s는 주제만, 재생 문장은 sub 지정)",
            base_id,
        )
        return []

    sub_ids = [int(s["sub_id"]) for s in cn_steps]
    ment_ids = _resolve_ment_ids_for_subs(row, sub_count=len(sub_ids))
    if len(ment_ids) > len(sub_ids):
        logger.warning(
            "conv: 멘트 %d개 > sub %d개 — 앞쪽만 사용 (base_id=%s)",
            len(ment_ids),
            len(sub_ids),
            base_id,
        )
        ment_ids = ment_ids[: len(sub_ids)]

    merged = _build_ko_then_sub_steps(
        set_id=set_id,
        sub_ids=sub_ids,
        ment_ids=ment_ids,
    )
    return _materialize_cn_steps(merged, base_id=base_id, repo=repo)
