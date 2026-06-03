"""
words(단어 마스터) 엑셀 → words.csv 변환.
컬럼: id, word, pinyin, masking, pos, type, meaning, en_meaning, tip, img_path, video_path, sound_path.

시트를 품사·용도별로 나눈 경우 `merge_all_sheets=True`로 모든 시트를 순서대로
한 CSV에 누적할 수 있다(배치 `python -m tools.csv_gen`는 words에 대해 기본 활성).
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from pandas import DataFrame

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xls")

FIELDNAMES = [
    "id",
    "word",
    "pinyin",
    "masking",
    "pos",
    "type",
    "meaning",
    "en_meaning",
    "tip",
    "img_path",
    "video_path",
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


def _rows_from_words_dataframe(df: DataFrame) -> list[dict[str, Any]]:
    """단어 시트 한 장을 FIELDNAMES 행 리스트로 변환."""
    df = df.dropna(axis=1, how="all")
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        word = _normalize(row.get("word", ""))
        if not word and _to_int(row.get("id"), -1) < 0:
            continue
        rows.append({
            "id": _to_int(row.get("id"), 0),
            "word": word,
            "pinyin": _normalize(row.get("pinyin", "")),
            "masking": _normalize(row.get("masking", "")),
            "pos": _normalize(row.get("pos", "")),
            "type": _normalize(row.get("type", "")),
            "meaning": _normalize(row.get("meaning", "")),
            "en_meaning": _normalize(row.get("en_meaning", "")),
            "tip": _normalize(row.get("tip", "")),
            "img_path": _normalize(row.get("img_path", "")),
            "video_path": _normalize(row.get("video_path", "")),
            "sound_path": _normalize(row.get("sound_path", "")),
        })
    return rows


def words_table_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
    *,
    merge_all_sheets: bool = False,
) -> str:
    """words 엑셀을 읽어 words.csv로 저장.

    Args:
        merge_all_sheets: True면 통합 문서의 **모든 시트**를 같은 컬럼 규칙으로 읽어
            한 CSV에 순서대로 누적한다(형용사/동사 등 시트 분리용).
            False면 기존과 같이 **첫 시트만** 사용한다.
    """
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    final_rows: list[dict[str, Any]] = []

    if merge_all_sheets:
        xls = pd.ExcelFile(path)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(path, sheet_name=sheet_name)
            if df is None or df.empty:
                logger.debug("words 시트 스킵(비어 있음): %s", sheet_name)
                continue
            chunk = _rows_from_words_dataframe(df)
            if chunk:
                logger.info("words 시트 %s → %d행 누적", sheet_name, len(chunk))
            final_rows.extend(chunk)
    else:
        df = pd.read_excel(path).dropna(axis=1, how="all")
        final_rows = _rows_from_words_dataframe(df)

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("words 엑셀 → CSV 저장: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
