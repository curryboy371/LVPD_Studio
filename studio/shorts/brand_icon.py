"""숏츠 하단 중앙 브랜드 icon.png 로드·캐시·그리기 (단일 진입점)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

import pygame

from core.paths import get_repo_root
from studio.shorts.constants import (
    SHORTS_BRAND_ICON,
    SHORTS_BRAND_ICON_H,
    SHORTS_BRAND_ICON_W,
    SHORTS_BRAND_TITLE_COLOR,
    SHORTS_BRAND_TITLE_TEXT,
    shorts_brand_icon_xy,
    shorts_brand_title_font_size,
    shorts_brand_title_gap,
)
from utils.fonts import load_font_korean

logger = logging.getLogger(__name__)

_icon_cache: Optional[pygame.Surface] = None
_title_surf_cache: Optional[pygame.Surface] = None
_title_font_size_cached: int = 0
_resolved_path: Optional[Path] = None
_draw_announced = False


def invalidate_brand_icon_cache() -> None:
    global _icon_cache, _title_surf_cache, _title_font_size_cached
    global _resolved_path, _draw_announced
    _icon_cache = None
    _title_surf_cache = None
    _title_font_size_cached = 0
    _resolved_path = None
    _draw_announced = False


def resolve_brand_icon_path() -> Optional[Path]:
    """icon.png 경로 (repo 기준 + cwd 폴백)."""
    global _resolved_path
    if _resolved_path is not None and _resolved_path.is_file():
        return _resolved_path

    candidates = [
        SHORTS_BRAND_ICON,
        get_repo_root() / "resource" / "image" / "icon" / "icon.png",
        Path.cwd() / "resource" / "image" / "icon" / "icon.png",
    ]
    seen: set[str] = set()
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            _resolved_path = p.resolve()
            return _resolved_path
    return None


def _crop_opaque_bounds(surf: pygame.Surface, *, pad: int = 4) -> pygame.Surface:
    """알파 영역 외곽선. outline()은 분리된 섬(발 등)을 누락할 수 있어 rects union 사용."""
    try:
        rects = pygame.mask.from_surface(surf).get_bounding_rects()
    except Exception:
        return surf
    if not rects:
        return surf
    bounds = rects[0]
    for r in rects[1:]:
        bounds = bounds.union(r)
    if pad:
        bounds = bounds.inflate(pad * 2, pad * 2)
        bounds.clamp_ip(surf.get_rect())
    if bounds.width <= 0 or bounds.height <= 0:
        return surf
    return surf.subsurface(bounds).copy()


def _scale_to_fit(surf: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
    sw, sh = surf.get_width(), surf.get_height()
    if sw <= 0 or sh <= 0:
        return surf
    scale = min(float(max_w) / sw, float(max_h) / sh)
    tw = max(1, int(round(sw * scale)))
    th = max(1, int(round(sh * scale)))
    if tw == sw and th == sh:
        return surf
    return pygame.transform.smoothscale(surf, (tw, th))


def _ensure_srcalpha(surf: pygame.Surface) -> pygame.Surface:
    if surf.get_flags() & pygame.SRCALPHA:
        return surf
    try:
        return surf.convert_alpha()
    except pygame.error:
        return surf


def load_brand_icon_surface() -> Optional[pygame.Surface]:
    """icon.png → 크롭·스케일 → 알파 유지 Surface 캐시."""
    global _icon_cache
    if _icon_cache is not None:
        return _icon_cache

    path = resolve_brand_icon_path()
    if path is None:
        msg = f"숏츠 브랜드 아이콘 파일 없음 (시도: {SHORTS_BRAND_ICON})"
        logger.error(msg)
        print(f"[shorts] ERROR: {msg}", file=sys.stderr)
        return None

    try:
        raw = pygame.image.load(str(path))
    except Exception as ex:
        msg = f"숏츠 브랜드 아이콘 로드 실패: {path} ({ex})"
        logger.error(msg)
        print(f"[shorts] ERROR: {msg}", file=sys.stderr)
        return None

    try:
        img = raw.convert_alpha()
    except pygame.error:
        try:
            img = raw.convert()
            img.set_colorkey((0, 0, 0))
        except pygame.error:
            img = raw

    cropped = _crop_opaque_bounds(_ensure_srcalpha(img))
    icon = _ensure_srcalpha(
        _scale_to_fit(cropped, SHORTS_BRAND_ICON_W, SHORTS_BRAND_ICON_H)
    )
    if icon.get_width() <= 0 or icon.get_height() <= 0:
        logger.error("숏츠 브랜드 아이콘 준비 실패(빈 결과): %s", path)
        return None

    _icon_cache = icon
    logger.info(
        "숏츠 브랜드 아이콘 준비: %s → %dx%d (alpha)",
        path.name,
        _icon_cache.get_width(),
        _icon_cache.get_height(),
    )
    return _icon_cache


def load_brand_icon_plate() -> Optional[pygame.Surface]:
    """하위 호환 alias."""
    return load_brand_icon_surface()


def _brand_title_font(size: int) -> Any:
    for weight in ("bold", "regular"):
        font = load_font_korean(size, SHORTS_BRAND_TITLE_COLOR, weight=weight)
        if font is not None:
            return font
    return None


def _render_brand_title_surface(frame_height: int) -> Optional[pygame.Surface]:
    """하단 브랜드 타이틀 Surface 캐시."""
    global _title_surf_cache, _title_font_size_cached

    text = (SHORTS_BRAND_TITLE_TEXT or "").strip()
    if not text:
        return None

    size = shorts_brand_title_font_size(frame_height)
    if _title_surf_cache is not None and _title_font_size_cached == size:
        return _title_surf_cache

    font = _brand_title_font(size)
    if font is None:
        return None
    try:
        surf = font.render(text, True, SHORTS_BRAND_TITLE_COLOR)
    except Exception:
        return None
    if surf is None or surf.get_width() <= 0:
        return None

    _title_surf_cache = surf
    _title_font_size_cached = size
    return _title_surf_cache


def _draw_brand_title(screen: pygame.Surface, *, icon_y: int) -> bool:
    fh = screen.get_height()
    title = _render_brand_title_surface(fh)
    if title is None:
        return False

    gap = shorts_brand_title_gap(fh)
    tx = (screen.get_width() - title.get_width()) // 2
    ty = max(0, icon_y - gap - title.get_height())
    screen.blit(title, (tx, ty))
    return True


def draw_brand_icon(screen: pygame.Surface, *, y_offset: int = 0) -> bool:
    """하단 중앙 icon.png (배경 투명). 성공 시 True."""
    global _draw_announced

    screen.set_clip(None)
    icon = load_brand_icon_surface()
    if icon is None:
        return False

    fw, fh = screen.get_width(), screen.get_height()
    iw, ih = icon.get_width(), icon.get_height()
    x, y = shorts_brand_icon_xy(
        fw, fh, icon_width=iw, icon_height=ih, y_offset=int(y_offset)
    )
    try:
        screen.blit(icon, (x, y), special_flags=pygame.BLEND_ALPHA_SDL2)
    except Exception:
        screen.blit(icon, (x, y))

    if not _draw_announced:
        _draw_announced = True
        p = resolve_brand_icon_path()
        print(
            f"[shorts] brand icon ON bottom-center ({x},{y}) "
            f"size {iw}x{ih} frame {fw}x{fh} path={p}",
            flush=True,
        )
    return True


def warm_brand_icon() -> Optional[pygame.Surface]:
    return load_brand_icon_surface()
