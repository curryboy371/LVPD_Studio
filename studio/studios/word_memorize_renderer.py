"""단어 외우기 배치 — FHD 프레임 그리기."""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import pygame

from core.paths import get_repo_root
from data.models import Word
from extra.table_editor.services.word_memorize_layout import (
    BASE_SLOT_HANZI_COLOR,
    BASE_SLOT_HANZI_PT_FHD,
    BASE_SLOT_LINE_GAP_FHD,
    BASE_SLOT_MEANING_BG_COLOR,
    BASE_SLOT_MEANING_BG_RADIUS_FHD,
    BASE_SLOT_MEANING_COLOR,
    BASE_SLOT_MEANING_PAD_X_FHD,
    BASE_SLOT_MEANING_PAD_Y_FHD,
    BASE_SLOT_MEANING_PT_FHD,
    BASE_SLOT_PINYIN_BG_COLOR,
    BASE_SLOT_PINYIN_BG_PAD_X_FHD,
    BASE_SLOT_PINYIN_BG_PAD_Y_FHD,
    BASE_SLOT_PINYIN_BG_RADIUS_FHD,
    BASE_SLOT_PINYIN_COLOR,
    BASE_SLOT_PINYIN_PT_FHD,
    CARD_CONTENT_REFERENCE_INNER_H,
    CARD_IMG_BOTTOM_PAD_FHD,
    RowHighlightType,
    WordMemorizeBox,
    WordMemorizeLayout,
    box_runtime_key,
    boxes_in_row_group,
    default_card_item_gap,
    find_box_by_runtime_key,
    is_base_slot_box,
    layout_card_content_vertical,
    layout_use_card_background,
    layout_title_line_specs,
    normalize_row_highlight,
    normalize_selection_highlight,
    normalize_title_font,
    normalize_title_font_pt,
    resolve_title_position,
    title_color_to_rgb,
    _is_zh_meaning_lang,
    resolve_word_memorize_bg_image_path,
    resolve_word_memorize_bg_video_path,
)
from studio.studios.word_memorize_laser import (
    draw_laser_center_to_card,
    draw_laser_impact_border,
    laser_impact_elapsed_sec,
)
from utils.pinyin_masking import (
    get_masked_pinyin_marks,
    normalize_word_masking,
    word_pinyin_to_marks_spaced,
)

PINYIN_COLOR = (198, 40, 40)
HANZI_COLOR = (33, 33, 33)
EN_COLOR = (76, 175, 80)
BOX_FILL = (255, 255, 255)
BOX_OUTLINE = (144, 164, 174)
ACTIVE_BORDER_RADIUS = 8
# 애니메이션 그라데이션 보더 (파스텔 스톱 — 시간에 따라 순환)
GRAD_BORDER_STOPS: tuple[tuple[int, int, int], ...] = (
    (120, 200, 255),
    (186, 148, 255),
    (255, 158, 198),
    (255, 188, 128),
    (130, 220, 195),
    (120, 200, 255),
)
GRAD_BORDER_CYCLE_SEC = 0.7
GRAD_BORDER_WIDTH = 4
GRAD_BORDER_WIDTH_ACTIVE = 7
GRAD_GLOW_LAYERS = 5
GRAD_GLOW_SPREAD = 10
GRAD_RING_SAMPLES_PER_EDGE = 32
GRAD_RING_ARC_STEPS = 12
GRAD_RING_SUBDIV = 5
ACTIVE_CARD_SCALE = 1.03
RED_ACTIVE_BORDER_COLOR = (244, 67, 54)
RED_ACTIVE_BORDER_WIDTH = 6
ROW_BAND_BORDER_WIDTH = 10
ROW_BAND_V_INSET = 6
ROW_BRACKET_ARM = 32
ROW_BRACKET_THICK = 8
ROW_BRACKET_THICK_BOTH = 14
ROW_BRACKET_MARGIN_X = 24
ROW_LEFT_BAR_WIDTH = 12
ROW_NEON_GLOW_STRENGTH = 0.42
TEXT_LINE_GAP = 4
IMG_BOTTOM_PAD = 8
IMG_LIFT = 12
PINYIN_FONT_PT = 32
HANZI_FONT_PT = 72
EN_FONT_PT = 30
ZH_HANZI_SCALE = 0.8
ZH_MEANING_SCALE = 1.2
TITLE_LINE_GAP = 10
TITLE_FONT_PT = 68
TITLE_COLOR = (255, 255, 255)
TITLE_SHADOW_COLOR = (0, 0, 0)
IMG_MAX_HEIGHT_RATIO = 0.38


def _lerp_rgb(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _sample_round_rect_outline(
    rect: pygame.Rect,
    radius: int,
    *,
    samples_per_edge: int = GRAD_RING_SAMPLES_PER_EDGE,
    arc_steps: int = GRAD_RING_ARC_STEPS,
) -> list[tuple[int, int]]:
    """둥근 사각형 외곽을 시계 방향으로 샘플링."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    r = min(max(0, radius), w // 2, h // 2)
    pts: list[tuple[int, int]] = []

    def line_pts(x0: float, y0: float, x1: float, y1: float, n: int) -> None:
        for i in range(n):
            t = (i + 1) / n
            pts.append((int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)))

    def arc_pts(cx: float, cy: float, a0: float, a1: float, steps: int) -> None:
        for i in range(steps):
            t = (i + 1) / steps
            ang = a0 + (a1 - a0) * t
            pts.append((int(cx + r * math.cos(ang)), int(cy + r * math.sin(ang))))

    line_pts(x + r, y, x + w - r, y, samples_per_edge)
    arc_pts(x + w - r, y + r, -math.pi / 2, 0.0, arc_steps)
    line_pts(x + w, y + r, x + w, y + h - r, samples_per_edge)
    arc_pts(x + w - r, y + h - r, 0.0, math.pi / 2, arc_steps)
    line_pts(x + w - r, y + h, x + r, y + h, samples_per_edge)
    arc_pts(x + r, y + h - r, math.pi / 2, math.pi, arc_steps)
    line_pts(x, y + h - r, x, y + r, samples_per_edge)
    arc_pts(x + r, y + r, math.pi, 3 * math.pi / 2, arc_steps)
    return pts


def border_anim_time_sec(config: Any | None) -> float:
    """그라데이션 보더 위상용 시간(초).

    녹화: runner의 recording_time_sec(프레임 인덱스/fps) — 렌더 속도와 무관.
    미리보기: pygame 벽시계.
    """
    if config is not None and getattr(config, "recording_log_event", None) is not None:
        return float(getattr(config, "recording_time_sec", 0.0) or 0.0)
    return pygame.time.get_ticks() / 1000.0


def _border_anim_phase(t_sec: float) -> float:
    """0~1 — 스톱 팔레트가 천천히 순환."""
    return (t_sec / GRAD_BORDER_CYCLE_SEC) % 1.0


def _animated_grad_color(t_along: float, phase: float) -> tuple[int, int, int]:
    """외곽 위치 + 시간 위상 → 연속 그라데이션 색."""
    x = (max(0.0, min(1.0, t_along)) + phase) % 1.0
    stops = GRAD_BORDER_STOPS
    n = max(1, len(stops) - 1)
    pos = x * n
    i = int(pos) % n
    f = pos - int(pos)
    return _lerp_rgb(stops[i], stops[i + 1], f)


def _interp_closed_polyline(
    pts: list[tuple[int, int]], t: float
) -> tuple[int, int]:
    n = len(pts)
    if n == 0:
        return (0, 0)
    ft = (t % 1.0) * n
    i = int(ft) % n
    f = ft - int(ft)
    j = (i + 1) % n
    x0, y0 = pts[i]
    x1, y1 = pts[j]
    return (int(x0 + (x1 - x0) * f), int(y0 + (y1 - y0) * f))


def _draw_smooth_gradient_ring(
    layer: pygame.Surface,
    pts: list[tuple[int, int]],
    *,
    t_sec: float,
    phase: float,
    border_width: int,
    breathe: float,
) -> None:
    """짧은 보간 선분으로 끊김 없는 그라데이션 링."""
    n = len(pts)
    if n < 2:
        return
    steps = n * GRAD_RING_SUBDIV
    soft_w = border_width + 3
    for k in range(steps):
        t0 = k / steps
        t1 = (k + 1) / steps
        p0 = _interp_closed_polyline(pts, t0)
        p1 = _interp_closed_polyline(pts, t1)
        c = _animated_grad_color((t0 + t1) * 0.5, phase)
        pygame.draw.line(
            layer,
            (*c, int(75 * breathe)),
            p0,
            p1,
            width=soft_w,
        )
        hi = _lerp_rgb(c, (255, 255, 255), 0.06 * breathe)
        pygame.draw.line(layer, (*hi, 255), p0, p1, width=border_width)
        if border_width >= 3:
            pygame.draw.aaline(layer, c, p0, p1)


def _draw_active_border(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    anim_time_sec: float,
    border_width: int = GRAD_BORDER_WIDTH_ACTIVE,
    glow_strength: float = 1.0,
    ring_alpha_scale: float = 1.0,
) -> None:
    """애니메이션 그라데이션 보더 + 은은한 외곽 글로우."""
    t_sec = anim_time_sec
    breathe = 0.88 + 0.12 * math.sin(t_sec * 2.2)
    border_width = max(2, int(border_width * (0.96 + 0.04 * breathe)))
    phase = _border_anim_phase(t_sec)
    grad_mid = _animated_grad_color(0.35, phase)
    glow_k = max(0.0, min(1.0, float(glow_strength)))
    ring_k = max(0.0, min(1.0, float(ring_alpha_scale)))

    pad = GRAD_GLOW_SPREAD + 6
    layer = pygame.Surface(
        (rect.width + pad * 2, rect.height + pad * 2),
        pygame.SRCALPHA,
    )
    inner = pygame.Rect(pad, pad, rect.width, rect.height)
    rad = ACTIVE_BORDER_RADIUS

    for i in range(GRAD_GLOW_LAYERS, 0, -1):
        expand = i * 2
        glow = inner.inflate(expand * 2, expand * 2)
        alpha = int((5 + i * 10) * breathe * glow_k)
        if alpha < 1:
            continue
        pygame.draw.rect(
            layer,
            (*grad_mid, alpha),
            glow,
            width=2,
            border_radius=rad + expand // 2,
        )

    pts = _sample_round_rect_outline(inner, rad)
    if len(pts) >= 4:
        _draw_smooth_gradient_ring(
            layer,
            pts,
            t_sec=t_sec,
            phase=phase,
            border_width=border_width,
            breathe=breathe * ring_k,
        )

    surface.blit(layer, (rect.x - pad, rect.y - pad))


def _draw_red_active_border(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    anim_time_sec: float,
) -> None:
    """빨간 테두리만 (글로우·그라데이션 없음)."""
    _ = anim_time_sec
    pad = 4
    layer = pygame.Surface(
        (rect.width + pad * 2, rect.height + pad * 2),
        pygame.SRCALPHA,
    )
    inner = pygame.Rect(pad, pad, rect.width, rect.height)
    pygame.draw.rect(
        layer,
        RED_ACTIVE_BORDER_COLOR,
        inner,
        width=RED_ACTIVE_BORDER_WIDTH,
        border_radius=ACTIVE_BORDER_RADIUS,
    )
    surface.blit(layer, (rect.x - pad, rect.y - pad))


def _row_highlight_geometry(
    layout: WordMemorizeLayout,
    anchor: WordMemorizeBox,
    *,
    frame_width: int,
) -> tuple[int, int, int, int]:
    """y, h, x_min, x_max (FHD) for a row group."""
    boxes = boxes_in_row_group(layout, anchor)
    inset = ROW_BAND_V_INSET
    y = max(0, int(anchor.y) - inset)
    h = int(anchor.h) + inset * 2
    x_min = min((int(b.x) for b in boxes), default=0)
    x_max = max((int(b.x + b.w) for b in boxes), default=frame_width)
    return y, h, x_min, x_max


def _row_accent_color(anim_time_sec: float) -> tuple[int, int, int]:
    return _animated_grad_color(0.35, _border_anim_phase(anim_time_sec))


def _draw_bracket_stroke(
    layer: pygame.Surface,
    color: tuple[int, int, int],
    *,
    x: int,
    y0: int,
    y1: int,
    arm: int,
    thick: int,
    alpha: int,
    facing: str,
) -> None:
    rgba = (*color, max(0, min(255, alpha)))
    if facing == "left":
        pygame.draw.line(layer, rgba, (x, y0), (x, y1), thick)
        pygame.draw.line(layer, rgba, (x, y0), (x + arm, y0), thick)
        pygame.draw.line(layer, rgba, (x, y1), (x + arm, y1), thick)
    else:
        pygame.draw.line(layer, rgba, (x, y0), (x, y1), thick)
        pygame.draw.line(layer, rgba, (x, y0), (x - arm, y0), thick)
        pygame.draw.line(layer, rgba, (x, y1), (x - arm, y1), thick)


def _draw_row_neon_glow(
    surface: pygame.Surface,
    *,
    frame_width: int,
    row_y: int,
    row_h: int,
    anim_time_sec: float,
) -> None:
    band = pygame.Rect(0, row_y, frame_width, row_h)
    _draw_active_border(
        surface,
        band,
        anim_time_sec=anim_time_sec,
        border_width=ROW_BAND_BORDER_WIDTH,
        glow_strength=ROW_NEON_GLOW_STRENGTH,
        ring_alpha_scale=0.55,
    )


def _draw_row_brackets(
    surface: pygame.Surface,
    *,
    frame_width: int,
    row_y: int,
    row_h: int,
    anim_time_sec: float,
    both_ends: bool,
    x_min: int,
) -> None:
    color = _row_accent_color(anim_time_sec)
    y0, y1 = row_y, row_y + row_h
    arm = max(16, min(ROW_BRACKET_ARM, row_h // 3))
    thick = ROW_BRACKET_THICK_BOTH if both_ends else ROW_BRACKET_THICK
    layer = pygame.Surface((frame_width, row_h), pygame.SRCALPHA)
    if both_ends:
        lx = ROW_BRACKET_MARGIN_X
        rx = frame_width - ROW_BRACKET_MARGIN_X
        _draw_bracket_stroke(
            layer,
            color,
            x=lx,
            y0=0,
            y1=row_h,
            arm=arm,
            thick=thick,
            alpha=248,
            facing="left",
        )
        _draw_bracket_stroke(
            layer,
            color,
            x=rx,
            y0=0,
            y1=row_h,
            arm=arm,
            thick=thick,
            alpha=248,
            facing="right",
        )
    else:
        ox = max(12, x_min - arm - 8)
        _draw_bracket_stroke(
            layer,
            color,
            x=ox,
            y0=0,
            y1=row_h,
            arm=arm,
            thick=thick,
            alpha=248,
            facing="left",
        )
    surface.blit(layer, (0, row_y))


def _draw_row_left_bar(
    surface: pygame.Surface,
    *,
    row_y: int,
    row_h: int,
    anim_time_sec: float,
) -> None:
    color = _row_accent_color(anim_time_sec)
    layer = pygame.Surface((ROW_LEFT_BAR_WIDTH + 4, row_h), pygame.SRCALPHA)
    pygame.draw.rect(
        layer,
        (*color, 235),
        pygame.Rect(0, 0, ROW_LEFT_BAR_WIDTH, row_h),
        border_radius=4,
    )
    surface.blit(layer, (0, row_y))


def draw_row_highlight(
    surface: pygame.Surface,
    row_type: RowHighlightType | str,
    layout: WordMemorizeLayout,
    anchor: WordMemorizeBox,
    *,
    anim_time_sec: float,
) -> None:
    """가로줄(y·h 동일) 강조 — 카드 하이라이트와 별도."""
    kind = normalize_row_highlight(row_type)
    if kind == "none":
        return
    fw = int(layout.frame_width)
    row_y, row_h, x_min, _x_max = _row_highlight_geometry(
        layout, anchor, frame_width=fw
    )
    if kind == "neon_glow":
        _draw_row_neon_glow(
            surface,
            frame_width=fw,
            row_y=row_y,
            row_h=row_h,
            anim_time_sec=anim_time_sec,
        )
    elif kind == "brackets":
        _draw_row_brackets(
            surface,
            frame_width=fw,
            row_y=row_y,
            row_h=row_h,
            anim_time_sec=anim_time_sec,
            both_ends=True,
            x_min=x_min,
        )
    elif kind == "bracket_one":
        _draw_row_brackets(
            surface,
            frame_width=fw,
            row_y=row_y,
            row_h=row_h,
            anim_time_sec=anim_time_sec,
            both_ends=False,
            x_min=x_min,
        )
    elif kind == "left_bar":
        _draw_row_left_bar(
            surface, row_y=row_y, row_h=row_h, anim_time_sec=anim_time_sec
        )


def _draw_active_highlight(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    highlight_type: str,
    anim_time_sec: float,
    word_elapsed_sec: float = 0.0,
    word_duration_sec: float = 0.0,
) -> None:
    kind = normalize_selection_highlight(highlight_type)
    if kind == "laser":
        return
    if kind == "red_border":
        _draw_red_active_border(surface, rect, anim_time_sec=anim_time_sec)
    else:
        _draw_active_border(surface, rect, anim_time_sec=anim_time_sec)


def load_en_meaning_by_id(csv_path: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    if not csv_path.is_file():
        return out
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                wid = int(float(row.get("id", 0)))
            except (TypeError, ValueError):
                continue
            out[wid] = (row.get("en_meaning") or "").strip()
    return out


def load_ko_meaning_by_id(csv_path: Path) -> dict[int, str]:
    """words.csv meaning 첫 항목(| 구분) — 카드 뜻 표시용."""
    out: dict[int, str] = {}
    if not csv_path.is_file():
        return out
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                wid = int(float(row.get("id", 0)))
            except (TypeError, ValueError):
                continue
            raw = (row.get("meaning") or "").strip()
            if raw:
                out[wid] = raw.split("|")[0].strip()
    return out


def display_pinyin(word: Word) -> str:
    hanzi = (word.word or "").strip()
    raw = (word.pinyin or "").strip()
    masking = (word.masking or "").strip()
    if raw and hanzi:
        marks = word_pinyin_to_marks_spaced(hanzi, raw).strip()
        if marks:
            return marks
        return raw
    if hanzi:
        marks = get_masked_pinyin_marks(hanzi, normalize_word_masking(masking)).strip()
        if marks:
            return marks
    return raw


def _resolve_image_path(repo_root: Path, word: Word) -> Path | None:
    from extra.table_editor.services.image_paths import preview_image_path

    raw = (word.img_path or "").strip()
    if not raw or raw.lower() == "none":
        return None
    return preview_image_path(
        repo_root,
        raw,
        word_id=str(word.id),
        word=word.word or "",
    )


def _load_scaled_image(path: Path, max_w: int, max_h: int) -> pygame.Surface | None:
    if max_w < 4 or max_h < 4:
        return None
    try:
        surf = pygame.image.load(str(path))
        if surf.get_alpha() is None:
            surf = surf.convert()
        else:
            surf = surf.convert_alpha()
        w, h = surf.get_size()
        if w <= 0 or h <= 0:
            return None
        scale = min(max_w / w, max_h / h, 1.0)
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
        if nw != w or nh != h:
            surf = pygame.transform.smoothscale(surf, (nw, nh))
        return surf
    except Exception:
        return None


def _blit_contained_background(
    surface: pygame.Surface, bg: pygame.Surface, fw: int, fh: int
) -> None:
    ix = (fw - bg.get_width()) // 2
    iy = (fh - bg.get_height()) // 2
    surface.blit(bg, (ix, iy))


class LoopingBackgroundVideo:
    """resource/BG 동명 MP4 — 끝나면 처음부터 반복."""

    def __init__(self) -> None:
        from studio.conversation.video_players import SimpleVideoPlayer

        self._player = SimpleVideoPlayer()

    def set_path(self, path: Path | None) -> None:
        if path is not None and path.is_file():
            self._player.set_source(str(path.resolve()), 0.0, -1.0)
        else:
            self._player.close()

    def tick(self, dt_sec: float) -> None:
        if not self._player.has_source():
            return
        if self._player.is_paused():
            end = self._player.get_effective_end_sec()
            if self._player.get_pts() >= end - 1e-3:
                self._player.seek_to(0.0)
                return
        self._player.tick(dt_sec)
        if self._player.is_paused():
            self._player.seek_to(0.0)

    def get_frame(self, fw: int, fh: int) -> pygame.Surface | None:
        if not self._player.has_source():
            return None
        return self._player.get_frame(fw, fh, contain=True)


class WordMemorizeRenderer:
    def __init__(
        self, repo_root: Path | None = None, *, show_images: bool = True
    ) -> None:
        self._repo = (repo_root or get_repo_root()).resolve()
        self._show_images = bool(show_images)
        self._fonts_ready = False
        self._font_pinyin: pygame.font.Font | None = None
        self._font_hanzi: pygame.font.Font | None = None
        self._font_en: pygame.font.Font | None = None
        self._base_font_cache: dict[tuple[str, int], pygame.font.Font | None] = {}
        self._font_title_by_key: dict[tuple[str, int], pygame.font.Font | None] = {}
        self._image_cache: dict[tuple[int, int, int], pygame.Surface | None] = {}
        self._bg_video = LoopingBackgroundVideo()
        self._bg_layout_stem = ""
        self._bg_meaning_lang = "ko"

    def set_background(self, layout_stem: str, meaning_lang: str = "ko") -> None:
        self._bg_layout_stem = (layout_stem or "").strip()
        new_lang = (meaning_lang or "ko").strip().lower()
        if new_lang != self._bg_meaning_lang:
            self._invalidate_fonts()
        self._bg_meaning_lang = new_lang
        video = resolve_word_memorize_bg_video_path(
            self._bg_layout_stem, meaning_lang=self._bg_meaning_lang
        )
        self._bg_video.set_path(video if video.is_file() else None)

    def _invalidate_fonts(self) -> None:
        self._fonts_ready = False
        self._font_pinyin = None
        self._font_hanzi = None
        self._font_en = None
        self._base_font_cache.clear()

    def _zh_card_font_pts(self) -> tuple[int, int, str]:
        """중국어 모드: 한자 20% 축소, 한국어 뜻 20% 확대·굵게."""
        hanzi_pt = HANZI_FONT_PT
        meaning_pt = EN_FONT_PT
        meaning_weight = "regular"
        if _is_zh_meaning_lang(self._bg_meaning_lang):
            hanzi_pt = max(1, int(round(HANZI_FONT_PT * ZH_HANZI_SCALE)))
            meaning_pt = max(1, int(round(EN_FONT_PT * ZH_MEANING_SCALE)))
            meaning_weight = "bold"
        return hanzi_pt, meaning_pt, meaning_weight

    def tick_background_video(self, dt_sec: float) -> None:
        self._bg_video.tick(dt_sec)

    def ensure_fonts(self) -> None:
        if self._fonts_ready:
            return
        from utils.fonts import load_font_korean, load_font_noto_sans_cjk_sc

        hanzi_pt, meaning_pt, meaning_weight = self._zh_card_font_pts()
        # 병음·한자: Noto Sans CJK SC (간체 고딕, 성조·한자 균형)
        self._font_pinyin = load_font_noto_sans_cjk_sc(PINYIN_FONT_PT, PINYIN_COLOR)
        self._font_hanzi = load_font_noto_sans_cjk_sc(
            hanzi_pt, HANZI_COLOR, weight="bold"
        )
        self._font_en = load_font_korean(
            meaning_pt, EN_COLOR, weight=meaning_weight
        )
        self._fonts_ready = True

    def _title_font(self, layout: WordMemorizeLayout, *, font_key: str, font_pt: int) -> pygame.font.Font | None:
        self.ensure_fonts()
        key = normalize_title_font(font_key)
        pt = normalize_title_font_pt(font_pt)
        cache_key = (key, pt)
        if cache_key in self._font_title_by_key:
            return self._font_title_by_key[cache_key]
        from utils.fonts import (
            load_font_korean,
            load_font_kr_chinese,
            load_font_noto_sans_cjk_sc,
        )

        if key == "noto_sc":
            font = load_font_noto_sans_cjk_sc(pt, TITLE_COLOR, weight="bold")
        elif key == "korean":
            font = load_font_korean(pt, TITLE_COLOR, weight="bold")
        else:
            font = load_font_kr_chinese(pt, TITLE_COLOR, weight="bold")
        self._font_title_by_key[cache_key] = font
        return font

    def draw(
        self,
        surface: pygame.Surface,
        layout: WordMemorizeLayout,
        words_by_id: dict[int, Word],
        card_meaning_by_id: dict[int, str],
        *,
        active_box_key: str | None = None,
        dim_inactive: bool = False,
        anim_time_sec: float | None = None,
        config: Any | None = None,
        use_video_background: bool = False,
        active_word_elapsed_sec: float = 0.0,
        active_word_duration_sec: float = 0.0,
    ) -> None:
        self.ensure_fonts()
        t_anim = (
            anim_time_sec
            if anim_time_sec is not None
            else border_anim_time_sec(config)
        )
        fw, fh = layout.frame_width, layout.frame_height
        self._draw_background(
            surface, layout, fw, fh, use_video=use_video_background
        )
        self._draw_title(surface, layout, fw, fh)

        active_anchor = find_box_by_runtime_key(layout, active_box_key or "")
        active_is_base = (
            active_anchor is not None
            and is_base_slot_box(active_anchor, layout)
        )
        card_highlight = normalize_selection_highlight(
            getattr(layout, "selection_highlight", "gradient")
        )
        row_highlight_type = normalize_row_highlight(
            getattr(layout, "row_highlight", "none")
        )

        entries: list[tuple[WordMemorizeBox, Word, str, str]] = []
        for box in layout.sorted_boxes():
            try:
                wid = int(box.word_id)
            except (TypeError, ValueError):
                continue
            word = words_by_id.get(wid)
            if word is None:
                continue
            entries.append((box, word, card_meaning_by_id.get(wid, ""), box_runtime_key(box)))

        inactive: list[tuple[WordMemorizeBox, Word, str]] = []
        active_cards: list[tuple[WordMemorizeBox, Word, str]] = []

        for box, word, card_meaning, runtime_key in entries:
            if active_box_key and runtime_key == active_box_key:
                active_cards.append((box, word, card_meaning))
            else:
                inactive.append((box, word, card_meaning))

        word_timing = (active_word_elapsed_sec, active_word_duration_sec)

        for box, word, card_meaning in inactive:
            self._draw_box(
                surface,
                box,
                word,
                card_meaning,
                layout=layout,
                active=False,
                anim_time_sec=t_anim,
                word_elapsed_sec=0.0,
                word_duration_sec=0.0,
            )

        if (
            row_highlight_type != "none"
            and active_anchor is not None
            and not active_is_base
        ):
            draw_row_highlight(
                surface,
                row_highlight_type,
                layout,
                active_anchor,
                anim_time_sec=t_anim,
            )

        if (
            card_highlight == "laser"
            and active_anchor is not None
            and active_cards
            and not active_is_base
        ):
            draw_laser_center_to_card(
                surface,
                frame_width=fw,
                frame_height=fh,
                card_rect=pygame.Rect(
                    active_anchor.x,
                    active_anchor.y,
                    active_anchor.w,
                    active_anchor.h,
                ),
                elapsed_sec=word_timing[0],
                duration_sec=word_timing[1],
                loop_preview=word_timing[1] <= 0,
            )

        for box, word, card_meaning in active_cards:
            self._draw_box(
                surface,
                box,
                word,
                card_meaning,
                layout=layout,
                active=True,
                anim_time_sec=t_anim,
                word_elapsed_sec=word_timing[0],
                word_duration_sec=word_timing[1],
            )

    def _draw_background(
        self,
        surface: pygame.Surface,
        layout: WordMemorizeLayout,
        fw: int,
        fh: int,
        *,
        use_video: bool = False,
    ) -> None:
        if use_video:
            frame = self._bg_video.get_frame(fw, fh)
            if frame is not None:
                _blit_contained_background(surface, frame, fw, fh)
                return
        img_path = resolve_word_memorize_bg_image_path(
            layout.background_value or self._bg_layout_stem,
            meaning_lang=self._bg_meaning_lang,
        )
        bg = _load_scaled_image(img_path, fw, fh) if img_path.is_file() else None
        if bg is not None:
            _blit_contained_background(surface, bg, fw, fh)
            return
        surface.fill((0, 0, 0))

    def _draw_title(
        self,
        surface: pygame.Surface,
        layout: WordMemorizeLayout,
        fw: int,
        fh: int,
    ) -> None:
        specs = layout_title_line_specs(layout)
        if not specs:
            return
        cx, cy = resolve_title_position(
            frame_width=fw,
            frame_height=fh,
            margin_top_ratio=layout.margin_top_ratio,
            y_offset_px=getattr(layout, "title_y_offset_px", 0),
            title_x=int(getattr(layout, "title_x", 0)),
            title_y=int(getattr(layout, "title_y", 0)),
        )
        gap = TITLE_LINE_GAP
        rendered: list[tuple[pygame.Surface, pygame.Surface, int]] = []
        for spec in specs[:8]:
            font_title = self._title_font(
                layout, font_key=spec.font, font_pt=spec.font_pt
            )
            if font_title is None:
                continue
            text = (spec.text or "").strip()[:60]
            if not text:
                continue
            color = title_color_to_rgb(spec.color)
            shadow = font_title.render(text, True, TITLE_SHADOW_COLOR)
            main = font_title.render(text, True, color)
            rendered.append((shadow, main, main.get_height()))
        if not rendered:
            return
        total_h = sum(h for _, _, h in rendered) + gap * (len(rendered) - 1)
        y = cy - total_h // 2
        for shadow, main, h in rendered:
            rect = main.get_rect(midtop=(cx, y))
            surface.blit(shadow, rect.move(2, 2))
            surface.blit(main, rect)
            y += h + gap

    def _base_slot_font(
        self, role: str, pt: int, *, weight: str = "regular"
    ) -> pygame.font.Font | None:
        key = (role, pt, weight)
        if key in self._base_font_cache:
            return self._base_font_cache[key]
        from utils.fonts import load_font_korean, load_font_noto_sans_cjk_sc

        self.ensure_fonts()
        if role == "meaning":
            meaning_weight = (
                "bold" if _is_zh_meaning_lang(self._bg_meaning_lang) else "regular"
            )
            font = load_font_korean(
                pt, BASE_SLOT_MEANING_COLOR, weight=meaning_weight
            )
        elif role == "hanzi":
            font = load_font_noto_sans_cjk_sc(
                pt,
                BASE_SLOT_HANZI_COLOR,
                weight="bold" if weight == "bold" else "regular",
            )
        else:
            font = load_font_noto_sans_cjk_sc(pt, BASE_SLOT_PINYIN_COLOR)
        self._base_font_cache[key] = font
        return font

    def _base_slot_font_pts(self, inner_h: int) -> tuple[int, int, int]:
        scale = max(1.12, min(1.5, inner_h / 120.0))
        pt_p = max(36, int(BASE_SLOT_PINYIN_PT_FHD * scale))
        pt_h = max(80, int(BASE_SLOT_HANZI_PT_FHD * scale))
        pt_m = max(32, int(BASE_SLOT_MEANING_PT_FHD * scale))
        if _is_zh_meaning_lang(self._bg_meaning_lang):
            pt_h = max(1, int(round(pt_h * ZH_HANZI_SCALE)))
            pt_m = max(1, int(round(pt_m * ZH_MEANING_SCALE)))
        return pt_p, pt_h, pt_m

    def _base_slot_scale(self, inner_h: int) -> float:
        return max(1.12, min(1.5, inner_h / 120.0))

    def _render_base_pinyin_badge(
        self, font: pygame.font.Font, text: str, *, inner_h: int
    ) -> pygame.Surface:
        """병음 — 주황 배경 + 흰 글자."""
        text_surf = font.render(text, True, BASE_SLOT_PINYIN_COLOR)
        scale = self._base_slot_scale(inner_h)
        pad_x = max(8, int(BASE_SLOT_PINYIN_BG_PAD_X_FHD * scale))
        pad_y = max(2, int(BASE_SLOT_PINYIN_BG_PAD_Y_FHD * scale))
        radius = max(4, int(BASE_SLOT_PINYIN_BG_RADIUS_FHD * scale))
        badge = pygame.Surface(
            (text_surf.get_width() + pad_x * 2, text_surf.get_height() + pad_y * 2),
            pygame.SRCALPHA,
        )
        pygame.draw.rect(
            badge,
            (*BASE_SLOT_PINYIN_BG_COLOR, 255),
            badge.get_rect(),
            border_radius=radius,
        )
        badge.blit(text_surf, (pad_x, pad_y))
        return badge

    def _render_base_meaning_badge(
        self, font: pygame.font.Font, text: str, *, inner_h: int
    ) -> pygame.Surface:
        """뜻 — 초록 배경 + 흰 글자 (병음 배지와 동일 방식)."""
        text_surf = font.render(text, True, BASE_SLOT_MEANING_COLOR)
        scale = self._base_slot_scale(inner_h)
        pad_x = max(8, int(BASE_SLOT_MEANING_PAD_X_FHD * scale))
        pad_y = max(2, int(BASE_SLOT_MEANING_PAD_Y_FHD * scale))
        radius = max(4, int(BASE_SLOT_MEANING_BG_RADIUS_FHD * scale))
        badge = pygame.Surface(
            (text_surf.get_width() + pad_x * 2, text_surf.get_height() + pad_y * 2),
            pygame.SRCALPHA,
        )
        pygame.draw.rect(
            badge,
            (*BASE_SLOT_MEANING_BG_COLOR, 255),
            badge.get_rect(),
            border_radius=radius,
        )
        badge.blit(text_surf, (pad_x, pad_y))
        return badge

    def _paint_base_slot_box(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        word: Word,
        card_meaning: str,
    ) -> None:
        """#1 슬롯 — 배경·테두리·이미지 없이 병음·한자·뜻만 크게."""
        pad = 8
        inner = rect.inflate(-pad * 2, -pad * 2)
        cx = inner.centerx
        pt_p, pt_h, pt_m = self._base_slot_font_pts(inner.height)
        font_p = self._base_slot_font("pinyin", pt_p)
        font_h = self._base_slot_font("hanzi", pt_h, weight="bold")
        font_m = self._base_slot_font("meaning", pt_m)

        line_heights: list[int] = []
        line_surfs: list[pygame.Surface] = []

        pinyin = display_pinyin(word)
        if pinyin and font_p is not None:
            surf = self._render_base_pinyin_badge(
                font_p, pinyin[:48], inner_h=inner.height
            )
            line_heights.append(surf.get_height())
            line_surfs.append(surf)

        hanzi = (word.word or "").strip()
        if hanzi and font_h is not None:
            surf = font_h.render(hanzi, True, BASE_SLOT_HANZI_COLOR)
            line_heights.append(surf.get_height())
            line_surfs.append(surf)

        meaning = (card_meaning or "").strip()
        if meaning and font_m is not None:
            surf = self._render_base_meaning_badge(
                font_m, meaning[:40], inner_h=inner.height
            )
            line_heights.append(surf.get_height())
            line_surfs.append(surf)

        gap = max(
            0.0,
            BASE_SLOT_LINE_GAP_FHD * inner.height / CARD_CONTENT_REFERENCE_INNER_H,
        )
        _start, line_ys, _image_y = layout_card_content_vertical(
            inner.height,
            line_heights,
            0,
            default_gap=gap,
            bottom_pad=0,
        )
        for surf, y_off in zip(line_surfs, line_ys):
            self._blit_centered(surface, surf, cx, inner.top + y_off)

    def _draw_base_slot_active_border(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        highlight_type: str,
        anim_time_sec: float,
        word_elapsed_sec: float,
        word_duration_sec: float,
    ) -> None:
        """Base 슬롯 재생 중 — 레이저 빔 없이 테두리만 (레이저 모드는 네온 충격 테두리)."""
        kind = normalize_selection_highlight(highlight_type)
        if kind == "laser":
            loop_preview = word_duration_sec <= 0
            impact_t = laser_impact_elapsed_sec(
                word_elapsed_sec, loop_preview=loop_preview
            )
            draw_laser_impact_border(
                surface,
                rect,
                impact_elapsed_sec=impact_t,
                border_radius=ACTIVE_BORDER_RADIUS,
            )
            return
        _draw_active_highlight(
            surface,
            rect,
            highlight_type=highlight_type,
            anim_time_sec=anim_time_sec,
        )

    def _draw_box(
        self,
        surface: pygame.Surface,
        box: WordMemorizeBox,
        word: Word,
        card_meaning: str,
        *,
        layout: WordMemorizeLayout,
        active: bool,
        anim_time_sec: float,
        word_elapsed_sec: float = 0.0,
        word_duration_sec: float = 0.0,
    ) -> None:
        highlight_type = normalize_selection_highlight(
            getattr(layout, "selection_highlight", "gradient")
        )
        is_laser = highlight_type == "laser"
        base = pygame.Rect(box.x, box.y, box.w, box.h)
        if is_base_slot_box(box, layout):
            self._paint_base_slot_box(surface, base, word, card_meaning)
            if active:
                self._draw_base_slot_active_border(
                    surface,
                    base,
                    highlight_type=highlight_type,
                    anim_time_sec=anim_time_sec,
                    word_elapsed_sec=word_elapsed_sec,
                    word_duration_sec=word_duration_sec,
                )
            return

        if not active:
            self._paint_box(
                surface,
                base,
                word,
                card_meaning,
                highlight_type=highlight_type,
                active=False,
                anim_time_sec=anim_time_sec,
                use_card_background=layout_use_card_background(layout),
            )
            return

        use_card_bg = layout_use_card_background(layout)
        if is_laser:
            self._paint_box(
                surface,
                base,
                word,
                card_meaning,
                highlight_type=highlight_type,
                active=True,
                draw_border=False,
                anim_time_sec=anim_time_sec,
                use_card_background=use_card_bg,
            )
            loop_preview = word_duration_sec <= 0
            impact_t = laser_impact_elapsed_sec(
                word_elapsed_sec, loop_preview=loop_preview
            )
            draw_laser_impact_border(
                surface,
                base,
                impact_elapsed_sec=impact_t,
                border_radius=ACTIVE_BORDER_RADIUS,
            )
            return

        layer = pygame.Surface((base.width, base.height), pygame.SRCALPHA)
        layer.fill((0, 0, 0, 0))
        local = pygame.Rect(0, 0, base.width, base.height)
        self._paint_box(
            layer,
            local,
            word,
            card_meaning,
            highlight_type=highlight_type,
            active=True,
            draw_border=False,
            anim_time_sec=anim_time_sec,
            use_card_background=use_card_bg,
        )
        sw = max(1, int(base.width * ACTIVE_CARD_SCALE))
        sh = max(1, int(base.height * ACTIVE_CARD_SCALE))
        scaled = pygame.transform.smoothscale(layer, (sw, sh))
        dest = scaled.get_rect(center=base.center)
        surface.blit(scaled, dest)
        _draw_active_highlight(
            surface,
            dest,
            highlight_type=highlight_type,
            anim_time_sec=anim_time_sec,
            word_elapsed_sec=word_elapsed_sec,
            word_duration_sec=word_duration_sec,
        )

    def _paint_box(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        word: Word,
        card_meaning: str,
        *,
        highlight_type: str,
        active: bool,
        anim_time_sec: float,
        draw_border: bool = True,
        use_card_background: bool = True,
    ) -> None:
        if use_card_background:
            pygame.draw.rect(surface, BOX_FILL, rect, border_radius=ACTIVE_BORDER_RADIUS)
            if active and draw_border and highlight_type != "laser":
                _draw_active_highlight(
                    surface,
                    rect,
                    highlight_type=highlight_type,
                    anim_time_sec=anim_time_sec,
                )
            elif not active:
                pygame.draw.rect(
                    surface,
                    BOX_OUTLINE,
                    rect,
                    width=1,
                    border_radius=ACTIVE_BORDER_RADIUS,
                )

        pad = 10
        inner = rect.inflate(-pad * 2, -pad * 2)
        cx = inner.centerx

        img_path = _resolve_image_path(self._repo, word) if self._show_images else None
        img_surf: pygame.Surface | None = None
        img_h = 0
        if img_path is not None:
            img_slot_h = max(32, int(inner.height * IMG_MAX_HEIGHT_RATIO))
            img_surf = self._get_word_image(
                word.id, img_path, inner.width, img_slot_h
            )
            if img_surf is not None:
                img_h = img_surf.get_height()

        line_heights: list[int] = []
        line_surfs: list[pygame.Surface] = []

        pinyin = display_pinyin(word)
        if pinyin and self._font_pinyin is not None:
            surf = self._font_pinyin.render(pinyin[:48], True, PINYIN_COLOR)
            line_heights.append(surf.get_height())
            line_surfs.append(surf)

        hanzi = (word.word or "").strip()
        if hanzi and self._font_hanzi is not None:
            surf = self._font_hanzi.render(hanzi, True, HANZI_COLOR)
            line_heights.append(surf.get_height())
            line_surfs.append(surf)

        en = (card_meaning or "").strip()
        if en and self._font_en is not None:
            surf = self._font_en.render(en[:40], True, EN_COLOR)
            line_heights.append(surf.get_height())
            line_surfs.append(surf)

        _start, line_ys, image_y = layout_card_content_vertical(
            inner.height,
            line_heights,
            img_h,
            default_gap=default_card_item_gap(inner.height),
            bottom_pad=CARD_IMG_BOTTOM_PAD_FHD if img_h else 0,
        )

        for surf, y_off in zip(line_surfs, line_ys):
            self._blit_centered(surface, surf, cx, inner.top + y_off)

        if img_surf is not None and img_h > 0 and image_y is not None:
            ix = cx - img_surf.get_width() // 2
            surface.blit(img_surf, (ix, inner.top + image_y))

    def _blit_centered(
        self,
        surface: pygame.Surface,
        img: pygame.Surface,
        cx: int,
        y: int,
    ) -> int:
        x = cx - img.get_width() // 2
        surface.blit(img, (x, y))
        return img.get_height()

    def _get_word_image(
        self,
        word_id: int,
        path: Path,
        max_w: int,
        max_h: int,
    ) -> pygame.Surface | None:
        key = (word_id, max_w, max_h)
        if key not in self._image_cache:
            self._image_cache[key] = _load_scaled_image(path, max_w, max_h)
        return self._image_cache[key]
