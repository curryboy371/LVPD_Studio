"""ko_narration_sets 엑셀 → CSV."""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xls")

FIELDNAMES = ["id", "title", "tts", "tts_voice"]


def _normalize(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def ko_narration_sets_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> str:
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    final_rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            sid = int(float(row.get("id") or "0"))
        except (TypeError, ValueError):
            continue
        if sid < 1:
            continue
        final_rows.append({
            "id": sid,
            "title": _normalize(row.get("title")),
            "tts": _normalize(row.get("tts")).lower(),
            "tts_voice": _normalize(row.get("tts_voice")),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("ko_narration_sets → CSV: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
