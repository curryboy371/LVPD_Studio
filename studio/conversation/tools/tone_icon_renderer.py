"""병음 위 성조 아이콘 배치·정렬 (CommonDrawer 텍스트 캐시와 분리된 책임)."""

from __future__ import annotations

from typing import Any, Callable, Literal, Optional

import pygame

from utils.tone_icon_assets import load_tone_icon_surface, tone_icon_path
from utils.tone_icon_layout import ToneIconSlot

from ..core.types import SentenceStyleConfig

Align = Literal["center", "left", "right"]

TONE_ICON_GAP_ABOVE_PX = 8


def split_pinyin_syllables(s: str) -> list[str]:
    """병음 문자열을 공백 기준 음절 리스트로 나눈다."""
    return [x for x in s.strip().split() if x]


class ToneIconRenderer:
    """음절 중심 x 계산, 슬롯 정렬, 병음 위 아이콘 blit.

    `load_tone_icon_surface`는 `utils.tone_icon_assets` 모듈 전역 LRU 캐시를 사용한다.
    """

    def __init__(self, *, get_pinyin_pair: Callable[[str, tuple[int, int, int]], tuple[Any, Any]]) -> None:
        self._get_pinyin_pair = get_pinyin_pair

    def pinyin_syllable_center_xs(
        self,
        syllables: list[str],
        *,
        color: tuple[int, int, int],
        center_x: int,
        min_margin_x: int,
        align: Align,
    ) -> list[int]:
        """병음 음절별 가로 중심 x 좌표(성조 아이콘 정렬용)."""
        if not syllables:
            return []
        widths: list[int] = []
        for syl in syllables:
            surf, _ = self._get_pinyin_pair(syl, color)
            if surf is None:
                widths.append(0)
            else:
                widths.append(int(surf.get_width()))
        try:
            sp_surf, _ = self._get_pinyin_pair(" ", color)
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

    @staticmethod
    def align_tone_icon_slots(
        syllables: list[str], slots: tuple[Optional[ToneIconSlot], ...]
    ) -> tuple[Optional[ToneIconSlot], ...]:
        """음절 개수에 맞춰 슬롯 튜플 길이를 맞춘다."""
        k = len(syllables)
        if k == 0:
            return ()
        lst = list(slots[:k]) if len(slots) >= k else list(slots) + [None] * (k - len(slots))
        return tuple(lst[:k])

    @staticmethod
    def _restore_surface_alpha(surf: pygame.Surface, old: Any) -> None:
        try:
            if old is None:
                surf.set_alpha(None)
            else:
                surf.set_alpha(old)
        except Exception:
            pass

    def draw_above_pinyin(
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
        """병음 줄 위에 음절별 성조 아이콘을 배치한다."""
        syllables = split_pinyin_syllables(pinyin_line)
        if not syllables or not any(s is not None for s in slots):
            return
        aligned = self.align_tone_icon_slots(syllables, slots)
        color = style.colors.pinyin_color
        centers = self.pinyin_syllable_center_xs(
            syllables,
            color=color,
            center_x=center_x,
            min_margin_x=style.layout.min_margin_x,
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
            iy = y_pinyin - TONE_ICON_GAP_ABOVE_PX - surf.get_height()
            ix = cx - surf.get_width() // 2
            ix = max(style.layout.min_margin_x, ix)
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
