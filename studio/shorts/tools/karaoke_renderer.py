"""음성 동기 노래방 스타일 한자·병음 하이라이트 (좌→우 진행 채움)."""

from __future__ import annotations

from typing import Any, Optional

import pygame

from studio.conversation.core.types import SentenceRenderData, SentenceStyleConfig
from studio.conversation.tools.common_drawer import CommonDrawer
from studio.shorts.constants import (
    KARAOKE_ACTIVE_HANZI,
    KARAOKE_ACTIVE_PINYIN,
    KARAOKE_INACTIVE_HANZI,
    KARAOKE_INACTIVE_PINYIN,
    SHORTS_VOCAB_POS_FONT_RATIO,
)


def compute_karaoke_progress(elapsed_sec: float, duration_sec: float) -> float:
    """0..1 재생 진행률. duration 없으면 재생 시작 전 0, 경과 후 1."""
    dur = max(0.0, float(duration_sec))
    if dur <= 1e-6:
        return 1.0 if float(elapsed_sec) > 1e-6 else 0.0
    return max(0.0, min(1.0, float(elapsed_sec) / dur))


def blit_horizontal_karaoke_wipe(
    screen: pygame.Surface,
    surf_inactive: pygame.Surface,
    surf_active: pygame.Surface,
    *,
    center_x: int,
    y: int,
    progress: float,
) -> None:
    """비활성 색 전체 + 활성 색을 왼쪽부터 progress 비율만큼 덮어 그린다."""
    progress = max(0.0, min(1.0, float(progress)))
    w = surf_inactive.get_width()
    h = surf_inactive.get_height()
    if w <= 0 or h <= 0:
        return
    x = center_x - w // 2
    screen.blit(surf_inactive, (x, y))
    if progress <= 0:
        return
    fill_w = w if progress >= 1.0 else max(1, int(round(w * progress)))
    screen.blit(surf_active, (x, y), area=pygame.Rect(0, 0, fill_w, h))


class KaraokeRenderer:
    """middle 구역에 노래방 스타일 문장을 그린다."""

    def __init__(self, *, drawer: CommonDrawer) -> None:
        self._drawer = drawer

    def draw(
        self,
        screen: pygame.Surface,
        *,
        data: SentenceRenderData,
        rect: pygame.Rect,
        style: SentenceStyleConfig,
        elapsed_sec: float,
        syllable_times: list[float],
        sound_duration_sec: float,
        y_offset: int = 0,
        pinyin_y_offset: int = 0,
        pinyin_hanzi_gap: Optional[int] = None,
        translation_extra_gap: Optional[int] = None,
        vocab_pos: str = "",
        vocab_kr_font_pt: int = 36,
        after_hanzi_pad: int = 0,
        fixed_pinyin_y: Optional[int] = None,
        fixed_hanzi_y: Optional[int] = None,
    ) -> None:
        """병음·한자·번역을 rect 안에 배치하고 재생 진행에 따라 좌→우로 채운다."""
        del syllable_times  # 음절 단위 하이라이트 미사용
        pinyin = (data.pinyin or "").strip()
        hanzi = (data.sentence or "").strip()
        trans = (data.translation or "").strip()
        vocab_pos = (vocab_pos or "").strip()
        progress = compute_karaoke_progress(elapsed_sec, sound_duration_sec)

        center_x = rect.centerx
        line_gap = style.layout.line_gap_px

        if fixed_hanzi_y is not None:
            hz_y = int(fixed_hanzi_y)
            if pinyin and fixed_pinyin_y is not None:
                self._draw_pinyin_wipe(
                    screen,
                    pinyin=pinyin,
                    center_x=center_x,
                    y=int(fixed_pinyin_y),
                    rect=rect,
                    style=style,
                    progress=progress,
                )
            if hanzi:
                self._draw_hanzi_wipe(
                    screen,
                    hanzi=hanzi,
                    center_x=center_x,
                    y=hz_y,
                    style=style,
                    progress=progress,
                )
            return

        y = rect.top + 12 + max(0, int(y_offset)) + max(0, int(pinyin_y_offset))
        gap_py_hz = int(pinyin_hanzi_gap) if pinyin_hanzi_gap is not None else line_gap

        if pinyin:
            y = self._draw_pinyin_wipe(
                screen,
                pinyin=pinyin,
                center_x=center_x,
                y=y,
                rect=rect,
                style=style,
                progress=progress,
            )
            y += gap_py_hz

        if hanzi:
            y = self._draw_hanzi_wipe(
                screen,
                hanzi=hanzi,
                center_x=center_x,
                y=y,
                style=style,
                progress=progress,
            )
            pad_after = max(0, int(after_hanzi_pad))
            if pad_after:
                y += pad_after
            elif not vocab_pos:
                y += line_gap

        if vocab_pos:
            extra_trans = (
                int(translation_extra_gap)
                if translation_extra_gap is not None
                else style.layout.translation_extra_gap_px
            )
            y += extra_trans
            trans_color = style.colors.translation_color
            from utils.fonts import load_font_korean

            pos_pt = max(
                14, int(int(vocab_kr_font_pt) * float(SHORTS_VOCAB_POS_FONT_RATIO))
            )
            pos_font = load_font_korean(pos_pt, trans_color)
            if pos_font is not None:
                surf_pos = pos_font.render(vocab_pos, True, trans_color)
                self._drawer._blit_surface(
                    screen,
                    surf_pos,
                    center_x=center_x,
                    y=min(y, rect.bottom - surf_pos.get_height() - 8),
                    min_margin_x=style.layout.min_margin_x,
                    align="center",
                )
        elif trans:
            extra_trans = (
                int(translation_extra_gap)
                if translation_extra_gap is not None
                else style.layout.translation_extra_gap_px
            )
            y += extra_trans
            surf = self._drawer._get_cached_translation_surf(trans, style.colors.translation_color)
            self._drawer._blit_surface(
                screen,
                surf,
                center_x=center_x,
                y=min(y, rect.bottom - surf.get_height() - 8),
                min_margin_x=style.layout.min_margin_x,
                align="center",
            )

    def _draw_cached_wipe(
        self,
        screen: pygame.Surface,
        *,
        cache: Any,
        font_ft: Any,
        font_pg: Any,
        text: str,
        center_x: int,
        y: int,
        progress: float,
        inactive_color: tuple[int, int, int],
        active_color: tuple[int, int, int],
    ) -> int:
        if not text:
            return y
        surf_in, _ = self._drawer._get_cached_text_pair(
            cache, font_ft, font_pg, text, inactive_color
        )
        surf_ac, _ = self._drawer._get_cached_text_pair(
            cache, font_ft, font_pg, text, active_color
        )
        blit_horizontal_karaoke_wipe(
            screen, surf_in, surf_ac, center_x=center_x, y=y, progress=progress
        )
        return y + max(surf_in.get_height(), surf_ac.get_height())

    def _draw_pinyin_wipe(
        self,
        screen: pygame.Surface,
        *,
        pinyin: str,
        center_x: int,
        y: int,
        rect: pygame.Rect,
        style: SentenceStyleConfig,
        progress: float,
    ) -> int:
        del rect
        fonts = self._drawer._fonts
        return self._draw_cached_wipe(
            screen,
            cache=self._drawer._cache_pinyin,
            font_ft=fonts.pinyin_ft,
            font_pg=fonts.pinyin_pg,
            text=pinyin,
            center_x=center_x,
            y=y,
            progress=progress,
            inactive_color=KARAOKE_INACTIVE_PINYIN,
            active_color=KARAOKE_ACTIVE_PINYIN,
        )

    def _draw_hanzi_wipe(
        self,
        screen: pygame.Surface,
        *,
        hanzi: str,
        center_x: int,
        y: int,
        style: SentenceStyleConfig,
        progress: float,
    ) -> int:
        del style
        fonts = self._drawer._fonts
        return self._draw_cached_wipe(
            screen,
            cache=self._drawer._cache_hanzi,
            font_ft=fonts.hanzi_ft,
            font_pg=fonts.hanzi_pg,
            text=hanzi,
            center_x=center_x,
            y=y,
            progress=progress,
            inactive_color=KARAOKE_INACTIVE_HANZI,
            active_color=KARAOKE_ACTIVE_HANZI,
        )
