"""
base_sentences 엑셀 → base_sentences.csv 변환.
media는 플랫 컬럼: video_path, sound_lv_path.
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
    "raw_sentence",
    "translation",
    "video_path",
    "sound_lv_path",
    "tip",
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


def base_sentences_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> str:
    """base_sentences 엑셀을 읽어 플랫 media 컬럼으로 CSV 저장."""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    final_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        raw_sent = _normalize(row.get("raw_sentence", ""))
        if not raw_sent and _to_int(row.get("id"), -1) < 0:
            continue

        video_path = _normalize(row.get("video_path", ""))
        sound_lv = _normalize(
            row.get(
                "sound_lv_path",
                row.get(
                    "sound_level_path",
                    row.get("sound_lv1_path", row.get("sound_level1_path", "")),
                ),
            )
        )

        final_rows.append({
            "id": _to_int(row.get("id"), 0),
            "topic": _normalize(row.get("topic", "")),
            "raw_sentence": raw_sent,
            "translation": _normalize(row.get("translation", "")),
            "video_path": video_path,
            "sound_lv_path": sound_lv,
            "tip": _normalize(row.get("tip", row.get("life_tip", row.get("life_tips", "")))),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("base_sentences 엑셀 → CSV 저장: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
