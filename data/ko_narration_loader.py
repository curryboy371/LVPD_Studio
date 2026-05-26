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
    """세트에 속한 한국어 TTS 1큐.

    - ``set_id``: ``ko_narration_sets.id``
    - ``id``: 같은 세트 안 **멘트 번호**(1·2·3…). script ``ko:1`` 과 대응.
    - ``seq``: **같은 멘트(id)** 를 여러 큐로 나눌 때 순서(1부터).
    """

    id: int
    set_id: int
    seq: int
    text: str


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

    lines_map: dict[int, list[KoNarrationLine]] = {}
    for row in _read_csv_rows(lines_path):
        try:
            line_id = int(float(row.get("id") or "0"))
            set_id = int(float(row.get("set_id") or "0"))
            seq = int(float(row.get("seq") or "0"))
        except (TypeError, ValueError):
            continue
        if set_id < 1 or line_id < 1:
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        lines_map.setdefault(set_id, []).append(
            KoNarrationLine(id=line_id, set_id=set_id, seq=seq, text=text)
        )

    for sid in lines_map:
        lines_map[sid].sort(key=lambda ln: (ln.id, ln.seq))

    _sets_by_id = sets
    _lines_by_set_id = lines_map
    logger.info(
        "ko_narration 테이블 로드: sets=%d, lines_sets=%d",
        len(sets),
        len(lines_map),
    )


def _ensure_loaded() -> None:
    if _sets_by_id is None or _lines_by_set_id is None:
        load_ko_narration_tables()


def get_ko_narration_set(set_id: int) -> Optional[KoNarrationSet]:
    _ensure_loaded()
    assert _sets_by_id is not None
    return _sets_by_id.get(int(set_id))


def get_ko_narration_lines_for_set(set_id: int) -> list[KoNarrationLine]:
    """세트 ID → 전체 행 (멘트 id, seq 순)."""
    _ensure_loaded()
    assert _lines_by_set_id is not None
    sid = int(set_id)
    if sid < 1:
        return []
    return list(_lines_by_set_id.get(sid) or [])


def get_ko_narration_ments_for_set(set_id: int) -> list[list[KoNarrationLine]]:
    """세트 ID → 멘트별 큐 묶음. 각 멘트는 id 동일·seq 오름차순."""
    lines = get_ko_narration_lines_for_set(set_id)
    if not lines:
        return []
    ments: list[list[KoNarrationLine]] = []
    current_id: Optional[int] = None
    bucket: list[KoNarrationLine] = []
    for line in lines:
        if current_id is None:
            current_id = int(line.id)
            bucket = [line]
            continue
        if int(line.id) != current_id:
            ments.append(bucket)
            current_id = int(line.id)
            bucket = [line]
        else:
            bucket.append(line)
    if bucket:
        ments.append(bucket)
    return ments


def get_ko_narration_lines_for_ment(set_id: int, ment_id: int) -> list[KoNarrationLine]:
    """세트·멘트 id → 해당 멘트의 모든 seq 행."""
    return [
        ln
        for ln in get_ko_narration_lines_for_set(set_id)
        if int(ln.id) == int(ment_id)
    ]


def ko_cue_index_for_line(set_id: int, *, ment_id: int, seq: int) -> int:
    """TTS plan cues 배열 인덱스 (정렬: id, seq). 없으면 -1."""
    for i, ln in enumerate(get_ko_narration_lines_for_set(set_id)):
        if int(ln.id) == int(ment_id) and int(ln.seq) == int(seq):
            return i
    return -1


def get_ko_narration_line_by_seq(set_id: int, seq: int) -> Optional[KoNarrationLine]:
    """(호환) 세트 내 seq 단독 검색 — 멘트가 여러 개면 모호. ``get_ko_narration_lines_for_ment`` 권장."""
    matches = [
        ln for ln in get_ko_narration_lines_for_set(set_id) if int(ln.seq) == int(seq)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def get_cue_texts_for_set(set_id: int) -> list[str]:
    """세트 ID → TTS 큐 텍스트 (멘트 id·seq 순)."""
    return [ln.text for ln in get_ko_narration_lines_for_set(set_id) if ln.text.strip()]


def get_adjusted_srt_path_for_set(set_id: int) -> Path:
    """배치 산출 SRT 경로 (CSV 입력 없음). batch_ko_tts 후 resource/sound/shorts."""
    from audio.ko_narration import adjusted_srt_path_for_set

    return adjusted_srt_path_for_set(int(set_id))


def get_adjusted_srt_for_set(set_id: int) -> Optional[Path]:
    """배치로 생성된 adjusted SRT가 있으면 경로 반환."""
    path = get_adjusted_srt_path_for_set(set_id)
    return path if path.is_file() else None
