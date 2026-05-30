"""ko_narration_lines 엑셀 → CSV."""
from __future__ import annotations

import csv
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xls")

FIELDNAMES = ["id", "set_id", "text"]


def _normalize(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _merge_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """(set_id, id) 별 text 병합 — legacy seq 행은 ``\\n`` 으로 이어 붙인다."""
    buckets: dict[tuple[int, int], list[tuple[int, str]]] = defaultdict(list)
    for row in raw_rows:
        try:
            line_id = int(float(row.get("id") or "0"))
            set_id = int(float(row.get("set_id") or "0"))
        except (TypeError, ValueError):
            continue
        if line_id < 1 or set_id < 1:
            continue
        text = _normalize(row.get("text"))
        if not text:
            continue
        seq_raw = row.get("seq")
        try:
            seq = int(float(seq_raw)) if seq_raw not in (None, "") else 0
        except (TypeError, ValueError):
            seq = 0
        buckets[(set_id, line_id)].append((seq, text))

    final_rows: list[dict[str, Any]] = []
    for (set_id, line_id), items in sorted(buckets.items()):
        if len(items) == 1 and items[0][0] <= 0:
            merged_text = items[0][1]
        else:
            items.sort(key=lambda t: (t[0] if t[0] > 0 else 999999, t[1]))
            merged_text = "\n".join(t for _, t in items)
        if not merged_text:
            continue
        final_rows.append({"id": line_id, "set_id": set_id, "text": merged_text})
    return final_rows


def ko_narration_lines_excel_to_csv(
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
    raw_rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        raw_rows.append({str(k): row.get(k) for k in row.index})

    final_rows = _merge_rows(raw_rows)

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("ko_narration_lines → CSV: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
