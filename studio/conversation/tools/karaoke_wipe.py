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
    line_h: int | None = None,
) -> None:
    """비활성 색 전체 + 활성 색을 왼쪽부터 progress 비율만큼 덮어 그린다.

    비활성·활성은 반드시 같은 y(상단)에 붙인다. 높이가 1px 달라 하단 정렬하면
    쉼표 문장에서 재생(노란) 글자만 아래로 내려가 보인다.
    `line_h`는 합성 레이어(이미 line_h 높이)일 때만 쓰며, 그때도 y는 그대로다.
    """
    progress = max(0.0, min(1.0, float(progress)))
    w = surf_inactive.get_width()
    h_in = surf_inactive.get_height()
    h_ac = surf_active.get_height()
    if w <= 0 or h_in <= 0:
        return
    x = max(int(min_margin_x), center_x - w // 2)
    yi = int(y)
    screen.blit(surf_inactive, (x, yi))
    if progress <= 0:
        return
    fill_w = w if progress >= 1.0 else max(1, int(round(w * progress)))
    if h_ac <= 0:
        return
    screen.blit(
        surf_active,
        (x, yi),
        area=pygame.Rect(0, 0, fill_w, h_ac),
    )
