"""Common rendering tools for Conversation steps."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal, Optional

import pygame

from utils.tone_icon_assets import load_tone_icon_surface, tone_icon_path

from ..core.types import (
    ConversationItemLike,
    FrameContext,
    SentenceRenderData,
    SentenceStyleConfig,
    build_sentence_render_data_with_tone_icons,
)
from .fade_controller import FadeController
from .tone_icon_renderer import (
    TONE_ICON_GAP_ABOVE_PX,
    ToneIconRenderer,
    split_pinyin_syllables,
)


Align = Literal["center", "left", "right"]
AlignV = Literal["center", "top", "bottom"]


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


@dataclass
class _LRUSentenceDataCache:
    """item → SentenceRenderData (빠른 스크롤 시 최근 N개 재사용)."""

    cap: int = 32
    _cache: "OrderedDict[Any, SentenceRenderData]" = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._cache = OrderedDict()

    def get(self, key: Any) -> Optional[SentenceRenderData]:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, key: Any, value: SentenceRenderData) -> None:
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
        """폰트 묶음·텍스트 캐시·페이드·성조 아이콘 렌더러를 초기화한다."""
        self._fonts = fonts
        self._cache_hanzi = _LRUTextCache()
        self._cache_pinyin = _LRUTextCache()
        self._cache_translation = _LRUTextCache()
        self._fade = FadeController()
        self._sentence_data_cache = _LRUSentenceDataCache()
        self._tone_icons = ToneIconRenderer(
            get_pinyin_pair=lambda text, color: self._get_cached_text_pair(
                self._cache_pinyin, self._fonts.pinyin_ft, self._fonts.pinyin_pg, text, color
            )
        )

    def fade_on(self, channel: str, sec: float = 0.0) -> None:
        """채널 알파를 255로 맞추되 sec>0이면 그 시간에 걸쳐 보간한다."""
        self._fade.fade_on(channel, sec)

    def fade_off(self, channel: str, sec: float = 0.0) -> None:
        """채널 알파를 0으로 내린다(선택적 페이드 시간)."""
        self._fade.fade_off(channel, sec)

    def fade_all_off(self, channels: list[str], sec: float = 0.0) -> None:
        """여러 채널을 한꺼번에 fade_off."""
        self._fade.fade_all_off(channels, sec)

    def fade_tick(self, dt_sec: float) -> None:
        """진행 중인 페이드 상태를 dt만큼 전진시킨다."""
        self._fade.tick(dt_sec)

    def fade_alpha(self, channel: str) -> int:
        """채널의 현재 알파(0~255); 없으면 0."""
        return self._fade.alpha(str(channel or "").strip())

    def measure_sentence_block_extents(self, data: SentenceRenderData, style: SentenceStyleConfig) -> tuple[int, int]:
        """문장 블록의 세로 범위. (y_base 위로 돌출, y_base 아래로 돌출) 픽셀.

        `y_base`는 `draw_sentence`의 첫 줄(병음 또는 한자) 상단과 같다.
        성조 아이콘은 병음 위로만 그려지므로 `extent_above`에 포함된다.
        """
        hanzi = (data.sentence or "")[: style.text.max_hanzi]
        pinyin = (data.pinyin or "")[: style.text.max_pinyin]
        trans = (data.translation or "")[: style.text.max_translation]

        extent_above = 0
        if pinyin:
            syllables = split_pinyin_syllables(pinyin)
            slots = data.tone_icon_slots or ()
            aligned = self._tone_icons.align_tone_icon_slots(syllables, slots) if syllables else ()
            max_icon_h = 0
            for slot in aligned:
                if slot is None:
                    continue
                path = tone_icon_path(slot.phonetic_tone, is_mismatch=slot.is_mismatch)
                if path is None:
                    continue
                # 모듈 전역 LRU — 매 프레임 디스크 로드 없음
                surf = load_tone_icon_surface(path, pygame, is_mismatch=slot.is_mismatch)
                if surf is not None:
                    max_icon_h = max(max_icon_h, int(surf.get_height()))
            if max_icon_h > 0:
                extent_above = max_icon_h + TONE_ICON_GAP_ABOVE_PX

        h_pinyin = self._cached_line_height(
            self._cache_pinyin, self._fonts.pinyin_ft, self._fonts.pinyin_pg, pinyin, style.colors.pinyin_color
        )
        h_hanzi = self._cached_line_height(
            self._cache_hanzi, self._fonts.hanzi_ft, self._fonts.hanzi_pg, hanzi, style.colors.hanzi_color
        )
        h_trans = 0
        if (trans or "").strip():
            surf = self._get_cached_translation_surf(trans, style.colors.translation_color)
            h_trans = int(surf.get_height()) if surf is not None else 0

        extent_below = 0
        if pinyin:
            extent_below += h_pinyin + style.layout.line_gap_px
        extent_below += h_hanzi
        if (trans or "").strip():
            extent_below += style.layout.line_gap_px + style.layout.translation_extra_gap_px + h_trans
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
        """타이틀 기준 세로 위치(화면 높이 비율)."""
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
        cached = self._sentence_data_cache.get(key)
        if cached is not None:
            data = cached
        else:
            data = build_sentence_render_data_with_tone_icons(item)
            self._sentence_data_cache.put(key, data)
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
            color=style.colors.hanzi_color,
            align=align,
            min_margin_x=style.layout.min_margin_x,
        )

    def _cached_line_height(
        self,
        cache: _LRUTextCache,
        font_ft: Any,
        font_pg: Any,
        text: str,
        color: tuple[int, int, int],
    ) -> int:
        """한 줄 텍스트의 렌더 높이(캐시된 서피스 기준)."""
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
        """폰트·문자열·색 키로 (surf, rect) 쌍을 캐시에서 가져오거나 렌더해 넣는다."""
        key = _text_cache_key(font_ft, font_pg, text, color)
        cached = cache.get(key)
        if cached is None:
            cached = self._render_text(font_ft, font_pg, text, color)
            cache.put(key, cached)
        return cached

    def _get_cached_translation_surf(self, text: str, color: tuple[int, int, int]) -> Any:
        """번역용 폰트로 렌더한 서피스를 전용 캐시에서 반환한다."""
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
        """set_alpha 실험 후 원래 알파 상태로 되돌린다."""
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
        """정렬·여백을 적용해 서피스를 화면에 붙이되 alpha<255면 임시 알파를 쓴다."""
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
        hanzi = (data.sentence or "")[: style.text.max_hanzi]
        pinyin = (data.pinyin or "")[: style.text.max_pinyin]
        trans = (data.translation or "")[: style.text.max_translation]

        y = y_base
        if pinyin:
            slots = data.tone_icon_slots or ()
            if slots:
                self._tone_icons.draw_above_pinyin(
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
                color=style.colors.pinyin_color,
                center_x=center_x,
                y=y,
                alpha=a,
                min_margin_x=style.layout.min_margin_x,
                align=align,
            )
            y += style.layout.line_gap_px

        self._blit_text(
            screen,
            cache=self._cache_hanzi,
            font_ft=self._fonts.hanzi_ft,
            font_pg=self._fonts.hanzi_pg,
            text=hanzi,
            color=style.colors.hanzi_color,
            center_x=center_x,
            y=y,
            alpha=a,
            min_margin_x=style.layout.min_margin_x,
            align=align,
        )
        y += style.layout.line_gap_px

        if trans:
            y += style.layout.translation_extra_gap_px
            surf = self._get_cached_translation_surf(trans, style.colors.translation_color)
            self._blit_surface_with_alpha(
                screen,
                surf,
                center_x=center_x,
                y=y,
                min_margin_x=style.layout.min_margin_x,
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
        """freeType 우선, 실패 시 pygame.font로 한 줄을 렌더한다."""
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
        """캐시된 텍스트 서피스를 알파·정렬에 맞춰 화면에 붙인다."""
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
        """center/left/right와 최소 여백을 적용해 서피스 좌표를 잡고 blit한다."""
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

