"""ko_narration_lines: legacy seq 행 병합 · 단일 id 모델 정규화."""
from __future__ import annotations

from pathlib import Path

from extra.table_editor.services.search import (
    _numeric_field_key,
    sort_ko_narration_lines_by_id,
)

def _seq_sort_key(row: dict[str, str]) -> tuple[int, float | int | str]:
    return _numeric_field_key(row.get("seq", ""), text_fallback="999999")


def normalize_ko_narration_line_rows(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """(set_id, id) 당 1행. legacy seq 행은 text를 ``\\n`` 으로 합친다."""
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        sid = (row.get("set_id") or "").strip()
        lid = (row.get("id") or "").strip()
        if not sid or not lid:
            continue
        groups.setdefault((sid, lid), []).append(dict(row))

    merged: list[dict[str, str]] = []
    for (_sid, _lid), group in groups.items():
        sid = (group[0].get("set_id") or "").strip()
        lid = (group[0].get("id") or "").strip()
        if len(group) == 1 and not (group[0].get("seq") or "").strip():
            text = (group[0].get("text") or "").strip()
        else:
            ordered = sorted(group, key=_seq_sort_key)
            parts = [
                (r.get("text") or "").strip()
                for r in ordered
                if (r.get("text") or "").strip()
            ]
            text = "\n".join(parts)
        if not text:
            continue
        merged.append({"id": lid, "set_id": sid, "text": text})

    return sort_ko_narration_lines_by_id(merged)


def rows_need_ko_line_merge(rows: list[dict[str, str]]) -> bool:
    """seq 열이 있거나 (set_id, id) 중복이면 병합 필요."""
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if (row.get("seq") or "").strip():
            return True
        sid = (row.get("set_id") or "").strip()
        lid = (row.get("id") or "").strip()
        if not sid or not lid:
            continue
        key = (sid, lid)
        if key in seen:
            return True
        seen.add(key)
    return False


def read_ko_line_rows_from_excel(path: Path) -> list[dict[str, str]]:
    """엑셀의 모든 열을 읽는다 (legacy ``seq`` 병합용)."""
    import pandas as pd

    from extra.table_editor.data.workbook import cell_to_str, normalize_id_display

    df = pd.read_excel(path).dropna(axis=1, how="all")
    rows: list[dict[str, str]] = []
    for _, series in df.iterrows():
        row: dict[str, str] = {}
        for col in series.index:
            col_s = str(col).strip()
            val = series[col]
            row[col_s] = (
                normalize_id_display(val) if col_s == "id" else cell_to_str(val)
            )
        rows.append(row)
    return rows


def ko_line_rows_for_editor(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """편집기/저장용 id·set_id·text 만."""
    normalized = normalize_ko_narration_line_rows(rows)
    return [
        {col: row.get(col, "") for col in ("id", "set_id", "text")}
        for row in normalized
    ]
