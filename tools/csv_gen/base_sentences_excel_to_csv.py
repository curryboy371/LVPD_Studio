"""
base_sentences 엑셀 → base_sentences.csv 변환.
media는 플랫 컬럼: video_path, video_start_ms, video_end_ms, sound_lv1_path, sound_lv2_path.
수동 관리 편의를 위해 base_words('|') 컬럼을 함께 저장한다.
"""
from __future__ import annotations

import csv
import logging
import re
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
    "video_start_ms",
    "video_end_ms",
    "sound_lv1_path",
    "sound_lv2_path",
    "base_words",
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


def _extract_base_words(raw_sentence: str) -> str:
    """raw_sentence 중괄호 슬롯에서 base_words('|') 문자열을 만든다."""
    parts = [str(x).strip() for x in re.findall(r"\{([^}]*)\}", str(raw_sentence or "")) if str(x).strip()]
    return "|".join(parts)


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
        video_start_ms = _to_int(row.get("video_start_ms", row.get("video_start_ms")), 0)
        video_end_ms = _to_int(row.get("video_end_ms", row.get("video_end_ms")), 0)
        sound_lv1 = _normalize(row.get("sound_lv1_path", row.get("sound_level1_path", "")))
        sound_lv2 = _normalize(row.get("sound_lv2_path", row.get("sound_level2_path", "")))

        final_rows.append({
            "id": _to_int(row.get("id"), 0),
            "topic": _normalize(row.get("topic", "")),
            "raw_sentence": raw_sent,
            "translation": _normalize(row.get("translation", "")),
            "video_path": video_path,
            "video_start_ms": video_start_ms,
            "video_end_ms": video_end_ms,
            "sound_lv1_path": sound_lv1,
            "sound_lv2_path": sound_lv2,
            "base_words": _normalize(row.get("base_words", "")) or _extract_base_words(raw_sent),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("base_sentences 엑셀 → CSV 저장: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
