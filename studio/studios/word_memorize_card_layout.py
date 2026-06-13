"""단어 외우기 카드 — 텍스트 줄 배치."""
from __future__ import annotations

import pygame

from data.models import Word
from extra.table_editor.services.word_memorize_layout import (
    CARD_IMG_BOTTOM_PAD_FHD,
    WordMemorizeBox,
    _is_zh_meaning_lang,
    default_card_item_gap,
    layout_card_content_vertical,
)
from utils.pinyin_masking import (
    get_masked_pinyin_marks,
    normalize_word_masking,
    word_pinyin_to_marks_spaced,
)

CARD_INNER_PAD = 10
PINYIN_FONT_PT = 32
HANZI_FONT_PT = 72
MEANING_FONT_PT = 30
IMG_MAX_HEIGHT_RATIO = 0.38
ZH_HANZI_SCALE = 0.8
ZH_MEANING_SCALE = 1.2

_font_cache: dict[tuple[str, int, str], pygame.font.Font | None] = {}


def _display_pinyin(word: Word) -> str:
    """렌더러와 동일한 병음 표시 문자열."""
    hanzi = (word.word or "").strip()
    raw = (word.pinyin or "").strip()
    masking = (word.masking or "").strip()
    if raw and hanzi:
        marks = word_pinyin_to_marks_spaced(hanzi, raw).strip()
        if marks:
            return marks
        return raw
    if hanzi:
        marks = get_masked_pinyin_marks(hanzi, normalize_word_masking(masking)).strip()
        if marks:
            return marks
    return raw


def _card_font(
    role: str,
    pt: int,
    *,
    meaning_lang: str,
    weight: str = "regular",
) -> pygame.font.Font | None:
    key = (role, pt, weight, meaning_lang)
    if key in _font_cache:
        return _font_cache[key]
    from utils.fonts import load_font_korean, load_font_noto_sans_cjk_sc

    from extra.table_editor.services.word_memorize_layout import _card_meaning_font_bold

    if role == "meaning":
        meaning_weight = (
            "bold" if _card_meaning_font_bold(meaning_lang) else "regular"
        )
        font = load_font_korean(pt, (76, 175, 80), weight=meaning_weight)
    elif role == "hanzi":
        font = load_font_noto_sans_cjk_sc(
            pt, (33, 33, 33), weight="bold" if weight == "bold" else "regular"
        )
    else:
        font = load_font_noto_sans_cjk_sc(pt, (198, 40, 40))
    _font_cache[key] = font
    return font


def _zh_font_pts(pt_p: int, pt_h: int, pt_m: int, meaning_lang: str) -> tuple[int, int, int]:
    if not _is_zh_meaning_lang(meaning_lang):
        return pt_p, pt_h, pt_m
    return (
        pt_p,
        max(1, int(round(pt_h * ZH_HANZI_SCALE))),
        max(1, int(round(pt_m * ZH_MEANING_SCALE))),
    )


def compute_card_line_screen_rects(
    box: WordMemorizeBox,
    word: Word,
    card_meaning: str,
    *,
    meaning_lang: str = "ko",
    show_images: bool = True,
    image_height: int = 0,
) -> dict[str, pygame.Rect]:
    """pinyin/hanzi/meaning 줄별 화면 좌표 rect."""
    outer = pygame.Rect(int(box.x), int(box.y), int(box.w), int(box.h))
    inner = outer.inflate(-CARD_INNER_PAD * 2, -CARD_INNER_PAD * 2)
    if inner.width <= 0 or inner.height <= 0:
        return {}

    pt_p, pt_h, pt_m = _zh_font_pts(PINYIN_FONT_PT, HANZI_FONT_PT, MEANING_FONT_PT, meaning_lang)
    font_p = _card_font("pinyin", pt_p, meaning_lang=meaning_lang)
    font_h = _card_font("hanzi", pt_h, meaning_lang=meaning_lang, weight="bold")
    font_m = _card_font("meaning", pt_m, meaning_lang=meaning_lang)

    line_heights: list[int] = []
    line_roles: list[str] = []
    line_widths: list[int] = []

    pinyin = _display_pinyin(word)
    if pinyin and font_p is not None:
        surf = font_p.render(pinyin[:48], True, (198, 40, 40))
        line_heights.append(surf.get_height())
        line_widths.append(surf.get_width())
        line_roles.append("pinyin")

    hanzi = (word.word or "").strip()
    if hanzi and font_h is not None:
        surf = font_h.render(hanzi, True, (33, 33, 33))
        line_heights.append(surf.get_height())
        line_widths.append(surf.get_width())
        line_roles.append("hanzi")

    meaning = (card_meaning or "").strip()
    if meaning and font_m is not None:
        surf = font_m.render(meaning[:40], True, (76, 175, 80))
        line_heights.append(surf.get_height())
        line_widths.append(surf.get_width())
        line_roles.append("meaning")

    img_h = max(0, int(image_height))
    if img_h <= 0 and show_images:
        img_h = max(32, int(inner.height * IMG_MAX_HEIGHT_RATIO))

    _start, line_ys, _image_y = layout_card_content_vertical(
        inner.height,
        line_heights,
        img_h if show_images else 0,
        default_gap=default_card_item_gap(inner.height),
        bottom_pad=CARD_IMG_BOTTOM_PAD_FHD if show_images and img_h > 0 else 0,
    )

    out: dict[str, pygame.Rect] = {}
    cx = inner.centerx
    for role, y_off, w, h in zip(line_roles, line_ys, line_widths, line_heights):
        x = cx - w // 2
        y = inner.top + y_off
        out[role] = pygame.Rect(x, y, w, h)
    return out
