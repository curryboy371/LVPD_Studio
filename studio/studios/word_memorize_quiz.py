"""단어 외우기 — 퀴즈 모드 프레임 UI (이미지·단어 가로 배치, 페이드 아웃)."""
from __future__ import annotations

import math
from collections import deque
from typing import Callable

import pygame

from data.models import Word
from extra.table_editor.services.word_memorize_layout import (
    word_memorize_quiz_box_path,
    word_memorize_quiz_gage_bg_path,
    word_memorize_quiz_gage_path,
)

# TTS 종료 후 유지(초) → 페이드 아웃
QUIZ_HOLD_AFTER_TTS_SEC = 1.0
QUIZ_FADE_OUT_SEC = 0.65
# 양피지 내부 — 이미지|단어 가로 배치 (inset은 에셋에서 자동 감지, 폴백용)
_QUIZ_CONTENT_PAD_X = 0.06
_QUIZ_CONTENT_PAD_Y = 0.10
_QUIZ_IMAGE_WIDTH_RATIO = 0.44
_QUIZ_GAP_RATIO = 0.04
_QUIZ_MAX_FRAME_WIDTH_RATIO = 0.92
_QUIZ_MAX_FRAME_HEIGHT_RATIO = 0.34
_QUIZ_CENTER_Y_RATIO = 0.42
_QUIZ_GAGE_WIDTH_RATIO = 0.36
_QUIZ_GAGE_MAX_HEIGHT_RATIO = 0.07
# 하단 프레임 밴드 세로 중앙 (0=양피지 경계, 1=박스 바닥)
_QUIZ_GAGE_FRAME_ANCHOR_RATIO = 0.55
_QUIZ_GAGE_Y_OFFSET_UP_RATIO = 0.048
_QUIZ_GAGE_RENDER_SCALE = 4
_QUIZ_SPRITE_BLACK_CUTOFF = 8
_QUIZ_SPRITE_SOFT_ALPHA_MAX_RGB = 48
_QUIZ_TEXT_COLOR_KO = (48, 42, 36)
_QUIZ_TEXT_COLOR_ZH = (28, 28, 28)
# 배경 매트 제거 — 흰 배경(신규 프레임)·검정 배경(구 두루마리) 모두 지원
_QUIZ_WHITE_FLOOD_DIST = 52
_QUIZ_BLACK_FLOOD_MAX_RGB = 28
_QUIZ_WHITE_MATTE_MAX_DIST = 88
_QUIZ_BLACK_MATTE_MAX_RGB = 56
_QUIZ_MIN_ALPHA_ISLAND_PX = 900
_QUIZ_CROP_ALPHA_PAD_PX = 2

_quiz_box_pil_cache: object | None = None
_quiz_box_scaled_cache: dict[tuple[int, int], pygame.Surface] = {}
_gage_sprite_cache: dict[tuple[int, int | None], pygame.Surface] = {}
_gage_bg_sprite_cache: dict[tuple[int, int], pygame.Surface] = {}
_gage_hi_res_cache: dict[tuple[int, int], pygame.Surface] = {}
# (left, top, right, bottom) — 프레임 대비 양피지 inset 비율
_quiz_content_insets: tuple[float, float, float, float] = (
    0.12,
    0.05,
    0.13,
    0.05,
)


def quiz_reveal_display_text(word: Word, *, meaning_lang: str) -> str:
    """퀴즈 프레임에 표시할 단어 — ko=한글 뜻, zh=한자."""
    lang = (meaning_lang or "ko").strip().lower()
    if lang in ("zh", "ch", "cn"):
        return (word.word or "").strip()
    return (word.meaning or "").strip()


def quiz_fade_alpha(
    substep: str,
    *,
    fade_elapsed_sec: float,
    fade_duration_sec: float = QUIZ_FADE_OUT_SEC,
) -> int:
    """quiz_reveal=255, quiz_fade_out=선형 감소."""
    if substep == "quiz_reveal":
        return 255
    if substep != "quiz_fade_out":
        return 0
    dur = max(1e-4, float(fade_duration_sec))
    t = max(0.0, min(1.0, float(fade_elapsed_sec) / dur))
    return int(round(255.0 * (1.0 - t)))


def quiz_timer_remaining_ratio(
    *,
    timer_sec: float,
    hold_sec: float,
) -> float:
    """TTS 재생 + 대기 전체(hold_sec) 구간에서 1→0."""
    total = max(0.0, float(hold_sec))
    timer = max(0.0, float(timer_sec))
    if total <= 1e-6:
        return 0.0
    if timer >= total:
        return 0.0
    return max(0.0, 1.0 - timer / total)


def _dist_from_white(r: int, g: int, b: int) -> int:
    return min(255 - r, 255 - g, 255 - b)


def _is_external_bg_seed(r: int, g: int, b: int, a: int) -> bool:
    if a < 8:
        return True
    if _dist_from_white(r, g, b) <= _QUIZ_WHITE_FLOOD_DIST:
        return True
    return max(r, g, b) <= _QUIZ_BLACK_FLOOD_MAX_RGB


def _unpremultiply_white_fringe(r: int, g: int, b: int) -> tuple[int, int, int, int]:
    dist = _dist_from_white(r, g, b)
    if dist <= 6:
        return 0, 0, 0, 0
    if dist >= _QUIZ_WHITE_MATTE_MAX_DIST:
        return r, g, b, 255
    alpha = dist
    nr = max(0, min(255, 255 - (255 - r) * 255 // alpha))
    ng = max(0, min(255, 255 - (255 - g) * 255 // alpha))
    nb = max(0, min(255, 255 - (255 - b) * 255 // alpha))
    return nr, ng, nb, alpha


def _unpremultiply_black_fringe(r: int, g: int, b: int) -> tuple[int, int, int, int]:
    mx = max(r, g, b)
    if mx <= 6:
        return 0, 0, 0, 0
    if mx >= _QUIZ_BLACK_MATTE_MAX_RGB:
        return r, g, b, 255
    alpha = mx
    nr = min(255, r * 255 // alpha)
    ng = min(255, g * 255 // alpha)
    nb = min(255, b * 255 // alpha)
    return nr, ng, nb, alpha


def _flood_external_background(
    px: object, w: int, h: int
) -> list[list[bool]]:
    """가장자리 흰/검정 배경 플러드필."""
    is_bg = [[False] * w for _ in range(h)]
    queue: deque[tuple[int, int]] = deque()

    def _seed(x: int, y: int) -> None:
        if is_bg[y][x]:
            return
        r, g, b, a = px[x, y]
        if _is_external_bg_seed(r, g, b, a):
            is_bg[y][x] = True
            queue.append((x, y))

    for x in range(w):
        _seed(x, 0)
        _seed(x, h - 1)
    for y in range(h):
        _seed(0, y)
        _seed(w - 1, y)

    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= w or ny >= h or is_bg[ny][nx]:
                continue
            r, g, b, a = px[nx, ny]
            if _is_external_bg_seed(r, g, b, a):
                is_bg[ny][nx] = True
                queue.append((nx, ny))
            elif _dist_from_white(r, g, b) <= _QUIZ_WHITE_MATTE_MAX_DIST:
                is_bg[ny][nx] = True
                queue.append((nx, ny))
            elif max(r, g, b) <= _QUIZ_BLACK_MATTE_MAX_RGB:
                is_bg[ny][nx] = True
                queue.append((nx, ny))
    return is_bg


def _is_parchment_pixel(r: int, g: int, b: int, a: int) -> bool:
    if a < 160:
        return False
    return r > 215 and g > 205 and b > 175 and r >= g >= b


def _detect_parchment_insets(
    px: object, w: int, h: int
) -> tuple[float, float, float, float]:
    """양피지 내부 영역 — 이미지·단어 배치 inset 비율."""
    min_x, min_y = w, h
    max_x, max_y = 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if not _is_parchment_pixel(r, g, b, a):
                continue
            found = True
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if not found or max_x <= min_x or max_y <= min_y:
        return _quiz_content_insets
    return (
        min_x / float(w),
        min_y / float(h),
        (w - 1 - max_x) / float(w),
        (h - 1 - max_y) / float(h),
    )


def _prune_small_alpha_islands(px: object, w: int, h: int) -> None:
    """작은 노이즈 섬(우하단 잔여 픽셀 등) 제거 — 최대 연결 요소만 유지."""
    visited = [[False] * w for _ in range(h)]
    best: list[tuple[int, int]] = []

    for sy in range(h):
        for sx in range(w):
            if visited[sy][sx] or px[sx, sy][3] < 24:
                continue
            queue: deque[tuple[int, int]] = deque([(sx, sy)])
            visited[sy][sx] = True
            component: list[tuple[int, int]] = []
            while queue:
                x, y = queue.popleft()
                component.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if nx < 0 or ny < 0 or nx >= w or ny >= h:
                        continue
                    if visited[ny][nx] or px[nx, ny][3] < 24:
                        continue
                    visited[ny][nx] = True
                    queue.append((nx, ny))
            if len(component) > len(best):
                best = component

    if len(best) < _QUIZ_MIN_ALPHA_ISLAND_PX:
        return
    keep = set(best)
    for y in range(h):
        for x in range(w):
            if px[x, y][3] >= 24 and (x, y) not in keep:
                px[x, y] = (0, 0, 0, 0)


def _crop_to_alpha_bbox(im: object, *, pad: int = _QUIZ_CROP_ALPHA_PAD_PX) -> object:
    from PIL import Image

    rgba = im.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    min_x, min_y = w, h
    max_x, max_y = 0, 0
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 8:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x <= min_x or max_y <= min_y:
        return rgba
    p = max(0, int(pad))
    return rgba.crop(
        (
            max(0, min_x - p),
            max(0, min_y - p),
            min(w, max_x + p + 1),
            min(h, max_y + p + 1),
        )
    )


def _mark_fringe_zone(
    is_bg: list[list[bool]], px: object, w: int, h: int, *, margin: int = 3
) -> list[list[bool]]:
    """배경에 닿은 가장자리 픽셀만 매트 보정 대상."""
    is_fringe = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if is_bg[y][x]:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)):
                nx, ny = x + dx, y + dy
                if nx < 0 or ny < 0 or nx >= w or ny >= h:
                    is_fringe[y][x] = True
                    break
                if is_bg[ny][nx] or px[nx, ny][3] < 8:
                    is_fringe[y][x] = True
                    break
    for _ in range(max(0, margin - 1)):
        grown = [[False] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if is_fringe[y][x]:
                    grown[y][x] = True
                    continue
                if is_bg[y][x]:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and is_fringe[ny][nx]:
                        grown[y][x] = True
                        break
        is_fringe = grown
    return is_fringe


def _solidify_interior(px: object, w: int, h: int) -> None:
    """양피지·프레임 내부 — 불필요한 반투명 제거."""
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 8:
                continue
            if _is_parchment_pixel(r, g, b, a) or max(r, g, b) > 80:
                px[x, y] = (r, g, b, 255)


def _defringe_quiz_box_image(im: object) -> object:
    """흰/검정 매트 배경 PNG → 깨끗한 RGBA + 양피지 inset 감지."""
    global _quiz_content_insets

    rgba = im.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    is_bg = _flood_external_background(px, w, h)
    is_fringe = _mark_fringe_zone(is_bg, px, w, h)

    for y in range(h):
        for x in range(w):
            if is_bg[y][x]:
                px[x, y] = (0, 0, 0, 0)
                continue
            r, g, b, a = px[x, y]
            if a == 0 or not is_fringe[y][x]:
                continue
            wd = _dist_from_white(r, g, b)
            mx = max(r, g, b)
            if wd < _QUIZ_WHITE_MATTE_MAX_DIST and wd <= mx:
                px[x, y] = _unpremultiply_white_fringe(r, g, b)
            elif mx < _QUIZ_BLACK_MATTE_MAX_RGB:
                px[x, y] = _unpremultiply_black_fringe(r, g, b)

    _solidify_interior(px, w, h)
    _prune_small_alpha_islands(px, w, h)
    cropped = _crop_to_alpha_bbox(rgba)
    px2 = cropped.load()
    cw, ch = cropped.size
    _quiz_content_insets = _detect_parchment_insets(px2, cw, ch)
    return cropped


def _load_quiz_box_pil() -> object | None:
    global _quiz_box_pil_cache
    if _quiz_box_pil_cache is not None:
        return _quiz_box_pil_cache
    path = word_memorize_quiz_box_path()
    if not path.is_file():
        return None
    try:
        from PIL import Image

        im = Image.open(path)
        if path.name == "quiz_box_rgba.png":
            rgba = im.convert("RGBA")
            px = rgba.load()
            cw, ch = rgba.size
            global _quiz_content_insets
            _quiz_content_insets = _detect_parchment_insets(px, cw, ch)
            _quiz_box_pil_cache = rgba
        else:
            _quiz_box_pil_cache = _defringe_quiz_box_image(im)
        return _quiz_box_pil_cache
    except Exception:
        return None


def _pil_rgba_to_pygame(im: object) -> pygame.Surface:
    from PIL import Image

    rgba = im.convert("RGBA")
    surf = pygame.image.frombuffer(rgba.tobytes(), rgba.size, "RGBA")
    return surf.convert_alpha()


def _scale_quiz_box(*, frame_width: int, frame_height: int) -> pygame.Surface | None:
    """PIL LANCZOS 리사이즈 — 알파 가장자리 품질 유지."""
    pil = _load_quiz_box_pil()
    if pil is None:
        return None
    from PIL import Image

    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    max_w = max(64, int(fw * _QUIZ_MAX_FRAME_WIDTH_RATIO))
    max_h = max(48, int(fh * _QUIZ_MAX_FRAME_HEIGHT_RATIO))
    sw, sh = pil.size
    scale = min(max_w / max(1, sw), max_h / max(1, sh), 1.0)
    nw = max(1, int(sw * scale))
    nh = max(1, int(sh * scale))
    key = (nw, nh)
    cached = _quiz_box_scaled_cache.get(key)
    if cached is not None:
        return cached
    if (nw, nh) == pil.size:
        scaled_im = pil
    else:
        scaled_im = pil.resize((nw, nh), Image.Resampling.LANCZOS)
    surf = _pil_rgba_to_pygame(scaled_im)
    _quiz_box_scaled_cache[key] = surf
    return surf


def _render_fitted_text(
    text: str,
    *,
    meaning_lang: str,
    max_w: int,
    max_h: int,
    base_pt: int,
) -> pygame.Surface | None:
    if not text or max_w < 8 or max_h < 8:
        return None
    from utils.fonts import load_font_korean, load_font_noto_sans_cjk_sc

    lang = (meaning_lang or "ko").strip().lower()
    color = _QUIZ_TEXT_COLOR_ZH if lang in ("zh", "ch", "cn") else _QUIZ_TEXT_COLOR_KO
    pt = max(32, int(base_pt))
    min_pt = 28
    while pt >= min_pt:
        if lang in ("zh", "ch", "cn"):
            font = load_font_noto_sans_cjk_sc(pt, color, weight="bold")
        else:
            font = load_font_korean(pt, color, weight="bold")
        if font is None:
            pt -= 4
            continue
        surf = font.render(text, True, color)
        if surf.get_width() <= max_w and surf.get_height() <= max_h:
            return surf
        pt -= 4
    font = (
        load_font_noto_sans_cjk_sc(min_pt, color, weight="bold")
        if lang in ("zh", "ch", "cn")
        else load_font_korean(min_pt, color, weight="bold")
    )
    if font is None:
        return None
    surf = font.render(text[:40], True, color)
    ratio = min(max_w / max(1, surf.get_width()), max_h / max(1, surf.get_height()), 1.0)
    nw = max(1, int(surf.get_width() * ratio))
    nh = max(1, int(surf.get_height() * ratio))
    return pygame.transform.smoothscale(surf, (nw, nh))


def _apply_black_bg_sprite_alpha(im: object) -> object:
    """검정 배경 스프라이트 — 알파 채널 생성."""
    rgba = im.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    cutoff = int(_QUIZ_SPRITE_BLACK_CUTOFF)
    soft_max = int(_QUIZ_SPRITE_SOFT_ALPHA_MAX_RGB)
    for y in range(h):
        for x in range(w):
            r, g, b, _a = px[x, y]
            mx = max(r, g, b)
            if mx <= cutoff:
                px[x, y] = (0, 0, 0, 0)
            elif mx < soft_max:
                alpha = min(255, mx * 255 // max(1, soft_max))
                px[x, y] = (r, g, b, alpha)
            else:
                px[x, y] = (r, g, b, 255)
    return rgba


def _crop_alpha_bbox_pil(im: object, *, pad: int = 1) -> object:
    rgba = im.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    min_x, min_y = w, h
    max_x, max_y = 0, 0
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 8:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x <= min_x or max_y <= min_y:
        return rgba
    p = max(0, int(pad))
    return rgba.crop(
        (
            max(0, min_x - p),
            max(0, min_y - p),
            min(w, max_x + p + 1),
            min(h, max_y + p + 1),
        )
    )


def _load_gage_sprite(
    target_w: int,
    *,
    max_h: int | None = None,
) -> pygame.Surface | None:
    """게이지 채움(gage) — 너비 기준 스케일, max_h 있으면 높이 상한."""
    from PIL import Image

    tw = max(32, int(target_w))
    mh = None if max_h is None else max(4, int(max_h))
    cache_key = (tw, mh)
    cached = _gage_sprite_cache.get(cache_key)
    if cached is not None:
        return cached

    fill_path = word_memorize_quiz_gage_path()
    if not fill_path.is_file():
        return None

    try:
        fill_im = _crop_alpha_bbox_pil(
            _apply_black_bg_sprite_alpha(Image.open(fill_path))
        )
        fw, fh = fill_im.size
        scale = tw / max(1, fw)
        th = max(4, int(round(fh * scale)))
        if mh is not None and th > mh:
            scale = mh / max(1, fh)
            th = mh
            tw = max(32, int(round(fw * scale)))
        scaled = fill_im.resize((tw, th), Image.Resampling.LANCZOS)
        surf = _pil_rgba_to_pygame(scaled)
        _gage_sprite_cache[cache_key] = surf
        return surf
    except Exception:
        return None


def _load_gage_bg_sprite(gage: pygame.Surface) -> pygame.Surface | None:
    """게이지 배경(gage_bg) — gage와 동일 크기로 스케일."""
    from PIL import Image

    tw, th = gage.get_size()
    cache_key = (tw, th)
    cached = _gage_bg_sprite_cache.get(cache_key)
    if cached is not None:
        return cached

    bg_path = word_memorize_quiz_gage_bg_path()
    if not bg_path.is_file():
        return None

    try:
        bg_im = _crop_alpha_bbox_pil(
            _apply_black_bg_sprite_alpha(Image.open(bg_path))
        )
        scaled = bg_im.resize((tw, th), Image.Resampling.LANCZOS)
        surf = _pil_rgba_to_pygame(scaled)
        _gage_bg_sprite_cache[cache_key] = surf
        return surf
    except Exception:
        return None


def _gage_gauge_dest(
    box_rect: pygame.Rect,
    bar_w: int,
) -> tuple[int, int]:
    """게이지 공통 좌하단 앵커 (left_x, bottom_y)."""
    _inset_l, _inset_t, _inset_r, inset_b = _quiz_content_insets
    bh = box_rect.height
    bottom_band = max(4, int(bh * inset_b))
    content_bottom = box_rect.bottom - bottom_band
    anchor_y = content_bottom + int(bottom_band * _QUIZ_GAGE_FRAME_ANCHOR_RATIO)
    bottom_y = min(anchor_y, box_rect.bottom) - max(
        2, int(bh * _QUIZ_GAGE_Y_OFFSET_UP_RATIO)
    )
    left_x = box_rect.centerx - bar_w // 2
    return left_x, bottom_y


def _gage_hi_res_sprite(gage: pygame.Surface) -> pygame.Surface:
    """게이지 — 서브픽셀 폭 보간용 고해상도 캐시."""
    key = gage.get_size()
    cached = _gage_hi_res_cache.get(key)
    if cached is not None:
        return cached
    w, h = key
    scale = max(2, int(_QUIZ_GAGE_RENDER_SCALE))
    hi = pygame.transform.smoothscale(gage, (w * scale, h * scale))
    _gage_hi_res_cache[key] = hi
    return hi


def _gage_sprite_for_ratio(gage: pygame.Surface, ratio: float) -> pygame.Surface | None:
    """좌측 고정·우측 감소 — 고해상도 클립 후 smoothscale."""
    gage_w, gage_h = gage.get_size()
    r = max(0.0, min(1.0, float(ratio)))
    if r <= 1e-4:
        return None
    if r >= 1.0 - 1e-6:
        return gage
    hi = _gage_hi_res_sprite(gage)
    hi_w, hi_h = hi.get_size()
    draw_hi_f = max(1.0, hi_w * r)
    src_w = min(hi_w, max(1, int(math.ceil(draw_hi_f))))
    clip = hi.subsurface((0, 0, src_w, hi_h))
    out_w = max(1, min(gage_w, int(round(gage_w * r))))
    return pygame.transform.smoothscale(clip, (out_w, gage_h))


def _blit_with_alpha(
    surface: pygame.Surface,
    sprite: pygame.Surface,
    dest: pygame.Rect,
    *,
    overlay_alpha: int = 255,
) -> None:
    if overlay_alpha >= 255:
        surface.blit(sprite, dest)
        return
    layer = sprite.copy()
    layer.set_alpha(max(0, min(255, int(overlay_alpha))))
    surface.blit(layer, dest)


def _draw_quiz_timer_gauge(
    surface: pygame.Surface,
    box_rect: pygame.Rect,
    *,
    remaining_ratio: float,
    overlay_alpha: int,
) -> None:
    """퀴즈박스 하단 — gage_bg + gage 채움(좌측 고정·우측 감소)."""
    ratio = max(0.0, min(1.0, float(remaining_ratio)))
    target_w = max(32, int(box_rect.width * _QUIZ_GAGE_WIDTH_RATIO))
    max_h = max(6, int(box_rect.height * _QUIZ_GAGE_MAX_HEIGHT_RATIO))
    gage = _load_gage_sprite(target_w, max_h=max_h)
    if gage is None:
        return

    gage_w = gage.get_width()
    left_x, bottom_y = _gage_gauge_dest(box_rect, gage_w)

    gage_bg = _load_gage_bg_sprite(gage)
    if gage_bg is not None:
        bg_dest = gage_bg.get_rect()
        bg_dest.bottomleft = (left_x, bottom_y)
        _blit_with_alpha(surface, gage_bg, bg_dest, overlay_alpha=overlay_alpha)

    if ratio <= 1e-4:
        return
    sprite = _gage_sprite_for_ratio(gage, ratio)
    if sprite is None:
        return

    dest = sprite.get_rect()
    dest.bottomleft = (left_x, bottom_y)
    _blit_with_alpha(surface, sprite, dest, overlay_alpha=overlay_alpha)


def draw_quiz_reveal_overlay(
    surface: pygame.Surface,
    *,
    frame_width: int,
    frame_height: int,
    word: Word,
    meaning_lang: str,
    alpha: int,
    load_word_image: Callable[[Word, int, int], pygame.Surface | None],
    time_remaining_ratio: float | None = None,
) -> None:
    """퀴즈 프레임 — 이미지(좌)·단어(우) 가로 배치."""
    if alpha <= 0:
        return
    box = _scale_quiz_box(frame_width=frame_width, frame_height=frame_height)
    if box is None:
        return

    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    bw, bh = box.get_size()
    cx = fw // 2
    cy = int(fh * _QUIZ_CENTER_Y_RATIO)
    box_rect = box.get_rect(center=(cx, cy))

    if alpha < 255:
        box_layer = box.copy()
        box_layer.set_alpha(alpha)
        surface.blit(box_layer, box_rect)
    else:
        surface.blit(box, box_rect)

    inset_l, inset_t, inset_r, inset_b = _quiz_content_insets
    px0 = box_rect.x + int(bw * inset_l)
    py0 = box_rect.y + int(bh * inset_t)
    px1 = box_rect.right - int(bw * inset_r)
    py1 = box_rect.bottom - int(bh * inset_b)
    content_w = max(1, px1 - px0)
    content_h = max(1, py1 - py0)
    pad_x = int(content_w * _QUIZ_CONTENT_PAD_X)
    pad_y = int(content_h * _QUIZ_CONTENT_PAD_Y)
    inner = pygame.Rect(
        px0 + pad_x,
        py0 + pad_y,
        max(1, content_w - 2 * pad_x),
        max(1, content_h - 2 * pad_y),
    )

    gap = max(4, int(inner.width * _QUIZ_GAP_RATIO))
    img_w = max(1, int(inner.width * _QUIZ_IMAGE_WIDTH_RATIO))
    text_w = max(1, inner.width - img_w - gap)
    img_rect = pygame.Rect(inner.x, inner.y, img_w, inner.height)
    text_rect = pygame.Rect(inner.right - text_w, inner.y, text_w, inner.height)

    display_text = quiz_reveal_display_text(word, meaning_lang=meaning_lang)
    scale = fh / 1920.0
    base_pt = max(48, int(96 * scale))

    img_surf = load_word_image(word, img_rect.width, img_rect.height)
    if img_surf is not None:
        dest = img_surf.get_rect(center=img_rect.center)
        if alpha < 255:
            img_copy = img_surf.copy()
            img_copy.set_alpha(alpha)
            surface.blit(img_copy, dest)
        else:
            surface.blit(img_surf, dest)
    else:
        text_rect = inner

    text_surf = _render_fitted_text(
        display_text,
        meaning_lang=meaning_lang,
        max_w=text_rect.width,
        max_h=text_rect.height,
        base_pt=base_pt,
    )
    if text_surf is not None:
        dest = text_surf.get_rect(center=text_rect.center)
        if alpha < 255:
            text_copy = text_surf.copy()
            text_copy.set_alpha(alpha)
            surface.blit(text_copy, dest)
        else:
            surface.blit(text_surf, dest)

    if time_remaining_ratio is not None:
        _draw_quiz_timer_gauge(
            surface,
            box_rect,
            remaining_ratio=time_remaining_ratio,
            overlay_alpha=alpha,
        )
