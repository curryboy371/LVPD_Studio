"""sub 치환 적용 후 완성형 표시 문장."""
from __future__ import annotations

from studio.conversation.slot_replacement import (
    parse_alt_word_ids as _parse_alt_word_ids,
    parse_target_slot_orders as _parse_target_slot_orders,
    replace_multiple_slots_in_raw_sentence as _replace_multiple_slots_in_raw_sentence,
    sort_key_slot_order as _sort_key_slot_order,
    zip_slot_orders_and_alt_word_ids as _zip_slot_orders_and_alt_word_ids,
)

from extra.table_editor.services.raw_sentence_slots import raw_to_display
from extra.table_editor.services.sub_replacement_slots import (
    ReplacementPair,
    pairs_to_storage,
)
from extra.table_editor.services.word_lookup import lookup_hanzi_by_word_id


def sort_replacement_pairs(pairs: list[ReplacementPair]) -> list[ReplacementPair]:
    kept = [
        p
        for p in pairs
        if (p.slot_order or "").strip() or (p.alt_word_id or "").strip()
    ]
    if not kept:
        return [ReplacementPair("", "")]

    def _key(p: ReplacementPair) -> tuple[int, float]:
        orders = _parse_target_slot_orders(p.slot_order)
        if orders:
            return _sort_key_slot_order(orders[0])
        return (3, 0.0)

    return sorted(kept, key=_key)


def build_sub_display_sentence(
    base_raw_sentence: str,
    pairs: list[ReplacementPair],
) -> str:
    raw = (base_raw_sentence or "").strip()
    if not raw:
        return "(base 문장 없음)"

    order_str, id_str = pairs_to_storage(pairs)
    if not order_str and not id_str:
        return raw_to_display(raw) or "(빈 문장)"

    slot_orders = _parse_target_slot_orders(order_str)
    alt_ids = _parse_alt_word_ids(id_str)
    if not slot_orders or not alt_ids:
        return raw_to_display(raw) or ""

    specs = _zip_slot_orders_and_alt_word_ids(
        target_slot_orders=slot_orders,
        alt_word_ids=alt_ids,
    )
    if not specs:
        return raw_to_display(raw) or ""

    replacements: list[tuple[object, str | None]] = []
    missing: list[str] = []
    for slot_order, alt_word_id in specs:
        wid = int(alt_word_id)
        if wid == 0:
            replacements.append((slot_order, None))
            continue
        word = lookup_hanzi_by_word_id(str(wid))
        if not word:
            missing.append(str(wid))
            continue
        replacements.append((slot_order, word))

    if missing:
        return f"(words.id 없음: {', '.join(missing)})"
    if len(replacements) != len(specs):
        return "(치환 단어 조회 실패)"

    replacements.sort(key=lambda x: _sort_key_slot_order(x[0]))
    out = _replace_multiple_slots_in_raw_sentence(
        raw,
        replacements=replacements,
    )
    return (out or "").strip() or "(결과 없음)"
