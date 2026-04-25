"""
sentence_word_map 엑셀 → sentence_word_map.csv 변환.
Deprecated: 3테이블 운영(base_sentences/words/sub_sentences)에서는 기본 파이프라인에서 사용하지 않는다.
컬럼: sentence_id, word_id, slot_order, is_clickable, is_slot_target.
is_clickable / is_slot_target 는 CSV에 true/false 또는 1/0 로 저장.
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
    "sentence_id",
    "word_id",
    "slot_order",
    "is_clickable",
    "is_slot_target",
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


def _to_bool_csv(val: Any) -> str:
    """엑셀/입력 값을 CSV용 'true'/'false' 문자열로."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "false"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return "true" if val else "false"
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "y"):
        return "true"
    return "false"


def sentence_word_map_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> str:
    """sentence_word_map 엑셀을 읽어 sentence_word_map.csv로 저장."""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    final_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        sentence_id = _to_int(row.get("sentence_id"), -1)
        word_id = _to_int(row.get("word_id"), -1)
        if sentence_id < 0 and word_id < 0:
            continue

        final_rows.append({
            "sentence_id": _to_int(row.get("sentence_id"), 0),
            "word_id": _to_int(row.get("word_id"), 0),
            "slot_order": _to_int(row.get("slot_order"), 0),
            "is_clickable": _to_bool_csv(row.get("is_clickable", True)),
            "is_slot_target": _to_bool_csv(row.get("is_slot_target", False)),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("sentence_word_map 엑셀 → CSV 저장: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
