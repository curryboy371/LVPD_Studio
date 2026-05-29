"""base raw_sentence 슬롯 파싱·조합 ({단어} 와 , ? 구두점)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SlotKind = Literal["word", "punct"]

COMMA_PUNCT = ", "
PUNCT_CHOICES: tuple[str, ...] = (COMMA_PUNCT, "?", "？")
PUNCT_QUESTION_CHARS = frozenset("?？")


@dataclass
class SentenceSlot:
    kind: SlotKind
    text: str

    def normalized(self) -> SentenceSlot:
        if self.kind == "punct":
            t = self.text if self.text is not None else ""
            if t in ("?", "？"):
                return SentenceSlot("punct", t)
            if t in (",", "，", COMMA_PUNCT):
                return SentenceSlot("punct", COMMA_PUNCT)
            return SentenceSlot("punct", t)
        return SentenceSlot("word", (self.text or "").strip())


def parse_raw_sentence(raw: str) -> list[SentenceSlot]:
    text = (raw or "").strip()
    if not text:
        return [SentenceSlot("word", "")]

    slots: list[SentenceSlot] = []
    cursor = 0
    for match in re.finditer(r"\{([^}]*)\}", text):
        literal = text[cursor : match.start()]
        slots.extend(_literal_to_slots(literal))
        slots.append(SentenceSlot("word", match.group(1)))
        cursor = match.end()
    slots.extend(_literal_to_slots(text[cursor:]))
    return slots if slots else [SentenceSlot("word", "")]


def _literal_to_slots(literal: str) -> list[SentenceSlot]:
    out: list[SentenceSlot] = []
    i = 0
    while i < len(literal):
        if literal.startswith(COMMA_PUNCT, i):
            out.append(SentenceSlot("punct", COMMA_PUNCT))
            i += 2
            continue
        ch = literal[i]
        if ch in ",，":
            out.append(SentenceSlot("punct", COMMA_PUNCT))
            i += 1
            while i < len(literal) and literal[i] == " ":
                i += 1
            continue
        if ch in PUNCT_QUESTION_CHARS:
            out.append(SentenceSlot("punct", ch))
            i += 1
            continue
        if ch.strip():
            out.append(SentenceSlot("word", ch))
        i += 1
    return out


def slots_to_raw(slots: list[SentenceSlot]) -> str:
    parts: list[str] = []
    for slot in slots:
        s = slot.normalized()
        if not s.text and s.kind == "word":
            continue
        if s.kind == "punct":
            parts.append(s.text)
        else:
            parts.append("{" + s.text + "}")
    return "".join(parts)


def raw_to_display(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\{([^}]*)\}", r"\1", raw)


def slot_column_header(slot: SentenceSlot, word_index: int) -> str:
    s = slot.normalized()
    if s.kind == "word":
        return f"#{word_index}"
    t = s.text or "·"
    return t if len(t) <= 4 else t[:4]
