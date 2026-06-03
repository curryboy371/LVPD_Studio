"""words.xlsx 시트·품사별 단어 목록 (단어 외우기 배치 가져오기)."""
from __future__ import annotations

from pathlib import Path

from core.paths import DEFAULT_WORDS_TABLE_CSV, DEFAULT_WORDS_TABLE_EXCEL
from extra.table_editor.config import POS_FILTER_ALL
from extra.table_editor.data.fields import WORDS_FIELDNAMES
from extra.table_editor.data.workbook import MultiSheetWorkbookStore
from extra.table_editor.services.word_lookup import _normalize_id

_sheet_rows: dict[str, list[dict[str, str]]] | None = None


def clear_word_sheet_browser_cache() -> None:
    global _sheet_rows
    _sheet_rows = None


def _row_dict(row: dict[str, str], sheet: str) -> dict[str, str]:
    wid = _normalize_id(row.get("id", ""))
    word = (row.get("word") or "").strip()
    if not wid or not word:
        return {}
    return {
        "id": wid,
        "word": word,
        "meaning": (row.get("meaning") or "").strip(),
        "en_meaning": (row.get("en_meaning") or "").strip(),
        "pos": (row.get("pos") or "").strip(),
        "type": (row.get("type") or "").strip(),
        "sheet": sheet,
    }


def _load_sheet_rows() -> dict[str, list[dict[str, str]]]:
    global _sheet_rows
    if _sheet_rows is not None:
        return _sheet_rows

    out: dict[str, list[dict[str, str]]] = {}
    if DEFAULT_WORDS_TABLE_EXCEL.exists():
        store = MultiSheetWorkbookStore(WORDS_FIELDNAMES)
        store.load(DEFAULT_WORDS_TABLE_EXCEL)
        for sheet in store.sheet_names:
            rows: list[dict[str, str]] = []
            for row in store.get_sheet_rows(sheet):
                parsed = _row_dict(row, sheet)
                if parsed:
                    rows.append(parsed)
            out[sheet] = rows
    elif DEFAULT_WORDS_TABLE_CSV.exists():
        import csv

        with open(DEFAULT_WORDS_TABLE_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                parsed = _row_dict(row, "")
                if parsed:
                    sheet = (parsed.get("sheet") or "").strip() or "(기본)"
                    out.setdefault(sheet, []).append(parsed)
    else:
        out = {}

    _sheet_rows = out
    return out


def get_sheet_names() -> list[str]:
    return list(_load_sheet_rows().keys())


def get_pos_values(sheet: str) -> list[str]:
    rows = _load_sheet_rows().get(sheet, [])
    seen: list[str] = []
    for row in rows:
        pos = (row.get("pos") or "").strip()
        if pos and pos not in seen:
            seen.append(pos)
    return [POS_FILTER_ALL, *sorted(seen)]


def get_type_values(sheet: str) -> list[str]:
    rows = _load_sheet_rows().get(sheet, [])
    seen: list[str] = []
    for row in rows:
        word_type = (row.get("type") or "").strip()
        if word_type and word_type not in seen:
            seen.append(word_type)
    return [POS_FILTER_ALL, *sorted(seen)]


def query_words(sheet: str, pos: str, word_type: str = "") -> list[dict[str, str]]:
    """시트·품사·종류 필터로 단어 행 목록 (id 오름차순)."""
    rows = list(_load_sheet_rows().get(sheet, []))
    pos_filter = (pos or "").strip()
    if pos_filter and pos_filter != POS_FILTER_ALL:
        rows = [r for r in rows if (r.get("pos") or "").strip() == pos_filter]
    type_filter = (word_type or "").strip()
    if type_filter and type_filter != POS_FILTER_ALL:
        rows = [r for r in rows if (r.get("type") or "").strip() == type_filter]

    def _sort_key(r: dict[str, str]) -> tuple[int, str]:
        try:
            return int(r.get("id", "0")), r.get("word", "")
        except ValueError:
            return 0, r.get("word", "")

    rows.sort(key=_sort_key)
    return rows
