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
