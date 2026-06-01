"""words.xlsx 시트별 단어 id 구간 및 빈 id 할당."""
from __future__ import annotations

from extra.table_editor.services.search import collect_numeric_ids

# 시트 이름 → (시작 id, 끝 id). CSV 통합 시 전 시트 id 는 서로 달라야 함.
SHEET_ID_RANGES: dict[str, tuple[int, int]] = {
    "수사": (1000, 1999),
    "양사": (2000, 2999),
    "기타": (3000, 3999),
    "대명사": (4000, 4999),
    "기타대명사": (5000, 9999),
    "동사": (10000, 19999),
    "명사": (20000, 29999),
    "고유명사": (30000, 39999),
    "표현": (40000, 49999),
    "작업용": (50000, 99999),
    "형용사": (100000, 199999),
    "전치사": (200000, 299999),
    "부사": (300000, 399999),
}

# 시트 이름 미등록 시 기존 id 로 블록 추정용
_ID_BLOCKS: tuple[tuple[int, int], ...] = tuple(SHEET_ID_RANGES.values())


def resolve_sheet_id_range(
    sheet_name: str,
    sheet_rows: list[dict[str, str]],
) -> tuple[int, int]:
    """시트의 허용 id 구간 (시작, 끝)."""
    name = (sheet_name or "").strip()
    if name in SHEET_ID_RANGES:
        return SHEET_ID_RANGES[name]

    ids = collect_numeric_ids(sheet_rows)
    if ids:
        lo = min(ids)
        for start, end in _ID_BLOCKS:
            if start <= lo <= end:
                return start, end

    known = ", ".join(sorted(SHEET_ID_RANGES))
    raise ValueError(
        f"시트 '{name}'의 ID 구간을 알 수 없습니다. "
        f"등록된 시트 이름을 쓰거나, 해당 시트에 기존 id 행이 있어야 합니다.\n"
        f"등록 시트: {known}"
    )


def collect_global_used_ids(
    all_sheet_rows: dict[str, list[dict[str, str]]] | None,
    *,
    fallback_rows: list[dict[str, str]] | None = None,
) -> set[int]:
    used: set[int] = set()
    if all_sheet_rows:
        for rows in all_sheet_rows.values():
            used.update(collect_numeric_ids(rows))
    elif fallback_rows is not None:
        used.update(collect_numeric_ids(fallback_rows))
    return used


def allocate_next_word_id(
    sheet_rows: list[dict[str, str]],
    all_sheet_rows: dict[str, list[dict[str, str]]] | None = None,
    *,
    sheet_name: str = "",
) -> str:
    """시트 id 구간 안에서 전역 미사용·가장 작은 빈 id."""
    range_start, range_end = resolve_sheet_id_range(sheet_name, sheet_rows)
    used = collect_global_used_ids(all_sheet_rows, fallback_rows=sheet_rows)

    for candidate in range(range_start, range_end + 1):
        if candidate not in used:
            return str(candidate)

    raise ValueError(
        f"시트 '{sheet_name}' ID 구간 {range_start}–{range_end}에 "
        f"비는 번호가 없습니다."
    )
