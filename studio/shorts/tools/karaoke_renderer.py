"""음성 동기 노래방 스타일 한자·병음 하이라이트."""

from __future__ import annotations

from typing import Optional

import pygame

from studio.conversation.core.types import SentenceRenderData, SentenceStyleConfig
from studio.conversation.tools.common_drawer import CommonDrawer
from studio.shorts.constants import (
    KARAOKE_ACTIVE_HANZI,
    KARAOKE_ACTIVE_PINYIN,
    KARAOKE_INACTIVE_HANZI,
    KARAOKE_INACTIVE_PINYIN,
    KARAOKE_PAST_HANZI,
    KARAOKE_PAST_PINYIN,
)


def _split_pinyin_syllables(pinyin: str) -> list[str]:
    return [s for s in (pinyin or "").split() if s]


def _hanzi_char_indices(sentence: str) -> list[int]:
    """한자·문자 단위 인덱스(구두점은 음절 카운트에서 제외할 수 있음)."""
    return list(range(len(sentence or "")))


def compute_active_syllable_index(times: list[float], elapsed_sec: float) -> int:
    """마지막 t <= elapsed 인 음절 인덱스. times 비면 -1."""
    if not times:
        return -1
    active = -1
    for i, t in enumerate(times):
        if float(t) <= float(elapsed_sec) + 1e-6:
            active = i
        else:
            break
    return active


def build_even_syllable_times(count: int, duration_sec: float) -> list[float]:
    """음절 수 count에 대해 0..duration 균등 분할."""
    n = max(0, int(count))
    dur = max(0.01, float(duration_sec))
    if n <= 0:
        return []
    if n == 1:
        return [0.0]
    step = dur / float(n)
    return [i * step for i in range(n)]


def map_syllable_to_hanzi_index(sentence: str, syllable_index: int) -> int:
    """음절 인덱스를 한자 문자열 인덱스에 매핑(단순: 비한자 제외 후 순서)."""
    hanzi_positions = [i for i, ch in enumerate(sentence) if not ch.isspace()]
    if syllable_index < 0 or not hanzi_positions:
        return -1
    if syllable_index >= len(hanzi_positions):
        return hanzi_positions[-1]
    return hanzi_positions[syllable_index]


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
    ) -> None:
        """병음·한자·번역을 rect 안에 배치하고 활성 음절을 강조한다."""
        pinyin = (data.pinyin or "").strip()
        hanzi = (data.sentence or "").strip()
        trans = (data.translation or "").strip()
        syllables = _split_pinyin_syllables(pinyin)
        n_syl = len(syllables) if syllables else max(1, len([c for c in hanzi if c.strip()]))

        times = list(syllable_times) if syllable_times else []
        if not times and sound_duration_sec > 0 and n_syl > 0:
            times = build_even_syllable_times(n_syl, sound_duration_sec)

        active_syl = compute_active_syllable_index(times, elapsed_sec)
        active_hanzi_idx = map_syllable_to_hanzi_index(hanzi, active_syl)

        center_x = rect.centerx
        y = rect.top + 12 + max(0, int(y_offset)) + max(0, int(pinyin_y_offset))
        line_gap = style.layout.line_gap_px

        gap_py_hz = int(pinyin_hanzi_gap) if pinyin_hanzi_gap is not None else line_gap

        if pinyin and syllables:
            y = self._draw_pinyin_line(
                screen,
                syllables=syllables,
                center_x=center_x,
                y=y,
                rect=rect,
                style=style,
                active_syl=active_syl,
            )
            y += gap_py_hz

        if hanzi:
            self._draw_hanzi_colored(
                screen,
                hanzi=hanzi,
                center_x=center_x,
                y=y,
                style=style,
                active_hanzi_idx=active_hanzi_idx,
                active_syl=active_syl,
            )
            y += line_gap

        if trans:
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

    def _draw_pinyin_line(
        self,
        screen: pygame.Surface,
        *,
        syllables: list[str],
        center_x: int,
        y: int,
        rect: pygame.Rect,
        style: SentenceStyleConfig,
        active_syl: int,
    ) -> int:
        fonts = self._drawer._fonts
        cache = self._drawer._cache_pinyin
        surfs: list[pygame.Surface] = []
        for i, syl in enumerate(syllables):
            if i < active_syl:
                color = KARAOKE_PAST_PINYIN
            elif i == active_syl:
                color = KARAOKE_ACTIVE_PINYIN
            else:
                color = KARAOKE_INACTIVE_PINYIN
            surf, _ = self._drawer._get_cached_text_pair(
                cache, fonts.pinyin_ft, fonts.pinyin_pg, syl + " ", color
            )
            surfs.append(surf)
        if not surfs:
            return y
        gap = 4
        total_w = sum(s.get_width() for s in surfs) + gap * (len(surfs) - 1)
        x = center_x - total_w // 2
        x = max(rect.left + style.layout.min_margin_x, x)
        for surf in surfs:
            screen.blit(surf, (x, y))
            x += surf.get_width() + gap
        return y + max(s.get_height() for s in surfs)

    def _draw_hanzi_colored(
        self,
        screen: pygame.Surface,
        *,
        hanzi: str,
        center_x: int,
        y: int,
        style: SentenceStyleConfig,
        active_hanzi_idx: int,
        active_syl: int,
    ) -> None:
        fonts = self._drawer._fonts
        cache = self._drawer._cache_hanzi
        hanzi_positions = [i for i, ch in enumerate(hanzi) if not ch.isspace()]

        segments: list[tuple[str, tuple[int, int, int]]] = []
        cur = ""
        cur_color: Optional[tuple[int, int, int]] = None

        def _color_for_char(i: int) -> tuple[int, int, int]:
            if active_syl < 0:
                return KARAOKE_INACTIVE_HANZI
            if i == active_hanzi_idx:
                return KARAOKE_ACTIVE_HANZI
            if i in hanzi_positions:
                pos_in_hanzi = hanzi_positions.index(i)
                if pos_in_hanzi < active_syl:
                    return KARAOKE_PAST_HANZI
            return KARAOKE_INACTIVE_HANZI

        for i, ch in enumerate(hanzi):
            col = _color_for_char(i)
            if cur_color is None:
                cur_color = col
                cur = ch
                continue
            if col == cur_color:
                cur += ch
            else:
                segments.append((cur, cur_color))
                cur = ch
                cur_color = col
        if cur:
            segments.append((cur, cur_color))

        seg_surfs: list[pygame.Surface] = []
        for text, color in segments:
            surf, _ = self._drawer._get_cached_text_pair(
                cache, fonts.hanzi_ft, fonts.hanzi_pg, text, color
            )
            seg_surfs.append(surf)
        if not seg_surfs:
            return
        gap = 0
        total_w = sum(s.get_width() for s in seg_surfs)
        x = center_x - total_w // 2
        for surf in seg_surfs:
            screen.blit(surf, (x, y))
            x += surf.get_width() + gap
