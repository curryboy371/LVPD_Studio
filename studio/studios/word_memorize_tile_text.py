"""단어 외우기 — text_tile로 타일 격자 부제목 렌더링."""
from __future__ import annotations

import math
import os
from typing import Callable

import pygame

from extra.table_editor.services.word_memorize_layout import (
    DEFAULT_MARGIN_BOTTOM_RATIO,
    DEFAULT_MARGIN_TOP_RATIO,
    SUBTITLE_FONT_PT_MAX,
    SUBTITLE_FONT_PT_MIN,
    SUBTITLE_LINE_GAP_TILES,
    SUBTITLE_MARGIN_TILES,
    SUBTITLE_MIN_LINE_TILES,
    SUBTITLE_CELL_PX,
    SubtitleLineSpec,
    WordMemorizeLayout,
    layout_subtitle_line_specs,
    normalize_title_font,
    resolve_subtitle_line_text_tile,
    resolve_subtitle_position,
    pick_game_tile_stem_for_cell,
    snap_tile_coord,
    subtitle_cell_px,
    subtitle_tile_band_rect,
)

MeasureLineFn = Callable[[str, int, str], tuple[int, int]]
TextTileLoaderFn = Callable[[str], pygame.Surface | None]


def ensure_pygame_minimal() -> None:
    """편집기 미리보기 등 — tkinter와 별도로 headless pygame만 켠다.

    dummy 드라이버는 init 직후 환경 변수에서 제거한다.
    (남겨 두면 F5 미리보기 subprocess가 SDL_VIDEODRIVER=dummy 를 물려받아 창이 안 뜸)
    """
    if pygame.get_init():
        if pygame.display.get_surface() is None:
            try:
                pygame.display.set_mode((1, 1))
            except pygame.error:
                pass
        return

    had_driver = "SDL_VIDEODRIVER" in os.environ
    prev_driver = os.environ.get("SDL_VIDEODRIVER")
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    try:
        pygame.init()
    finally:
        if had_driver:
            if prev_driver is not None:
                os.environ["SDL_VIDEODRIVER"] = prev_driver
        else:
            os.environ.pop("SDL_VIDEODRIVER", None)

    if pygame.display.get_surface() is None:
        try:
            pygame.display.set_mode((1, 1))
        except pygame.error:
            pass


def blit_tiled_band(
    surface: pygame.Surface,
    tile: pygame.Surface,
    frame_width: int,
    frame_height: int,
    *,
    y0: int = 0,
    y1: int | None = None,
) -> None:
    """프레임 y0~y1 구간을 타일 이미지로 채운다."""
    fw = int(frame_width)
    fh = int(frame_height)
    tw, th = tile.get_size()
    if tw <= 0 or th <= 0:
        return
    y_start = max(0, int(y0))
    y_end = fh if y1 is None else max(y_start, min(fh, int(y1)))
    for y in range(y_start, y_end, th):
        if y + th > y_end:
            break
        for x in range(0, fw, tw):
            if x + tw > fw:
                break
            surface.blit(tile, (x, y))


def blit_mixed_tile_band(
    surface: pygame.Surface,
    tile_by_stem: dict[str, pygame.Surface],
    stems: list[str],
    frame_width: int,
    frame_height: int,
    *,
    y0: int = 0,
    y1: int | None = None,
    tile_px: int,
    seed: int = 0,
) -> None:
    """타일 목록에서 격자 칸마다 시드·좌표로 고정 선택해 채운다."""
    if not stems or tile_px <= 0:
        return
    fw = int(frame_width)
    fh = int(frame_height)
    px = max(1, int(tile_px))
    y_start = max(0, int(y0))
    y_end = fh if y1 is None else max(y_start, min(fh, int(y1)))
    for y in range(y_start, y_end, px):
        if y + px > y_end:
            break
        row = y // px
        for x in range(0, fw, px):
            if x + px > fw:
                break
            col = x // px
            stem = pick_game_tile_stem_for_cell(stems, col, row, seed)
            tile = tile_by_stem.get(stem)
            if tile is None:
                continue
            surface.blit(tile, (x, y))


def load_subtitle_font(font_key: str, font_pt: int) -> pygame.font.Font | None:
    """부제목용 pygame 폰트."""
    from utils.fonts import (
        load_font_korean,
        load_font_kr_chinese,
        load_font_noto_sans_cjk_sc,
    )

    key = normalize_title_font(font_key)
    pt = max(SUBTITLE_FONT_PT_MIN, int(font_pt))
    white = (255, 255, 255)
    if key == "noto_sc":
        return load_font_noto_sans_cjk_sc(pt, white, weight="bold")
    if key == "korean":
        return load_font_korean(pt, white, weight="bold")
    return load_font_kr_chinese(pt, white, weight="bold")


def measure_subtitle_line(text: str, font_pt: int, font_key: str) -> tuple[int, int]:
    """한 줄 (width, height)."""
    font = load_subtitle_font(font_key, font_pt)
    if font is None:
        return 0, 0
    surf = font.render((text or "").strip(), True, (255, 255, 255))
    return surf.get_width(), surf.get_height()


def subtitle_bake_cache_token(layout: WordMemorizeLayout) -> tuple[str, ...]:
    """타일 베이스 캐시에 포함할 부제목 식별자."""
    specs = layout_subtitle_line_specs(layout)
    if not specs:
        return ("",)
    parts: list[str] = [
        str(int(getattr(layout, "subtitle_y_offset_px", 0))),
        f"{layout.margin_top_ratio:.6f}",
        f"{layout.margin_bottom_ratio:.6f}",
        f"cell:{SUBTITLE_CELL_PX}",
    ]
    for spec in specs:
        parts.append(
            f"{spec.text}|{spec.font}|{resolve_subtitle_line_text_tile(layout, spec)}"
        )
    return tuple(parts)


def _subtitle_layout_limits(
    *,
    frame_width: int,
    frame_height: int,
    margin_top_ratio: float,
    margin_bottom_ratio: float,
    tile_px: int,
) -> tuple[int, int, int, int]:
    """(max_w, max_h, band_y0, band_y1) — 타일 밴드 안 상·하·좌·우 5타일 여백."""
    _x0, band_y0, fw, band_y1 = subtitle_tile_band_rect(
        frame_width,
        frame_height,
        margin_top_ratio=margin_top_ratio,
        margin_bottom_ratio=margin_bottom_ratio,
        tile_px=tile_px,
    )
    px = max(1, int(tile_px))
    pad = SUBTITLE_MARGIN_TILES * px
    band_h = max(1, band_y1 - band_y0)
    max_w = max(px * 4, int(fw) - 2 * pad)
    max_h = max(px * SUBTITLE_MIN_LINE_TILES, int(band_h) - 2 * pad)
    return max_w, max_h, band_y0, band_y1


def _subtitle_line_gap(tile_px: int) -> int:
    px = max(1, int(tile_px))
    return max(px, SUBTITLE_LINE_GAP_TILES * px)


def compute_subtitle_font_pt(
    specs: list[SubtitleLineSpec],
    *,
    frame_width: int,
    frame_height: int,
    margin_top_ratio: float = DEFAULT_MARGIN_TOP_RATIO,
    margin_bottom_ratio: float = DEFAULT_MARGIN_BOTTOM_RATIO,
    tile_px: int,
    measure_line: MeasureLineFn | None = None,
) -> int:
    """5타일 여백 박스 안에 들어가는 최대 pt."""
    measurer = measure_line or measure_subtitle_line
    lines = [
        ((spec.text or "").strip()[:80], normalize_title_font(spec.font))
        for spec in specs
        if (spec.text or "").strip()
    ]
    if not lines:
        return SUBTITLE_FONT_PT_MIN

    px = max(1, int(tile_px))
    max_w, max_h, _, _ = _subtitle_layout_limits(
        frame_width=frame_width,
        frame_height=frame_height,
        margin_top_ratio=margin_top_ratio,
        margin_bottom_ratio=margin_bottom_ratio,
        tile_px=px,
    )
    gap = _subtitle_line_gap(px)
    pt_hi = min(SUBTITLE_FONT_PT_MAX, max(max_h, max_w))
    pt_min = max(SUBTITLE_FONT_PT_MIN, px * 2)

    def _fits(pt: int) -> bool:
        widest = 0
        total_h = 0
        for i, (text, font_key) in enumerate(lines):
            w, h = measurer(text, pt, font_key)
            widest = max(widest, w)
            total_h += h
            if i < len(lines) - 1:
                total_h += gap
        return widest > 0 and total_h > 0 and widest <= max_w and total_h <= max_h

    if not _fits(pt_min):
        return pt_min
    if _fits(pt_hi):
        return pt_hi

    lo, hi = pt_min, pt_hi
    best_pt = pt_min
    while lo <= hi:
        mid = (lo + hi) // 2
        mid = mid - (mid % 4) if mid > pt_min else mid
        if mid < pt_min:
            mid = pt_min
        if _fits(mid):
            best_pt = mid
            lo = mid + 4
        else:
            hi = mid - 4
    return best_pt


def _render_text_mask(
    font: pygame.font.Font, text: str
) -> pygame.Surface | None:
    line = (text or "").strip()
    if not line:
        return None
    surf = font.render(line, True, (255, 255, 255))
    if surf.get_width() <= 0 or surf.get_height() <= 0:
        return None
    mask = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))
    mask.blit(surf, (0, 0))
    return mask


def _ceil_tile_units(value: int, tile_px: int) -> int:
    px = max(1, int(tile_px))
    return max(px, int(math.ceil(float(value) / px)) * px)


def _scale_mask_to_tile_grid(
    mask: pygame.Surface,
    cell_px: int,
    *,
    min_line_px: int,
) -> pygame.Surface:
    """마스크를 부제목 세밀 격자 배수 크기로 맞춘다."""
    px = max(1, int(cell_px))
    w, h = mask.get_size()
    nw = _ceil_tile_units(w, px)
    nh = max(min_line_px, _ceil_tile_units(h, px))
    if nw == w and nh == h:
        return mask
    return pygame.transform.scale(mask, (nw, nh))


def _fit_subtitle_masks_to_band(
    items: list[tuple[pygame.Surface, str, int]],
    *,
    max_w: int,
    max_h: int,
    tile_px: int,
    cell_px: int,
    gap: int,
) -> list[tuple[pygame.Surface, str, int]]:
    """밴드 안에 최대한 크게 — 세밀 격자에 맞춘 마스크 목록."""
    gpx = max(1, int(tile_px))
    cpx = max(1, int(cell_px))
    min_line_px = max(cpx, SUBTITLE_MIN_LINE_TILES * gpx)
    if not items:
        return []

    quantized: list[tuple[pygame.Surface, str, int]] = []
    for mask, text_tile_stem, _h in items:
        scaled = _scale_mask_to_tile_grid(mask, cpx, min_line_px=min_line_px)
        quantized.append((scaled, text_tile_stem, scaled.get_height()))

    def _block_size(
        rows: list[tuple[pygame.Surface, str, int]],
    ) -> tuple[int, int]:
        bw = max(m.get_width() for m, _, _ in rows)
        bh = sum(h for _, _, h in rows) + gap * max(0, len(rows) - 1)
        return bw, bh

    block_w, block_h = _block_size(quantized)
    if block_w <= 0 or block_h <= 0:
        return quantized

    fit = min(max_w / block_w, max_h / block_h)
    if fit <= 0:
        return quantized

    if abs(fit - 1.0) < 0.001:
        return quantized

    target_w = max(cpx * 2, int(block_w * fit))
    target_h = max(min_line_px, int(block_h * fit))
    target_w = min(max_w, _ceil_tile_units(target_w, cpx))
    target_h = min(max_h, _ceil_tile_units(target_h, cpx))
    sx = target_w / block_w
    sy = target_h / block_h
    uniform = min(sx, sy)

    fitted: list[tuple[pygame.Surface, str, int]] = []
    for mask, text_tile_stem, _h in quantized:
        nw = max(cpx, _ceil_tile_units(int(mask.get_width() * uniform), cpx))
        nh = max(
            min_line_px,
            _ceil_tile_units(int(mask.get_height() * uniform), cpx),
        )
        scaled = pygame.transform.scale(mask, (nw, nh))
        fitted.append((scaled, text_tile_stem, nh))
    return fitted


def _prepare_text_tile_surface(
    tile: pygame.Surface, tile_px: int
) -> pygame.Surface:
    """text_tile을 격자 한 칸 크기로 맞춘다."""
    px = max(1, int(tile_px))
    if tile.get_size() == (px, px):
        return tile
    return pygame.transform.scale(tile, (px, px))


def _blit_text_tile_mask(
    surface: pygame.Surface,
    text_surf: pygame.Surface,
    pos: tuple[int, int],
    text_tile: pygame.Surface,
    *,
    tile_px: int,
    cell_px: int,
) -> None:
    """텍스트 마스크와 겹치는 세밀 격자 칸을 text_tile(축소)로 대체."""
    tx0, ty0 = int(pos[0]), int(pos[1])
    tw, th = text_surf.get_size()
    if tw <= 0 or th <= 0:
        return
    gpx = max(1, int(tile_px))
    cpx = max(1, int(cell_px))
    text_mask = pygame.mask.from_surface(text_surf)
    cell_mask = pygame.Mask((cpx, cpx), fill=True)
    cell_tile = _prepare_text_tile_surface(text_tile, cpx)

    x_start = snap_tile_coord(tx0, gpx)
    y_start = snap_tile_coord(ty0, gpx)
    x_end = tx0 + tw
    y_end = ty0 + th

    for ty in range(y_start, y_end, cpx):
        for tx in range(x_start, x_end, cpx):
            if text_mask.overlap(cell_mask, (tx - tx0, ty - ty0)):
                surface.blit(cell_tile, (tx, ty))


def _snap_block_origin(
    cx: int, cy: int, block_w: int, block_h: int, tile_px: int
) -> tuple[int, int]:
    px = max(1, int(tile_px))
    x = snap_tile_coord(cx - block_w // 2, px)
    y = snap_tile_coord(cy - block_h // 2, px)
    return x, y


def apply_tile_subtitle(
    surface: pygame.Surface,
    layout: WordMemorizeLayout,
    *,
    load_text_tile: TextTileLoaderFn,
    tile_px: int,
    font_pt: int | None = None,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> None:
    """타일 레이어 위 부제목 — 글자 위치의 배경 타일을 text_tile로 교체."""
    specs = layout_subtitle_line_specs(layout)
    if not specs or tile_px <= 0:
        return

    fw = int(frame_width) if frame_width is not None else int(layout.frame_width)
    fh = int(frame_height) if frame_height is not None else int(layout.frame_height)
    px = max(1, int(tile_px))
    cell_px = subtitle_cell_px(tile_px=px)
    margin_top = float(layout.margin_top_ratio)
    margin_bottom = float(layout.margin_bottom_ratio)

    max_w, max_h, band_y0, band_y1 = _subtitle_layout_limits(
        frame_width=fw,
        frame_height=fh,
        margin_top_ratio=margin_top,
        margin_bottom_ratio=margin_bottom,
        tile_px=px,
    )
    pt = (
        int(font_pt)
        if font_pt is not None
        else compute_subtitle_font_pt(
            specs,
            frame_width=fw,
            frame_height=fh,
            margin_top_ratio=margin_top,
            margin_bottom_ratio=margin_bottom,
            tile_px=px,
        )
    )
    cx, cy = resolve_subtitle_position(
        frame_width=fw,
        frame_height=fh,
        margin_top_ratio=margin_top,
        margin_bottom_ratio=margin_bottom,
        tile_px=px,
        y_offset_px=int(getattr(layout, "subtitle_y_offset_px", 0)),
    )
    gap = _subtitle_line_gap(px)

    raw_items: list[tuple[pygame.Surface, str, int]] = []
    for spec in specs[:8]:
        text = (spec.text or "").strip()[:80]
        if not text:
            continue
        text_tile_stem = resolve_subtitle_line_text_tile(layout, spec)
        if not text_tile_stem:
            continue
        font = load_subtitle_font(spec.font, pt)
        if font is None:
            continue
        mask = _render_text_mask(font, text)
        if mask is None:
            continue
        raw_items.append((mask, text_tile_stem, mask.get_height()))

    if not raw_items:
        return

    items = _fit_subtitle_masks_to_band(
        raw_items,
        max_w=max_w,
        max_h=max_h,
        tile_px=px,
        cell_px=cell_px,
        gap=gap,
    )
    total_h = sum(h for _, _, h in items) + gap * (len(items) - 1)
    block_w = max(m.get_width() for m, _, _ in items)
    x0, y0 = _snap_block_origin(cx, cy, block_w, total_h, px)
    y0 = max(band_y0, min(y0, max(band_y0, band_y1 - total_h)))

    text_tile_cache: dict[str, pygame.Surface] = {}
    y = y0
    for mask, text_tile_stem, h in items:
        line_x = snap_tile_coord(x0 + (block_w - mask.get_width()) // 2, px)
        cached = text_tile_cache.get(text_tile_stem)
        if cached is None:
            loaded = load_text_tile(text_tile_stem)
            if loaded is None:
                y += h + gap
                continue
            cached = _prepare_text_tile_surface(loaded, cell_px)
            text_tile_cache[text_tile_stem] = cached
        _blit_text_tile_mask(
            surface,
            mask,
            (line_x, y),
            cached,
            tile_px=px,
            cell_px=cell_px,
        )
        y += h + gap


# 하위 호환 — 기존 import명
draw_tile_subtitle = apply_tile_subtitle
