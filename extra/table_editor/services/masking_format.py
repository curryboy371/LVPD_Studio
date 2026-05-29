"""words.masking 표시(편집) ↔ 저장(엑셀/CSV 따옴표) 변환."""
from __future__ import annotations

from utils.pinyin_masking import normalize_word_masking

_QUOTE_CHARS = "\"'`"


def _masking_inner(stored: str) -> str:
    """저장/입력 값에서 편집용 숫자·토큰 문자열만 추출."""
    s = normalize_word_masking(stored)
    while len(s) >= 2 and s[0] in _QUOTE_CHARS and s[-1] == s[0]:
        s = s[1:-1].strip()
    return s


def masking_for_display(stored: str) -> str:
    """엑셀/CSV 값 → 편집창 입력 (`\"000\"` → `000`)."""
    return _masking_inner(stored)


def masking_for_storage(display: str) -> str:
    """편집창 입력 → 저장 값 (숫자만이면 `\"…\"` 로 감쌈)."""
    inner = _masking_inner(display)
    if not inner:
        return ""
    if inner.isdigit():
        return f'"{inner}"'
    return inner
