"""words.xlsx / words.csv 한자 → id 조회 (base 슬롯 표시용)."""
from __future__ import annotations

import csv
from pathlib import Path

from core.paths import DEFAULT_WORDS_TABLE_CSV, DEFAULT_WORDS_TABLE_EXCEL
from extra.table_editor.data.fields import WORDS_FIELDNAMES
from extra.table_editor.data.workbook import MultiSheetWorkbookStore

_hanzi_to_ids: dict[str, list[str]] | None = None
_id_to_hanzi: dict[str, str] | None = None


def clear_words_index_cache() -> None:
    global _hanzi_to_ids, _id_to_hanzi
    _hanzi_to_ids = None
    _id_to_hanzi = None


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


def lookup_hanzi_by_word_id(word_id: str) -> str:
    """words.id → 한자 (첫 매칭)."""
    target = _normalize_id(word_id)
    if not target:
        return ""
    return get_word_id_to_hanzi().get(target, "")

