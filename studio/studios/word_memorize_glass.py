"""단어 외우기 — 레이저+base 슬롯 모드 유리(서리) 가림·노이즈 디졸브."""
from __future__ import annotations

import hashlib
import math
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pygame

from extra.table_editor.services.word_memorize_layout import (
    DEFAULT_LASER_VARIANT,
    DissolveEffectVariant,
    is_laser_selection_highlight,
    layout_use_base_slot,
    laser_border_color,
    list_word_memorize_dissolve_effects,
    normalize_laser_variant,
    normalize_selection_highlight,
    word_memorize_dissolve_effect_path,
    word_memorize_dissolve_mask_path,
)
from studio.studios.word_memorize_laser import laser_impact_elapsed_sec

if TYPE_CHECKING:
    from extra.table_editor.services.word_memorize_layout import WordMemorizeLayout

# 레이저 적중 후 유리가 녹아 없어지는 시간(초)
GLASS_DISSOLVE_SEC = 1.05
# 피날레 — 역디졸브 완료 후 레이저 빔 소멸 시간(초)
LASER_FINALE_FADE_SEC = 0.42
# 디졸브 중 spark 효과음 랜덤 반복 간격(초)
GLASS_SPARK_SOUND_INTERVAL_MIN_SEC = 0.10
GLASS_SPARK_SOUND_INTERVAL_MAX_SEC = 0.21
# 유리 불투명도 (40~60%)
GLASS_BASE_ALPHA = 0.52
# 디졸브 경계 edge burn 밴드 (noise 공간 0~1)
GLASS_EDGE_BURN_BAND = 0.055
# threshold가 이 값 이상 움직인 뒤에만 glow (t≈0 전체 균열 방지)
GLASS_EDGE_BURN_MIN_T = 0.04
# 유리 디졸브 soft band (noise 0~1) — hard cut 방지
GLASS_DISSOLVE_SOFT = 0.042
# 유리 제거 후 선명해지는 구간
CONTENT_SHARPEN_SOFT = 0.085
# dissolve.png UV 타일링 — 값↑ 세밀한 grain (카드~320px 기준 2.5~3.5)
DISSOLVE_UV_SCALE = 2.85
# 영토형 경계 — 저주파 노이즈 + 카드 가장자리 perturb
TERRITORY_UV_SCALE = 1.25
TERRITORY_COARSE_MIX = 0.20
TERRITORY_EDGE_PERTURB = 0.24
TERRITORY_EDGE_BAND_RATIO = 0.16
TERRITORY_SILHOUETTE_AMP = 0.38
# edge emission — 디졸브 edge에 소량·불씨(spark)만
EMIT_GRID_PX = 14
EMIT_EDGE_BAND = 0.042
EMIT_SPAWN_RATE = 0.09
PARTICLE_SUB_SPAWN_COUNT = 1
PARTICLE_MIN_T = 0.012
PARTICLE_SIZE_REF_PX = 220.0
PARTICLE_ALPHA_SCALE = 0.90
PARTICLE_SPRITE_MIN_PX = 3
PARTICLE_SPRITE_MAX_PX = 8
PARTICLE_SPRITE_BASE_PX = 3
PARTICLE_SPRITE_SIZE_MULT = 5.0
PARTICLE_SPIN_DEG_MIN = -72.0
PARTICLE_SPIN_DEG_MAX = 72.0
PARTICLE_LIFE_MIN_SEC = 2.0
PARTICLE_LIFE_MAX_SEC = 5.0
PARTICLE_RENDER_MAX_SEC = 5.5
# 반짝임 — 느린 glow pulsation
PARTICLE_TWINKLE_HZ_MIN = 5.5
PARTICLE_TWINKLE_HZ_MAX = 11.0
PARTICLE_TWINKLE_SLOW_HZ = 1.6
PARTICLE_TWINKLE_FLOOR = 0.72
PARTICLE_TWINKLE_GLOW_THRESHOLD = 0.58
# 색·알파 수명 곡선 — 레이저 30% 유지 → 흰색 → 알파 fade-out
PARTICLE_LASER_HOLD_RATIO = 0.30
PARTICLE_WHITE_FULL_RATIO = 0.52
PARTICLE_ALPHA_FADE_START_RATIO = 0.48
# 불씨 drift — 속도·이동거리 상향
EMBER_DRIFT_SPEED_MIN = 38.0
EMBER_DRIFT_SPEED_MAX = 92.0
EMBER_RISE_LIFT = 18.0
EMBER_GRAVITY = 11.0
EMBER_DRAG = 0.88
EMBER_CURL_AMP = 5.5
EMBER_SIZE_FADE_START = 0.48
# 흐릿함 — 카드 짧은 변 대비 블러 sigma 비율
GLASS_BLUR_SIGMA_RATIO = 0.045
# 투명 카드(_paint_box pad) — 서리·알파 적용 내부 영역
CARD_INNER_PAD_PX = 10
# 투명 카드 서리 강도 (1=불투明白판, 낮을수록 배경이 비침)
TRANSPARENT_GLASS_RGB_MIX = 0.28
TRANSPARENT_GLASS_ALPHA_SCALE = 0.68

_DISSOLVE_TEXTURE: np.ndarray | None = None
_MASK_CACHE: dict[tuple[int, int, str], np.ndarray] = {}
_TERRITORY_CACHE: dict[tuple[int, int, str], np.ndarray] = {}
_GLASS_BASE_CACHE: dict[tuple[int, int, str], np.ndarray] = {}
_DISSOLVE_EFFECT_SPRITES: dict[tuple[str, DissolveEffectVariant], pygame.Surface] = {}


def layout_uses_laser_glass(layout: WordMemorizeLayout) -> bool:
    """base 슬롯 + 레이저 하이라이트일 때 비-base 카드에 유리 가림 적용."""
    if not layout_use_base_slot(layout):
        return False
    kind = normalize_selection_highlight(getattr(layout, "selection_highlight", ""))
    return is_laser_selection_highlight(kind)


def glass_dissolve_t(
    elapsed_sec: float,
    *,
    loop_preview: bool = False,
) -> float:
    """유리 디졸브 진행도 — 0=완전 가림, 1=완전 노출."""
    impact = laser_impact_elapsed_sec(elapsed_sec, loop_preview=loop_preview)
    if impact <= 0.0:
        return 0.0
    raw = min(1.0, impact / max(0.08, GLASS_DISSOLVE_SEC))
    return _ease_out_cubic(raw)


def glass_dissolve_complete(
    elapsed_sec: float,
    *,
    loop_preview: bool = False,
) -> bool:
    """디졸브가 끝났는지."""
    return glass_dissolve_t(elapsed_sec, loop_preview=loop_preview) >= 1.0 - 1e-4


def glass_dissolve_total_sec() -> float:
    """레이저 발사(0)부터 디졸브 완료까지 걸리는 시간(초)."""
    from studio.studios.word_memorize_laser import LASER_HIT_START_SEC

    return LASER_HIT_START_SEC + GLASS_DISSOLVE_SEC


def glass_dissolve_remaining_sec(
    elapsed_sec: float,
    *,
    loop_preview: bool = False,
) -> float:
    """디졸브가 끝나기까지 남은 시간(초)."""
    if glass_dissolve_complete(elapsed_sec, loop_preview=loop_preview):
        return 0.0
    return max(0.0, glass_dissolve_total_sec() - max(0.0, float(elapsed_sec)))


def glass_dissolve_t_reverse(
    impact_elapsed_sec: float,
) -> float:
    """역디졸브 — 1=완전 노출, 0=유리 완전 가림 (피날레 복구용)."""
    if impact_elapsed_sec <= 0.0:
        return 1.0
    raw = min(1.0, impact_elapsed_sec / max(0.08, GLASS_DISSOLVE_SEC))
    return 1.0 - _ease_out_cubic(raw)


def glass_dissolve_reverse_complete(impact_elapsed_sec: float) -> bool:
    """역디졸브가 끝났는지 — 유리가 다시 덮임."""
    return glass_dissolve_t_reverse(impact_elapsed_sec) <= 1e-4


def glass_finale_reverse_complete_elapsed_sec() -> float:
    """피날레 — 역디졸브가 끝나는 시점(초)."""
    from studio.studios.word_memorize_laser import LASER_HIT_START_SEC

    return LASER_HIT_START_SEC + GLASS_DISSOLVE_SEC


def glass_finale_laser_fade_mult(elapsed_sec: float) -> float:
    """피날레 — 역디졸브 후 레이저 알파 배율 (1→0)."""
    fade_start = glass_finale_reverse_complete_elapsed_sec()
    if elapsed_sec <= fade_start:
        return 1.0
    fade_t = elapsed_sec - fade_start
    if fade_t >= LASER_FINALE_FADE_SEC:
        return 0.0
    raw = min(1.0, fade_t / max(0.06, LASER_FINALE_FADE_SEC))
    return 1.0 - _ease_out_cubic(raw)


def glass_finale_lasers_gone(elapsed_sec: float) -> bool:
    """피날레 — 모든 레이저 빔이 완전히 사라졌는지."""
    return glass_finale_laser_fade_mult(elapsed_sec) <= 0.0


def glass_finale_close_duration_sec() -> float:
    """피날레 — 동시 레이저·역디졸브·레이저 소멸까지."""
    return glass_finale_reverse_complete_elapsed_sec() + LASER_FINALE_FADE_SEC + 0.05


def clear_glass_caches() -> None:
    """레이아웃·해상도 변경 시 캐시 비우기."""
    global _DISSOLVE_TEXTURE
    _DISSOLVE_TEXTURE = None
    _MASK_CACHE.clear()
    _TERRITORY_CACHE.clear()
    _GLASS_BASE_CACHE.clear()
    _DISSOLVE_EFFECT_SPRITES.clear()


def apply_laser_glass_to_surface(
    surface: pygame.Surface,
    rect: pygame.Rect,
    content: pygame.Surface,
    *,
    seed: str,
    dissolve_t: float,
    dissolve_elapsed_sec: float = 0.0,
    laser_variant: str = DEFAULT_LASER_VARIANT,
    use_card_background: bool = True,
    card_fill_rgb: tuple[int, int, int] = (255, 255, 255),
) -> None:
    """카드 내용물 위에 유리·디졸브 합성 (content는 rect 크기 SRCALPHA)."""
    t = max(0.0, min(1.0, float(dissolve_t)))
    if t >= 1.0 - 1e-4:
        surface.blit(content, rect.topleft)
        return

    w, h = rect.width, rect.height
    if w <= 0 or h <= 0:
        return

    if use_card_background:
        backdrop = np.full((h, w, 3), card_fill_rgb, dtype=np.float32)
    else:
        backdrop = _read_backdrop_rgb(surface, rect)

    content_rgb, content_alpha = _content_rgba(content, w, h)
    sharp = _composite_content_on_backdrop(content_rgb, content_alpha, backdrop)
    blur = _blur_rgb(sharp, w, h)
    noise = _dissolve_field(w, h, seed)
    laser_rgb = _laser_rgb(laser_variant)
    glass = _glass_base_layer(w, h, laser_variant)

    out, out_alpha = _composite(
        sharp,
        blur,
        noise,
        glass,
        laser_rgb,
        t,
        seed=seed,
        content_alpha=content_alpha,
        transparent_card=not use_card_background,
    )

    if out_alpha is None:
        surface.blit(_rgb_to_surface(out), rect.topleft)
    else:
        _blit_rgba_on_surface(surface, rect, out, out_alpha)


def blit_dissolve_particles(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    seed: str,
    dissolve_t: float,
    dissolve_elapsed_sec: float,
    laser_variant: str = DEFAULT_LASER_VARIANT,
    effect_keys: list[str] | None = None,
    display_scale: float = 1.0,
) -> None:
    """디졸브 파티클 — 카드·레이저 이펙트 위에 effect PNG 스프라이트 합성."""
    if dissolve_elapsed_sec <= 0.0:
        return
    if dissolve_elapsed_sec > PARTICLE_RENDER_MAX_SEC:
        return
    t = max(0.0, min(1.0, float(dissolve_t)))
    if t < PARTICLE_MIN_T and t < 1.0 - 1e-4:
        return
    w, h = rect.width, rect.height
    if w <= 0 or h <= 0:
        return
    keys = effect_keys or list_word_memorize_dissolve_effects()
    if not keys:
        return
    noise = _dissolve_field(w, h, seed)
    laser_rgb = _laser_rgb(laser_variant)
    _draw_particles_on_surface(
        surface,
        rect,
        noise,
        t,
        seed=seed,
        elapsed_sec=dissolve_elapsed_sec,
        effect_keys=keys,
        laser_rgb=laser_rgb,
        display_scale=max(0.5, float(display_scale)),
    )


def _ease_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


def _seed_int(seed: str) -> int:
    digest = hashlib.md5(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little", signed=False)


def _load_dissolve_texture() -> np.ndarray:
    """resource/image/game/dissolve.png — HxW float32 0~1 (밝을수록 늦게 제거)."""
    global _DISSOLVE_TEXTURE
    if _DISSOLVE_TEXTURE is not None:
        return _DISSOLVE_TEXTURE

    path = word_memorize_dissolve_mask_path()
    if not path.is_file():
        raise FileNotFoundError(f"디졸브 마스크 없음: {path}")

    surf = pygame.image.load(str(path))
    arr = pygame.surfarray.array3d(surf).astype(np.float32)
    gray = np.mean(arr, axis=2) / 255.0
    field = np.transpose(gray, (1, 0))
    mn = float(field.min())
    mx = float(field.max())
    if mx - mn > 1e-6:
        field = (field - mn) / (mx - mn)
    _DISSOLVE_TEXTURE = field.astype(np.float32)
    return _DISSOLVE_TEXTURE


def _dissolve_mask(w: int, h: int, seed: str) -> np.ndarray:
    """카드 크기로 타일링·bilinear 샘플 — grain 크기 일정."""
    key = (w, h, seed)
    cached = _MASK_CACHE.get(key)
    if cached is not None:
        return cached

    tex = _load_dissolve_texture()
    seed_val = _seed_int(f"dissolve:{seed}")
    ox = float(seed_val % 10007) / 10007.0 * tex.shape[1]
    oy = float((seed_val // 13) % 10007) / 10007.0 * tex.shape[0]

    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = gx * DISSOLVE_UV_SCALE + ox
    map_y = gy * DISSOLVE_UV_SCALE + oy
    field = cv2.remap(
        tex,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_WRAP,
    )
    field = field.astype(np.float32)
    _MASK_CACHE[key] = field
    return field


def _territory_coarse_field(w: int, h: int, seed: str) -> np.ndarray:
    """저주파 dissolve 샘플 — 영토형 큰 굴곡."""
    key = (w, h, seed)
    cached = _TERRITORY_CACHE.get(key)
    if cached is not None:
        return cached

    tex = _load_dissolve_texture()
    seed_val = _seed_int(f"territory:{seed}")
    ox = float(seed_val % 10007) / 10007.0 * tex.shape[1]
    oy = float((seed_val // 17) % 10007) / 10007.0 * tex.shape[0]

    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = gx * TERRITORY_UV_SCALE + ox
    map_y = gy * TERRITORY_UV_SCALE + oy
    field = cv2.remap(
        tex,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_WRAP,
    ).astype(np.float32)
    _TERRITORY_CACHE[key] = field
    return field


def _card_edge_proximity(h: int, w: int) -> np.ndarray:
    """카드 외곽에 가까울수록 1 — HxW float32."""
    yy = np.arange(h, dtype=np.float32)[:, None]
    xx = np.arange(w, dtype=np.float32)[None, :]
    edge_dist = np.minimum(
        np.minimum(yy, h - 1 - yy),
        np.minimum(xx, w - 1 - xx),
    )
    band = max(8.0, min(w, h) * TERRITORY_EDGE_BAND_RATIO)
    return 1.0 - np.clip(edge_dist / band, 0.0, 1.0)


def _dissolve_field(w: int, h: int, seed: str) -> np.ndarray:
    """미세 grain + 영토형 저주파 + 가장자리 perturb — 디졸브 threshold."""
    fine = _dissolve_mask(w, h, seed)
    coarse = _territory_coarse_field(w, h, seed)
    edge_prox = _card_edge_proximity(h, w)
    perturb = (coarse - 0.5) * 2.0 * TERRITORY_EDGE_PERTURB * edge_prox
    blended = fine * (1.0 - TERRITORY_COARSE_MIX) + coarse * TERRITORY_COARSE_MIX
    return np.clip(blended + perturb, 0.0, 1.0).astype(np.float32)


def _territory_silhouette_mod(
    h: int,
    w: int,
    seed: str,
    *,
    sharpen: np.ndarray,
) -> np.ndarray:
    """카드 실루엣 — 직선 테두리 대신 불규칙 영토 경계."""
    coarse = _territory_coarse_field(w, h, seed)
    edge_prox = _card_edge_proximity(h, w)
    bite = (coarse - 0.5) * 2.0 * TERRITORY_SILHOUETTE_AMP * edge_prox
    return np.clip(1.0 - bite * sharpen, 0.0, 1.0)


def _glass_base_layer(w: int, h: int, laser_variant: str) -> np.ndarray:
    """HxWx4 float32 RGBA 0~1 — 레이저 색이 섞인 서리 유리."""
    variant = normalize_laser_variant(laser_variant)
    key = (w, h, variant)
    cached = _GLASS_BASE_CACHE.get(key)
    if cached is not None:
        return cached

    laser = _laser_rgb(variant) / 255.0
    frost = np.array([0.88, 0.92, 0.97], dtype=np.float32)
    tint = frost * 0.68 + laser * 0.32

    layer = np.zeros((h, w, 4), dtype=np.float32)
    layer[..., 0] = tint[0]
    layer[..., 1] = tint[1]
    layer[..., 2] = tint[2]
    layer[..., 3] = GLASS_BASE_ALPHA

    yy = np.arange(h, dtype=np.float32)[:, None]
    xx = np.arange(w, dtype=np.float32)[None, :]
    edge_dist = np.minimum(
        np.minimum(yy, h - 1 - yy),
        np.minimum(xx, w - 1 - xx),
    )
    edge_glow = np.clip(1.0 - edge_dist / max(4.0, min(w, h) * 0.06), 0.0, 1.0)
    layer[..., 3] += edge_glow * 0.14
    layer[..., :3] += edge_glow[..., None] * laser * 0.12

    norm_x = xx / max(1.0, w - 1)
    norm_y = yy / max(1.0, h - 1)
    reflect = (np.sin((norm_x + norm_y) * np.pi * 2.8) * 0.5 + 0.5) * 0.10
    layer[..., :3] += reflect[..., None] * (frost * 0.6 + laser * 0.4)
    layer[..., 3] += reflect * 0.12

    layer = np.clip(layer, 0.0, 1.0)
    _GLASS_BASE_CACHE[key] = layer
    return layer


def _laser_rgb(laser_variant: str) -> np.ndarray:
    """선택 레이저 RGB float32 (0~255)."""
    key = normalize_laser_variant(laser_variant)
    r, g, b = laser_border_color(key)
    return np.array([float(r), float(g), float(b)], dtype=np.float32)


def _blur_rgb(rgb: np.ndarray, w: int, h: int) -> np.ndarray:
    sigma = max(2.5, min(w, h) * GLASS_BLUR_SIGMA_RATIO)
    return cv2.GaussianBlur(rgb, (0, 0), sigmaX=sigma, sigmaY=sigma)


def _read_backdrop_rgb(surface: pygame.Surface, rect: pygame.Rect) -> np.ndarray:
    """카드 영역 아래 이미 그려진 프레임(만다라 등) 샘플."""
    w, h = rect.width, rect.height
    clip = rect.clip(surface.get_rect())
    if clip.width <= 0 or clip.height <= 0:
        return np.zeros((h, w, 3), dtype=np.float32)
    sub = surface.subsurface(clip)
    if sub.get_width() != w or sub.get_height() != h:
        sub = pygame.transform.smoothscale(sub, (w, h))
    arr = pygame.surfarray.array3d(sub).astype(np.float32)
    return np.transpose(arr, (1, 0, 2))


def _content_rgba(
    surf: pygame.Surface,
    w: int,
    h: int,
) -> tuple[np.ndarray, np.ndarray]:
    """SRCALPHA content → HxWx3 RGB, HxW alpha 0~1."""
    if surf.get_width() != w or surf.get_height() != h:
        surf = pygame.transform.smoothscale(surf, (w, h))
    rgb = np.transpose(
        pygame.surfarray.array3d(surf).astype(np.float32), (1, 0, 2)
    )
    try:
        alpha = (
            np.transpose(
                pygame.surfarray.array_alpha(surf).astype(np.float32), (1, 0)
            )
            / 255.0
        )
    except ValueError:
        alpha = np.ones((h, w), dtype=np.float32)
    return rgb, alpha


def _composite_content_on_backdrop(
    content_rgb: np.ndarray,
    content_alpha: np.ndarray,
    backdrop: np.ndarray,
) -> np.ndarray:
    """투명 카드 — 배경 위에 내용 합성 (흰색 flatten ❌)."""
    ca = content_alpha[..., None]
    return backdrop * (1.0 - ca) + content_rgb * ca


def _surface_to_rgb(
    surf: pygame.Surface,
    w: int,
    h: int,
    *,
    bg_rgb: tuple[int, int, int] = (255, 255, 255),
) -> np.ndarray:
    """SRCALPHA 서피스 — 투명 영역을 지정색으로 펼친 뒤 RGB 추출."""
    backdrop = np.full((h, w, 3), bg_rgb, dtype=np.float32)
    rgb, alpha = _content_rgba(surf, w, h)
    return _composite_content_on_backdrop(rgb, alpha, backdrop)


def _rgb_to_surface(rgb: np.ndarray) -> pygame.Surface:
    arr = np.clip(rgb, 0, 255).astype(np.uint8)
    transposed = np.transpose(arr, (1, 0, 2))
    surf = pygame.Surface((transposed.shape[0], transposed.shape[1]))
    pygame.surfarray.blit_array(surf, transposed)
    try:
        return surf.convert()
    except pygame.error:
        return surf


def _rgb_alpha_to_surface(rgb: np.ndarray, alpha: np.ndarray) -> pygame.Surface:
    """HxWx3 + HxW alpha → SRCALPHA surface."""
    h, w = rgb.shape[:2]
    arr = np.clip(rgb, 0, 255).astype(np.uint8)
    a = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    px_rgb = pygame.surfarray.pixels3d(surf)
    px_alpha = pygame.surfarray.pixels_alpha(surf)
    px_rgb[:] = np.transpose(arr, (1, 0, 2))
    px_alpha[:] = np.transpose(a, (1, 0))
    del px_rgb, px_alpha
    return surf


def _composite(
    sharp: np.ndarray,
    blur: np.ndarray,
    noise: np.ndarray,
    glass: np.ndarray,
    laser_rgb: np.ndarray,
    t: float,
    *,
    seed: str = "",
    content_alpha: np.ndarray | None = None,
    transparent_card: bool = False,
) -> tuple[np.ndarray, np.ndarray | None]:
    """유리 soft dissolve → blur 유지 → 점진적 선명화 + edge glow."""
    past_front = t - noise

    glass_remain = np.clip(1.0 - past_front / max(1e-4, GLASS_DISSOLVE_SOFT), 0.0, 1.0)
    # smoothstep — 계단·덩어리 경계 완화
    glass_remain = glass_remain * glass_remain * (3.0 - 2.0 * glass_remain)

    sharpen_past = np.clip(past_front - GLASS_DISSOLVE_SOFT * 0.45, 0.0, None)
    sharpen = np.clip(sharpen_past / max(1e-4, CONTENT_SHARPEN_SOFT), 0.0, 1.0)
    sharpen = sharpen * sharpen * (3.0 - 2.0 * sharpen)

    out = blur.astype(np.float32) * (1.0 - sharpen[..., None]) + sharp * sharpen[..., None]

    glass_alpha = glass[..., 3] * glass_remain
    h, w = sharp.shape[:2]
    if np.any(glass_alpha > 0.005):
        ga = glass_alpha[..., None]
        grgb = glass[..., :3] * 255.0
        if transparent_card:
            region = _inner_region_mask(h, w)[..., None]
            ga = ga * region * TRANSPARENT_GLASS_RGB_MIX
            out = out * (1.0 - ga) + (out * 0.86 + grgb * 0.14) * ga
        else:
            out = out * (1.0 - ga) + grgb * ga

    out = _apply_dissolve_edge(out, noise, t, laser_rgb)

    if not transparent_card:
        return out, None

    ca = (
        content_alpha
        if content_alpha is not None
        else np.zeros((h, w), dtype=np.float32)
    )
    region = _inner_region_mask(h, w)
    glass_vis = glass_alpha * region * TRANSPARENT_GLASS_ALPHA_SCALE
    content_vis = ca * sharpen
    out_alpha = np.clip(np.maximum(content_vis, glass_vis), 0.0, 1.0)
    if seed:
        out_alpha = out_alpha * _territory_silhouette_mod(
            h, w, seed, sharpen=sharpen
        )
    return out, out_alpha


def _inner_region_mask(h: int, w: int, *, pad: int = CARD_INNER_PAD_PX) -> np.ndarray:
    """카드 내부 콘텐츠 영역 — _paint_box inner pad 와 동일."""
    pad = min(pad, max(1, min(w, h) // 4))
    mask = np.zeros((h, w), dtype=np.float32)
    if w <= pad * 2 or h <= pad * 2:
        mask[:] = 1.0
        return mask
    mask[pad : h - pad, pad : w - pad] = 1.0
    return mask


def _blit_rgba_on_surface(
    surface: pygame.Surface,
    rect: pygame.Rect,
    rgb: np.ndarray,
    alpha: np.ndarray,
) -> None:
    """알파>0 픽셀만 프레임 위에 합성 — 투명 영역은 배경(만다라) 유지."""
    if not np.any(alpha > 0.004):
        return
    overlay = _rgb_alpha_to_surface(rgb, alpha)
    surface.blit(overlay, rect.topleft)


def _load_dissolve_effect_sprite(
    key: str,
    *,
    variant: DissolveEffectVariant,
) -> pygame.Surface | None:
    """effect PNG 로드 — (key, variant) 단위 캐시."""
    cache_key = (key, variant)
    cached = _DISSOLVE_EFFECT_SPRITES.get(cache_key)
    if cached is not None:
        return cached
    path = word_memorize_dissolve_effect_path(key, variant=variant)
    if not path.is_file():
        return None
    try:
        surf = pygame.image.load(str(path))
        if surf.get_alpha() is None:
            surf = surf.convert_alpha()
        else:
            surf = surf.convert_alpha()
    except pygame.error:
        return None
    _DISSOLVE_EFFECT_SPRITES[cache_key] = surf
    return surf


def _draw_particles_on_surface(
    surface: pygame.Surface,
    rect: pygame.Rect,
    noise: np.ndarray,
    t: float,
    *,
    seed: str,
    elapsed_sec: float,
    effect_keys: list[str],
    laser_rgb: np.ndarray,
    display_scale: float = 1.0,
) -> None:
    """디졸브 edge emission — effect PNG 스프라이트 합성."""
    if elapsed_sec <= 0.0 or elapsed_sec > PARTICLE_RENDER_MAX_SEC:
        return
    if t < PARTICLE_MIN_T and t < 1.0 - 1e-4:
        return
    if not effect_keys:
        return

    h, w = noise.shape
    particles = _collect_edge_particles(
        noise,
        t,
        seed=seed,
        elapsed_sec=elapsed_sec,
        w=w,
        h=h,
        effect_keys=effect_keys,
    )
    if not particles:
        return

    ox, oy = rect.x, rect.y
    lr, lg, lb = int(laser_rgb[0]), int(laser_rgb[1]), int(laser_rgb[2])
    for px, py, radius, alpha, effect_key, rotation_deg, twinkle, white_mix in particles:
        if alpha <= 0.04:
            continue
        sprite = _load_dissolve_effect_sprite(effect_key, variant="transparent")
        if sprite is None:
            continue
        display_px = max(
            PARTICLE_SPRITE_MIN_PX,
            min(
                PARTICLE_SPRITE_MAX_PX,
                int(
                    round(
                        (
                            PARTICLE_SPRITE_BASE_PX
                            + radius * PARTICLE_SPRITE_SIZE_MULT
                        )
                        * display_scale
                    )
                ),
            ),
        )
        tint_rgb = _particle_tint_rgb(lr, lg, lb, white_mix)
        center = (ox + int(px), oy + int(py))
        _blit_particle_sprite(
            surface,
            sprite,
            center,
            display_px=display_px,
            rotation_deg=rotation_deg,
            alpha=alpha,
            tint_rgb=tint_rgb,
        )
        if twinkle >= PARTICLE_TWINKLE_GLOW_THRESHOLD:
            glow_mix = (twinkle - PARTICLE_TWINKLE_GLOW_THRESHOLD) / max(
                1e-4, 1.0 - PARTICLE_TWINKLE_GLOW_THRESHOLD
            )
            glow_px = max(4, int(round(display_px * (0.50 + glow_mix * 0.45))))
            glow_tint = _particle_tint_rgb(
                lr,
                lg,
                lb,
                min(1.0, white_mix + glow_mix * (1.0 - white_mix) * 0.75),
            )
            _blit_particle_sprite(
                surface,
                sprite,
                center,
                display_px=glow_px,
                rotation_deg=rotation_deg,
                alpha=min(1.0, alpha * glow_mix * 0.55),
                tint_rgb=glow_tint,
                additive=True,
            )


def _particle_tint_rgb(
    laser_r: int,
    laser_g: int,
    laser_b: int,
    white_mix: float,
) -> tuple[int, int, int]:
    """레이저 RGB → 수명에 따라 white_mix(0~1)만큼 흰색으로 보간."""
    wm = max(0.0, min(1.0, float(white_mix)))
    return (
        int(laser_r + (255 - laser_r) * wm),
        int(laser_g + (255 - laser_g) * wm),
        int(laser_b + (255 - laser_b) * wm),
    )


def _recolor_particle_surface(
    surf: pygame.Surface,
    tint_rgb: tuple[int, int, int],
) -> pygame.Surface:
    """스프라이트 알파 유지 · RGB를 tint로 치환."""
    colored = surf.copy()
    tr, tg, tb = tint_rgb
    colored.fill((tr, tg, tb, 255), None, pygame.BLEND_RGBA_MULT)
    return colored


def _blit_particle_sprite(
    surface: pygame.Surface,
    sprite: pygame.Surface,
    center: tuple[int, int],
    *,
    display_px: int,
    rotation_deg: float,
    alpha: float,
    tint_rgb: tuple[int, int, int],
    additive: bool = False,
) -> None:
    """effect PNG — 레이저 tint·알파 fade·반짝임 합성."""
    if alpha <= 0.02 or display_px <= 0:
        return
    scaled = pygame.transform.smoothscale(sprite, (display_px, display_px))
    rotated = _recolor_particle_surface(
        pygame.transform.rotate(scaled, rotation_deg),
        tint_rgb,
    )
    a = max(0, min(255, int(alpha * 255.0)))
    if a <= 0:
        return
    dest = rotated.get_rect(center=center)
    if additive:
        if a < 255:
            tinted = rotated.copy()
            tinted.fill((255, 255, 255, a), None, pygame.BLEND_RGBA_MULT)
            surface.blit(tinted, dest, special_flags=pygame.BLEND_ADD)
        else:
            surface.blit(rotated, dest, special_flags=pygame.BLEND_ADD)
        return
    if a >= 255:
        surface.blit(rotated, dest)
        return
    tinted = rotated.copy()
    tinted.fill((255, 255, 255, a), None, pygame.BLEND_RGBA_MULT)
    surface.blit(tinted, dest)


def _particle_spawn_elapsed_sec(noise_val: float) -> float:
    """noise 값이 디졸브 프론트에 닿은 시점(impact 경과 초) — 대략적."""
    return max(0.0, float(noise_val)) * GLASS_DISSOLVE_SEC * 1.12


def _particle_lifetime_sec(particle_id: int) -> float:
    """파티클별 수명 — 2~5초 (deterministic)."""
    span = PARTICLE_LIFE_MAX_SEC - PARTICLE_LIFE_MIN_SEC
    return PARTICLE_LIFE_MIN_SEC + _hash_scalar(particle_id + 157) * span


def _particle_opacity_over_life(age_sec: float, life_sec: float) -> float:
    """레이저·흰색 구간 후 알파를 점점 줄여 소멸."""
    if life_sec <= 1e-4 or age_sec >= life_sec:
        return 0.0
    u = age_sec / life_sec
    if u < 0.04:
        return _smoothstep01(u / 0.04) * 0.94
    if u <= PARTICLE_ALPHA_FADE_START_RATIO:
        return 0.94
    fade = (u - PARTICLE_ALPHA_FADE_START_RATIO) / max(
        1e-4,
        1.0 - PARTICLE_ALPHA_FADE_START_RATIO,
    )
    return max(0.0, (1.0 - _smoothstep01(fade)) * 0.94)


def _particle_size_over_life(age_sec: float, life_sec: float) -> float:
    """수명 후반 — 불씨가 작아지며 소멸."""
    if life_sec <= 1e-4:
        return 1.0
    u = age_sec / life_sec
    if u <= EMBER_SIZE_FADE_START:
        return 1.0
    shrink = (u - EMBER_SIZE_FADE_START) / max(1e-4, 1.0 - EMBER_SIZE_FADE_START)
    return max(0.35, 1.0 - _smoothstep01(shrink) * 0.62)


def _particle_twinkle(elapsed_sec: float, particle_id: int) -> float:
    """0~1 반짝임 — 이동 중 subtle glow용 (알파 주 pulsation 아님)."""
    phase = _hash_scalar(particle_id + 811) * math.tau
    hz_span = PARTICLE_TWINKLE_HZ_MAX - PARTICLE_TWINKLE_HZ_MIN
    fast_hz = PARTICLE_TWINKLE_HZ_MIN + _hash_scalar(particle_id + 823) * hz_span
    fast = 0.5 + 0.5 * math.sin(elapsed_sec * fast_hz * math.tau + phase)
    slow = 0.65 + 0.35 * math.sin(
        elapsed_sec * PARTICLE_TWINKLE_SLOW_HZ * math.tau + phase * 1.73
    )
    return max(0.0, min(1.0, fast * slow))


def _particle_twinkle_alpha_scale(twinkle: float) -> float:
    """반짝임 → 알파 배율 (완전 소멸 방지)."""
    floor = PARTICLE_TWINKLE_FLOOR
    return floor + (1.0 - floor) * twinkle


def _particle_white_mix(age_sec: float, life_sec: float) -> float:
    """수명 30%까지 순수 레이저색 → 이후 흰색으로 보간."""
    if life_sec <= 1e-4:
        return 0.0
    u = age_sec / life_sec
    if u <= PARTICLE_LASER_HOLD_RATIO:
        return 0.0
    if u >= PARTICLE_WHITE_FULL_RATIO:
        return 1.0
    span = max(1e-4, PARTICLE_WHITE_FULL_RATIO - PARTICLE_LASER_HOLD_RATIO)
    return _smoothstep01((u - PARTICLE_LASER_HOLD_RATIO) / span)


def _particle_exit_alpha(age_sec: float, life_sec: float) -> float:
    """_particle_opacity_over_life와 동일 곡선 — 하위 호환."""
    return _particle_opacity_over_life(age_sec, life_sec)


def _collect_edge_particles(
    noise: np.ndarray,
    t: float,
    *,
    seed: str,
    elapsed_sec: float,
    w: int,
    h: int,
    effect_keys: list[str],
) -> list[tuple[float, float, float, float, str, float, float, float]]:
    """edge spawn → (px, py, radius, alpha, key, rot, twinkle, white_mix)."""
    cell = max(2, EMIT_GRID_PX)
    size_scale = min(1.22, max(0.72, min(w, h) / PARTICLE_SIZE_REF_PX))
    seed_base = _seed_int(f"emit:{seed}")
    key_count = len(effect_keys)
    out: list[tuple[float, float, float, float, str, float, float, float]] = []

    gh = max(1, (h + cell - 1) // cell)
    gw = max(1, (w + cell - 1) // cell)
    gy_c = np.clip(np.arange(gh) * cell + cell // 2, 0, h - 1)
    gx_c = np.clip(np.arange(gw) * cell + cell // 2, 0, w - 1)
    n_grid = noise[gy_c[:, None], gx_c[None, :]]

    for gy in range(gh):
        for gx in range(gw):
            n_val = float(n_grid[gy, gx])
            spawn_sec = _particle_spawn_elapsed_sec(n_val)
            for sub in range(PARTICLE_SUB_SPAWN_COUNT):
                pid = (
                    (gx * 73856093)
                    ^ (gy * 19349663)
                    ^ seed_base
                    ^ (sub * 97531)
                )
                if _hash_scalar(pid) > EMIT_SPAWN_RATE:
                    continue

                age_sec = elapsed_sec - spawn_sec
                if age_sec <= 0.0:
                    continue

                life = _particle_lifetime_sec(pid)
                if age_sec >= life:
                    continue

                if t < 1.0 - 1e-4 and n_val > t + EMIT_EDGE_BAND:
                    continue

                on_edge = abs(n_val - t) < EMIT_EDGE_BAND and t < 1.0 - 1e-4

                rnd_a = _hash_scalar(pid + 11)
                rnd_b = _hash_scalar(pid + 23)
                sx = gx * cell + cell * (0.18 + rnd_a * 0.64)
                sy = gy * cell + cell * (0.18 + rnd_b * 0.64)

                drift_x, drift_y = _ember_drift_offset(pid, age_sec)
                curl_x, curl_y = _ember_drift_curl(pid, age_sec)
                px = sx + drift_x + curl_x
                py = sy + drift_y + curl_y

                twinkle = _particle_twinkle(elapsed_sec, pid)
                life_fade = _particle_opacity_over_life(age_sec, life)
                size_fade = _particle_size_over_life(age_sec, life)
                alpha_boost = 0.92
                white_mix = _particle_white_mix(age_sec, life)
                radius = (0.18 + _hash_scalar(pid + 67) * 0.28) * size_scale * size_fade
                effect_idx = int(_hash_scalar(pid + 401) * key_count * 0.999999)
                effect_key = effect_keys[effect_idx]
                spin = PARTICLE_SPIN_DEG_MIN + _hash_scalar(pid + 503) * (
                    PARTICLE_SPIN_DEG_MAX - PARTICLE_SPIN_DEG_MIN
                )
                rotation_deg = _hash_scalar(pid + 211) * 360.0 + elapsed_sec * spin

                fade = _particle_fade(
                    age_sec,
                    life,
                    edge_boost=0.22 if on_edge else 0.0,
                )
                alpha = min(
                    1.0,
                    fade
                    * life_fade
                    * alpha_boost
                    * PARTICLE_ALPHA_SCALE,
                )
                if alpha <= 0.03:
                    continue
                out.append(
                    (px, py, radius, alpha, effect_key, rotation_deg, twinkle, white_mix)
                )
    return out


def _hash_scalar(value: int) -> float:
    """정수 id → [0, 1) deterministic hash."""
    n = (
        np.uint64(value & 0xFFFFFFFF) * np.uint64(374761393)
        ^ np.uint64((value >> 16) & 0xFFFF) * np.uint64(668265263)
    ) & np.uint64(0xFFFFFFFF)
    n = ((n ^ (n >> np.uint64(13))) * np.uint64(1274126177)) & np.uint64(0xFFFFFFFF)
    return float(n % np.uint64(10000)) / 10000.0


def _smoothstep01(x: float) -> float:
    """0~1 smoothstep."""
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _ember_drift_offset(particle_id: int, age_sec: float) -> tuple[float, float]:
    """불씨 — 초기 랜덤 속도 + drag + 중력 arc (누적 이동)."""
    angle = _hash_scalar(particle_id + 601) * math.tau
    speed_span = EMBER_DRIFT_SPEED_MAX - EMBER_DRIFT_SPEED_MIN
    speed = EMBER_DRIFT_SPEED_MIN + _hash_scalar(particle_id + 613) * speed_span
    drag = EMBER_DRAG
    travel = (1.0 - math.exp(-drag * age_sec)) / max(drag, 1e-4)
    vx0 = math.cos(angle) * speed
    vy0 = math.sin(angle) * speed - EMBER_RISE_LIFT
    vx = vx0 * travel
    vy = vy0 * travel + 0.5 * EMBER_GRAVITY * age_sec * age_sec
    return vx, vy


def _ember_drift_curl(particle_id: int, age_sec: float) -> tuple[float, float]:
    """이동 방향 수직 미세 curl — 제자리 흔들림 대신 drift를 따라감."""
    angle = _hash_scalar(particle_id + 601) * math.tau
    perp_x = -math.sin(angle)
    perp_y = math.cos(angle)
    phase = _hash_scalar(particle_id + 727) * math.tau
    curl = math.sin(age_sec * 2.4 + phase) * EMBER_CURL_AMP
    grow = 1.0 - math.exp(-age_sec * 0.55)
    return perp_x * curl * grow * 0.35, perp_y * curl * grow * 0.35


def _particle_fade(
    age_sec: float,
    life_sec: float,
    *,
    edge_boost: float = 0.0,
) -> float:
    """spawn edge 가시성 보조 — 주 fade는 _particle_opacity_over_life."""
    if age_sec >= life_sec:
        return 0.0
    ramp = _smoothstep01(age_sec / max(0.08, life_sec * 0.04))
    return min(1.0, 0.76 + 0.24 * ramp + edge_boost)


def _apply_dissolve_edge(
    rgb: np.ndarray,
    noise: np.ndarray,
    t: float,
    laser_rgb: np.ndarray,
) -> np.ndarray:
    """디졸브 프론트 — 선택 레이저 색으로 경계 발광."""
    if t < GLASS_EDGE_BURN_MIN_T or t >= 1.0 - 1e-4:
        return rgb

    band = GLASS_EDGE_BURN_BAND
    dist = np.abs(noise - t)
    edge = dist < band
    if not np.any(edge):
        return rgb

    strength = (1.0 - dist[edge] / band).astype(np.float32)
    strength = np.clip(strength, 0.0, 1.0)
    mix = strength[..., None] * 0.82
    bloom = strength[..., None] * 0.38
    pixels = rgb[edge]
    rgb[edge] = np.clip(
        pixels * (1.0 - mix) + laser_rgb * mix + laser_rgb * bloom,
        0.0,
        255.0,
    )
    return rgb
