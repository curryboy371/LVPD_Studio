"""9:16 화면 30/40/30 구역 Rect 계산."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pygame

from studio.shorts.constants import (
    ZONE_BOTTOM_RATIO,
    ZONE_MIDDLE_RATIO,
    ZONE_TOP_RATIO,
)


@dataclass(frozen=True)
class ShortsLayoutZones:
    """프레임 크기 기준 상·중·하 구역."""

    top: pygame.Rect
    middle: pygame.Rect
    bottom: pygame.Rect

    @classmethod
    def from_frame(cls, width: int, height: int) -> ShortsLayoutZones:
        """높이 비율로 top/middle/bottom Rect를 나눈다."""
        w = max(1, int(width))
        h = max(1, int(height))
        top_h = int(h * ZONE_TOP_RATIO)
        mid_h = int(h * ZONE_MIDDLE_RATIO)
        bot_h = h - top_h - mid_h
        return cls(
            top=pygame.Rect(0, 0, w, top_h),
            middle=pygame.Rect(0, top_h, w, mid_h),
            bottom=pygame.Rect(0, top_h + mid_h, w, bot_h),
        )

    @classmethod
    def from_surface(cls, screen: pygame.Surface, ctx: Any) -> ShortsLayoutZones:
        """실제 그리기 surface 크기 기준 구역( config와 불일치 방지 )."""
        w = max(1, int(screen.get_width()))
        h = max(1, int(screen.get_height()))
        if w <= 1 or h <= 1:
            w = max(1, int(getattr(ctx, "width", 1080) or 1080))
            h = max(1, int(getattr(ctx, "height", 1920) or 1920))
        return cls.from_frame(w, h)


def compute_contain_frame_rect(
    zone_middle: pygame.Rect,
    media_size: tuple[int, int],
    *,
    pad: int = 16,
) -> pygame.Rect:
    """middle 구역 contain 배치 시 미디어 프레임 Rect (자막·mux 앵커)."""
    inner = zone_middle.inflate(-pad * 2, -pad * 2)
    mw, mh = max(1, int(media_size[0])), max(1, int(media_size[1]))
    if inner.width <= 0 or inner.height <= 0:
        return inner
    scale = min(inner.width / mw, inner.height / mh)
    fw = max(1, int(mw * scale))
    fh = max(1, int(mh * scale))
    x = inner.centerx - fw // 2
    y = inner.centery - fh // 2
    return pygame.Rect(x, y, fw, fh)
