"""단어 외우기 박스 — CTA 타입별 단어장 표시 단어 해석."""
from __future__ import annotations

from data.models import Word
from data.table_manager import get_word, get_word_by_hanzi
from extra.table_editor.services.word_memorize_layout import (
    WordMemorizeBox,
    box_cta_audio_path,
    box_cta_hanzi,
    box_cta_caption,
)


def resolve_box_word_id(box: WordMemorizeBox) -> int | None:
    """재생·렌더용 words.id — CTA 타입이면 단어장 고정 한자 항목."""
    cta_hanzi = box_cta_hanzi(box)
    if cta_hanzi:
        word = get_word_by_hanzi(cta_hanzi)
        if word is not None:
            return int(word.id)
    try:
        return int(box.word_id)
    except (TypeError, ValueError):
        return None


def resolve_box_word(
    box: WordMemorizeBox,
    *,
    words_by_id: dict[int, Word] | None = None,
) -> Word | None:
    """박스에 그릴 Word — 구독·좋아요는 订阅·点赞 단어장 항목."""
    wid = resolve_box_word_id(box)
    if wid is None:
        return None
    if words_by_id is not None:
        cached = words_by_id.get(wid)
        if cached is not None:
            return cached
    return get_word(wid)


def resolve_box_card_meaning(
    box: WordMemorizeBox,
    card_meaning_by_id: dict[int, str],
) -> str:
    """박스 뜻 텍스트 — 표시 단어 id 기준."""
    wid = resolve_box_word_id(box)
    if wid is None:
        return ""
    return (card_meaning_by_id.get(wid) or "").strip()


def box_uses_cta_audio(box: WordMemorizeBox) -> bool:
    """CTA 타입 고정 mp3 사용 여부."""
    return box_cta_audio_path(box) is not None


def active_cta_caption_for_box(box: WordMemorizeBox | None) -> str:
    """CTA 음성 재생 중 표시할 자막 — 없으면 빈 문자열."""
    if box is None or not box_uses_cta_audio(box):
        return ""
    return box_cta_caption(box)
