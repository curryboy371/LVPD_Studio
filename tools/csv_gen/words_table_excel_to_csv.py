"""
words(단어 마스터) 엑셀 → words.csv 변환.
컬럼: id, word, pinyin, pos, meaning, img_path, sound_path.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xls")

FIELDNAMES = ["id", "word", "pinyin", "pos", "meaning", "img_path", "sound_path"]


def _normalize(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _to_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def words_table_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> str:
    """words 엑셀을 읽어 words.csv로 저장."""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    final_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        word = _normalize(row.get("word", ""))
        if not word and _to_int(row.get("id"), -1) < 0:
            continue

        final_rows.append({
            "id": _to_int(row.get("id"), 0),
            "word": word,
            "pinyin": _normalize(row.get("pinyin", "")),
            "pos": _normalize(row.get("pos", "")),
            "meaning": _normalize(row.get("meaning", "")),
            "img_path": _normalize(row.get("img_path", "")),
            "sound_path": _normalize(row.get("sound_path", "")),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("words 엑셀 → CSV 저장: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
