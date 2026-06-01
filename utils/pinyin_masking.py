"""병음 성조 마스킹 유틸리티."""
from __future__ import annotations

import re
from typing import Optional

from utils.pinyin_processor import PinyinProcessor, get_pinyin_processor


def _split_mask_tokens(masking: str, syllable_count: int) -> list[str]:
    raw = str(masking or "").strip()
    if not raw:
        return []
    tokens = [t.strip() for t in re.split(r"[\s,|]+", raw) if t and t.strip()]
    cleaned_tokens: list[str] = []
    for tok in tokens:
        cleaned = tok.strip().strip("\"'`").strip()
        if cleaned:
            cleaned_tokens.append(cleaned)
    tokens = cleaned_tokens
    if len(tokens) == 1:
        compact = tokens[0]
        if compact.isdigit() and len(compact) == syllable_count:
            return list(compact)
    return tokens


def apply_mask_to_lexical_syllables(
    lexical_syllables: list[str],
    masking: str,
    *,
    processor: Optional[PinyinProcessor] = None,
) -> list[str]:
    """숫자 마스크를 lexical 병음 숫자 리스트에 적용해 새 lexical 리스트를 만든다."""
    if not lexical_syllables:
        return []
    pp = processor or get_pinyin_processor()
    tokens = _split_mask_tokens(masking, len(lexical_syllables))
    if not tokens:
        return list(lexical_syllables)

    adjusted: list[str] = []
    for idx, syllable in enumerate(lexical_syllables):
        base, tone = pp._split_tone(syllable)
        if not base:
            adjusted.append(syllable)
            continue
        cur_tone = int(tone) if tone is not None else 0
        if idx < len(tokens):
            tok = tokens[idx]
            if tok.isdigit():
                tone_mask = int(tok)
                if tone_mask == 0:
                    pass
                elif 1 <= tone_mask <= 5:
                    cur_tone = tone_mask
        adjusted.append(f"{base}{cur_tone}" if cur_tone > 0 else base)
    return adjusted


_TONE3_SYLLABLE_RE = re.compile(r"^[a-züv]+(?:[0-5](?:\.5)?)?$", re.IGNORECASE)


def _mark_syllable_to_lexical(marked: str, fallback: str, pp: PinyinProcessor) -> str:
    """성조 기호 음절(예: lè) 또는 숫자 병음(예: le4)을 lexical(숫자) 형식으로 변환."""
    tok = (marked or "").strip()
    if not tok:
        return (fallback or "").strip()
    norm = tok.replace("ü", "v")
    if _TONE3_SYLLABLE_RE.match(norm):
        return norm.lower()
    tone = 0
    base_chars: list[str] = []
    for ch in tok:
        ch_base = ch.lower()
        ch_tone = 0
        for vowel, variants in pp.tone_map.items():
            for ti, mv in enumerate(variants):
                if ch == mv:
                    ch_base = "v" if vowel == "ü" else vowel
                    ch_tone = ti
                    break
        if ch_tone == 0 and ch_base in "abcdefghijklmnopqrstuvwxyz":
            pass
        base_chars.append(ch_base)
        if ch_tone > tone:
            tone = ch_tone
    base = "".join(base_chars)
    if tone == 0:
        fb_base, fb_tone = pp._split_tone(fallback)
        if fb_base:
            base = fb_base
        tone = int(fb_tone) if fb_tone is not None else 0
    return f"{base}{int(tone)}" if tone > 0 else base


_TONED_VOWEL = r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]"
_PINYIN_SYLLABLE_RE = re.compile(
    rf"[bpmfdtnlgkhjqxzcsrwy]?(?:[a-z]*{_TONED_VOWEL})(?:ng|n|r)?",
    re.IGNORECASE,
)


def _split_pinyin_display_tokens(pinyin_text: str, syllable_count: int) -> list[str]:
    """공백 구분 또는 붙여 쓴 성조 병음(예: kělè, xīngqīyī)을 음절 토큰으로 분리."""
    text = (pinyin_text or "").strip()
    if not text:
        return []
    tokens = [t.strip() for t in re.split(r"\s+", text) if t.strip()]
    if len(tokens) > 1 or syllable_count <= 1:
        return tokens
    parts = _PINYIN_SYLLABLE_RE.findall(text)
    if len(parts) == syllable_count:
        return parts
    return tokens


def word_pinyin_to_lexical_syllables(
    hanzi: str,
    pinyin_text: str,
    *,
    processor: Optional[PinyinProcessor] = None,
) -> list[str]:
    """words.csv `pinyin` 값을 문장 병음용 lexical 음절 리스트로 변환."""
    text = (pinyin_text or "").strip()
    if not text:
        return []
    pp = processor or get_pinyin_processor()
    hz = (hanzi or "").strip()
    fallbacks: list[str] = []
    if pp.available and hz:
        fallbacks = pp.get_lexical_pinyin(hz) or []
    expected = len(fallbacks) or len(hz) or 1
    tokens = _split_pinyin_display_tokens(text, expected)
    if fallbacks and len(tokens) != len(fallbacks):
        return list(fallbacks)
    if not tokens:
        return []
    out: list[str] = []
    for i, tok in enumerate(tokens):
        fb = fallbacks[i] if i < len(fallbacks) else (fallbacks[-1] if fallbacks else "")
        out.append(_mark_syllable_to_lexical(tok, fb, pp))
    return out


def word_pinyin_to_marks(
    hanzi: str,
    pinyin_text: str,
    *,
    processor: Optional[PinyinProcessor] = None,
) -> str:
    """words.csv `pinyin` → 성조 기호 병음 문자열."""
    pp = processor or get_pinyin_processor()
    if not pp.available:
        return (pinyin_text or "").strip()
    syllables = word_pinyin_to_lexical_syllables(hanzi, pinyin_text, processor=pp)
    if not syllables:
        return (pinyin_text or "").strip()
    raw = (pinyin_text or "").strip()
    sep = " " if re.search(r"\s", raw) else ""
    return sep.join(pp.tone3_to_mark(s) for s in syllables).strip()


def word_pinyin_to_marks_spaced(
    hanzi: str,
    pinyin_text: str,
    *,
    processor: Optional[PinyinProcessor] = None,
) -> str:
    """성조 병음을 한자 음절마다 공백으로 구분 (단어 카드·xīng qī yī 형태)."""
    pp = processor or get_pinyin_processor()
    if not pp.available:
        return (pinyin_text or "").strip()
    syllables = word_pinyin_to_lexical_syllables(hanzi, pinyin_text, processor=pp)
    if not syllables:
        return (pinyin_text or "").strip()
    marked = [pp.tone3_to_mark(s) for s in syllables]
    if len(marked) <= 1:
        return marked[0] if marked else ""
    return " ".join(marked).strip()


def normalize_word_masking(raw: str) -> str:
    """words.csv masking 셀 정규화 (`\"\"\"40\"\"\"` → `40`)."""
    s = str(raw or "").strip()
    while len(s) >= 2 and s[0] == s[1] and s[0] in "\"'`":
        s = s[1:-1].strip()
    return s


def get_masked_pinyin_marks(
    hanzi: str,
    masking: str,
    *,
    processor: Optional[PinyinProcessor] = None,
) -> str:
    """한자 텍스트에 마스크를 반영한 성조 기호 병음을 반환한다."""
    text = (hanzi or "").strip()
    if not text:
        return ""
    pp = processor or get_pinyin_processor()
    if not pp.available:
        return ""
    lexical = pp.get_lexical_pinyin(text)
    if not lexical:
        return ""
    masked_lexical = apply_mask_to_lexical_syllables(lexical, masking, processor=pp)
    return " ".join(pp.tone3_to_mark(s) for s in masked_lexical).strip()
