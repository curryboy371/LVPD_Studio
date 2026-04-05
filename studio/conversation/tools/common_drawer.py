"""Common rendering tools for Conversation steps."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal, Optional

import pygame

from utils.tone_icon_assets import load_tone_icon_surface, tone_icon_path
from utils.tone_icon_layout import ToneIconSlot

from ..core.types import (
    ConversationItemLike,
    FrameContext,
    SentenceRenderData,
    SentenceStyleConfig,
    build_sentence_render_data_with_tone_icons,
)


Align = Literal["center", "left", "right"]
AlignV = Literal["center", "top", "bottom"]

# 병음 줄 위 성조 아이콘
_TONE_ICON_GAP_ABOVE_PX = 8


def _split_pinyin_syllables(s: str) -> list[str]:
    return [x for x in s.strip().split() if x]


def _text_cache_key(font_ft: Any, font_pg: Any, text: str, color: tuple[int, int, int]) -> tuple[Any, ...]:
    """폰트 객체 id + 문자열 + 색으로 캐시 키를 만든다 (매 프레임 메타데이터 조회 비용 절감)."""
    return (id(font_ft), id(font_pg), text, color)


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
    - Step은 아이템·채널·레이아웃 의도(`align_v` 등)만 넘기고, item→`SentenceRenderData` 변환과
      세로 배치는 Drawer 내부에서 처리한다.
    """

    # `draw_item_sentence` 기본(align_v=center): 블록 시각적 중심이 놓일 세로 위치(화면 높이 비율)
    ITEM_SENTENCE_CENTER_Y_RATIO = 0.43

    def __init__(self, *, fonts: Any) -> None:
        self._fonts = fonts
        self._cache_hanzi = _LRUTextCache()
        self._cache_pinyin = _LRUTextCache()
        self._cache_translation = _LRUTextCache()
        self._fade_states: dict[str, dict[str, float | int]] = {}
        self._sentence_data_cache_key: Any | None = None
        self._sentence_data_cache_val: SentenceRenderData | None = None

    def fade_on(self, channel: str, sec: float = 0.0) -> None:
        self._start_fade(channel, target_alpha=255, sec=sec)

    def fade_off(self, channel: str, sec: float = 0.0) -> None:
        self._start_fade(channel, target_alpha=0, sec=sec)

    def fade_all_off(self, channels: list[str], sec: float = 0.0) -> None:
        for ch in channels:
            self.fade_off(ch, sec)

    def fade_tick(self, dt_sec: float) -> None:
        dt = max(0.0, float(dt_sec))
        if dt <= 0.0 or not self._fade_states:
            return
        for st in self._fade_states.values():
            sec = float(st.get("sec", 0.0) or 0.0)
            if sec <= 1e-6:
                continue
            elapsed = float(st.get("elapsed", 0.0) or 0.0) + dt
            frm = int(st.get("from", 0) or 0)
            to = int(st.get("to", 0) or 0)
            t = max(0.0, min(1.0, elapsed / sec))
            st["alpha"] = int(frm + (to - frm) * t)
            if t >= 1.0:
                st["alpha"] = to
                st["from"] = to
                st["to"] = to
                st["elapsed"] = 0.0
                st["sec"] = 0.0
            else:
                st["elapsed"] = elapsed

    def fade_alpha(self, channel: str) -> int:
        st = self._fade_states.get(channel)
        if st is None:
            return 0
        return max(0, min(255, int(st.get("alpha", 0) or 0)))

    def _start_fade(self, channel: str, *, target_alpha: int, sec: float) -> None:
        key = str(channel or "").strip()
        if not key:
            return
        st = self._fade_states.get(key)
        cur = int(st.get("alpha", 0) or 0) if st is not None else 0
        to = max(0, min(255, int(target_alpha)))
        duration = max(0.0, float(sec))
        if duration <= 1e-6:
            self._fade_states[key] = {
                "alpha": to,
                "from": to,
                "to": to,
                "elapsed": 0.0,
                "sec": 0.0,
            }
            return
        self._fade_states[key] = {
            "alpha": cur,
            "from": cur,
            "to": to,
            "elapsed": 0.0,
            "sec": duration,
        }

    def measure_sentence_block_extents(self, data: SentenceRenderData, style: SentenceStyleConfig) -> tuple[int, int]:
        """문장 블록의 세로 범위. (y_base 위로 돌출, y_base 아래로 돌출) 픽셀.

        `y_base`는 `draw_sentence`의 첫 줄(병음 또는 한자) 상단과 같다.
        성조 아이콘은 병음 위로만 그려지므로 `extent_above`에 포함된다.
        """
        hanzi = (data.sentence or "")[: style.max_hanzi]
        pinyin = (data.pinyin or "")[: style.max_pinyin]
        trans = (data.translation or "")[: style.max_translation]

        extent_above = 0
        if pinyin:
            syllables = _split_pinyin_syllables(pinyin)
            slots = data.tone_icon_slots or ()
            aligned = self._align_tone_icon_slots(syllables, slots) if syllables else ()
            max_icon_h = 0
            for slot in aligned:
                if slot is None:
                    continue
                path = tone_icon_path(slot.phonetic_tone, is_mismatch=slot.is_mismatch)
                if path is None:
                    continue
                surf = load_tone_icon_surface(path, pygame, is_mismatch=slot.is_mismatch)
                if surf is not None:
                    max_icon_h = max(max_icon_h, int(surf.get_height()))
            if max_icon_h > 0:
                extent_above = max_icon_h + _TONE_ICON_GAP_ABOVE_PX

        h_pinyin = self._cached_line_height(
            self._cache_pinyin, self._fonts.pinyin_ft, self._fonts.pinyin_pg, pinyin, style.pinyin_color
        )
        h_hanzi = self._cached_line_height(
            self._cache_hanzi, self._fonts.hanzi_ft, self._fonts.hanzi_pg, hanzi, style.hanzi_color
        )
        h_trans = 0
        if (trans or "").strip():
            surf = self._get_cached_translation_surf(trans, style.translation_color)
            h_trans = int(surf.get_height()) if surf is not None else 0

        extent_below = 0
        if pinyin:
            extent_below += h_pinyin + style.line_gap_px
        extent_below += h_hanzi
        if (trans or "").strip():
            extent_below += style.line_gap_px + style.translation_extra_gap_px + h_trans
        return extent_above, extent_below

    def y_base_for_vertical_center(self, center_y: int, data: SentenceRenderData, style: SentenceStyleConfig) -> int:
        """블록의 시각적 세로 중심이 `center_y`가 되도록 하는 `y_base` (첫 줄 상단)."""
        above, below = self.measure_sentence_block_extents(data, style)
        return int(center_y - (below - above) / 2)

    @staticmethod
    def _sentence_item_cache_key(item: ConversationItemLike) -> Any:
        try:
            return (
                str(item.get("id") or ""),
                float(item.get("start_time", 0.0) or 0.0),
                float(item.get("end_time", -1.0) or -1.0),
            )
        except Exception:
            return id(item)

    def layout_sentence_y_base(
        self,
        ctx: FrameContext,
        data: SentenceRenderData,
        style: SentenceStyleConfig,
        *,
        align_v: AlignV = "center",
        center_y_ratio: float = 0.43,
        top_y_ratio: float = 0.12,
        bottom_margin_px: int = 48,
    ) -> int:
        """문장 블록 첫 줄 상단(`y_base`)을 세로 정렬 모드에 맞게 계산한다."""
        h = max(1, int(ctx.height))
        if align_v == "center":
            cy = int(h * float(center_y_ratio))
            return self.y_base_for_vertical_center(cy, data, style)
        if align_v == "top":
            return int(h * float(top_y_ratio))
        above, below = self.measure_sentence_block_extents(data, style)
        return max(0, h - int(bottom_margin_px) - below)

    def layout_title_y(self, ctx: FrameContext, *, y_ratio: float = 0.12) -> int:
        return int(ctx.height * float(y_ratio))

    def draw_item_sentence(
        self,
        screen: pygame.Surface,
        item: ConversationItemLike,
        *,
        ctx: FrameContext,
        channel: str,
        style: SentenceStyleConfig,
        align: Align = "center",
        align_v: AlignV = "center",
        top_y_ratio: float = 0.12,
        bottom_margin_px: int = 48,
    ) -> None:
        """`build_sentence_render_data_with_tone_icons`로 item을 변환(아이템 단위 캐시) 후 레이아웃·`draw_sentence`.

        `align_v`가 ``center``일 때 세로 앵커는 `ITEM_SENTENCE_CENTER_Y_RATIO`(기본 0.43)로 고정한다.
        """
        key = self._sentence_item_cache_key(item)
        if self._sentence_data_cache_key == key and self._sentence_data_cache_val is not None:
            data = self._sentence_data_cache_val
        else:
            data = build_sentence_render_data_with_tone_icons(item)
            self._sentence_data_cache_key = key
            self._sentence_data_cache_val = data
        center_y_ratio = self.ITEM_SENTENCE_CENTER_Y_RATIO if align_v == "center" else 0.43
        y_base = self.layout_sentence_y_base(
            ctx,
            data,
            style,
            align_v=align_v,
            center_y_ratio=center_y_ratio,
            top_y_ratio=top_y_ratio,
            bottom_margin_px=bottom_margin_px,
        )
        self.draw_sentence(
            screen,
            data,
            channel=channel,
            center_x=int(ctx.width) // 2,
            y_base=y_base,
            style=style,
            align=align,
        )

    def draw_item_title(
        self,
        screen: pygame.Surface,
        text: str,
        *,
        ctx: FrameContext,
        channel: str,
        style: SentenceStyleConfig,
        align: Align = "center",
        y_ratio: float = 0.12,
    ) -> None:
        """타이틀 세로 위치를 `ctx` 기준으로 잡고 `draw_title`로 그린다."""
        self.draw_title(
            screen,
            text,
            channel=channel,
            center_x=int(ctx.width) // 2,
            y=self.layout_title_y(ctx, y_ratio=y_ratio),
            color=style.hanzi_color,
            align=align,
            min_margin_x=style.min_margin_x,
        )

    def _cached_line_height(
        self,
        cache: _LRUTextCache,
        font_ft: Any,
        font_pg: Any,
        text: str,
        color: tuple[int, int, int],
    ) -> int:
        if not (text or "").strip():
            return 0
        surf, _ = self._get_cached_text_pair(cache, font_ft, font_pg, text, color)
        return int(surf.get_height()) if surf is not None else 0

    def _get_cached_text_pair(
        self,
        cache: _LRUTextCache,
        font_ft: Any,
        font_pg: Any,
        text: str,
        color: tuple[int, int, int],
    ) -> tuple[Any, Any]:
        key = _text_cache_key(font_ft, font_pg, text, color)
        cached = cache.get(key)
        if cached is None:
            cached = self._render_text(font_ft, font_pg, text, color)
            cache.put(key, cached)
        return cached

    def _get_cached_translation_surf(self, text: str, color: tuple[int, int, int]) -> Any:
        font_pg = self._fonts.translation_pg
        key = _text_cache_key(None, font_pg, text, color)
        cached = self._cache_translation.get(key)
        if cached is None:
            surf = font_pg.render(text, True, color)
            cached = (surf, surf.get_rect())
            self._cache_translation.put(key, cached)
        surf, _ = cached
        return surf

    @staticmethod
    def _restore_surface_alpha(surf: pygame.Surface, old: Any) -> None:
        try:
            if old is None:
                surf.set_alpha(None)
            else:
                surf.set_alpha(old)
        except Exception:
            pass

    def _blit_surface_with_alpha(
        self,
        screen: pygame.Surface,
        surf: pygame.Surface,
        *,
        center_x: int,
        y: int,
        min_margin_x: int,
        align: Align,
        alpha: int,
    ) -> None:
        if alpha <= 0:
            return
        if alpha >= 255:
            self._blit_surface(screen, surf, center_x=center_x, y=y, min_margin_x=min_margin_x, align=align)
            return
        old = surf.get_alpha()
        surf.set_alpha(alpha)
        try:
            self._blit_surface(screen, surf, center_x=center_x, y=y, min_margin_x=min_margin_x, align=align)
        finally:
            self._restore_surface_alpha(surf, old)

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
            surf, _ = self._get_cached_text_pair(
                self._cache_pinyin, self._fonts.pinyin_ft, self._fonts.pinyin_pg, syl, color
            )
            if surf is None:
                widths.append(0)
            else:
                widths.append(int(surf.get_width()))
        try:
            sp_surf, _ = self._get_cached_text_pair(
                self._cache_pinyin, self._fonts.pinyin_ft, self._fonts.pinyin_pg, " ", color
            )
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
            cx = centers[i]
            iy = y_pinyin - _TONE_ICON_GAP_ABOVE_PX - surf.get_height()
            ix = cx - surf.get_width() // 2
            ix = max(style.min_margin_x, ix)
            if alpha <= 0:
                continue
            if alpha >= 255:
                screen.blit(surf, (ix, iy))
            else:
                old_a = surf.get_alpha()
                surf.set_alpha(alpha)
                try:
                    screen.blit(surf, (ix, iy))
                finally:
                    self._restore_surface_alpha(surf, old_a)

    def draw_sentence(
        self,
        screen: pygame.Surface,
        data: SentenceRenderData,
        *,
        channel: str,
        center_x: int,
        y_base: int,
        style: SentenceStyleConfig,
        align: Align = "center",
        alpha: Optional[int] = None,
    ) -> None:
        """병음 → 한자 → 번역 순으로 y_base부터 line_gap만큼 내려가며 그린다.
        한자와 번역 사이는 line_gap + translation_extra_gap_px.

        알파는 기본적으로 `fade_alpha(channel)`을 따른다. `alpha`를 넘기면 그 값으로 오버라이드한다.
        """
        if alpha is not None:
            a = int(max(0, min(255, alpha)))
        else:
            a = self.fade_alpha(str(channel or "").strip())
        if a <= 0:
            return
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
                    alpha=a,
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
                alpha=a,
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
            alpha=a,
            min_margin_x=style.min_margin_x,
            align=align,
        )
        y += style.line_gap_px

        if trans:
            y += style.translation_extra_gap_px
            surf = self._get_cached_translation_surf(trans, style.translation_color)
            self._blit_surface_with_alpha(
                screen,
                surf,
                center_x=center_x,
                y=y,
                min_margin_x=style.min_margin_x,
                align=align,
                alpha=a,
            )

    def draw_title(
        self,
        screen: pygame.Surface,
        text: str,
        *,
        channel: str,
        center_x: int,
        y: int,
        color: tuple[int, int, int] = (255, 255, 255),
        align: Align = "center",
        min_margin_x: int = 20,
        alpha: Optional[int] = None,
    ) -> None:
        """타이틀 텍스트 렌더링. 폰트는 translation 폰트를 재사용한다.

        알파는 기본적으로 `fade_alpha(channel)`을 따른다. `alpha`를 넘기면 그 값으로 오버라이드한다.
        """
        if not text:
            return
        if alpha is not None:
            a = int(max(0, min(255, alpha)))
        else:
            a = self.fade_alpha(str(channel or "").strip())
        if a <= 0:
            return
        surf = self._get_cached_translation_surf(text, color)
        self._blit_surface_with_alpha(
            screen,
            surf,
            center_x=center_x,
            y=y,
            min_margin_x=min_margin_x,
            align=align,
            alpha=a,
        )

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
        surf, _ = self._get_cached_text_pair(cache, font_ft, font_pg, text, color)
        if surf is None:
            return
        self._blit_surface_with_alpha(
            screen,
            surf,
            center_x=center_x,
            y=y,
            min_margin_x=min_margin_x,
            align=align,
            alpha=alpha,
        )

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

