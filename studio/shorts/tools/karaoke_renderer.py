"""음성 동기 노래방 스타일 한자·병음 하이라이트 (좌→우 진행 채움)."""

from __future__ import annotations

from typing import Any, Optional

import pygame

from studio.conversation.core.types import SentenceRenderData, SentenceStyleConfig
from studio.conversation.tools.common_drawer import CommonDrawer
from studio.conversation.tools.karaoke_wipe import (
    blit_horizontal_karaoke_wipe,
    compute_karaoke_progress,
)
from studio.shorts.constants import (
    KARAOKE_ACTIVE_HANZI,
    KARAOKE_ACTIVE_PINYIN,
    KARAOKE_INACTIVE_HANZI,
    KARAOKE_INACTIVE_PINYIN,
    KO_KARAOKE_ACTIVE,
    KO_KARAOKE_INACTIVE,
    SHORTS_VOCAB_POS_FONT_RATIO,
)

__all__ = [
    "KaraokeRenderer",
    "blit_horizontal_karaoke_wipe",
    "compute_karaoke_progress",
]


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
        return_translation_y: bool = False,
        hanzi_karaoke_only: bool = False,
    ) -> int | None:
        """병음·한자·번역을 rect 안에 배치하고 재생 진행에 따라 좌→우로 채운다.

        hanzi_karaoke_only=True면 병음은 정적, 한자만 노래방 채움.
        """
        del syllable_times  # 음절 단위 하이라이트 미사용
        pinyin = (data.pinyin or "").strip()
        hanzi = (data.sentence or "").strip()
        trans = (data.translation or "").strip()
        vocab_pos = (vocab_pos or "").strip()
        progress = compute_karaoke_progress(elapsed_sec, sound_duration_sec)

        center_x = rect.centerx
        line_gap = style.layout.line_gap_px
        after_hanzi_y: int | None = None
        extra_trans = (
            int(translation_extra_gap)
            if translation_extra_gap is not None
            else style.layout.translation_extra_gap_px
        )

        if fixed_hanzi_y is not None:
            hz_y = int(fixed_hanzi_y)
            if pinyin and fixed_pinyin_y is not None:
                if hanzi_karaoke_only:
                    self._draw_pinyin_static(
                        screen,
                        pinyin=pinyin,
                        center_x=center_x,
                        y=int(fixed_pinyin_y),
                        style=style,
                    )
                else:
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
                after_hanzi_y = self._draw_hanzi_wipe(
                    screen,
                    hanzi=hanzi,
                    center_x=center_x,
                    y=hz_y,
                    style=style,
                    progress=progress,
                )
            if return_translation_y and after_hanzi_y is not None:
                return min(after_hanzi_y + line_gap + extra_trans, rect.bottom - 8)
            return None

        y = rect.top + 12 + max(0, int(y_offset)) + max(0, int(pinyin_y_offset))
        gap_py_hz = int(pinyin_hanzi_gap) if pinyin_hanzi_gap is not None else line_gap

        if pinyin:
            if hanzi_karaoke_only:
                y = self._draw_pinyin_static(
                    screen,
                    pinyin=pinyin,
                    center_x=center_x,
                    y=y,
                    style=style,
                )
            else:
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
            after_hanzi_y = y
            pad_after = max(0, int(after_hanzi_pad))
            if pad_after:
                y += pad_after
            elif not vocab_pos:
                y += line_gap

        if return_translation_y and after_hanzi_y is not None:
            return min(after_hanzi_y + line_gap + extra_trans, rect.bottom - 8)

        if vocab_pos:
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
        return None

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
        line_h: int | None = None,
    ) -> int:
        if not text:
            return y
        surf_in, _ = self._drawer._get_cached_text_pair(
            cache, font_ft, font_pg, text, inactive_color
        )
        if active_color == inactive_color:
            surf_ac = surf_in
        elif cache is self._drawer._cache_hanzi:
            surf_ac = self._drawer._surface_with_recolored_ink(surf_in, active_color)
        else:
            surf_ac, _ = self._drawer._get_cached_text_pair(
                cache, font_ft, font_pg, text, active_color
            )
        blit_horizontal_karaoke_wipe(
            screen,
            surf_in,
            surf_ac,
            center_x=center_x,
            y=y,
            progress=progress,
            line_h=line_h,
        )
        if line_h is not None and int(line_h) > 0:
            return y + int(line_h)
        return y + max(surf_in.get_height(), surf_ac.get_height())

    def _draw_pinyin_static(
        self,
        screen: pygame.Surface,
        *,
        pinyin: str,
        center_x: int,
        y: int,
        style: SentenceStyleConfig,
    ) -> int:
        """병음 정적 표시 — 노래방 채움 없음."""
        if not pinyin:
            return y
        fonts = self._drawer._fonts
        self._drawer._blit_text(
            screen,
            cache=self._drawer._cache_pinyin,
            font_ft=fonts.pinyin_ft,
            font_pg=fonts.pinyin_pg,
            text=pinyin,
            color=KARAOKE_ACTIVE_PINYIN,
            center_x=center_x,
            y=y,
            alpha=255,
            min_margin_x=style.layout.min_margin_x,
            align="center",
        )
        h = self._drawer._cached_line_height(
            self._drawer._cache_pinyin,
            fonts.pinyin_ft,
            fonts.pinyin_pg,
            pinyin,
            KARAOKE_ACTIVE_PINYIN,
        )
        return y + h

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

    def draw_translation_karaoke_wipe(
        self,
        screen: pygame.Surface,
        *,
        text: str,
        center_x: int,
        y: int,
        style: SentenceStyleConfig,
        elapsed_sec: float,
        sound_duration_sec: float,
        font_pt: Optional[int] = None,
        rect_bottom: Optional[int] = None,
    ) -> None:
        """뜻/번역 줄 — 중국어 mp3 구간 정적 번역과 동일 y·폰트, TTS 중 좌→우 노래방."""
        line = (text or "").strip()
        if not line:
            return
        progress = compute_karaoke_progress(elapsed_sec, sound_duration_sec)
        inactive = style.colors.translation_color
        active = KO_KARAOKE_ACTIVE
        if font_pt is not None:
            from utils.fonts import load_font_korean

            font = load_font_korean(max(14, int(font_pt)), inactive)
            if font is None:
                return
            surf_in = font.render(line, True, inactive)
            surf_ac = font.render(line, True, active)
        else:
            font_pg = self._drawer._fonts.translation_pg
            surf_in = font_pg.render(line, True, inactive)
            surf_ac = font_pg.render(line, True, active)
        # y는 레이아웃(한자·품사 아래 meaning_y) 고정 — 아래 공간 부족해도 위로 당기지 않음
        draw_y = max(0, int(y))
        blit_horizontal_karaoke_wipe(
            screen,
            surf_in,
            surf_ac,
            center_x=int(center_x),
            y=draw_y,
            progress=progress,
        )

    def draw_meaning_karaoke(
        self,
        screen: pygame.Surface,
        *,
        text: str,
        rect: pygame.Rect,
        elapsed_sec: float,
        sound_duration_sec: float,
        vocab_kr_font_pt: int = 36,
        alpha: int | None = None,
        y_top: Optional[int] = None,
        rect_bottom: Optional[int] = None,
    ) -> None:
        """한국어 뜻만 좌→우 노래방 채움(TTS 구간). y_top 있으면 상단 정렬(번역 줄과 동일)."""
        line = (text or "").strip()
        if not line:
            return
        progress = compute_karaoke_progress(elapsed_sec, sound_duration_sec)
        from utils.fonts import load_font_korean

        pt = max(14, int(vocab_kr_font_pt))
        font = load_font_korean(pt, KO_KARAOKE_INACTIVE)
        if font is None:
            return
        surf_in = font.render(line, True, KO_KARAOKE_INACTIVE)
        surf_ac = font.render(line, True, KO_KARAOKE_ACTIVE)
        if y_top is not None:
            y = max(0, int(y_top))
        else:
            y = rect.centery - surf_in.get_height() // 2
            y = max(rect.top, y)
        a: int | None = None
        if alpha is not None:
            a = int(max(0, min(255, alpha)))
            if a <= 0:
                return
        old_in = surf_in.get_alpha()
        old_ac = surf_ac.get_alpha()
        if a is not None and a < 255:
            surf_in.set_alpha(a)
            surf_ac.set_alpha(a)
        try:
            blit_horizontal_karaoke_wipe(
                screen,
                surf_in,
                surf_ac,
                center_x=rect.centerx,
                y=y,
                progress=progress,
            )
        finally:
            if a is not None and a < 255:
                if old_in is None:
                    surf_in.set_alpha(None)
                else:
                    surf_in.set_alpha(old_in)
                if old_ac is None:
                    surf_ac.set_alpha(None)
                else:
                    surf_ac.set_alpha(old_ac)

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
            line_h=self._drawer._hanzi_layout_line_height(KARAOKE_INACTIVE_HANZI),
        )
