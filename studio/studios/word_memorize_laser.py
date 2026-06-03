"""단어 외우기 — 레이저 카드 하이라이트 (icon/laser.png 가로 빔).

리소스는 가로로 누운 형태(왼쪽=꼬리, 오른쪽=머리). 프레임 중앙(꼬리)에서
카드 중심(머리) 방향으로 거리만큼 가로 스케일 후 atan2 각도로 회전한다.
"""
from __future__ import annotations

import math

import pygame

from extra.table_editor.services.word_memorize_layout import word_memorize_laser_beam_path

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
LASER_BORDER_COLOR = (0, 229, 255)
LASER_BORDER_THIN = 3
LASER_BORDER_THICK = 12
LASER_BORDER_ALPHA_DIM = 85
LASER_BORDER_ALPHA_BRIGHT = 255
# ADD는 어두운 픽셀이 잘 안 쌓여 흐릿해 보임 — 알파 합성으로 선명하게
LASER_BLEND_FLAGS = 0
LASER_ALPHA_RATIO = 0.75
BEAM_ALPHA_BOOST = 1.55
BEAM_MIN_VISIBLE_ALPHA = 200
BEAM_THICKNESS_RATIO = 0.68

_BEAM_CACHE: pygame.Surface | None = None
_HEAD_CACHE: pygame.Surface | None = None


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
    """PNG 알파(평균 ~176)를 올려 빔이 흐릿하지 않게."""
    out = _ensure_srcalpha(surf.copy())
    w, h = out.get_size()
    for y in range(h):
        for x in range(w):
            r, g, b, a = out.get_at((x, y))
            if a < 8:
                continue
            boosted = min(255, int(a * BEAM_ALPHA_BOOST))
            a_out = max(boosted, BEAM_MIN_VISIBLE_ALPHA) if a >= 24 else boosted
            out.set_at((x, y), (r, g, b, a_out))
    return out


def _beam_thickness_px(sprite: pygame.Surface) -> int:
    _, sh = sprite.get_size()
    return max(6, int(sh * BEAM_THICKNESS_RATIO))


def _load_beam() -> pygame.Surface | None:
    global _BEAM_CACHE
    if _BEAM_CACHE is not None:
        return _BEAM_CACHE
    path = word_memorize_laser_beam_path()
    if not path.is_file():
        return None
    try:
        _BEAM_CACHE = _boost_beam_opacity(pygame.image.load(str(path)))
    except Exception:
        _BEAM_CACHE = None
    return _BEAM_CACHE


def _load_head_glow(beam_src: pygame.Surface) -> pygame.Surface:
    """빔 오른쪽(머리) 구간 — 임팩트 글로우용."""
    global _HEAD_CACHE
    if _HEAD_CACHE is not None:
        return _HEAD_CACHE
    w, h = beam_src.get_size()
    head_w = max(8, int(w * 0.38))
    head_x = max(0, w - head_w)
    _HEAD_CACHE = _ensure_srcalpha(beam_src.subsurface((head_x, 0, head_w, h)).copy())
    return _HEAD_CACHE


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


def draw_laser_impact_border(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    impact_elapsed_sec: float,
    border_radius: int = 8,
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
    color = LASER_BORDER_COLOR

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
    alpha = int(215 + 40 * (0.5 + 0.5 * math.sin(t * 1.35 + 0.6)))
    return length_scale, max(160, min(255, alpha))


def _aim_angle_rad(dx: float, dy: float) -> float:
    return math.atan2(dy, dx)


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
    card_center: tuple[int, int],
    elapsed_sec: float,
    duration_sec: float,
    loop_preview: bool = False,
) -> None:
    """프레임 정중앙(꼬리)에서 카드 중심(머리)으로 레이저 발사."""
    beam_src = _load_beam()
    if beam_src is None:
        return

    origin = (frame_width * 0.5, frame_height * 0.5)
    target = (float(card_center[0]), float(card_center[1]))
    dx = target[0] - origin[0]
    dy = target[1] - origin[1]
    distance = math.hypot(dx, dy)
    if distance < 16:
        return

    angle = _aim_angle_rad(dx, dy)
    t = _normalized_t(elapsed_sec, duration_sec, loop_preview=loop_preview)
    phase, phase_t = _phase_at(t)

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
            alpha=_laser_alpha(255),
        )
        return

    beam_alpha = _laser_alpha(255)
    if phase == "propagate":
        length = distance * _smoothstep(phase_t)
    else:
        length_scale, pulse_alpha = _hold_beam_pulse(elapsed_sec)
        length = distance * length_scale
        beam_alpha = _laser_alpha(pulse_alpha)

    beam = _scale_beam_to_length(beam_src, length)

    _blit_beam_from_tail(
        surface,
        beam,
        tail_world=origin,
        angle_rad=angle,
        alpha=beam_alpha,
    )

    if phase == "hold" or (
        phase == "propagate" and phase_t > PROPAGATE_HIT_PHASE
    ):
        head_src = _load_head_glow(beam_src)
        hw, hh = head_src.get_size()
        tip_w = max(12, int(hw * 1.25))
        tip_h = max(8, int(hh * 1.45))
        tip = _ensure_srcalpha(pygame.transform.smoothscale(head_src, (tip_w, tip_h)))
        tip.set_alpha(_laser_alpha(255))
        rect = tip.get_rect(center=(int(target[0]), int(target[1])))
        surface.blit(tip, rect, special_flags=LASER_BLEND_FLAGS)
