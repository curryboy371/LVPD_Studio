"""
vocabulary_word_rows(단어장 행) 엑셀 → vocabulary_word_rows.csv 변환.
컬럼: id, topic, word_id, pronunciation_mask, desc (table_manager / VocabularyWordRow 와 동일).
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xls")

FIELDNAMES = ["id", "topic", "word_id", "pronunciation_mask", "desc"]


def _normalize(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _to_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def vocabulary_word_rows_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> str:
    """vocabulary_word_rows 엑셀을 읽어 vocabulary_word_rows.csv로 저장."""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    final_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        wid = _to_int(row.get("word_id"), 0)
        if wid < 1:
            continue

        final_rows.append({
            "id": _to_int(row.get("id"), 0),
            "topic": _normalize(row.get("topic", "")),
            "word_id": wid,
            "pronunciation_mask": _normalize(row.get("pronunciation_mask", "")),
            "desc": _normalize(row.get("desc", "")),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("vocabulary_word_rows 엑셀 → CSV 저장: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
