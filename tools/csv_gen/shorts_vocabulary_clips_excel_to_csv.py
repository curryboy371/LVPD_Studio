"""
shorts_vocabulary_clips(숏츠·단어) 엑셀 → shorts_vocabulary_clips.csv 변환.
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
    "hook_image_path",
    "situation_subtitle",
    "cta_text",
    "ko_narration_id",
    "syllable_times_ms",
    "sound_path",
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
        clip_id = _to_int(row.get("id"), 0)
        word_id = _to_int(row.get("word_id"), 0)
        hook_title = _normalize(row.get("hook_title"))
        if clip_id < 1 or word_id < 1 or not hook_title:
            continue
        final_rows.append({
            "id": clip_id,
            "topic": _normalize(row.get("topic")),
            "word_id": word_id,
            "hook_title": hook_title,
            "hook_image_path": _normalize(row.get("hook_image_path")),
            "situation_subtitle": _normalize(row.get("situation_subtitle")),
            "cta_text": _normalize(row.get("cta_text")),
            "ko_narration_id": _to_int(row.get("ko_narration_id"), 0),
            "syllable_times_ms": _normalize(row.get("syllable_times_ms")),
            "sound_path": _normalize(row.get("sound_path")),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("shorts_vocabulary_clips → CSV: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
