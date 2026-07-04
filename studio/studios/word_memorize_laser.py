"""단어 외우기 — 레이저 카드 하이라이트 (icon/laser_b|g|p|y.png 가로 빔).

리소스는 가로로 누운 형태(왼쪽=꼬리, 오른쪽=머리). 프레임 중앙(꼬리)에서
카드 중심(머리) 방향으로 거리만큼 가로 스케일 후 atan2 각도로 회전한다.
"""
from __future__ import annotations

import math
import random

import pygame

from extra.table_editor.services.word_memorize_layout import (
    DEFAULT_LASER_VARIANT,
    laser_border_color,
    normalize_laser_variant,
    word_memorize_laser_beam_path,
)

# 단어 읽기(TTS) 길이와 무관 — 이 구간에 카드까지 도달(이후 hold 펄스)
# 0.28s는 30fps 기준 ~8프레임이라 거의 정지처럼 보였음
LASER_SHOOT_SEC = 0.55
PHASE_CHARGE_END = 0.06
PHASE_PROPAGATE_END = 0.78
HOLD_BEAM_PULSE_HZ = 5.5
HOLD_BEAM_LENGTH_WOBBLE = 0.018
# 전파 82% 지점 — 빔이 카드에 닿는 시점(머리 글로우·테두리 쇼크와 동기)
PROPAGATE_HIT_PHASE = 0.82
LASER_HIT_START_SEC = LASER_SHOOT_SEC * (
    PHASE_CHARGE_END
    + (PHASE_PROPAGATE_END - PHASE_CHARGE_END) * PROPAGATE_HIT_PHASE
)
SHOCK_PULSE_PERIOD_SEC = 0.10
SHOCK_PULSE_COUNT = 3
LASER_BORDER_THIN = 3
LASER_BORDER_THICK = 12
LASER_BORDER_ALPHA_DIM = 85
LASER_BORDER_ALPHA_BRIGHT = 255
# base 슬롯 한자 — 충격 후 up/down 반복 (테두리 대신)
LASER_HANZI_SCALE_MIN = 1.0
LASER_HANZI_SCALE_PEAK = 1.18
LASER_HANZI_PULSE_PERIOD_SEC = 0.70
# ADD는 어두운 픽셀이 잘 안 쌓여 흐릿해 보임 — 알파 합성으로 선명하게
LASER_BLEND_FLAGS = 0
LASER_ALPHA_RATIO = 1.0
# 테두리 교차점에서 카드 안쪽으로 빔·도달을 조금 더 당김 (px)
LASER_CARD_OVERSHOOT_PX = 3
BEAM_THICKNESS_RATIO = 0.68
# 레이저 경로 그을림(문신) — 레이저보다 얇·연한 파티클 스탬프
SCORCH_ORIGIN_OFFSET_PX = 200
SCORCH_WIDTH_RATIO = 0.52  # 레이저 두께 대비
SCORCH_SAMPLE_SPACING_PX = 8
SCORCH_JITTER_PX = 2
SCORCH_OUTER_RADIUS = (4, 7)
SCORCH_INNER_RADIUS = (2, 4)
SCORCH_PARTICLE_SPREAD_PX = 5
SCORCH_MARK_RGBA = (170, 170, 175, 105)  # 연한 회색, 고정 (랜덤 없음)
SCORCH_PARTICLE_CHANCE = 0.3

_BEAM_CACHE: dict[str, pygame.Surface] = {}


def _laser_alpha(alpha: int) -> int:
    return max(0, min(255, int(alpha * LASER_ALPHA_RATIO)))


def _ensure_srcalpha(surf: pygame.Surface) -> pygame.Surface:
    if surf.get_flags() & pygame.SRCALPHA:
        return surf
    w, h = surf.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    out.blit(surf, (0, 0))
    return out


def _boost_beam_opacity(surf: pygame.Surface) -> pygame.Surface:
    """PNG 알파(평균 ~176)를 255로 올려 빔을 선명·불투명하게."""
    out = _ensure_srcalpha(surf.copy())
    w, h = out.get_size()
    for y in range(h):
        for x in range(w):
            r, g, b, a = out.get_at((x, y))
            if a < 8:
                continue
            out.set_at((x, y), (r, g, b, 255))
    return out


def _beam_thickness_px(sprite: pygame.Surface) -> int:
    _, sh = sprite.get_size()
    return max(6, int(sh * BEAM_THICKNESS_RATIO))


def _load_beam(laser_variant: str = DEFAULT_LASER_VARIANT) -> pygame.Surface | None:
    key = normalize_laser_variant(laser_variant)
    cached = _BEAM_CACHE.get(key)
    if cached is not None:
        return cached
    path = word_memorize_laser_beam_path(key)
    if not path.is_file():
        return None
    try:
        _BEAM_CACHE[key] = _boost_beam_opacity(pygame.image.load(str(path)))
    except Exception:
        return None
    return _BEAM_CACHE[key]


def _normalized_t(
    elapsed_sec: float, duration_sec: float, *, loop_preview: bool
) -> float:
    if loop_preview:
        return (elapsed_sec / max(0.12, LASER_SHOOT_SEC * 0.85)) % 1.0
    if LASER_SHOOT_SEC > 0:
        return min(1.0, max(0.0, elapsed_sec / LASER_SHOOT_SEC))
    return 1.0 if elapsed_sec > 0 else 0.0


def _phase_at(t: float) -> tuple[str, float]:
    if t < PHASE_CHARGE_END:
        return "charge", t / PHASE_CHARGE_END
    if t < PHASE_PROPAGATE_END:
        span = PHASE_PROPAGATE_END - PHASE_CHARGE_END
        return "propagate", (t - PHASE_CHARGE_END) / span
    return "hold", 1.0


def laser_impact_elapsed_sec(
    elapsed_sec: float, *, loop_preview: bool = False
) -> float:
    """레이저가 카드에 닿은 뒤 경과 시간(초). 닿기 전이면 0."""
    if loop_preview:
        local = elapsed_sec % max(0.12, LASER_SHOOT_SEC)
        return max(0.0, local - LASER_HIT_START_SEC)
    return max(0.0, elapsed_sec - LASER_HIT_START_SEC)


def _shock_border_style(impact_elapsed_sec: float) -> tuple[int, int, int]:
    """(border_width, ring_alpha, glow_alpha) — 번쩍 펄스 후 은은한 네온 유지."""
    burst_span = SHOCK_PULSE_PERIOD_SEC * SHOCK_PULSE_COUNT
    if impact_elapsed_sec < burst_span:
        local = impact_elapsed_sec % SHOCK_PULSE_PERIOD_SEC
        half = SHOCK_PULSE_PERIOD_SEC * 0.5
        if local < half:
            k = local / half
            width = int(LASER_BORDER_THIN + (LASER_BORDER_THICK - LASER_BORDER_THIN) * k)
            alpha = int(
                LASER_BORDER_ALPHA_DIM
                + (LASER_BORDER_ALPHA_BRIGHT - LASER_BORDER_ALPHA_DIM) * k
            )
        else:
            k = (local - half) / half
            width = int(LASER_BORDER_THICK - (LASER_BORDER_THICK - LASER_BORDER_THIN) * k)
            alpha = int(
                LASER_BORDER_ALPHA_BRIGHT
                - (LASER_BORDER_ALPHA_BRIGHT - LASER_BORDER_ALPHA_DIM) * k
            )
        glow = int(40 + alpha * 0.35)
        return max(2, width), max(0, min(255, alpha)), max(0, min(255, glow))

    breathe = 0.5 + 0.5 * math.sin(impact_elapsed_sec * 7.5)
    width = int(LASER_BORDER_THIN + (LASER_BORDER_THICK - LASER_BORDER_THIN) * 0.35 * breathe)
    alpha = int(150 + 70 * breathe)
    glow = int(28 + 50 * breathe)
    return width, alpha, glow


def laser_impact_hanzi_scale(impact_elapsed_sec: float) -> float:
    """base 슬롯 한자 scale — 레이저 적중 후 up/down 무한 반복 (주기 끝=down)."""
    if impact_elapsed_sec <= 0:
        return LASER_HANZI_SCALE_MIN

    period = max(0.04, LASER_HANZI_PULSE_PERIOD_SEC)
    local = impact_elapsed_sec % period
    half = period * 0.5
    lo, hi = LASER_HANZI_SCALE_MIN, LASER_HANZI_SCALE_PEAK
    if local < half:
        k = local / half
        return lo + (hi - lo) * k
    k = (local - half) / half
    return hi - (hi - lo) * k


def draw_laser_impact_border(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    impact_elapsed_sec: float,
    border_radius: int = 8,
    laser_variant: str = DEFAULT_LASER_VARIANT,
) -> None:
    """카드 테두리 네온 쇼크 — 닿는 순간 0.1초×3회 번쩍, 이후 다음 카드까지 유지."""
    if impact_elapsed_sec <= 0:
        return

    width, ring_alpha, glow_alpha = _shock_border_style(impact_elapsed_sec)
    ring_alpha = _laser_alpha(ring_alpha)
    glow_alpha = _laser_alpha(glow_alpha)
    pad = 10
    layer = pygame.Surface(
        (rect.width + pad * 2, rect.height + pad * 2),
        pygame.SRCALPHA,
    )
    inner = pygame.Rect(pad, pad, rect.width, rect.height)
    rad = max(0, min(border_radius, rect.width // 2, rect.height // 2))
    color = laser_border_color(laser_variant)

    for i in range(3, 0, -1):
        expand = i * 2
        glow_rect = inner.inflate(expand * 2, expand * 2)
        pygame.draw.rect(
            layer,
            (*color, min(255, glow_alpha // i)),
            glow_rect,
            width=2,
            border_radius=rad + expand // 2,
        )

    pygame.draw.rect(
        layer,
        (*color, ring_alpha),
        inner,
        width=max(2, width),
        border_radius=rad,
    )
    hi = tuple(min(255, c + 40) for c in color)
    pygame.draw.rect(
        layer,
        (*hi, min(255, ring_alpha + 30)),
        inner,
        width=max(1, width - 2),
        border_radius=rad,
    )
    surface.blit(layer, (rect.x - pad, rect.y - pad))


def _ease_out_quad(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 2


def _smoothstep(x: float) -> float:
    """전파 구간 — 끝에서 멈춘 것처럼 보이지 않게 완만히 가속·감속."""
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _hold_beam_pulse(elapsed_sec: float) -> tuple[float, int]:
    """(길이 배율, 알파) — TTS 대기 중에도 빔이 살아 있게."""
    t = elapsed_sec * HOLD_BEAM_PULSE_HZ
    length_scale = 1.0 + HOLD_BEAM_LENGTH_WOBBLE * math.sin(t)
    return length_scale, 255


def _aim_angle_rad(dx: float, dy: float) -> float:
    return math.atan2(dy, dx)


def draw_scorch_mark(surface: pygame.Surface, pos: tuple[int, int]) -> None:
    """연한 회색 고정색 — 외곽·중심·파티클 동일 색."""
    x, y = pos
    outer_r = random.randint(*SCORCH_OUTER_RADIUS)
    pygame.draw.circle(surface, SCORCH_MARK_RGBA, (x, y), outer_r)
    inner_r = random.randint(*SCORCH_INNER_RADIUS)
    pygame.draw.circle(surface, SCORCH_MARK_RGBA, (x, y), inner_r)
    if random.random() < SCORCH_PARTICLE_CHANCE:
        spread = SCORCH_PARTICLE_SPREAD_PX
        p_x = x + random.randint(-spread, spread)
        p_y = y + random.randint(-spread, spread)
        pygame.draw.circle(surface, SCORCH_MARK_RGBA, (p_x, p_y), 1)


def stamp_beam_scorch(
    scorch_surface: pygame.Surface,
    origin: tuple[float, float],
    target: tuple[float, float],
    *,
    start_dist_px: float,
    end_dist_px: float,
    beam_thickness_px: int,
) -> None:
    """origin→target [start_dist, end_dist] — 고정 간격·약한 지터 파티클 스탬프."""
    start = max(SCORCH_ORIGIN_OFFSET_PX, start_dist_px)
    end = max(start, end_dist_px)
    if end - start < 0.5:
        return

    ox, oy = origin
    dx = target[0] - ox
    dy = target[1] - oy
    total = math.hypot(dx, dy)
    if total < 1e-6:
        return

    ux, uy = dx / total, dy / total
    perp_x, perp_y = -uy, ux
    half_w = max(2, int(beam_thickness_px * SCORCH_WIDTH_RATIO * 0.5))

    dist = start
    while dist <= end:
        px = ox + ux * dist
        py = oy + uy * dist
        j_perp = random.uniform(-SCORCH_JITTER_PX, SCORCH_JITTER_PX)
        j_perp = max(-half_w, min(half_w, j_perp))
        sx = int(px + perp_x * j_perp)
        sy = int(py + perp_y * j_perp)
        draw_scorch_mark(scorch_surface, (sx, sy))
        dist += SCORCH_SAMPLE_SPACING_PX


def stamp_beam_scorch_full_path(
    scorch_surface: pygame.Surface,
    origin: tuple[float, float],
    target: tuple[float, float],
    *,
    beam_thickness_px: int,
) -> None:
    """중앙 offset부터 목표까지 경로 전체 — 얇은 파티클 스탬프."""
    ox, oy = origin
    distance = math.hypot(target[0] - ox, target[1] - oy)
    if distance <= SCORCH_ORIGIN_OFFSET_PX:
        return
    stamp_beam_scorch(
        scorch_surface,
        origin,
        target,
        start_dist_px=SCORCH_ORIGIN_OFFSET_PX,
        end_dist_px=distance,
        beam_thickness_px=beam_thickness_px,
    )


def laser_target_on_card_center(
    card_rect: tuple[int, int, int, int] | pygame.Rect,
) -> tuple[float, float]:
    """카드 사각형의 기하학적 중심."""
    if isinstance(card_rect, pygame.Rect):
        rect = card_rect
    else:
        x, y, w, h = card_rect
        rect = pygame.Rect(int(x), int(y), int(w), int(h))
    return rect.x + rect.width * 0.5, rect.y + rect.height * 0.5


def laser_target_on_card_border(
    origin: tuple[float, float],
    card_rect: tuple[int, int, int, int] | pygame.Rect,
) -> tuple[float, float]:
    """프레임 중앙→카드 광선이 테두리에 닿은 뒤 LASER_CARD_OVERSHOOT_PX 만큼 더 진행한 점."""
    if isinstance(card_rect, pygame.Rect):
        rect = card_rect
    else:
        x, y, w, h = card_rect
        rect = pygame.Rect(int(x), int(y), int(w), int(h))

    ox, oy = origin
    cx = rect.x + rect.width * 0.5
    cy = rect.y + rect.height * 0.5
    dx = cx - ox
    dy = cy - oy
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return cx, cy

    t_enter = -math.inf
    t_exit = math.inf
    for p, d, lo, hi in (
        (ox, dx, rect.left, rect.right),
        (oy, dy, rect.top, rect.bottom),
    ):
        if abs(d) < 1e-9:
            if p < lo or p > hi:
                return cx, cy
            continue
        t1 = (lo - p) / d
        t2 = (hi - p) / d
        t_enter = max(t_enter, min(t1, t2))
        t_exit = min(t_exit, max(t1, t2))

    if t_enter > t_exit or t_exit < 0:
        return cx, cy
    t_hit = t_enter if t_enter > 0 else t_exit
    if t_hit < 0:
        return cx, cy
    hx = ox + dx * t_hit
    hy = oy + dy * t_hit
    seg_dx = hx - ox
    seg_dy = hy - oy
    seg_len = math.hypot(seg_dx, seg_dy)
    if seg_len > 1e-6 and LASER_CARD_OVERSHOOT_PX > 0:
        scale = (seg_len + LASER_CARD_OVERSHOOT_PX) / seg_len
        hx = ox + seg_dx * scale
        hy = oy + seg_dy * scale
    return hx, hy


def _scale_beam_to_length(sprite: pygame.Surface, length_px: float) -> pygame.Surface:
    length = max(12, int(length_px))
    thickness = _beam_thickness_px(sprite)
    return _ensure_srcalpha(pygame.transform.smoothscale(sprite, (length, thickness)))


def _tail_pivot(sprite: pygame.Surface) -> tuple[float, float]:
    """가로 빔 왼쪽(꼬리) — 발사 원점에 고정."""
    return (0.0, sprite.get_height() / 2.0)


def _blit_beam_from_tail(
    surface: pygame.Surface,
    image: pygame.Surface,
    *,
    tail_world: tuple[float, float],
    angle_rad: float,
    alpha: int = 255,
) -> None:
    image = _ensure_srcalpha(image)
    if alpha < 255:
        image = image.copy()
        image.set_alpha(max(0, min(255, alpha)))

    rotated = pygame.transform.rotate(image, -math.degrees(angle_rad))
    px, py = _tail_pivot(image)
    cx, cy = image.get_width() / 2.0, image.get_height() / 2.0
    dx = px - cx
    dy = py - cy
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    rdx = dx * cos_a - dy * sin_a
    rdy = dx * sin_a + dy * cos_a
    rcx, rcy = rotated.get_width() / 2.0, rotated.get_height() / 2.0
    blit_x = int(tail_world[0] - rcx - rdx)
    blit_y = int(tail_world[1] - rcy - rdy)
    surface.blit(rotated, (blit_x, blit_y), special_flags=LASER_BLEND_FLAGS)


def draw_laser_center_to_card(
    surface: pygame.Surface,
    *,
    frame_width: int,
    frame_height: int,
    card_rect: tuple[int, int, int, int] | pygame.Rect,
    elapsed_sec: float,
    duration_sec: float,
    loop_preview: bool = False,
    scorch_surface: pygame.Surface | None = None,
    scorch_prev_length_px: float = 0.0,
    laser_variant: str = DEFAULT_LASER_VARIANT,
    beam_alpha_mult: float = 1.0,
    aim_at_center: bool = False,
) -> float:
    """프레임 정중앙(꼬리)에서 카드(머리)로 레이저 발사.

    aim_at_center=True면 카드 중심까지, False면 테두리 충돌점(+overshoot)까지.

    scorch_surface가 주어지면 빔 경로에 그을림을 누적하고, 갱신된 prev_length를 반환한다.
    """
    if beam_alpha_mult <= 0.0:
        return scorch_prev_length_px
    beam_src = _load_beam(laser_variant)
    if beam_src is None:
        return scorch_prev_length_px

    origin = (frame_width * 0.5, frame_height * 0.5)
    target = (
        laser_target_on_card_center(card_rect)
        if aim_at_center
        else laser_target_on_card_border(origin, card_rect)
    )
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    distance = math.hypot(dx, dy)
    if distance < 16:
        return scorch_prev_length_px

    beam_th = _beam_thickness_px(beam_src)
    angle = _aim_angle_rad(dx, dy)
    t = _normalized_t(elapsed_sec, duration_sec, loop_preview=loop_preview)
    phase, phase_t = _phase_at(t)
    prev_len = scorch_prev_length_px
    alpha_scale = max(0.0, min(1.0, float(beam_alpha_mult)))

    if phase == "charge":
        pulse = 0.88 + 0.12 * math.sin(elapsed_sec * 12.0)
        charge_len = max(24.0, distance * 0.08 * pulse)
        charge = _scale_beam_to_length(beam_src, charge_len)
        cw, ch = charge.get_size()
        sw = max(8, int(cw * pulse * 0.95))
        sh = max(6, int(ch * pulse * 0.92))
        charge_s = _ensure_srcalpha(pygame.transform.smoothscale(charge, (sw, sh)))
        _blit_beam_from_tail(
            surface,
            charge_s,
            tail_world=origin,
            angle_rad=angle,
            alpha=_laser_alpha(int(255 * alpha_scale)),
        )
        return prev_len

    beam_alpha = _laser_alpha(int(255 * alpha_scale))
    if phase == "propagate":
        length = distance * _smoothstep(phase_t)
    else:
        length_scale, pulse_alpha = _hold_beam_pulse(elapsed_sec)
        length = distance * length_scale
        beam_alpha = _laser_alpha(int(pulse_alpha * alpha_scale))

    beam = _scale_beam_to_length(beam_src, length)

    _blit_beam_from_tail(
        surface,
        beam,
        tail_world=origin,
        angle_rad=angle,
        alpha=beam_alpha,
    )

    if scorch_surface is not None:
        if phase == "propagate":
            stamp_beam_scorch(
                scorch_surface,
                origin,
                target,
                start_dist_px=prev_len,
                end_dist_px=length,
                beam_thickness_px=beam_th,
            )
            prev_len = max(prev_len, length)
            if length >= distance - 1.0:
                stamp_beam_scorch_full_path(
                    scorch_surface,
                    origin,
                    target,
                    beam_thickness_px=beam_th,
                )
                prev_len = distance
        else:
            if prev_len < distance - 0.5:
                stamp_beam_scorch_full_path(
                    scorch_surface,
                    origin,
                    target,
                    beam_thickness_px=beam_th,
                )
            prev_len = distance

    return prev_len
