"""한국어 내레이션 전용 테이블 로드·조회 (sets + lines)."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.paths import (
    DEFAULT_KO_NARRATION_LINES_CSV,
    DEFAULT_KO_NARRATION_SETS_CSV,
)

logger = logging.getLogger(__name__)

_sets_by_id: dict[int, "KoNarrationSet"] | None = None
_lines_by_set_id: dict[int, list["KoNarrationLine"]] | None = None


@dataclass(frozen=True)
class KoNarrationSet:
    """내레이션 세트(숏츠 클립이 ko_narration_id로 참조)."""

    id: int
    title: str
    tts: str
    tts_voice: str


@dataclass(frozen=True)
class KoNarrationLine:
    """세트에 속한 멘트 1행.

    - ``set_id``: ``ko_narration_sets.id``
    - ``id``: 같은 세트 안 **멘트 번호**(1·2·3…). script ``ko:1`` 과 대응.
    - ``text``: TTS 큐 텍스트. ``\\n`` 으로 여러 큐를 구분.
    """

    id: int
    set_id: int
    text: str


@dataclass(frozen=True)
class KoNarrationCue:
    """멘트 1행에서 분리된 TTS 큐 1개."""

    ment_id: int
    set_id: int
    segment: int
    text: str


def _normalize_multiline_text(value: str) -> str:
    if not value:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text and "\\n" in text:
        text = text.replace("\\n", "\n")
    return text


def split_ko_line_text(text: str) -> list[str]:
    """멘트 text → TTS 큐 목록 (``\\n`` 구분)."""
    raw = _normalize_multiline_text(text)
    if not raw:
        return []
    return [ln.strip() for ln in raw.split("\n") if ln.strip()]


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        logger.warning("CSV 없음: %s", path)
        return []
    rows: list[dict[str, str]] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    (k or "").strip(): (v or "").strip() if isinstance(v, str) else str(v or "").strip()
                    for k, v in row.items()
                }
            )
    return rows


def _merge_line_rows(rows: list[dict[str, str]]) -> dict[int, list[KoNarrationLine]]:
    """CSV 행 → set_id별 KoNarrationLine (legacy seq 행 병합)."""
    buckets: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for row in rows:
        try:
            line_id = int(float(row.get("id") or "0"))
            set_id = int(float(row.get("set_id") or "0"))
        except (TypeError, ValueError):
            continue
        if set_id < 1 or line_id < 1:
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        seq_raw = (row.get("seq") or "").strip()
        try:
            seq = int(float(seq_raw)) if seq_raw else 0
        except (TypeError, ValueError):
            seq = 0
        buckets.setdefault((set_id, line_id), []).append((seq, text))

    lines_map: dict[int, list[KoNarrationLine]] = {}
    for (set_id, line_id), items in buckets.items():
        if len(items) == 1 and items[0][0] <= 0:
            merged = items[0][1]
        else:
            items.sort(key=lambda t: (t[0] if t[0] > 0 else 999999, t[1]))
            merged = "\n".join(t for _, t in items)
        if not merged.strip():
            continue
        lines_map.setdefault(set_id, []).append(
            KoNarrationLine(id=line_id, set_id=set_id, text=merged)
        )

    for sid in lines_map:
        lines_map[sid].sort(key=lambda ln: ln.id)
    return lines_map


def load_ko_narration_tables(
    *,
    sets_csv: str | Path | None = None,
    lines_csv: str | Path | None = None,
) -> None:
    """ko_narration_sets / ko_narration_lines CSV를 메모리에 로드."""
    global _sets_by_id, _lines_by_set_id
    sets_path = Path(sets_csv) if sets_csv else DEFAULT_KO_NARRATION_SETS_CSV
    lines_path = Path(lines_csv) if lines_csv else DEFAULT_KO_NARRATION_LINES_CSV

    sets: dict[int, KoNarrationSet] = {}
    for row in _read_csv_rows(sets_path):
        try:
            sid = int(float(row.get("id") or "0"))
        except (TypeError, ValueError):
            continue
        if sid < 1:
            continue
        sets[sid] = KoNarrationSet(
            id=sid,
            title=(row.get("title") or "").strip(),
            tts=(row.get("tts") or "").strip().lower(),
            tts_voice=(row.get("tts_voice") or "").strip(),
        )

    _sets_by_id = sets
    _lines_by_set_id = _merge_line_rows(_read_csv_rows(lines_path))
    logger.info(
        "ko_narration 테이블 로드: sets=%d, lines_sets=%d",
        len(sets),
        len(_lines_by_set_id),
    )


def _ensure_loaded() -> None:
    if _sets_by_id is None or _lines_by_set_id is None:
        load_ko_narration_tables()


def get_ko_narration_set(set_id: int) -> Optional[KoNarrationSet]:
    _ensure_loaded()
    assert _sets_by_id is not None
    return _sets_by_id.get(int(set_id))


def get_ko_narration_lines_for_set(set_id: int) -> list[KoNarrationLine]:
    """세트 ID → 멘트 행 (id 순)."""
    _ensure_loaded()
    assert _lines_by_set_id is not None
    sid = int(set_id)
    if sid < 1:
        return []
    return list(_lines_by_set_id.get(sid) or [])


def get_ko_narration_line(set_id: int, ment_id: int) -> Optional[KoNarrationLine]:
    for line in get_ko_narration_lines_for_set(set_id):
        if int(line.id) == int(ment_id):
            return line
    return None


def get_ko_narration_cues_for_ment(set_id: int, ment_id: int) -> list[KoNarrationCue]:
    """세트·멘트 id → ``\\n`` 으로 나뉜 TTS 큐 목록."""
    line = get_ko_narration_line(set_id, ment_id)
    if line is None:
        return []
    segments = split_ko_line_text(line.text)
    return [
        KoNarrationCue(
            ment_id=int(line.id),
            set_id=int(line.set_id),
            segment=i + 1,
            text=seg,
        )
        for i, seg in enumerate(segments)
    ]


def get_ko_narration_lines_for_ment(set_id: int, ment_id: int) -> list[KoNarrationCue]:
    """(호환) 멘트 id → TTS 큐 목록."""
    return get_ko_narration_cues_for_ment(set_id, ment_id)


def get_ko_narration_ments_for_set(set_id: int) -> list[list[KoNarrationCue]]:
    """세트 ID → 멘트별 큐 묶음."""
    return [
        get_ko_narration_cues_for_ment(set_id, int(line.id))
        for line in get_ko_narration_lines_for_set(set_id)
    ]


def ko_cue_index_for_line(set_id: int, *, ment_id: int, seq: int) -> int:
    """TTS plan cues 배열 인덱스. ``seq`` = 멘트 내 segment(1부터)."""
    return ko_cue_index_for_segment(set_id, ment_id=ment_id, segment=seq)


def ko_cue_index_for_segment(set_id: int, *, ment_id: int, segment: int) -> int:
    """TTS plan cues 배열 인덱스 (정렬: ment id → segment). 없으면 -1."""
    target_segment = max(1, int(segment))
    index = 0
    for line in get_ko_narration_lines_for_set(set_id):
        segments = split_ko_line_text(line.text)
        if int(line.id) == int(ment_id):
            if 1 <= target_segment <= len(segments):
                return index + (target_segment - 1)
            return -1
        index += len(segments)
    return -1


def get_cue_texts_for_set(set_id: int) -> list[str]:
    """세트 ID → TTS 큐 텍스트 (멘트 id 순, 각 멘트는 ``\\n`` segment 순)."""
    texts: list[str] = []
    for line in get_ko_narration_lines_for_set(set_id):
        texts.extend(split_ko_line_text(line.text))
    return texts


def get_adjusted_srt_path_for_set(set_id: int) -> Path:
    """배치 산출 SRT 경로 (CSV 입력 없음). batch_ko_tts 후 resource/sound/shorts."""
    from audio.ko_narration import adjusted_srt_path_for_set

    return adjusted_srt_path_for_set(int(set_id))


def get_adjusted_srt_for_set(set_id: int) -> Optional[Path]:
    """배치로 생성된 adjusted SRT가 있으면 경로 반환."""
    path = get_adjusted_srt_path_for_set(set_id)
    return path if path.is_file() else None
