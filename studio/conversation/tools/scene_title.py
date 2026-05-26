"""회화 학습·연습 장면 좌상단 타이틀(텍스트)."""

from __future__ import annotations

import pygame

from utils.fonts import load_font_korean

SCENE_TITLE_MARGIN_LEFT_PX = 44
SCENE_TITLE_MARGIN_TOP_PX = 18
SCENE_TITLE_MAX_WIDTH_RATIO = 0.54

# 재생 게이지·말하기 구간과 동일 계열
SCENE_TITLE_COLOR_LEARNING = (46, 204, 113)  # 초록 — 기본 문장 버전
SCENE_TITLE_COLOR_PRACTICE = (255, 159, 67)  # 주황 — 문장 응용 버전

_font_cache: dict[tuple[int, tuple[int, int, int]], pygame.font.Font] = {}


def scene_title_font_size(frame_height: int) -> int:
    """화면 높이 기준 타이틀 폰트 크기."""
    return max(52, min(96, int(round(float(frame_height) * 0.078))))


def _title_font(frame_height: int, color: tuple[int, int, int]) -> pygame.font.Font:
    size = scene_title_font_size(frame_height)
    key = (size, color)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    font = load_font_korean(size, color, weight="bold")
    if font is None:
        font = pygame.font.Font(None, size)
    _font_cache[key] = font
    return font


def resolve_scene_title_color(text: str, *, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    """문구 기준 색(응용/따라→주황, 기본/이해/연습→초록). 기본은 장면별 fallback."""
    label = str(text or "").strip()
    if "응용" in label or "따라" in label:
        return SCENE_TITLE_COLOR_PRACTICE
    if "기본" in label or "연습" in label or "이해" in label:
        return SCENE_TITLE_COLOR_LEARNING
    return fallback


def draw_conversation_scene_title(
    screen: pygame.Surface,
    *,
    text: str,
    alpha: int,
    frame_width: int,
    frame_height: int,
    min_margin_x: int = 0,
    color: tuple[int, int, int] | None = None,
) -> None:
    """좌상단 타이틀 문자열을 페이드 채널 알파에 맞춰 그린다."""
    label = str(text or "").strip()
    if not label:
        return
    px_alpha = max(0, min(255, int(alpha)))
    if px_alpha <= 0:
        return

    rgb = color if color is not None else SCENE_TITLE_COLOR_LEARNING
    font = _title_font(int(frame_height), rgb)
    surf = font.render(label, True, rgb)
    if px_alpha < 255:
        surf = surf.copy()
        surf.set_alpha(px_alpha)

    max_w = max(1, int(int(frame_width) * SCENE_TITLE_MAX_WIDTH_RATIO))
    sw, sh = int(surf.get_width()), int(surf.get_height())
    if sw > max_w and sw > 0:
        scale = float(max_w) / float(sw)
        tw = max(1, int(round(sw * scale)))
        th = max(1, int(round(sh * scale)))
        surf = pygame.transform.smoothscale(surf, (tw, th))

    x = max(int(min_margin_x), SCENE_TITLE_MARGIN_LEFT_PX)
    y = max(0, SCENE_TITLE_MARGIN_TOP_PX)
    screen.blit(surf, (x, y))
