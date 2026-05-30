"""sub_sentences target_slot_order · alt_word_id 파이프(|) 편집."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReplacementPair:
    slot_order: str
    alt_word_id: str


def _split_pipe(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(",", "|").split("|") if part.strip()]


def _zip_pairs(orders: list[str], word_ids: list[str]) -> list[ReplacementPair]:
    if not orders and not word_ids:
        return []
    if not orders:
        return [ReplacementPair("", wid) for wid in word_ids]
    if not word_ids:
        return [ReplacementPair(slot, "") for slot in orders]
    if len(orders) == len(word_ids):
        return [ReplacementPair(o, w) for o, w in zip(orders, word_ids)]
    if len(orders) == 1:
        return [ReplacementPair(orders[0], w) for w in word_ids]
    if len(word_ids) == 1:
        return [ReplacementPair(o, word_ids[0]) for o in orders]
    n = min(len(orders), len(word_ids))
    return [ReplacementPair(orders[i], word_ids[i]) for i in range(n)]


def parse_replacement_pairs(
    slot_order_raw: str, alt_word_id_raw: str
) -> list[ReplacementPair]:
    pairs = _zip_pairs(_split_pipe(slot_order_raw), _split_pipe(alt_word_id_raw))
    return pairs if pairs else [ReplacementPair("", "")]


def pairs_to_storage(pairs: list[ReplacementPair]) -> tuple[str, str]:
    kept = [
        p
        for p in pairs
        if (p.slot_order or "").strip() or (p.alt_word_id or "").strip()
    ]
    if not kept:
        return "", ""
    return (
        "|".join((p.slot_order or "").strip() for p in kept),
        "|".join((p.alt_word_id or "").strip() for p in kept),
    )


def slot_order_matches(a: str, b: str) -> bool:
    """target_slot_order / main_slot 비교 (0 vs 0.0, end 등)."""
    sa = (a or "").strip().lower()
    sb = (b or "").strip().lower()
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    if sa in ("end",) and sb in ("end",):
        return True
    try:
        return float(sa) == float(sb)
    except (TypeError, ValueError):
        return False


def main_slot_for_pair_index(pairs: list[ReplacementPair], index: int) -> str:
    if index < 0 or index >= len(pairs):
        return ""
    return (pairs[index].slot_order or "").strip()


def index_for_main_slot(
    pairs: list[ReplacementPair], main_slot: str
) -> int:
    target = (main_slot or "").strip()
    if target:
        for i, pair in enumerate(pairs):
            if slot_order_matches(pair.slot_order, target):
                return i
    for i, pair in enumerate(pairs):
        slot = (pair.slot_order or "").strip()
        wid = (pair.alt_word_id or "").strip()
        if slot and wid and wid != "0":
            return i
    return -1
