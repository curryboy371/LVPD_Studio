"""Common rendering tools for Conversation steps."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal, Optional

import pygame

from utils.tone_icon_assets import load_tone_icon_surface, tone_icon_path
from utils.tone_icon_layout import ToneIconSlot

from ..core.types import SentenceRenderData, SentenceStyleConfig


Align = Literal["center", "left", "right"]

# 병음 줄 위 성조 아이콘
_TONE_ICON_GAP_ABOVE_PX = 8


def _split_pinyin_syllables(s: str) -> list[str]:
    return [x for x in s.strip().split() if x]


def _font_sig(font: Any) -> tuple[Any, ...]:
    if font is None:
        return ("none", 0)
    name: Any
    try:
        name = font.get_name()
    except Exception:
        name = type(font).__name__
    h = 0
    try:
        h = int(font.get_height())
    except Exception:
        h = 0
    bold: Any
    try:
        bold = bool(font.get_bold())
    except Exception:
        bold = None
    italic: Any
    try:
        italic = bool(font.get_italic())
    except Exception:
        italic = None
    return (name, h, bold, italic)


@dataclass
class _LRUTextCache:
    cap: int = 2048
    _cache: "OrderedDict[tuple[Any, ...], tuple[Any, Any]]" = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._cache = OrderedDict()

    def get(self, key: tuple[Any, ...]) -> Optional[tuple[Any, Any]]:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, key: tuple[Any, ...], value: tuple[Any, Any]) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        if len(self._cache) > self.cap:
            self._cache.popitem(last=False)


class CommonDrawer:
    """공통 렌더러.

    - 문장(한자/병음/번역) 렌더링을 1곳으로 모은다.
    - Step은 '무엇을 그릴지'만 결정하고, 실제 텍스트 draw는 여기서 수행한다.
    """

    def __init__(self, *, fonts: Any) -> None:
        self._fonts = fonts
        self._cache_hanzi = _LRUTextCache()
        self._cache_pinyin = _LRUTextCache()

    def _pinyin_syllable_center_xs(
        self,
        syllables: list[str],
        *,
        color: tuple[int, int, int],
        center_x: int,
        min_margin_x: int,
        align: Align,
    ) -> list[int]:
        """공백 구분 음절 각각의 가로 중심 x (화면 좌표)."""
        if not syllables:
            return []
        widths: list[int] = []
        for syl in syllables:
            surf, _ = self._render_text(self._fonts.pinyin_ft, self._fonts.pinyin_pg, syl, color)
            if surf is None:
                widths.append(0)
            else:
                widths.append(int(surf.get_width()))
        try:
            sp_surf, _ = self._render_text(self._fonts.pinyin_ft, self._fonts.pinyin_pg, " ", color)
            space_w = int(sp_surf.get_width()) if sp_surf is not None else 0
        except Exception:
            space_w = 0
        total = sum(widths) + space_w * max(0, len(syllables) - 1)
        if align == "center":
            left = center_x - total // 2
        elif align == "left":
            left = center_x
        else:
            left = center_x - total
        left = max(min_margin_x, int(left))
        centers: list[int] = []
        x = left
        for i, w in enumerate(widths):
            centers.append(x + (w // 2 if w else 0))
            x += w
            if i < len(widths) - 1:
                x += space_w
        return centers

    def _align_tone_icon_slots(
        self, syllables: list[str], slots: tuple[Optional[ToneIconSlot], ...]
    ) -> tuple[Optional[ToneIconSlot], ...]:
        k = len(syllables)
        if k == 0:
            return ()
        lst = list(slots[:k]) if len(slots) >= k else list(slots) + [None] * (k - len(slots))
        return tuple(lst[:k])

    def _draw_tone_icons_above_pinyin(
        self,
        screen: pygame.Surface,
        *,
        pinyin_line: str,
        slots: tuple[Optional[ToneIconSlot], ...],
        y_pinyin: int,
        center_x: int,
        style: SentenceStyleConfig,
        alpha: int,
        align: Align,
    ) -> None:
        syllables = _split_pinyin_syllables(pinyin_line)
        if not syllables or not any(s is not None for s in slots):
            return
        aligned = self._align_tone_icon_slots(syllables, slots)
        color = style.pinyin_color
        centers = self._pinyin_syllable_center_xs(
            syllables,
            color=color,
            center_x=center_x,
            min_margin_x=style.min_margin_x,
            align=align,
        )
        for i, slot in enumerate(aligned):
            if slot is None or i >= len(centers):
                continue
            path = tone_icon_path(slot.phonetic_tone, is_mismatch=slot.is_mismatch)
            if path is None:
                continue
            surf = load_tone_icon_surface(path, pygame, is_mismatch=slot.is_mismatch)
            if surf is None:
                continue
            if alpha < 255:
                surf = surf.copy()
                surf.set_alpha(alpha)
            cx = centers[i]
            y = y_pinyin - _TONE_ICON_GAP_ABOVE_PX - surf.get_height()
            x = cx - surf.get_width() // 2
            x = max(style.min_margin_x, x)
            screen.blit(surf, (x, y))

    def draw_sentence(
        self,
        screen: pygame.Surface,
        data: SentenceRenderData,
        *,
        center_x: int,
        y_base: int,
        style: SentenceStyleConfig,
        alpha: int = 255,
        align: Align = "center",
    ) -> None:
        """병음 → 한자 → 번역 순으로 y_base부터 line_gap만큼 내려가며 그린다.
        한자와 번역 사이는 line_gap + translation_extra_gap_px."""
        alpha = int(max(0, min(255, alpha)))
        hanzi = (data.sentence or "")[: style.max_hanzi]
        pinyin = (data.pinyin or "")[: style.max_pinyin]
        trans = (data.translation or "")[: style.max_translation]

        y = y_base
        if pinyin:
            slots = data.tone_icon_slots or ()
            if slots:
                self._draw_tone_icons_above_pinyin(
                    screen,
                    pinyin_line=pinyin,
                    slots=slots,
                    y_pinyin=y,
                    center_x=center_x,
                    style=style,
                    alpha=alpha,
                    align=align,
                )
            self._blit_text(
                screen,
                cache=self._cache_pinyin,
                font_ft=self._fonts.pinyin_ft,
                font_pg=self._fonts.pinyin_pg,
                text=pinyin,
                color=style.pinyin_color,
                center_x=center_x,
                y=y,
                alpha=alpha,
                min_margin_x=style.min_margin_x,
                align=align,
            )
            y += style.line_gap_px

        self._blit_text(
            screen,
            cache=self._cache_hanzi,
            font_ft=self._fonts.hanzi_ft,
            font_pg=self._fonts.hanzi_pg,
            text=hanzi,
            color=style.hanzi_color,
            center_x=center_x,
            y=y,
            alpha=alpha,
            min_margin_x=style.min_margin_x,
            align=align,
        )
        y += style.line_gap_px

        if trans:
            y += style.translation_extra_gap_px
            surf = self._fonts.translation_pg.render(trans, True, style.translation_color)
            if alpha < 255:
                surf.set_alpha(alpha)
            self._blit_surface(screen, surf, center_x=center_x, y=y, min_margin_x=style.min_margin_x, align=align)

    def draw_tone_graph(self, screen: pygame.Surface, data: Any, rect: pygame.Rect, style: Any = None) -> None:
        """성조 그래프 렌더링 훅(현재 render_only 범위에서는 stub)."""
        _ = (screen, data, rect, style)
        return

    def _render_text(self, font_ft: Any, font_pg: Any, text: str, color: tuple[int, int, int]) -> tuple[Any, Any]:
        if font_ft is not None:
            try:
                surf, rect = font_ft.render(text, color)
                return surf, rect
            except Exception:
                pass
        surf = font_pg.render(text, True, color)
        return surf, surf.get_rect()

    def _blit_text(
        self,
        screen: pygame.Surface,
        *,
        cache: _LRUTextCache,
        font_ft: Any,
        font_pg: Any,
        text: str,
        color: tuple[int, int, int],
        center_x: int,
        y: int,
        alpha: int,
        min_margin_x: int,
        align: Align,
    ) -> None:
        key = (_font_sig(font_ft), _font_sig(font_pg), text, color)
        cached = cache.get(key)
        if cached is None:
            cached = self._render_text(font_ft, font_pg, text, color)
            cache.put(key, cached)
        surf, _ = cached
        if surf is None:
            return
        if alpha < 255:
            surf = surf.copy()
            surf.set_alpha(alpha)
        self._blit_surface(screen, surf, center_x=center_x, y=y, min_margin_x=min_margin_x, align=align)

    def _blit_surface(
        self,
        screen: pygame.Surface,
        surf: pygame.Surface,
        *,
        center_x: int,
        y: int,
        min_margin_x: int,
        align: Align,
    ) -> None:
        if surf is None:
            return
        if align == "center":
            x = center_x - surf.get_width() // 2
        elif align == "left":
            x = center_x
        else:
            x = center_x - surf.get_width()
        x = max(min_margin_x, x)
        screen.blit(surf, (x, y))

