"""
sub_sentences 엑셀 → sub_sentences.csv 변환.
컬럼: id, base_id, target_slot_order, alt_word_id, main_slot, alt_translation, alt_sound_path.
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
    "base_id",
    "target_slot_order",
    "alt_word_id",
    "main_slot",
    "alt_translation",
    "alt_sound_path",
]


def _normalize(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _normalize_multi_pipe(value: Any) -> str:
    """다중 값 입력의 구분자를 파이프(|)로 통일한다."""
    text = _normalize(value)
    if not text:
        return ""
    return "|".join(part.strip() for part in text.replace(",", "|").split("|") if part.strip())


def _to_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def sub_sentences_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> str:
    """sub_sentences 엑셀을 읽어 sub_sentences.csv로 저장."""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    final_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        row_id = _to_int(row.get("id"), -1)
        base_id = _to_int(row.get("base_id"), -1)
        if row_id < 0 and base_id < 0:
            continue

        final_rows.append({
            "id": _to_int(row.get("id"), 0),
            "base_id": _to_int(row.get("base_id"), 0),
            # 다중 치환 구분자를 파이프(|)로 통일해 CSV 저장한다.
            "target_slot_order": _normalize_multi_pipe(row.get("target_slot_order")),
            "alt_word_id": _normalize_multi_pipe(row.get("alt_word_id")),
            "main_slot": _normalize(row.get("main_slot", "")),
            "alt_translation": _normalize(row.get("alt_translation", "")),
            "alt_sound_path": _normalize(row.get("alt_sound_path", "")),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("sub_sentences 엑셀 → CSV 저장: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
