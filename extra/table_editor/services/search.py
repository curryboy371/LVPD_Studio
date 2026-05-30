"""Search and filter helpers for table rows."""
from __future__ import annotations

import re
from typing import Literal

from extra.table_editor.config import POS_FILTER_ALL, TOPIC_FILTER_ALL

SearchKind = Literal["id", "hanzi", "text"]


def parse_search_query(query: str) -> tuple[SearchKind, str]:
    text = (query or "").strip()
    if not text:
        return "text", ""
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        try:
            n = float(text)
            if n == int(n):
                return "id", str(int(n))
        except ValueError:
            pass
        return "id", text
    return "hanzi", text


def _id_key(row: dict[str, str]) -> tuple[int, str]:
    raw = (row.get("id") or "").strip()
    try:
        return (0, f"{int(float(raw)):010d}")
    except (ValueError, TypeError):
        return (1, raw)


def sort_rows_by_id(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=_id_key)


def _numeric_field_key(value: str, *, text_fallback: str = "") -> tuple[int, float | int | str]:
    raw = (value or "").strip()
    if not raw:
        return (1, text_fallback)
    try:
        n = float(raw)
        if n == int(n):
            return (0, int(n))
        return (0, n)
    except (ValueError, TypeError):
        return (1, raw)


def sort_ko_narration_lines(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """set_id → seq → id 순 (seq는 set_id 소속)."""
    return sorted(
        rows,
        key=lambda r: (
            _numeric_field_key(r.get("set_id", "")),
            _numeric_field_key(r.get("seq", "")),
            _id_key(r),
        ),
    )


def sort_ko_narration_lines_by_seq(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """선택 set 내부: seq → id 순."""
    return sorted(
        rows,
        key=lambda r: (
            _numeric_field_key(r.get("seq", "")),
            _id_key(r),
        ),
    )


def sort_ko_narration_lines_by_id_seq(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """선택 set 내부: id → seq 순."""
    return sorted(
        rows,
        key=lambda r: (
            _id_key(r),
            _numeric_field_key(r.get("seq", "")),
        ),
    )


def filter_rows_by_pos(rows: list[dict[str, str]], pos_filter: str) -> list[dict[str, str]]:
    if not pos_filter or pos_filter == POS_FILTER_ALL:
        return list(rows)
    return [r for r in rows if (r.get("pos") or "").strip() == pos_filter]


def filter_rows_by_topic(rows: list[dict[str, str]], topic_filter: str) -> list[dict[str, str]]:
    if not topic_filter or topic_filter == TOPIC_FILTER_ALL:
        return list(rows)
    return [r for r in rows if (r.get("topic") or "").strip() == topic_filter]


def unique_pos_values(rows: list[dict[str, str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        pos = (row.get("pos") or "").strip()
        if pos and pos not in seen:
            seen.add(pos)
            out.append(pos)
    return sorted(out)


def unique_topic_values(rows: list[dict[str, str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        topic = (row.get("topic") or "").strip()
        if topic and topic not in seen:
            seen.add(topic)
            out.append(topic)
    return sorted(out)


def ids_equal(left: str, right: str) -> bool:
    """행 id·base_id 비교 (1 과 1.0 동일 취급)."""
    a, b = (left or "").strip(), (right or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return int(float(a)) == int(float(b))
    except (ValueError, TypeError):
        return False


def rows_match(
    left: dict[str, str],
    right: dict[str, str],
    fieldnames: list[str],
) -> bool:
    for col in fieldnames:
        if (left.get(col, "") or "").strip() != (right.get(col, "") or "").strip():
            return False
    return True


def find_row_index_by_id(
    rows: list[dict[str, str]],
    row_id: str,
    *,
    match: dict[str, str] | None = None,
    fieldnames: list[str] | None = None,
) -> int | None:
    """id 일치 행 인덱스. 동일 id가 여러 개면 match 스냅샷으로 구분."""
    target = (row_id or "").strip()
    if not target:
        return None
    candidates = [
        i for i, r in enumerate(rows) if ids_equal(r.get("id", ""), target)
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if match is not None and fieldnames:
        for i in candidates:
            if rows_match(rows[i], match, fieldnames):
                return i
    return candidates[0]


def filter_rows_by_base_id(
    rows: list[dict[str, str]], base_id: str
) -> list[dict[str, str]]:
    target = (base_id or "").strip()
    if not target:
        return []
    return [r for r in rows if ids_equal(r.get("base_id", ""), target)]


def filter_rows_by_set_id(
    rows: list[dict[str, str]], set_id: str
) -> list[dict[str, str]]:
    target = (set_id or "").strip()
    if not target:
        return []
    return [r for r in rows if ids_equal(r.get("set_id", ""), target)]


def find_row_by_id(rows: list[dict[str, str]], row_id: str) -> dict[str, str] | None:
    idx = find_row_index_by_id(rows, row_id)
    if idx is None:
        return None
    return rows[idx]


def find_rows_by_word(rows: list[dict[str, str]], hanzi: str) -> list[dict[str, str]]:
    target = hanzi.strip()
    return [r for r in rows if (r.get("word") or "").strip() == target]


def parse_row_id(row: dict[str, str]) -> int | None:
    raw = (row.get("id") or "").strip()
    if not raw:
        return None
    try:
        n = int(float(raw))
        return n
    except (ValueError, TypeError):
        return None


def collect_numeric_ids(rows: list[dict[str, str]]) -> list[int]:
    out: list[int] = []
    for row in rows:
        n = parse_row_id(row)
        if n is not None:
            out.append(n)
    return out


def allocate_next_row_id(
    rows: list[dict[str, str]],
    *,
    default: str = "1",
) -> str:
    """비어 있는 가장 작은 숫자 id (1부터 빈 칸 탐색)."""
    used = set(collect_numeric_ids(rows))
    if not used:
        return default
    candidate = 1
    while candidate in used:
        candidate += 1
    return str(candidate)


def allocate_next_sub_row_id(
    rows: list[dict[str, str]],
    base_id: str,
    *,
    default: str = "1",
) -> str:
    """선택한 base_id 의 sub 중 다음 id."""
    scoped = filter_rows_by_base_id(rows, base_id)
    return allocate_next_row_id(scoped, default=default)


def find_sub_row_index(
    rows: list[dict[str, str]],
    base_id: str,
    row_id: str,
    *,
    match: dict[str, str] | None = None,
    fieldnames: list[str] | None = None,
) -> int | None:
    """base_id + id 로 sub 행 인덱스 (id는 base별로 중복 가능)."""
    bid = (base_id or "").strip()
    if not bid:
        return None
    target = (row_id or "").strip()
    if not target:
        return None
    candidates = [
        i
        for i, r in enumerate(rows)
        if ids_equal(r.get("base_id", ""), bid)
        and ids_equal(r.get("id", ""), target)
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if match is not None and fieldnames:
        for i in candidates:
            if rows_match(rows[i], match, fieldnames):
                return i
    return candidates[0]


def sub_row_id_exists(
    rows: list[dict[str, str]],
    base_id: str,
    row_id: str,
) -> bool:
    return find_sub_row_index(rows, base_id, row_id) is not None


def find_ko_line_row_index(
    rows: list[dict[str, str]],
    set_id: str,
    row_id: str,
    *,
    match: dict[str, str] | None = None,
    fieldnames: list[str] | None = None,
) -> int | None:
    """set_id + id 로 ko_narration_lines 행 인덱스 (id는 set별로 중복 가능)."""
    sid = (set_id or "").strip()
    if not sid:
        return None
    target = (row_id or "").strip()
    if not target:
        return None
    candidates = [
        i
        for i, r in enumerate(rows)
        if ids_equal(r.get("set_id", ""), sid)
        and ids_equal(r.get("id", ""), target)
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if match is not None and fieldnames:
        for i in candidates:
            if rows_match(rows[i], match, fieldnames):
                return i
    return candidates[0]


def ko_line_id_exists(
    rows: list[dict[str, str]],
    set_id: str,
    row_id: str,
) -> bool:
    return find_ko_line_row_index(rows, set_id, row_id) is not None


def allocate_next_ko_line_id(
    rows: list[dict[str, str]],
    set_id: str,
    *,
    default: str = "1",
) -> str:
    scoped = filter_rows_by_set_id(rows, set_id)
    return allocate_next_row_id(scoped, default=default)


def allocate_next_ko_line_seq(
    rows: list[dict[str, str]],
    set_id: str,
    *,
    default: str = "1",
) -> str:
    scoped = filter_rows_by_set_id(rows, set_id)
    seqs: list[int] = []
    for row in scoped:
        raw = (row.get("seq") or "").strip()
        if not raw:
            continue
        try:
            seqs.append(int(float(raw)))
        except (ValueError, TypeError):
            continue
    if not seqs:
        return default
    return str(max(seqs) + 1)


def allocate_next_word_id(
    sheet_rows: list[dict[str, str]],
    all_sheet_rows: dict[str, list[dict[str, str]]] | None = None,
) -> str:
    """다음 단어 id: 현재 시트 max+1. 시트가 비어 있으면 통합 문서 max+1."""
    sheet_ids = collect_numeric_ids(sheet_rows)
    if sheet_ids:
        return str(max(sheet_ids) + 1)

    global_max = 0
    if all_sheet_rows:
        for rows in all_sheet_rows.values():
            ids = collect_numeric_ids(rows)
            if ids:
                global_max = max(global_max, max(ids))
    if global_max > 0:
        return str(global_max + 1)
    return "1000"
