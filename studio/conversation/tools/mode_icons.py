"""Listen/speak 아이콘: LEARNING(이해)·PRACTICE(연습)에서 동일한 스케일·좌하단 배치."""

from __future__ import annotations

from pathlib import Path

import pygame

MODE_ICON_TARGET_SIZE_PX = 318
MODE_ICON_MARGIN_LEFT_PX = 24
MODE_ICON_MARGIN_BOTTOM_PX = 20


def load_mode_icon(repo_root: Path, filename: str) -> pygame.Surface | None:
    """`resource/.../icon/{filename}` 를 찾아 재생 UI용 정사각 스케일로 로드한다."""
    candidates = (
        repo_root / "resource" / "image" / "icon" / filename,
        repo_root / "resource" / "images" / "icon" / filename,
    )
    s = int(MODE_ICON_TARGET_SIZE_PX)
    for path in candidates:
        if not path.exists():
            continue
        try:
            surface = pygame.image.load(str(path))
            return pygame.transform.smoothscale(surface, (s, s))
        except Exception:
            continue
    return None


def blit_mode_icon_bottom_left(
    screen: pygame.Surface,
    icon: pygame.Surface | None,
    *,
    frame_height: int,
    margin_left: int = MODE_ICON_MARGIN_LEFT_PX,
    margin_bottom: int = MODE_ICON_MARGIN_BOTTOM_PX,
) -> None:
    if icon is None:
        return
    h = int(icon.get_height())
    if h <= 0:
        return
    x = int(margin_left)
    y = int(frame_height) - h - int(margin_bottom)
    screen.blit(icon, (x, y))
