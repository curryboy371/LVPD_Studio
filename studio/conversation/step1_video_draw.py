"""VIDEO/LISTEN 공통: 비디오 프레임·페이드·듣기 UI 레이어 그리기."""
from __future__ import annotations

from typing import Any

import pygame


def draw_step1_video(studio: Any, screen: Any, config: Any) -> None:
    """비디오 프레임 그리기."""
    w, h = config.width, config.height
    vid_surf = studio._video_player.get_frame(w, h)
    if vid_surf is not None:
        screen.blit(vid_surf, (0, 0))


def draw_step1_fade_overlay(studio: Any, screen: Any, config: Any) -> None:
    """페이드 오버레이 (멈춤 시 어둡게)."""
    if studio._fade_alpha <= 0:
        return
    w, h = config.width, config.height
    if studio._fade_overlay_surface is None or studio._fade_overlay_size != (w, h):
        studio._fade_overlay_surface = pygame.Surface((w, h))
        studio._fade_overlay_surface.fill((0, 0, 0))
        studio._fade_overlay_size = (w, h)
    studio._fade_overlay_surface.set_alpha(int(min(192, studio._fade_alpha)))
    screen.blit(studio._fade_overlay_surface, (0, 0))


def draw_step1_ui(studio: Any, screen: Any, config: Any) -> None:
    """UI(병음/한자/해석) — _ui_visible일 때만."""
    if studio._ui_visible:
        from . import step1_support_draw as s1

        s1.draw_step1(studio, screen, config)


def draw_impl_step1(studio: Any, screen: Any, config: Any) -> None:
    """영상 → 페이드 오버레이 → UI(병음/한자/해석)."""
    draw_step1_video(studio, screen, config)
    draw_step1_fade_overlay(studio, screen, config)
    draw_step1_ui(studio, screen, config)
