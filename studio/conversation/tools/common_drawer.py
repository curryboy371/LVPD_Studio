"""Common rendering tools for Conversation steps."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal, Optional

import pygame

from ..core.types import SentenceRenderData, SentenceStyleConfig


Align = Literal["center", "left", "right"]


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
        """한자 → 병음 → 번역 순으로 y_base부터 line_gap만큼 내려가며 그린다."""
        alpha = int(max(0, min(255, alpha)))
        hanzi = (data.sentence or "")[: style.max_hanzi]
        pinyin = (data.pinyin or "")[: style.max_pinyin]
        trans = (data.translation or "")[: style.max_translation]

        y = y_base
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

        if pinyin:
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

        if trans:
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

