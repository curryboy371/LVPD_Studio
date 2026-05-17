"""숏츠 클립 종류 상수."""

from __future__ import annotations

CLIP_TYPE_CONVERSATION = "conversation"
CLIP_TYPE_VOCABULARY = "vocabulary"

_CONVERSATION_ALIASES = frozenset({"conversation", "situation", "situation_drama", "dialogue", "회화", "상황극"})
_VOCABULARY_ALIASES = frozenset({"vocabulary", "word", "words", "단어", "단어장"})


def normalize_clip_type(raw: str) -> str:
    """CSV clip_type 문자열을 conversation | vocabulary 로 정규화."""
    key = (raw or "").strip().lower()
    if not key or key in _CONVERSATION_ALIASES:
        return CLIP_TYPE_CONVERSATION
    if key in _VOCABULARY_ALIASES:
        return CLIP_TYPE_VOCABULARY
    return key
