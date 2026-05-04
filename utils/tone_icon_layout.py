"""표기·발음 성조가 다른 음절에만 성조 아이콘 슬롯을 채운다."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Any, Mapping, Optional

from utils.pinyin_processor import get_pinyin_processor, parse_tone_from_syllable


@dataclass(frozen=True)
class ToneIconSlot:
    """표기≠발음일 때만 사용. PNG는 표기 성조 기준이며 반3성(3.5) 구간은 슬롯 없음."""

    icon_tone: float
    is_mismatch: bool


def _sentence_plain(item: Mapping[str, Any]) -> str:
    raw = item.get("sentence") or []
    if isinstance(raw, (list, tuple)):
        return " ".join(str(x) for x in list(raw)[:3]).strip()
    return str(raw).strip()


def _split_syllables(s: str) -> list[str]:
    return [x for x in s.strip().split() if x]


def _tones_equal(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return False
    return isclose(a, b, rel_tol=0.0, abs_tol=1e-6)


def _is_half_third_tone(t: Optional[float]) -> bool:
    return t is not None and isclose(float(t), 3.5, rel_tol=0.0, abs_tol=1e-6)


def build_tone_icon_slots(item: Mapping[str, Any], display_pinyin: str) -> tuple[Optional[ToneIconSlot], ...]:
    """병음 표시 줄(display_pinyin) 음절 수에 맞춰 슬롯을 만든다.

    표기/발음은 `pinyin_lexical`·`pinyin_phonetic` 또는 원문으로 g2pM 보강.
    표기 성조와 발음 성조가 같으면 슬롯을 두지 않는다. 반3성(3.5) 포함 시에도 아이콘 없음.
    음절 수가 맞지 않으면 짧은 쪽 길이만 채우고 나머지는 None.
    """
    display = _split_syllables(display_pinyin[:500])
    if not display:
        return ()

    out: list[Optional[ToneIconSlot]] = [None] * len(display)

    chinese = _sentence_plain(item)
    if not chinese or chinese == "(문장 없음)":
        return tuple(out)

    lex_s = str(item.get("pinyin_lexical") or "").strip()
    ph_s = str(item.get("pinyin_phonetic") or "").strip()

    pp = get_pinyin_processor()
    if not pp.available:
        return tuple(out)

    if not lex_s:
        lex_s = " ".join(pp.get_lexical_pinyin(chinese)).strip()
    if not ph_s:
        ph_s = " ".join(pp.get_phonetic_pinyin(chinese)).strip()

    lex = _split_syllables(lex_s)
    ph = _split_syllables(ph_s)
    if not lex or not ph:
        return tuple(out)

    n = min(len(display), len(lex), len(ph))

    for i in range(n):
        t_lex = parse_tone_from_syllable(lex[i])
        t_ph = parse_tone_from_syllable(ph[i])
        if t_lex is None or t_ph is None:
            continue
        if _is_half_third_tone(t_lex) or _is_half_third_tone(t_ph):
            continue
        if _tones_equal(t_lex, t_ph):
            continue
        out[i] = ToneIconSlot(icon_tone=float(t_lex), is_mismatch=True)

    return tuple(out)


__all__ = ["ToneIconSlot", "build_tone_icon_slots"]
