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
    """세트에 속한 한국어 문장 1줄."""

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
        lines_map[sid].sort(key=lambda ln: (ln.seq, ln.id))

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


def get_cue_texts_for_set(set_id: int) -> list[str]:
    """세트 ID → ko_narration_lines 문장 목록(seq 순)."""
    _ensure_loaded()
    assert _lines_by_set_id is not None
    sid = int(set_id)
    if sid < 1:
        return []
    lines = _lines_by_set_id.get(sid) or []
    return [ln.text for ln in lines if ln.text.strip()]


def get_adjusted_srt_path_for_set(set_id: int) -> Path:
    """배치 산출 SRT 경로 (CSV 입력 없음). batch_ko_tts 후 resource/sound/shorts."""
    from audio.ko_narration import adjusted_srt_path_for_set

    return adjusted_srt_path_for_set(int(set_id))


def get_adjusted_srt_for_set(set_id: int) -> Optional[Path]:
    """배치로 생성된 adjusted SRT가 있으면 경로 반환."""
    path = get_adjusted_srt_path_for_set(set_id)
    return path if path.is_file() else None
