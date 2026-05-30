"""words.xlsx / words.csv 한자 → id 조회 (base 슬롯 표시용)."""
from __future__ import annotations

import csv
from pathlib import Path

from core.paths import DEFAULT_WORDS_TABLE_CSV, DEFAULT_WORDS_TABLE_EXCEL
from extra.table_editor.data.fields import WORDS_FIELDNAMES
from extra.table_editor.data.workbook import MultiSheetWorkbookStore

_hanzi_to_ids: dict[str, list[str]] | None = None
_id_to_hanzi: dict[str, str] | None = None
_id_to_details: dict[str, dict[str, str]] | None = None


def clear_words_index_cache() -> None:
    global _hanzi_to_ids, _id_to_hanzi, _id_to_details
    _hanzi_to_ids = None
    _id_to_hanzi = None
    _id_to_details = None


def _normalize_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        f = float(raw)
        if f == int(f):
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return raw


def _load_from_excel(path: Path) -> dict[str, list[str]]:
    store = MultiSheetWorkbookStore(WORDS_FIELDNAMES)
    store.load(path)
    index: dict[str, list[str]] = {}
    for sheet in store.sheet_names:
        for row in store.get_sheet_rows(sheet):
            hanzi = (row.get("word") or "").strip()
            wid = _normalize_id(row.get("id", ""))
            if not hanzi or not wid:
                continue
            bucket = index.setdefault(hanzi, [])
            if wid not in bucket:
                bucket.append(wid)
    return index


def _load_from_csv(path: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            hanzi = (row.get("word") or "").strip()
            wid = _normalize_id(row.get("id", ""))
            if not hanzi or not wid:
                continue
            bucket = index.setdefault(hanzi, [])
            if wid not in bucket:
                bucket.append(wid)
    return index


def get_hanzi_to_word_ids() -> dict[str, list[str]]:
    global _hanzi_to_ids
    if _hanzi_to_ids is not None:
        return _hanzi_to_ids
    if DEFAULT_WORDS_TABLE_EXCEL.exists():
        _hanzi_to_ids = _load_from_excel(DEFAULT_WORDS_TABLE_EXCEL)
    elif DEFAULT_WORDS_TABLE_CSV.exists():
        _hanzi_to_ids = _load_from_csv(DEFAULT_WORDS_TABLE_CSV)
    else:
        _hanzi_to_ids = {}
    return _hanzi_to_ids


def lookup_word_ids(hanzi: str) -> list[str]:
    text = (hanzi or "").strip()
    if not text:
        return []
    return list(get_hanzi_to_word_ids().get(text, []))


def format_word_ids(ids: list[str]) -> str:
    if not ids:
        return "—"
    return " | ".join(ids)


def get_word_id_to_hanzi() -> dict[str, str]:
    global _id_to_hanzi
    if _id_to_hanzi is not None:
        return _id_to_hanzi
    index: dict[str, str] = {}
    for hanzi, ids in get_hanzi_to_word_ids().items():
        for wid in ids:
            norm = _normalize_id(wid)
            if norm and norm not in index:
                index[norm] = hanzi
    _id_to_hanzi = index
    return _id_to_hanzi


def _load_details_from_excel(path: Path) -> dict[str, dict[str, str]]:
    store = MultiSheetWorkbookStore(WORDS_FIELDNAMES)
    store.load(path)
    index: dict[str, dict[str, str]] = {}
    for sheet in store.sheet_names:
        for row in store.get_sheet_rows(sheet):
            wid = _normalize_id(row.get("id", ""))
            if not wid or wid in index:
                continue
            index[wid] = {
                "word": (row.get("word") or "").strip(),
                "meaning": (row.get("meaning") or "").strip(),
                "pos": (row.get("pos") or "").strip(),
                "sheet": sheet,
            }
    return index


def _load_details_from_csv(path: Path) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            wid = _normalize_id(row.get("id", ""))
            if not wid or wid in index:
                continue
            index[wid] = {
                "word": (row.get("word") or "").strip(),
                "meaning": (row.get("meaning") or "").strip(),
                "pos": (row.get("pos") or "").strip(),
                "sheet": "",
            }
    return index


def get_word_details_by_id() -> dict[str, dict[str, str]]:
    global _id_to_details
    if _id_to_details is not None:
        return _id_to_details
    if DEFAULT_WORDS_TABLE_EXCEL.exists():
        _id_to_details = _load_details_from_excel(DEFAULT_WORDS_TABLE_EXCEL)
    elif DEFAULT_WORDS_TABLE_CSV.exists():
        _id_to_details = _load_details_from_csv(DEFAULT_WORDS_TABLE_CSV)
    else:
        _id_to_details = {}
    return _id_to_details


def lookup_word_details(word_id: str) -> dict[str, str]:
    """words.id → 한자·뜻·품사·시트(엑셀 시트명)."""
    target = _normalize_id(word_id)
    empty = {"word": "", "meaning": "", "pos": "", "sheet": ""}
    if not target:
        return empty
    return dict(get_word_details_by_id().get(target, empty))


def lookup_hanzi_by_word_id(word_id: str) -> str:
    """words.id → 한자 (첫 매칭)."""
    return lookup_word_details(word_id).get("word", "")


def _word_search_row(word_id: str) -> dict[str, str]:
    details = lookup_word_details(word_id)
    return {
        "id": _normalize_id(word_id),
        "word": details.get("word", ""),
        "meaning": details.get("meaning", ""),
        "pos": details.get("pos", ""),
        "sheet": details.get("sheet", ""),
    }


def search_words(query: str) -> list[dict[str, str]]:
    """id 또는 한자(정확히 일치)로 words 검색."""
    from extra.table_editor.services.search import parse_search_query

    kind, value = parse_search_query(query)
    if not value:
        return []

    if kind == "id":
        row = _word_search_row(value)
        return [row] if row.get("word") else []

    ids = lookup_word_ids(value)
    rows = [_word_search_row(wid) for wid in ids]
    return [row for row in rows if row.get("word")]
