"""한국어 내레이션 전용 테이블 로드·조회 (sets + lines)."""
from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.paths import (
    DEFAULT_KO_NARRATION_LINES_CSV,
    DEFAULT_KO_NARRATION_SETS_CSV,
    get_repo_root,
)

logger = logging.getLogger(__name__)

_sets_by_id: dict[int, "KoNarrationSet"] | None = None
_lines_by_set_id: dict[int, list["KoNarrationLine"]] | None = None


@dataclass(frozen=True)
class KoNarrationSet:
    """내레이션 세트(숏츠 클립이 ko_narration_id로 참조)."""

    id: int
    title: str
    srt_path: str


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


def _resolve_repo_path(raw: str) -> str:
    p = (raw or "").strip()
    if not p:
        return ""
    path = Path(p)
    if not path.is_absolute():
        path = get_repo_root() / p
    return str(path.resolve()) if path.is_file() else p.replace("\\", "/")


def load_ko_narration_tables(
    *,
    sets_csv: str | Path | None = None,
    lines_csv: str | Path | None = None,
) -> None:
    """ko_narration_sets / ko_narration_lines CSV를 메모리에 로드."""
    global _sets_by_id, _lines_by_set_id
    sets_path = Path(sets_csv) if sets_csv else DEFAULT_KO_NARRATION_SETS_CSV
    lines_path = Path(lines_csv) if lines_csv else DEFAULT_KO_NARRATION_LINES_CSV
    repo = get_repo_root()

    sets: dict[int, KoNarrationSet] = {}
    for row in _read_csv_rows(sets_path):
        try:
            sid = int(float(row.get("id") or "0"))
        except (TypeError, ValueError):
            continue
        if sid < 1:
            continue
        srt = (row.get("srt_path") or "").strip()
        if srt and "/" not in srt and "\\" not in srt:
            srt = str((repo / srt).resolve()) if (repo / srt).is_file() else srt
        elif srt:
            srt = _resolve_repo_path(srt)
        sets[sid] = KoNarrationSet(
            id=sid,
            title=(row.get("title") or "").strip(),
            srt_path=srt,
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
    """세트 ID → TTS·자막용 문장 목록. srt_path 우선, 없으면 lines 테이블."""
    _ensure_loaded()
    assert _sets_by_id is not None
    assert _lines_by_set_id is not None
    sid = int(set_id)
    if sid < 1:
        return []

    ko_set = _sets_by_id.get(sid)
    srt_path = (ko_set.srt_path if ko_set else "") or ""
    if srt_path:
        path = Path(srt_path)
        if not path.is_file():
            path = get_repo_root() / srt_path
        if path.is_file():
            try:
                import pysrt

                subs = pysrt.open(str(path), encoding="utf-8")
                texts = [
                    re.sub(r"\s+", " ", (sub.text or "").replace("\n", " ")).strip()
                    for sub in subs
                ]
                return [t for t in texts if t]
            except Exception as ex:
                logger.warning("ko set srt 파싱 실패 set_id=%s: %s", sid, ex)

    lines = _lines_by_set_id.get(sid) or []
    return [ln.text for ln in lines if ln.text.strip()]
