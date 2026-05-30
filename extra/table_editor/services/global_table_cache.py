"""테이블 편집기 전역 캐시 — base / sub / ko_narration (모드 전환 후에도 유지)."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from core.paths import (
    DEFAULT_BASE_SENTENCES_CSV,
    DEFAULT_BASE_SENTENCES_EXCEL,
    DEFAULT_KO_NARRATION_LINES_CSV,
    DEFAULT_KO_NARRATION_LINES_EXCEL,
    DEFAULT_KO_NARRATION_SETS_CSV,
    DEFAULT_KO_NARRATION_SETS_EXCEL,
    DEFAULT_SUB_SENTENCES_CSV,
    DEFAULT_SUB_SENTENCES_EXCEL,
)
from extra.table_editor.config import SUB_ALT_WORD_ID_FIELD, SUB_SLOT_ORDER_FIELD
from extra.table_editor.data.fields import (
    BASE_FIELDNAMES,
    KO_NARRATION_LINES_FIELDNAMES,
    KO_NARRATION_SETS_FIELDNAMES,
    SUB_FIELDNAMES,
)
from extra.table_editor.data.workbook import ExcelWorkbookStore
from extra.table_editor.services.search import (
    filter_rows_by_base_id,
    filter_rows_by_set_id,
    ids_equal,
    sort_ko_narration_lines_by_seq,
    sort_rows_by_id,
)
from extra.table_editor.services.sub_replacement_slots import parse_replacement_pairs
from extra.table_editor.services.sub_sentence_preview import build_sub_display_sentence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectOption:
    id: str
    label: str
    preview: str


def _norm_row_id(value: str) -> str:
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


def _read_table_rows(
    excel_path: Path, csv_path: Path, fieldnames: list[str]
) -> list[dict[str, str]]:
    if excel_path.exists():
        store = ExcelWorkbookStore(fieldnames)
        store.load(excel_path)
        return store.get_rows()
    if csv_path.exists():
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(f)]
    return []


def _truncate(text: str, max_len: int = 48) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _ko_line_seq_is_one(row: dict[str, str]) -> bool:
    raw = (row.get("seq") or "").strip()
    if not raw:
        return False
    try:
        return int(float(raw)) == 1
    except (ValueError, TypeError):
        return False


def _combo_label(item_id: str, preview: str) -> str:
    short = _truncate(preview, 44)
    return f"{item_id} - {short}" if short else item_id


class GlobalTableCache:
    """프로세스 수명 동안 유지되는 base · sub · ko line 인덱스·파생 캐시."""

    _instance: GlobalTableCache | None = None

    def __init__(self) -> None:
        self._base_rows: list[dict[str, str]] | None = None
        self._sub_rows: list[dict[str, str]] | None = None
        self._ko_line_rows: list[dict[str, str]] | None = None
        self._base_raw_by_id: dict[str, str] = {}
        self._subs_by_base_id: dict[str, list[dict[str, str]]] = {}
        self._ko_lines_by_set_id: dict[str, list[dict[str, str]]] = {}
        self._sub_options_by_base: dict[str, list[SelectOption]] = {}
        self._ko_options_by_set: dict[str, list[SelectOption]] = {}
        self._ko_text_by_key: dict[tuple[str, str], str] = {}
        self._sub_display_by_key: dict[tuple[str, str], str] = {}
        self._ko_set_choices: list[tuple[str, str]] | None = None
        self._word_options: list[SelectOption] | None = None
        self._base_options: list[SelectOption] | None = None
        self._warmed_shorts = False
        self._warmed_shorts_vocab = False

    @classmethod
    def get(cls) -> GlobalTableCache:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def _clear_derived(self) -> None:
        self._base_raw_by_id.clear()
        self._subs_by_base_id.clear()
        self._ko_lines_by_set_id.clear()
        self._sub_options_by_base.clear()
        self._ko_options_by_set.clear()
        self._ko_text_by_key.clear()
        self._sub_display_by_key.clear()
        self._ko_set_choices = None
        self._word_options = None
        self._base_options = None
        self._warmed_shorts = False
        self._warmed_shorts_vocab = False

    def ensure_loaded(self) -> None:
        if self._base_rows is not None and self._sub_rows is not None and self._ko_line_rows is not None:
            return
        self._base_rows = _read_table_rows(
            DEFAULT_BASE_SENTENCES_EXCEL,
            DEFAULT_BASE_SENTENCES_CSV,
            BASE_FIELDNAMES,
        )
        self._sub_rows = _read_table_rows(
            DEFAULT_SUB_SENTENCES_EXCEL,
            DEFAULT_SUB_SENTENCES_CSV,
            SUB_FIELDNAMES,
        )
        self._ko_line_rows = _read_table_rows(
            DEFAULT_KO_NARRATION_LINES_EXCEL,
            DEFAULT_KO_NARRATION_LINES_CSV,
            KO_NARRATION_LINES_FIELDNAMES,
        )
        self._build_indexes()
        logger.debug(
            "global_table_cache loaded: base=%d sub=%d ko_lines=%d",
            len(self._base_rows),
            len(self._sub_rows),
            len(self._ko_line_rows),
        )

    def _build_indexes(self) -> None:
        self._base_raw_by_id.clear()
        for row in self._base_rows or []:
            bid = _norm_row_id(row.get("id", ""))
            if bid:
                self._base_raw_by_id[bid] = (row.get("raw_sentence") or "").strip()

        self._subs_by_base_id.clear()
        for row in self._sub_rows or []:
            bid = _norm_row_id(row.get("base_id", ""))
            if not bid:
                continue
            self._subs_by_base_id.setdefault(bid, []).append(row)
        for bid in self._subs_by_base_id:
            self._subs_by_base_id[bid] = sort_rows_by_id(self._subs_by_base_id[bid])

        self._ko_lines_by_set_id.clear()
        for row in self._ko_line_rows or []:
            sid = _norm_row_id(row.get("set_id", ""))
            if not sid:
                continue
            self._ko_lines_by_set_id.setdefault(sid, []).append(row)
        for sid in self._ko_lines_by_set_id:
            self._ko_lines_by_set_id[sid] = sort_ko_narration_lines_by_seq(
                self._ko_lines_by_set_id[sid]
            )

    def get_base_raw(self, base_id: str) -> str:
        self.ensure_loaded()
        bid = _norm_row_id(base_id)
        if not bid:
            return ""
        if bid in self._base_raw_by_id:
            return self._base_raw_by_id[bid]
        for row in self._base_rows or []:
            if ids_equal(row.get("id", ""), bid):
                raw = (row.get("raw_sentence") or "").strip()
                self._base_raw_by_id[bid] = raw
                return raw
        return ""

    def _build_sub_display(self, base_id: str, sub_row: dict[str, str]) -> str:
        bid = _norm_row_id(base_id)
        sid = _norm_row_id(sub_row.get("id", ""))
        key = (bid, sid)
        if key in self._sub_display_by_key:
            return self._sub_display_by_key[key]
        base_raw = self.get_base_raw(bid)
        pairs = parse_replacement_pairs(
            sub_row.get(SUB_SLOT_ORDER_FIELD, ""),
            sub_row.get(SUB_ALT_WORD_ID_FIELD, ""),
        )
        display = build_sub_display_sentence(base_raw, pairs)
        self._sub_display_by_key[key] = display
        return display

    def get_sub_display(self, base_id: str, sub_id: str) -> str:
        self.ensure_loaded()
        bid = _norm_row_id(base_id)
        sid = _norm_row_id(sub_id)
        if not bid or not sid:
            return ""
        cached = self._sub_display_by_key.get((bid, sid))
        if cached is not None:
            return cached
        for row in self._subs_by_base_id.get(bid, []):
            if ids_equal(row.get("id", ""), sid):
                return self._build_sub_display(bid, row)
        return ""

    def get_ko_line_text(self, set_id: str, line_id: str) -> str:
        self.ensure_loaded()
        sid = _norm_row_id(set_id)
        lid = _norm_row_id(line_id)
        if not sid or not lid:
            return ""
        key = (sid, lid)
        if key in self._ko_text_by_key:
            return self._ko_text_by_key[key]
        for row in self._ko_lines_by_set_id.get(sid, []):
            if ids_equal(row.get("id", ""), lid):
                text = (row.get("text") or "").strip()
                self._ko_text_by_key[key] = text
                return text
        return ""

    def get_base_options(self) -> list[SelectOption]:
        self.ensure_loaded()
        if self._base_options is not None:
            return self._base_options
        from extra.table_editor.services.raw_sentence_slots import raw_to_display

        keyed: list[tuple[int, str, str]] = []
        for row in self._base_rows or []:
            bid = _norm_row_id(row.get("id", ""))
            if not bid:
                continue
            raw = (row.get("raw_sentence") or "").strip()
            display = raw_to_display(raw) or raw or "(문장 없음)"
            try:
                sort_key = int(bid)
            except ValueError:
                sort_key = 0
            keyed.append((sort_key, bid, display))
        keyed.sort(key=lambda t: (t[0], t[1]))
        self._base_options = [
            SelectOption(
                id=bid,
                label=_combo_label(bid, display),
                preview=display,
            )
            for _k, bid, display in keyed
        ]
        return self._base_options

    def get_sub_options(self, base_id: str) -> list[SelectOption]:
        self.ensure_loaded()
        bid = _norm_row_id(base_id)
        if not bid:
            return []
        if bid in self._sub_options_by_base:
            return self._sub_options_by_base[bid]
        options: list[SelectOption] = []
        for row in self._subs_by_base_id.get(bid, []):
            sid = _norm_row_id(row.get("id", ""))
            if not sid:
                continue
            display = self._build_sub_display(bid, row)
            options.append(
                SelectOption(
                    id=sid,
                    label=_combo_label(sid, display),
                    preview=display,
                )
            )
        self._sub_options_by_base[bid] = options
        return options

    def get_ko_line_options(self, set_id: str) -> list[SelectOption]:
        self.ensure_loaded()
        sid = _norm_row_id(set_id)
        if not sid:
            return []
        if sid in self._ko_options_by_set:
            return self._ko_options_by_set[sid]
        options: list[SelectOption] = []
        seen_ids: set[str] = set()
        for row in self._ko_lines_by_set_id.get(sid, []):
            if not _ko_line_seq_is_one(row):
                continue
            line_id = _norm_row_id(row.get("id", ""))
            if not line_id or line_id in seen_ids:
                continue
            seen_ids.add(line_id)
            text = (row.get("text") or "").strip() or "(text 없음)"
            self._ko_text_by_key[(sid, line_id)] = text
            options.append(
                SelectOption(
                    id=line_id,
                    label=_combo_label(line_id, text),
                    preview=text,
                )
            )
        self._ko_options_by_set[sid] = options
        return options

    def distinct_base_ids(self) -> list[str]:
        self.ensure_loaded()
        ids = set(self._base_raw_by_id)
        ids.update(self._subs_by_base_id)
        return sorted(ids, key=lambda x: (0, int(x)) if x.isdigit() else (1, x))

    def get_ko_narration_set_choices(self) -> list[tuple[str, str]]:
        """(set id, 콤보 라벨) — ko_narration_sets.xlsx/csv."""
        if self._ko_set_choices is not None:
            return self._ko_set_choices
        rows = _read_table_rows(
            DEFAULT_KO_NARRATION_SETS_EXCEL,
            DEFAULT_KO_NARRATION_SETS_CSV,
            KO_NARRATION_SETS_FIELDNAMES,
        )
        keyed: list[tuple[int, str, str]] = []
        for row in rows:
            sid = _norm_row_id(row.get("id", ""))
            if not sid:
                continue
            try:
                sort_key = int(sid)
            except ValueError:
                sort_key = 0
            title = (row.get("title") or "").strip()
            label = f"{sid} - {title}" if title else sid
            keyed.append((sort_key, sid, label))
        keyed.sort(key=lambda t: (t[0], t[1]))
        self._ko_set_choices = [(sid, label) for _k, sid, label in keyed]
        return self._ko_set_choices

    def distinct_ko_set_ids(self) -> list[str]:
        self.ensure_loaded()
        return sorted(
            self._ko_lines_by_set_id.keys(),
            key=lambda x: (0, int(x)) if x.isdigit() else (1, x),
        )

    def get_word_options(self) -> list[SelectOption]:
        if self._word_options is not None:
            return self._word_options
        from extra.table_editor.services.word_lookup import get_word_details_by_id

        keyed: list[tuple[int, str, str]] = []
        for wid, details in get_word_details_by_id().items():
            hanzi = (details.get("word") or "").strip()
            meaning = (details.get("meaning") or "").strip()
            pos = (details.get("pos") or "").strip()
            preview = f"{hanzi} — {meaning}" if hanzi and meaning else hanzi or meaning or wid
            if pos:
                preview = f"{preview} ({pos})"
            try:
                sort_key = int(wid)
            except ValueError:
                sort_key = 0
            keyed.append((sort_key, wid, preview))
        keyed.sort(key=lambda t: (t[0], t[1]))
        self._word_options = [
            SelectOption(
                id=wid,
                label=_combo_label(wid, preview),
                preview=preview,
            )
            for _k, wid, preview in keyed
        ]
        return self._word_options

    def warm_shorts_vocab_editor(self) -> None:
        """숏츠 단어 편집용 — words · ko_narration_sets 캐시."""
        if self._warmed_shorts_vocab:
            return
        self.get_word_options()
        self.get_ko_narration_set_choices()
        self._warmed_shorts_vocab = True
        logger.info(
            "shorts vocab editor cache warmed: %d words",
            len(self._word_options or []),
        )

    def warm_shorts_editor(self) -> None:
        """숏츠 회화 편집용 — words 인덱스 + sub/ko 옵션 전부 선계산."""
        if self._warmed_shorts:
            return
        self.ensure_loaded()
        from extra.table_editor.services.word_lookup import get_hanzi_to_word_ids

        get_hanzi_to_word_ids()
        self.get_base_options()
        for set_id in self.distinct_ko_set_ids():
            self.get_ko_line_options(set_id)
        for base_id in self.distinct_base_ids():
            self.get_sub_options(base_id)
        self._warmed_shorts = True
        logger.info(
            "shorts editor cache warmed: %d sets, %d bases",
            len(self._ko_options_by_set),
            len(self._sub_options_by_base),
        )


def invalidate_global_table_cache(
    *,
    base: bool = False,
    sub: bool = False,
    ko_lines: bool = False,
    ko_sets: bool = False,
    words: bool = False,
    all_tables: bool = False,
) -> None:
    """관련 xlsx/csv 저장 후 호출."""
    cache = GlobalTableCache.get()
    if all_tables:
        cache._base_rows = None
        cache._sub_rows = None
        cache._ko_line_rows = None
        cache._clear_derived()
        return
    if base:
        cache._base_rows = None
        cache._sub_options_by_base.clear()
        cache._sub_display_by_key.clear()
        cache._base_raw_by_id.clear()
    if sub:
        cache._sub_rows = None
        cache._subs_by_base_id.clear()
        cache._sub_options_by_base.clear()
        cache._sub_display_by_key.clear()
    if ko_lines:
        cache._ko_line_rows = None
        cache._ko_lines_by_set_id.clear()
        cache._ko_options_by_set.clear()
        cache._ko_text_by_key.clear()
    if ko_sets:
        cache._ko_set_choices = None
    if words:
        cache._word_options = None
        cache._warmed_shorts_vocab = False
        from extra.table_editor.services.word_lookup import clear_words_index_cache

        clear_words_index_cache()
    if base or sub or ko_lines or ko_sets:
        cache._warmed_shorts = False
    if words or ko_sets:
        cache._warmed_shorts_vocab = False
        if cache._base_rows is not None and cache._sub_rows is not None and cache._ko_line_rows is not None:
            cache._build_indexes()


def warm_shorts_editor_cache() -> None:
    GlobalTableCache.get().warm_shorts_editor()


def warm_shorts_vocab_editor_cache() -> None:
    GlobalTableCache.get().warm_shorts_vocab_editor()


def clear_global_table_cache() -> None:
    """테스트·강제 초기화."""
    if GlobalTableCache._instance is not None:
        GlobalTableCache._instance._base_rows = None
        GlobalTableCache._instance._sub_rows = None
        GlobalTableCache._instance._ko_line_rows = None
        GlobalTableCache._instance._clear_derived()
