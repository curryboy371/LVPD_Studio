"""단어 외우기 배치 — FHD 프레임 그리기."""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import pygame

from core.paths import get_repo_root
from data.models import Word
from extra.table_editor.services.word_memorize_layout import WordMemorizeBox, WordMemorizeLayout
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
GRAD_BORDER_CYCLE_SEC = 1.1
GRAD_BORDER_WIDTH = 3
GRAD_BORDER_WIDTH_ACTIVE = 4
GRAD_GLOW_LAYERS = 5
GRAD_GLOW_SPREAD = 10
GRAD_RING_SAMPLES_PER_EDGE = 32
GRAD_RING_ARC_STEPS = 12
GRAD_RING_SUBDIV = 5
ACTIVE_CARD_SCALE = 1.06
TEXT_LINE_GAP = 4
IMG_BOTTOM_PAD = 8
IMG_LIFT = 12
PINYIN_FONT_PT = 32
HANZI_FONT_PT = 72
EN_FONT_PT = 30
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
) -> None:
    """애니메이션 그라데이션 보더 + 은은한 외곽 글로우."""
    t_sec = anim_time_sec
    breathe = 0.88 + 0.12 * math.sin(t_sec * 2.2)
    border_width = max(2, int(border_width * (0.96 + 0.04 * breathe)))
    phase = _border_anim_phase(t_sec)
    grad_mid = _animated_grad_color(0.35, phase)

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
        alpha = int((5 + i * 10) * breathe)
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
            breathe=breathe,
        )

    surface.blit(layer, (rect.x - pad, rect.y - pad))


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


class WordMemorizeRenderer:
    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo = (repo_root or get_repo_root()).resolve()
        self._fonts_ready = False
        self._font_pinyin: pygame.font.Font | None = None
        self._font_hanzi: pygame.font.Font | None = None
        self._font_en: pygame.font.Font | None = None
        self._image_cache: dict[tuple[int, int, int], pygame.Surface | None] = {}

    def ensure_fonts(self) -> None:
        if self._fonts_ready:
            return
        from utils.fonts import load_font_korean, load_font_noto_sans_cjk_sc

        # 병음·한자: Noto Sans CJK SC (간체 고딕, 성조·한자 균형)
        self._font_pinyin = load_font_noto_sans_cjk_sc(PINYIN_FONT_PT, PINYIN_COLOR)
        self._font_hanzi = load_font_noto_sans_cjk_sc(
            HANZI_FONT_PT, HANZI_COLOR, weight="bold"
        )
        self._font_en = load_font_korean(EN_FONT_PT, EN_COLOR)
        self._fonts_ready = True

    def draw(
        self,
        surface: pygame.Surface,
        layout: WordMemorizeLayout,
        words_by_id: dict[int, Word],
        en_by_id: dict[int, str],
        *,
        active_box_key: str | None = None,
        dim_inactive: bool = False,
        anim_time_sec: float | None = None,
        config: Any | None = None,
    ) -> None:
        self.ensure_fonts()
        t_anim = (
            anim_time_sec
            if anim_time_sec is not None
            else border_anim_time_sec(config)
        )
        fw, fh = layout.frame_width, layout.frame_height
        self._draw_background(surface, layout, fw, fh)

        entries: list[tuple[WordMemorizeBox, Word, str, bool]] = []
        for box in layout.sorted_boxes():
            try:
                wid = int(box.word_id)
            except (TypeError, ValueError):
                continue
            word = words_by_id.get(wid)
            if word is None:
                continue
            active = bool(active_box_key and box.box_key == active_box_key)
            entries.append((box, word, en_by_id.get(wid, ""), active))

        for box, word, en_meaning, active in entries:
            if not active:
                self._draw_box(
                    surface, box, word, en_meaning, active=False, anim_time_sec=t_anim
                )
        for box, word, en_meaning, _active in entries:
            if _active:
                self._draw_box(
                    surface, box, word, en_meaning, active=True, anim_time_sec=t_anim
                )

    def _draw_background(
        self,
        surface: pygame.Surface,
        layout: WordMemorizeLayout,
        fw: int,
        fh: int,
    ) -> None:
        if layout.background_type == "image":
            path = Path(layout.background_value)
            if not path.is_absolute():
                path = self._repo / path.as_posix().replace("\\", "/")
            bg = _load_scaled_image(path, fw, fh) if path.is_file() else None
            if bg is not None:
                ix = (fw - bg.get_width()) // 2
                iy = (fh - bg.get_height()) // 2
                surface.blit(bg, (ix, iy))
                return
        color = self._parse_color(layout.background_value or "#ffffff")
        surface.fill(color)

    def _parse_color(self, raw: str) -> tuple[int, int, int]:
        s = (raw or "").strip()
        if s.startswith("#") and len(s) >= 7:
            try:
                return (
                    int(s[1:3], 16),
                    int(s[3:5], 16),
                    int(s[5:7], 16),
                )
            except ValueError:
                pass
        return (255, 255, 255)

    def _draw_box(
        self,
        surface: pygame.Surface,
        box: WordMemorizeBox,
        word: Word,
        en_meaning: str,
        *,
        active: bool,
        anim_time_sec: float,
    ) -> None:
        base = pygame.Rect(box.x, box.y, box.w, box.h)
        if not active:
            self._paint_box(
                surface, base, word, en_meaning, active=False, anim_time_sec=anim_time_sec
            )
            return

        layer = pygame.Surface((base.width, base.height), pygame.SRCALPHA)
        layer.fill((0, 0, 0, 0))
        local = pygame.Rect(0, 0, base.width, base.height)
        self._paint_box(
            layer,
            local,
            word,
            en_meaning,
            active=True,
            draw_border=False,
            anim_time_sec=anim_time_sec,
        )
        sw = max(1, int(base.width * ACTIVE_CARD_SCALE))
        sh = max(1, int(base.height * ACTIVE_CARD_SCALE))
        scaled = pygame.transform.smoothscale(layer, (sw, sh))
        dest = scaled.get_rect(center=base.center)
        surface.blit(scaled, dest)
        _draw_active_border(surface, dest, anim_time_sec=anim_time_sec)

    def _paint_box(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        word: Word,
        en_meaning: str,
        *,
        active: bool,
        anim_time_sec: float,
        draw_border: bool = True,
    ) -> None:
        pygame.draw.rect(surface, BOX_FILL, rect, border_radius=ACTIVE_BORDER_RADIUS)
        if active and draw_border:
            _draw_active_border(surface, rect, anim_time_sec=anim_time_sec)
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

        img_path = _resolve_image_path(self._repo, word)
        img_surf: pygame.Surface | None = None
        img_h = 0
        if img_path is not None:
            img_slot_h = max(32, int(inner.height * IMG_MAX_HEIGHT_RATIO))
            img_surf = self._get_word_image(
                word.id, img_path, inner.width, img_slot_h
            )
            if img_surf is not None:
                img_h = img_surf.get_height()

        img_reserve = (img_h + IMG_BOTTOM_PAD + IMG_LIFT) if img_h else 0
        text_bottom = inner.bottom - img_reserve
        y = inner.top

        pinyin = display_pinyin(word)
        if pinyin and self._font_pinyin is not None and y < text_bottom:
            surf = self._font_pinyin.render(pinyin[:48], True, PINYIN_COLOR)
            y += self._blit_centered(surface, surf, cx, y) + TEXT_LINE_GAP

        hanzi = (word.word or "").strip()
        if hanzi and self._font_hanzi is not None and y < text_bottom:
            surf = self._font_hanzi.render(hanzi, True, HANZI_COLOR)
            y += self._blit_centered(surface, surf, cx, y) + TEXT_LINE_GAP

        en = (en_meaning or "").strip()
        if en and self._font_en is not None and y < text_bottom:
            surf = self._font_en.render(en[:40], True, EN_COLOR)
            y += self._blit_centered(surface, surf, cx, y) + TEXT_LINE_GAP

        if img_surf is not None and img_h > 0:
            ix = cx - img_surf.get_width() // 2
            iy = inner.bottom - img_h - IMG_LIFT
            surface.blit(img_surf, (ix, iy))

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
