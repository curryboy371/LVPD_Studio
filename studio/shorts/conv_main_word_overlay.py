"""숏츠 회화: 영상 아래 main_slot 단어 이미지 + 한자·병음·뜻."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

import pygame

from core.paths import get_repo_root
from studio.shorts.constants import (
    KARAOKE_ACTIVE_PINYIN,
    KO_KARAOKE_ACTIVE,
    shorts_conv_main_word_img_max,
    shorts_conv_main_word_label_font_size,
    shorts_conv_main_word_label_gap,
    shorts_conv_main_word_meaning_font_pt,
)
from utils.fonts import load_font_chinese, load_font_kr_chinese

_img_cache: dict[str, pygame.Surface | None] = {}


def _scale_word_image(surf: pygame.Surface, *, max_px: int) -> pygame.Surface:
    sw, sh = surf.get_size()
    scale = min(max_px / max(sw, 1), max_px / max(sh, 1), 1.0)
    if scale >= 1.0:
        return surf
    nw = max(1, int(sw * scale))
    nh = max(1, int(sh * scale))
    if hasattr(pygame.transform, "smoothscale"):
        return pygame.transform.smoothscale(surf, (nw, nh))
    return pygame.transform.scale(surf, (nw, nh))


def _load_word_image(img_path: str, *, max_px: int) -> Optional[pygame.Surface]:
    key = (img_path or "").strip()
    if not key:
        return None
    if key in _img_cache:
        return _img_cache[key]
    path = Path(key.replace("\\", "/"))
    if not path.is_absolute():
        path = get_repo_root() / path
    if not path.is_file():
        _img_cache[key] = None
        return None
    try:
        surf = pygame.image.load(str(path)).convert_alpha()
    except Exception:
        _img_cache[key] = None
        return None
    scaled = _scale_word_image(surf, max_px=max_px)
    _img_cache[key] = scaled
    return scaled


def _render_part(font: Any, text: str, color: tuple[int, int, int]) -> Optional[pygame.Surface]:
    if font is None or not (text or "").strip():
        return None
    try:
        return font.render(text, True, color)
    except Exception:
        return None


def _compose_hanzi_pinyin_line(
    hanzi: str,
    pinyin: str,
    *,
    font_pt: int,
) -> Optional[pygame.Surface]:
    hanzi = (hanzi or "").strip()
    pinyin = (pinyin or "").strip()
    if not hanzi and not pinyin:
        return None

    font_kr = load_font_kr_chinese(font_pt, KO_KARAOKE_ACTIVE)
    font_py = load_font_chinese(font_pt, KARAOKE_ACTIVE_PINYIN) or font_kr
    if font_kr is None and font_py is None:
        return None

    parts: list[pygame.Surface] = []
    if hanzi and pinyin:
        for text, font, color in (
            (hanzi, font_kr or font_py, KO_KARAOKE_ACTIVE),
            ("(", font_kr or font_py, KO_KARAOKE_ACTIVE),
            (pinyin, font_py or font_kr, KARAOKE_ACTIVE_PINYIN),
            (")", font_kr or font_py, KO_KARAOKE_ACTIVE),
        ):
            surf = _render_part(font, text, color)
            if surf is not None:
                parts.append(surf)
    elif hanzi:
        surf = _render_part(font_kr or font_py, hanzi, KO_KARAOKE_ACTIVE)
        if surf is not None:
            parts.append(surf)
    else:
        surf = _render_part(font_py or font_kr, pinyin, KARAOKE_ACTIVE_PINYIN)
        if surf is not None:
            parts.append(surf)

    if not parts:
        return None

    total_w = sum(s.get_width() for s in parts)
    max_h = max(s.get_height() for s in parts)
    out = pygame.Surface((total_w, max_h), pygame.SRCALPHA)
    x = 0
    for surf in parts:
        y = (max_h - surf.get_height()) // 2
        out.blit(surf, (x, y))
        x += surf.get_width()
    return out


def _render_meaning_line(meaning: str, *, font_pt: int) -> Optional[pygame.Surface]:
    meaning = (meaning or "").strip()
    if not meaning:
        return None
    font = load_font_kr_chinese(font_pt, KO_KARAOKE_ACTIVE)
    if font is None:
        return None
    return font.render(meaning, True, KO_KARAOKE_ACTIVE)


def draw_conv_main_word_overlay(
    screen: pygame.Surface,
    *,
    meta: Mapping[str, Any],
    anchor_top_y: int,
    fade_alpha: int = 255,
) -> bool:
    """영상 바로 아래: 단어 이미지 → 한자(병음) / 뜻. 성공 시 True."""
    alpha = max(0, min(255, int(fade_alpha)))
    if alpha <= 0:
        return False

    img_path = str(meta.get("main_word_img_path") or meta.get("img_path") or "").strip()
    hanzi = str(meta.get("main_word_hanzi") or meta.get("hanzi") or "").strip()
    pinyin = str(meta.get("main_word_pinyin") or meta.get("pinyin") or "").strip()
    meaning = str(meta.get("main_word_meaning") or meta.get("meaning") or "").strip()
    if not img_path and not hanzi and not pinyin and not meaning:
        return False

    screen.set_clip(None)
    fw, fh = screen.get_width(), screen.get_height()
    max_px = shorts_conv_main_word_img_max(fh)
    img_surf = _load_word_image(img_path, max_px=max_px) if img_path else None
    font_pt = shorts_conv_main_word_label_font_size(fh)
    meaning_pt = shorts_conv_main_word_meaning_font_pt(font_pt)
    hanzi_line = _compose_hanzi_pinyin_line(hanzi, pinyin, font_pt=font_pt)
    meaning_line = _render_meaning_line(meaning, font_pt=meaning_pt)

    label_gap = shorts_conv_main_word_label_gap(fh)
    line_gap = label_gap
    cursor_y = max(0, int(anchor_top_y))

    if img_surf is not None:
        ix = (fw - img_surf.get_width()) // 2
        if alpha < 255:
            img_surf = img_surf.copy()
            img_surf.set_alpha(alpha)
        screen.blit(img_surf, (ix, cursor_y))
        cursor_y += img_surf.get_height() + label_gap

    drew_text = False
    if hanzi_line is not None:
        lx = (fw - hanzi_line.get_width()) // 2
        if alpha < 255:
            hanzi_line = hanzi_line.copy()
            hanzi_line.set_alpha(alpha)
        screen.blit(hanzi_line, (lx, cursor_y))
        cursor_y += hanzi_line.get_height() + line_gap
        drew_text = True

    if meaning_line is not None:
        lx = (fw - meaning_line.get_width()) // 2
        if alpha < 255:
            meaning_line = meaning_line.copy()
            meaning_line.set_alpha(alpha)
        screen.blit(meaning_line, (lx, cursor_y))
        drew_text = True

    return img_surf is not None or drew_text


# 하위 호환
draw_conv_main_word_above_icon = draw_conv_main_word_overlay
