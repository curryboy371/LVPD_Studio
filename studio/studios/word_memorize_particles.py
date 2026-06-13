"""단어 외우기 — 곡괭이 채굴 시 타일 파괴 파티클."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import pygame

from extra.table_editor.services.word_memorize_layout import (
    WordMemorizeBox,
    WordMemorizeLayout,
    layout_game_particles,
    word_memorize_game_particle_path,
)

PARTICLES_PER_TILE_MIN = 5
PARTICLES_PER_TILE_MAX = 10
PARTICLE_LIFETIME_MIN_SEC = 0.28
PARTICLE_LIFETIME_MAX_SEC = 1.35
PARTICLE_GRAVITY_PX_S2 = 580.0
PARTICLE_SPEED_MIN_RATIO = 9.0
PARTICLE_SPEED_MAX_RATIO = 24.0
PARTICLE_BURST_SPEED_MULT_MIN = 1.25
PARTICLE_BURST_SPEED_MULT_MAX = 1.95
PARTICLE_BURST_CHANCE = 0.28
PARTICLE_SIZE_TINY_MIN_RATIO = 0.10
PARTICLE_SIZE_TINY_MAX_RATIO = 0.30
PARTICLE_SIZE_MED_MIN_RATIO = 0.32
PARTICLE_SIZE_MED_MAX_RATIO = 0.62
PARTICLE_SIZE_LARGE_MIN_RATIO = 0.68
PARTICLE_SIZE_LARGE_MAX_RATIO = 1.18
PARTICLE_SIZE_TINY_CHANCE = 0.38
PARTICLE_SIZE_LARGE_CHANCE = 0.22
PARTICLE_POSITION_NOISE_RATIO = 0.55
# 폭발 방향 — 10·2·6시 위주, 12시(위) 직진은 거의 없음
PARTICLE_DIRECTION_BINS: tuple[tuple[float, float, float], ...] = (
    (-2.0 * math.pi / 3.0, 0.32, math.radians(24.0)),  # 10시
    (-math.pi / 3.0, 0.32, math.radians(24.0)),  # 2시
    (math.pi / 2.0, 0.26, math.radians(30.0)),  # 6시
    (math.pi / 4.0, 0.05, math.radians(18.0)),  # 4시 (아래·오른쪽)
    (3.0 * math.pi / 4.0, 0.05, math.radians(18.0)),  # 8시 (아래·왼쪽)
)
# 12시(-π/2)에 가까울수록 알파를 더 빨리 줄임 — 단어 가림 방지
CLOCK12_ANGLE_RAD = -math.pi / 2.0
CLOCK12_PROXIMITY_ANGLE_RAD = math.radians(38.0)
CLOCK12_FADE_START_REDUCE = 0.42
CLOCK12_FADE_POWER_BOOST = 2.4
PARTICLE_ROT_SPEED_MIN_DEG = -520.0
PARTICLE_ROT_SPEED_MAX_DEG = 520.0
PARTICLE_FADE_START_MIN_RATIO = 0.0
PARTICLE_FADE_START_MAX_RATIO = 0.55
PARTICLE_FADE_POWER_MIN = 0.65
PARTICLE_FADE_POWER_MAX = 3.8


@dataclass
class MiningParticle:
    """활성 파티클 한 개."""

    x: float
    y: float
    vx: float
    vy: float
    rotation_deg: float
    rotation_speed_deg: float
    age_sec: float
    lifetime_sec: float
    fade_start_ratio: float
    fade_power: float
    clock12_proximity: float
    display_px: int
    sprite: pygame.Surface


@dataclass
class MiningParticleSystem:
    """채굴 파티클 물리·렌더."""

    particles: list[MiningParticle] = field(default_factory=list)

    def clear(self) -> None:
        """모든 파티클 제거."""
        self.particles.clear()

    def tick(self, dt_sec: float) -> None:
        """중력·이동·수명 갱신."""
        if dt_sec <= 0.0 or not self.particles:
            return
        gravity = float(PARTICLE_GRAVITY_PX_S2)
        alive: list[MiningParticle] = []
        for particle in self.particles:
            age = particle.age_sec + dt_sec
            if age >= particle.lifetime_sec:
                continue
            vy = particle.vy + gravity * dt_sec
            alive.append(
                MiningParticle(
                    x=particle.x + particle.vx * dt_sec,
                    y=particle.y + particle.vy * dt_sec,
                    vx=particle.vx,
                    vy=vy,
                    rotation_deg=particle.rotation_deg
                    + particle.rotation_speed_deg * dt_sec,
                    rotation_speed_deg=particle.rotation_speed_deg,
                    age_sec=age,
                    lifetime_sec=particle.lifetime_sec,
                    fade_start_ratio=particle.fade_start_ratio,
                    fade_power=particle.fade_power,
                    clock12_proximity=particle.clock12_proximity,
                    display_px=particle.display_px,
                    sprite=particle.sprite,
                )
            )
        self.particles = alive

    def spawn_at_center(
        self,
        center_x: float,
        center_y: float,
        *,
        tile_px: int,
        sprites: list[pygame.Surface],
        rng: random.Random | None = None,
    ) -> None:
        """타일 칸 중심에서 파티클을 생성한다."""
        if tile_px <= 0 or not sprites:
            return
        randomizer = rng or random.Random()
        count = randomizer.randint(PARTICLES_PER_TILE_MIN, PARTICLES_PER_TILE_MAX)
        noise = tile_px * PARTICLE_POSITION_NOISE_RATIO
        for _ in range(count):
            sprite = randomizer.choice(sprites)
            display_px = max(
                2, int(round(tile_px * _random_particle_size_ratio(randomizer)))
            )
            speed = tile_px * randomizer.uniform(
                PARTICLE_SPEED_MIN_RATIO, PARTICLE_SPEED_MAX_RATIO
            )
            if randomizer.random() < PARTICLE_BURST_CHANCE:
                speed *= randomizer.uniform(
                    PARTICLE_BURST_SPEED_MULT_MIN, PARTICLE_BURST_SPEED_MULT_MAX
                )
            vx, vy, clock12_prox = _random_burst_velocity(randomizer, speed)
            lifetime = randomizer.uniform(
                PARTICLE_LIFETIME_MIN_SEC, PARTICLE_LIFETIME_MAX_SEC
            )
            fade_start = randomizer.uniform(
                PARTICLE_FADE_START_MIN_RATIO, PARTICLE_FADE_START_MAX_RATIO
            )
            fade_power = randomizer.uniform(
                PARTICLE_FADE_POWER_MIN, PARTICLE_FADE_POWER_MAX
            )
            self.particles.append(
                MiningParticle(
                    x=center_x + randomizer.uniform(-noise, noise),
                    y=center_y + randomizer.uniform(-noise, noise),
                    vx=vx,
                    vy=vy,
                    rotation_deg=randomizer.uniform(0.0, 360.0),
                    rotation_speed_deg=randomizer.uniform(
                        PARTICLE_ROT_SPEED_MIN_DEG, PARTICLE_ROT_SPEED_MAX_DEG
                    ),
                    age_sec=0.0,
                    lifetime_sec=lifetime,
                    fade_start_ratio=fade_start,
                    fade_power=fade_power,
                    clock12_proximity=clock12_prox,
                    display_px=display_px,
                    sprite=sprite,
                )
            )

    def spawn_row(
        self,
        box: WordMemorizeBox,
        row_index: int,
        *,
        tile_px: int,
        sprites: list[pygame.Surface],
        rng: random.Random | None = None,
    ) -> None:
        """행이 사라질 때 해당 행의 타일 칸마다 파티클을 생성한다."""
        if tile_px <= 0 or not sprites:
            return
        for center_x, center_y in iter_tile_centers_in_row(box, row_index, tile_px):
            self.spawn_at_center(
                center_x,
                center_y,
                tile_px=tile_px,
                sprites=sprites,
                rng=rng,
            )

    def draw(self, surface: pygame.Surface) -> None:
        """알파 페이드와 함께 파티클을 그린다."""
        if not self.particles:
            return
        for particle in self.particles:
            life = max(1e-6, particle.lifetime_sec)
            t = max(0.0, min(1.0, particle.age_sec / life))
            fade_start = particle.fade_start_ratio
            fade_power = particle.fade_power
            prox = max(0.0, min(1.0, particle.clock12_proximity))
            if prox > 0.0:
                fade_start = max(
                    0.0, fade_start - CLOCK12_FADE_START_REDUCE * prox
                )
                fade_power = fade_power * (1.0 + CLOCK12_FADE_POWER_BOOST * prox)
            alpha = _particle_alpha(
                t,
                fade_start_ratio=fade_start,
                fade_power=fade_power,
            )
            if alpha <= 0:
                continue
            px = max(1, int(particle.display_px))
            scaled = pygame.transform.smoothscale(particle.sprite, (px, px))
            rotated = pygame.transform.rotate(scaled, -particle.rotation_deg)
            rotated.set_alpha(alpha)
            rect = rotated.get_rect(center=(int(round(particle.x)), int(round(particle.y))))
            surface.blit(rotated, rect)


def _random_particle_size_ratio(rng: random.Random) -> float:
    """작은·중간·큰 파편 비율을 섞어 크기 노이즈를 준다."""
    roll = rng.random()
    if roll < PARTICLE_SIZE_TINY_CHANCE:
        return rng.uniform(PARTICLE_SIZE_TINY_MIN_RATIO, PARTICLE_SIZE_TINY_MAX_RATIO)
    if roll < PARTICLE_SIZE_TINY_CHANCE + PARTICLE_SIZE_LARGE_CHANCE:
        return rng.uniform(PARTICLE_SIZE_LARGE_MIN_RATIO, PARTICLE_SIZE_LARGE_MAX_RATIO)
    return rng.uniform(PARTICLE_SIZE_MED_MIN_RATIO, PARTICLE_SIZE_MED_MAX_RATIO)


def _clock12_proximity(angle_rad: float) -> float:
    """12시(-π/2) 방향과의 각도 근접도 0~1."""
    diff = angle_rad - CLOCK12_ANGLE_RAD
    while diff > math.pi:
        diff -= 2.0 * math.pi
    while diff < -math.pi:
        diff += 2.0 * math.pi
    threshold = max(1e-6, CLOCK12_PROXIMITY_ANGLE_RAD)
    return max(0.0, 1.0 - abs(diff) / threshold)


def _random_burst_velocity(
    rng: random.Random, speed: float
) -> tuple[float, float, float]:
    """10·2·6시 위주 폭발 속도 + 12시 근접도(알파 감쇠용)."""
    bins = PARTICLE_DIRECTION_BINS
    total_w = sum(item[1] for item in bins)
    roll = rng.random() * total_w
    center = bins[-1][0]
    spread = bins[-1][2]
    for center_angle, weight, half_spread in bins:
        roll -= weight
        if roll <= 0.0:
            center = center_angle
            spread = half_spread
            break
    angle = center + rng.uniform(-spread, spread)
    vx = math.cos(angle) * speed
    vy = math.sin(angle) * speed
    return vx, vy, _clock12_proximity(angle)


def _particle_alpha(
    life_ratio: float,
    *,
    fade_start_ratio: float,
    fade_power: float,
) -> int:
    """수명 비율에 따른 알파 — 시작 지연·감쇠 곡선마다 노이즈."""
    start = max(0.0, min(0.95, fade_start_ratio))
    power = max(0.2, fade_power)
    if life_ratio <= start:
        return 255
    fade_span = max(1e-6, 1.0 - start)
    fade_t = max(0.0, min(1.0, (life_ratio - start) / fade_span))
    return int(round(255.0 * (1.0 - fade_t) ** power))


def iter_tile_centers_in_row(
    box: WordMemorizeBox, row_index: int, tile_px: int
) -> list[tuple[float, float]]:
    """카드 박스 안 한 행의 타일 칸 중심 좌표."""
    if tile_px <= 0:
        return []
    x0 = float(box.x)
    y0 = float(box.y)
    w = float(box.w)
    h = float(box.h)
    if w <= 0.0 or h <= 0.0:
        return []
    row_top = y0 + float(row_index) * float(tile_px)
    row_bottom = min(y0 + h, row_top + float(tile_px))
    if row_bottom <= row_top:
        return []
    centers: list[tuple[float, float]] = []
    col = 0
    while True:
        cell_x = x0 + float(col) * float(tile_px)
        if cell_x >= x0 + w:
            break
        cell_right = min(x0 + w, cell_x + float(tile_px))
        if cell_right <= cell_x:
            break
        center_x = (cell_x + cell_right) * 0.5
        center_y = (row_top + row_bottom) * 0.5
        centers.append((center_x, center_y))
        col += 1
    return centers


def split_particle_sprite_sheet(surface: pygame.Surface) -> list[pygame.Surface]:
    """파티클 PNG — 2x2 스프라이트 시트면 조각별로 분리."""
    w, h = surface.get_size()
    if w < 4 or h < 4:
        return [surface]
    half_w = w // 2
    half_h = h // 2
    if half_w < 2 or half_h < 2:
        return [surface]
    sprites: list[pygame.Surface] = []
    for row in range(2):
        for col in range(2):
            rect = pygame.Rect(col * half_w, row * half_h, half_w, half_h)
            piece = surface.subsurface(rect).copy()
            sprites.append(piece)
    return sprites


def load_particle_sprites(path: Path | str) -> list[pygame.Surface]:
    """파티클 이미지 로드 후 스프라이트 조각 목록 반환."""
    file_path = Path(path)
    if not file_path.is_file():
        return []
    try:
        surf = pygame.image.load(str(file_path))
        if surf.get_alpha() is None:
            surf = surf.convert_alpha()
        else:
            surf = surf.convert_alpha()
        return split_particle_sprite_sheet(surf)
    except Exception:
        return []


def spawn_mining_rows_particles(
    system: MiningParticleSystem,
    layout: WordMemorizeLayout,
    box: WordMemorizeBox,
    *,
    from_row: int,
    to_row: int,
    tile_px: int,
    frame_width: int,
    frame_height: int,
    sprites: list[pygame.Surface],
    box_key: str | None = None,
    revealed_box_keys: set[str] | None = None,
    rng: random.Random | None = None,
) -> None:
    """새로 부서진 타일 칸(가장자리·인접 빈 영역 포함)에 파티클 생성."""
    from extra.table_editor.services.word_memorize_layout import layout_tile_band_y
    from studio.studios.word_memorize_pick import (
        box_runtime_key,
        collect_mining_punch_rects,
    )

    if not layout_game_particles(layout) or not sprites:
        return
    start = max(0, int(from_row))
    end = max(start, int(to_row))
    if end <= start:
        return
    key = box_key or box_runtime_key(box)
    band_y0, band_y1 = layout_tile_band_y(
        int(frame_height),
        margin_top_ratio=float(layout.margin_top_ratio),
        margin_bottom_ratio=float(layout.margin_bottom_ratio),
        tile_px=tile_px,
    )
    punch_kw = {
        "tile_px": tile_px,
        "frame_width": frame_width,
        "frame_height": frame_height,
        "box_key": key,
        "include_vertical_fringe": False,
        "tile_band_y0": band_y0,
        "tile_band_y1": band_y1,
        "layout": layout,
        "revealed_box_keys": revealed_box_keys or set(),
    }
    # 채굴 완료 시 상·하 vertical fringe는 타일 구멍 연출용이며,
    # 곡괭이 위치와 무관 — 파티클은 실제 행 채굴 diff만 반영한다.
    prev_rects = {
        (rect.x, rect.y)
        for rect in collect_mining_punch_rects(
            box,
            completed_rows=start,
            **punch_kw,
        )
    }
    new_rects = collect_mining_punch_rects(
        box,
        completed_rows=end,
        **punch_kw,
    )
    randomizer = rng or random.Random()
    for rect in new_rects:
        if (rect.x, rect.y) in prev_rects:
            continue
        system.spawn_at_center(
            float(rect.centerx),
            float(rect.centery),
            tile_px=tile_px,
            sprites=sprites,
            rng=randomizer,
        )
