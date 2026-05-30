"""sub 완성형 문장 미리보기 캐시 (편집 창 즉시 표시용)."""
from __future__ import annotations

from typing import Callable

from extra.table_editor.config import SUB_ALT_WORD_ID_FIELD, SUB_SLOT_ORDER_FIELD
from extra.table_editor.services.sub_replacement_slots import parse_replacement_pairs
from extra.table_editor.services.sub_sentence_preview import build_sub_display_sentence


def _cache_key(sub_row: dict[str, str], base_raw_sentence: str) -> tuple[str, str, str, str]:
    return (
        (sub_row.get("id") or "").strip(),
        (sub_row.get(SUB_SLOT_ORDER_FIELD) or "").strip(),
        (sub_row.get(SUB_ALT_WORD_ID_FIELD) or "").strip(),
        (base_raw_sentence or "").strip(),
    )


class SubSentencePreviewCache:
    """sub 행별 완성형 문장 캐시. base/sub 로드·선택 시 미리 채우고, 저장 시 갱신."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str, str], str] = {}

    def clear(self) -> None:
        self._entries.clear()

    def get(self, sub_row: dict[str, str], base_raw_sentence: str) -> str | None:
        return self._entries.get(_cache_key(sub_row, base_raw_sentence))

    def put(
        self,
        sub_row: dict[str, str],
        base_raw_sentence: str,
        display_sentence: str,
    ) -> None:
        self._entries[_cache_key(sub_row, base_raw_sentence)] = display_sentence

    def build(
        self,
        sub_row: dict[str, str],
        base_raw_sentence: str,
        *,
        store: bool = True,
    ) -> str:
        pairs = parse_replacement_pairs(
            sub_row.get(SUB_SLOT_ORDER_FIELD, ""),
            sub_row.get(SUB_ALT_WORD_ID_FIELD, ""),
        )
        display = build_sub_display_sentence(base_raw_sentence, pairs)
        if store:
            self.put(sub_row, base_raw_sentence, display)
        return display

    def warm_rows(
        self,
        sub_rows: list[dict[str, str]],
        base_raw_for: Callable[[str], str],
    ) -> None:
        for row in sub_rows:
            base_id = (row.get("base_id") or "").strip()
            base_raw = base_raw_for(base_id)
            self.build(row, base_raw)

    def invalidate_for_base(
        self,
        base_id: str,
        sub_rows: list[dict[str, str]],
        base_raw_sentence: str,
    ) -> None:
        bid = (base_id or "").strip()
        if not bid:
            return
        for row in sub_rows:
            if (row.get("base_id") or "").strip() != bid:
                continue
            self.build(row, base_raw_sentence)
