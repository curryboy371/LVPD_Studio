"""Reusable playback bar renderer for pygame scenes.

This module is intentionally scene-agnostic so each scene can add
"bar + play time" with a single draw call.

Minimal usage:
    bar = PlaybackBarRenderer()
    bar.draw(
        screen,
        frame_width=ctx.width,
        frame_height=ctx.height,
        current_sec=video_player.get_pts(),
        total_sec=video_player.get_effective_end_sec(),
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pygame


HorizontalAlign = Literal["left", "center", "right"]
VerticalAlign = Literal["top", "bottom"]


@dataclass(frozen=True)
class PlaybackBarStyle:
    """Visual style for playback bar and time label."""

    bar_height_px: int = 10
    corner_radius_px: int = 5
    track_color: tuple[int, int, int] = (45, 45, 45)
    progress_color: tuple[int, int, int] = (46, 204, 113)
    border_color: tuple[int, int, int] = (210, 210, 210)
    border_width_px: int = 1
    time_text_color: tuple[int, int, int] = (235, 235, 235)
    time_text_bg_alpha: int = 0
    time_gap_px: int = 10
    font_size_px: int = 22


@dataclass(frozen=True)
class PlaybackBarLayout:
    """Layout for bar rectangle placement.

    Attributes:
        width_ratio: Width ratio based on frame width. Used when `fixed_width_px`
            is not set.
        fixed_width_px: Optional absolute bar width.
        align_x: Horizontal anchor.
        align_y: Vertical anchor.
        margin_x_px: Horizontal margin from screen side.
        margin_y_px: Vertical margin from top or bottom side.
        x_px: Optional absolute x coordinate for bar left.
        y_px: Optional absolute y coordinate for bar top.
    """

    width_ratio: float = 0.72
    fixed_width_px: Optional[int] = None
    align_x: HorizontalAlign = "center"
    align_y: VerticalAlign = "bottom"
    margin_x_px: int = 24
    margin_y_px: int = 28
    x_px: Optional[int] = None
    y_px: Optional[int] = None


def format_playback_time(seconds: float) -> str:
    """Convert seconds to `MM:SS` or `H:MM:SS` text."""
    sec = max(0, int(float(seconds or 0.0)))
    if sec >= 3600:
        hour = sec // 3600
        minute = (sec % 3600) // 60
        second = sec % 60
        return f"{hour}:{minute:02d}:{second:02d}"
    minute = sec // 60
    second = sec % 60
    return f"{minute:02d}:{second:02d}"


class PlaybackBarRenderer:
    """Draw playback bar and `current / total` label on a pygame surface."""

    def __init__(
        self,
        *,
        style: PlaybackBarStyle | None = None,
        layout: PlaybackBarLayout | None = None,
        font: pygame.font.Font | None = None,
    ) -> None:
        """Initialize renderer with optional style/layout/font overrides."""
        self.style = style or PlaybackBarStyle()
        self.layout = layout or PlaybackBarLayout()
        self._font = font

    def draw(
        self,
        surface: pygame.Surface,
        *,
        frame_width: int,
        frame_height: int,
        current_sec: float | None = None,
        total_sec: float | None = None,
        progress: float | None = None,
        show_time_text: bool = True,
    ) -> float:
        """Draw playback bar and return normalized progress.

        Priority:
            1) `current_sec + total_sec` when both are provided.
            2) `progress` when time pair is not available.
        """
        normalized = self._resolve_progress(current_sec=current_sec, total_sec=total_sec, progress=progress)
        bar_rect = self._resolve_bar_rect(frame_width=frame_width, frame_height=frame_height)

        radius = max(0, int(self.style.corner_radius_px))
        pygame.draw.rect(surface, self.style.track_color, bar_rect, border_radius=radius)

        fill_width = int(round(bar_rect.width * normalized))
        if fill_width > 0:
            fill_rect = pygame.Rect(bar_rect.left, bar_rect.top, fill_width, bar_rect.height)
            pygame.draw.rect(surface, self.style.progress_color, fill_rect, border_radius=radius)

        if self.style.border_width_px > 0:
            pygame.draw.rect(
                surface,
                self.style.border_color,
                bar_rect,
                width=max(1, int(self.style.border_width_px)),
                border_radius=radius,
            )

        if show_time_text:
            self._draw_time_text(
                surface,
                frame_width=frame_width,
                bar_rect=bar_rect,
                current_sec=current_sec,
                total_sec=total_sec,
                normalized=normalized,
            )
        return normalized

    def _resolve_progress(
        self,
        *,
        current_sec: float | None,
        total_sec: float | None,
        progress: float | None,
    ) -> float:
        """Resolve progress from time pair or direct progress input."""
        if current_sec is not None and total_sec is not None and float(total_sec) > 1e-6:
            cur = max(0.0, float(current_sec))
            tot = max(0.0, float(total_sec))
            return self._clamp01(cur / tot if tot > 1e-6 else 0.0)
        if progress is None:
            return 0.0
        return self._clamp01(float(progress))

    def _resolve_bar_rect(self, *, frame_width: int, frame_height: int) -> pygame.Rect:
        """Build playback bar rect from layout options."""
        layout = self.layout
        style = self.style

        width = int(layout.fixed_width_px) if layout.fixed_width_px is not None else int(frame_width * float(layout.width_ratio))
        width = max(8, min(int(frame_width), width))
        height = max(2, int(style.bar_height_px))

        if layout.x_px is not None:
            x = int(layout.x_px)
        elif layout.align_x == "left":
            x = int(layout.margin_x_px)
        elif layout.align_x == "right":
            x = int(frame_width - width - layout.margin_x_px)
        else:
            x = int((frame_width - width) * 0.5)

        if layout.y_px is not None:
            y = int(layout.y_px)
        elif layout.align_y == "top":
            y = int(layout.margin_y_px)
        else:
            y = int(frame_height - height - layout.margin_y_px)

        x = max(0, min(frame_width - width, x))
        y = max(0, min(frame_height - height, y))
        return pygame.Rect(x, y, width, height)

    def _draw_time_text(
        self,
        surface: pygame.Surface,
        *,
        frame_width: int,
        bar_rect: pygame.Rect,
        current_sec: float | None,
        total_sec: float | None,
        normalized: float,
    ) -> None:
        """Draw `current / total` time label near the playback bar."""
        if total_sec is None and current_sec is None:
            return
        total_display = max(0.0, float(total_sec or 0.0))
        if current_sec is None:
            current_display = total_display * normalized
        else:
            current_display = max(0.0, float(current_sec))
        if total_display > 0:
            current_display = min(current_display, total_display)

        text = f"{format_playback_time(current_display)} / {format_playback_time(total_display)}"
        font = self._ensure_font()
        text_surface = font.render(text, True, self.style.time_text_color)
        text_rect = text_surface.get_rect()
        text_rect.centery = bar_rect.centery
        text_rect.right = bar_rect.left - max(0, int(self.style.time_gap_px))

        if text_rect.right < 0:
            text_rect.left = bar_rect.right + max(0, int(self.style.time_gap_px))
        if text_rect.left < 0:
            text_rect.left = 0
        if text_rect.right > frame_width:
            text_rect.right = frame_width

        bg_alpha = max(0, min(255, int(self.style.time_text_bg_alpha)))
        if bg_alpha > 0:
            bg = pygame.Surface((text_rect.width + 8, text_rect.height + 6), pygame.SRCALPHA)
            bg.fill((0, 0, 0, bg_alpha))
            bg_rect = bg.get_rect(center=text_rect.center)
            surface.blit(bg, bg_rect)
        surface.blit(text_surface, text_rect)

    def _ensure_font(self) -> pygame.font.Font:
        """Lazily create fallback pygame font if custom font was not given."""
        if self._font is None:
            self._font = pygame.font.Font(None, max(12, int(self.style.font_size_px)))
        return self._font

    @staticmethod
    def _clamp01(value: float) -> float:
        """Clamp float to [0.0, 1.0]."""
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value
