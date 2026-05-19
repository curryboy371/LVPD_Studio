"""
shorts_vocabulary_clips(숏츠·단어) 엑셀 → shorts_vocabulary_clips.csv 변환.

topic당 행 1개. word_id·hook_title는 | 로 복수 지정.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xls")

FIELDNAMES = [
    "id",
    "topic",
    "word_id",
    "hook_title",
    "ko_narration_id",
    "video_path",
    "sound_repeat_count",
    "after_sound_delay_sec",
]


def _normalize(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _to_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def shorts_vocabulary_clips_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> str:
    """단어 숏츠 엑셀을 CSV로 저장."""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    final_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        topic_row_id = _to_int(row.get("id"), 0)
        hook_title = _normalize(row.get("hook_title"))
        word_id_raw = _normalize(row.get("word_id"))
        if topic_row_id < 1 or not word_id_raw or not hook_title:
            continue
        final_rows.append({
            "id": topic_row_id,
            "topic": _normalize(row.get("topic")),
            "word_id": word_id_raw,
            "hook_title": hook_title,
            "ko_narration_id": _to_int(row.get("ko_narration_id"), 0),
            "video_path": _normalize(row.get("video_path")),
            "sound_repeat_count": _normalize(row.get("sound_repeat_count")),
            "after_sound_delay_sec": _normalize(row.get("after_sound_delay_sec")),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("shorts_vocabulary_clips → CSV: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
