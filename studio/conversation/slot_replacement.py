"""Pure slot parsing/replacement for raw sentences (no pygame, no CSV loading)."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Union

_SLOT_APPEND = "__append__"


def _split_csv_multi_value(raw: Any) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    chunks = text.split("|")
    return [c.strip() for c in chunks if c is not None and c.strip()]


def _raw_sentence_to_display(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\{([^}]*)\}", r"\1", raw)


def _raw_sentence_to_words(raw: str) -> list[str]:
    if not raw:
        return []
    return re.findall(r"\{([^}]*)\}", raw)


def parse_target_slot_orders(raw: Any) -> list[Union[int, str, float]]:
    out: list[Union[int, str, float]] = []
    for token in _split_csv_multi_value(raw):
        t = token.strip().lower()
        if t in ("-1", "front", "start", "prefix", "맨앞", "앞"):
            out.append(-1)
            continue
        if t in ("end", "last", "suffix", "맨끝", "끝"):
            out.append(_SLOT_APPEND)
            continue
        try:
            v = float(token)
        except (TypeError, ValueError):
            continue
        if v.is_integer():
            out.append(int(v))
        else:
            out.append(v)
    return out


def parse_alt_word_ids(raw: Any) -> list[int]:
    out: list[int] = []
    for token in _split_csv_multi_value(raw):
        try:
            out.append(int(float(token)))
        except (TypeError, ValueError):
            continue
    return out


def zip_slot_orders_and_alt_word_ids(
    *,
    target_slot_orders: list[Union[int, str, float]],
    alt_word_ids: list[int],
) -> list[tuple[Union[int, str, float], int]]:
    if not target_slot_orders or not alt_word_ids:
        return []
    if len(target_slot_orders) == len(alt_word_ids):
        return list(zip(target_slot_orders, alt_word_ids))
    if len(target_slot_orders) == 1:
        return [(target_slot_orders[0], wid) for wid in alt_word_ids]
    if len(alt_word_ids) == 1:
        return [(slot, alt_word_ids[0]) for slot in target_slot_orders]
    n = min(len(target_slot_orders), len(alt_word_ids))
    return list(zip(target_slot_orders[:n], alt_word_ids[:n]))


def sort_key_slot_order(slot_order: Any) -> tuple[int, float]:
    if slot_order == _SLOT_APPEND:
        return (2, 1e12)
    if slot_order == -1:
        return (0, -1.0)
    try:
        return (1, float(slot_order))
    except (TypeError, ValueError):
        return (3, 0.0)


def slot_order_matches(a: Any, b: Any) -> bool:
    """target_slot_order / main_slot 비교."""
    sa = str(a or "").strip().lower()
    sb = str(b or "").strip().lower()
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    end_tokens = ("end", "last", "suffix", "맨끝", "끝")
    if sa in end_tokens and sb in end_tokens:
        return True
    try:
        return float(sa) == float(sb)
    except (TypeError, ValueError):
        return False


def resolve_main_word_id(
    *,
    main_slot: str,
    slot_orders: list[Any],
    alt_word_ids: list[int],
    fallback_word_id: int = 0,
) -> int:
    """main_slot에 해당하는 alt_word_id. 없으면 fallback(보통 primary 치환)."""
    target = str(main_slot or "").strip()
    if target:
        for slot, wid in zip(slot_orders, alt_word_ids):
            if slot_order_matches(slot, target) and int(wid) != 0:
                return int(wid)
    return int(fallback_word_id or 0)


def replace_multiple_slots_in_raw_sentence(
    raw_sentence: str,
    *,
    replacements: list[tuple[Union[int, str, float], str | None]],
) -> str:
    if not raw_sentence:
        return ""

    slot_words = _raw_sentence_to_words(raw_sentence)
    if not slot_words:
        return ""

    literals: list[str] = []
    cursor = 0
    for m in re.finditer(r"\{([^}]*)\}", raw_sentence):
        literals.append(raw_sentence[cursor : m.start()])
        cursor = m.end()
    literals.append(raw_sentence[cursor:])
    if len(literals) != len(slot_words) + 1:
        return _raw_sentence_to_display(raw_sentence)

    merged_slots = list(slot_words)
    prefix_words: list[str] = []
    suffix_words: list[str] = []
    slot_replacements: dict[int, str] = {}
    slots_to_remove: set[int] = set()
    insert_after: defaultdict[int, list[tuple[float, str]]] = defaultdict(list)

    for slot_order, new_word in replacements:
        if new_word is None:
            if isinstance(slot_order, int) and not isinstance(slot_order, bool) and slot_order >= 0:
                slots_to_remove.add(slot_order)
            continue
        w = str(new_word or "").strip()
        if not w:
            continue
        if slot_order == _SLOT_APPEND:
            suffix_words.append(w)
            continue
        if slot_order == -1:
            prefix_words.append(w)
            continue
        if isinstance(slot_order, int) and not isinstance(slot_order, bool):
            if slot_order < 0:
                continue
            slot_replacements[slot_order] = w
            continue
        try:
            order_f = float(slot_order)
        except (TypeError, ValueError):
            continue
        if order_f < 0:
            continue
        base_i = int(order_f)
        frac = order_f - base_i
        if frac <= 0:
            continue
        insert_after[base_i].append((order_f, w))

    for si, w in slot_replacements.items():
        if 0 <= si < len(merged_slots):
            merged_slots[si] = w
        else:
            suffix_words.append(w)

    for si in sorted(slots_to_remove, reverse=True):
        if not (0 <= si < len(merged_slots)):
            continue
        merged_slots.pop(si)
        if si + 1 < len(literals):
            literals[si] = literals[si] + literals[si + 1]
            del literals[si + 1]

    if slots_to_remove:
        remapped: defaultdict[int, list[tuple[float, str]]] = defaultdict(list)
        for k, items in insert_after.items():
            if k in slots_to_remove:
                continue
            shift = sum(1 for r in slots_to_remove if r < k)
            nk = k - shift
            if 0 <= nk < len(merged_slots):
                remapped[nk].extend(items)
        insert_after = remapped

    orphan_inserts: list[tuple[float, str]] = []
    for k in list(insert_after.keys()):
        if not (0 <= k < len(merged_slots)):
            orphan_inserts.extend(insert_after.pop(k))
    orphan_inserts.sort(key=lambda x: x[0])
    for _, w in orphan_inserts:
        suffix_words.append(w)

    for k in insert_after:
        insert_after[k].sort(key=lambda x: x[0])

    parts: list[str] = []
    parts.extend(prefix_words)
    for i, slot_word in enumerate(merged_slots):
        parts.append(literals[i])
        parts.append(slot_word)
        for _, w in insert_after.get(i, []):
            parts.append(w)
    parts.append(literals[-1])
    parts.extend(suffix_words)
    return "".join(parts).strip()
