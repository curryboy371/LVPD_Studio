"""좌→우 노래방 채움 유틸 (CommonDrawer·숏츠 공용, 순환 import 방지)."""

from __future__ import annotations

import pygame


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
    min_margin_x: int = 0,
) -> None:
    """비활성 색 전체 + 활성 색을 왼쪽부터 progress 비율만큼 덮어 그린다."""
    progress = max(0.0, min(1.0, float(progress)))
    w = surf_inactive.get_width()
    h = surf_inactive.get_height()
    if w <= 0 or h <= 0:
        return
    x = max(int(min_margin_x), center_x - w // 2)
    screen.blit(surf_inactive, (x, y))
    if progress <= 0:
        return
    fill_w = w if progress >= 1.0 else max(1, int(round(w * progress)))
    screen.blit(surf_active, (x, y), area=pygame.Rect(0, 0, fill_w, h))
