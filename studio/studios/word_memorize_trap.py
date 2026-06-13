"""단어 외우기 — trap 발동 시 디스크 조각모음식 랜덤 타일 채우기 → 최초 밴드 복원."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pygame

from data.models import Word
from extra.table_editor.services.word_memorize_layout import (
    TRAP_CARD_SCALE_END,
    TRAP_CARD_SCALE_START,
    TRAP_CARD_SIZE_UP_SEC,
    TRAP_REGROW_SEC,
    TRAP_REGROW_SEC_MAX,
    TRAP_REGROW_HOLD_SEC,
    PICK_REVEAL_SEC,
    WordMemorizeBox,
    WordMemorizeLayout,
    box_uses_mining_regrow,
    box_uses_trap,
    game_tile_display_px,
    layout_tile_band_y,
    word_memorize_game_trap_dir,
    word_memorize_game_trap_path,
)
from studio.studios.word_memorize_pick import (
    box_runtime_key,
    card_mining_row_count,
    card_mining_state,
    collect_layout_mining_punch_rects,
    pick_reveal_progress,
    punch_mining_rects,
)

# 조각모음식 타일 채우기 — 전체 구간·타일당 스냅
TRAP_DEFRAG_FILL_SEC = 1.05
TRAP_DEFRAG_TILE_SEC = 0.085
TRAP_DEFRAG_START_JITTER_SEC = 0.14
TRAP_DEFRAG_LERP_POWER = 1.12
# 착지 연기 — 타일보다 큼직하게(약 5배), 착지마다 소수만
TRAP_SMOKE_POSITION_NOISE_RATIO = 0.32
TRAP_SMOKE_SIZE_MIN_RATIO = 2.50
TRAP_SMOKE_SIZE_MAX_RATIO = 5.75
TRAP_SMOKE_LAND_SAMPLE_CHANCE = 0.04
TRAP_SMOKE_LIFETIME_MIN_SEC = 0.42
TRAP_SMOKE_LIFETIME_MAX_SEC = 1.15
TRAP_SMOKE_FADE_POWER_MIN = 0.62
TRAP_SMOKE_FADE_POWER_MAX = 2.35
TRAP_SMOKE_PUFF_CHANCE = 1.0
TRAP_SMOKE_EXTRA_PUFF_CHANCE = 0.0
_defrag_schedule_cache: dict[tuple[Any, ...], list["TrapDefragFill"]] = {}
_defrag_sprite_cache: dict[tuple[Any, ...], pygame.Surface] = {}
# trap_regrow 오버레이 캐시 양자화 FPS (낮을수록 재생성 횟수 감소)
TRAP_REGROW_OVERLAY_FPS = 15.0


def clear_trap_regrow_cache() -> None:
    """trap 조각모음 스케줄·오버레이 캐시 무효화."""
    from studio.studios.word_memorize_pick import clear_regrow_overlay_cache

    _defrag_schedule_cache.clear()
    _defrag_sprite_cache.clear()
    _mining_complete_elapsed_cache.clear()
    clear_regrow_overlay_cache()


@dataclass(frozen=True)
class TrapDefragFill:
    """빈 칸 한 개 — 랜덤 위치에서 목표 칸으로 스냅."""

    col: int
    target_y: int
    start_x: float
    start_y: float
    fill_start: float
    land_time: float


@dataclass(frozen=True)
class TrapDefragCellState:
    """조각모음 한 칸의 보간 상태."""

    current_x: float
    current_y: float
    target_x: int
    target_y: int
    is_landed: bool
    is_active: bool
    land_time_sec: float


def _mining_snapshot_key(
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int],
) -> tuple[Any, ...]:
    return (
        frozenset(revealed_box_keys),
        tuple(sorted((k, int(v)) for k, v in revealed_rows_by_key.items())),
    )


def _punched_band_cells(
    layout: WordMemorizeLayout,
    *,
    band_y0: int,
    row_count: int,
    col_end: int,
    tile_px: int,
    frame_width: int,
    frame_height: int,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int],
    words_by_id: dict[int, Word] | None = None,
    card_meaning_by_id: dict[int, str] | None = None,
    meaning_lang: str = "ko",
) -> set[tuple[int, int]]:
    """밴드 격자 (col, row_index) 중 채굴로 비어 있는 칸."""
    px = max(1, int(tile_px))
    punched: set[tuple[int, int]] = set()
    for rect in collect_layout_mining_punch_rects(
        layout,
        revealed_box_keys=revealed_box_keys,
        revealed_rows_by_key=revealed_rows_by_key,
        tile_px=px,
        frame_width=frame_width,
        frame_height=frame_height,
        words_by_id=words_by_id,
        card_meaning_by_id=card_meaning_by_id,
        meaning_lang=meaning_lang,
    ):
        col = int(rect.x) // px
        row_index = (int(rect.y) - int(band_y0)) // px
        if 0 <= row_index < row_count and 0 <= col < col_end:
            punched.add((col, row_index))
    return punched


def _defrag_schedule_seed(
    cache_key: tuple[Any, ...],
    punched: set[tuple[int, int]],
) -> random.Random:
    """스냅샷마다 동일한 조각모음 순서."""
    tag = repr(cache_key) + repr(sorted(punched))
    return random.Random(hash(tag) & 0xFFFFFFFF)


def build_trap_defrag_schedule(
    layout: WordMemorizeLayout,
    *,
    frame_width: int,
    frame_height: int,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int],
    tile_px: int | None = None,
    words_by_id: dict[int, Word] | None = None,
    card_meaning_by_id: dict[int, str] | None = None,
    meaning_lang: str = "ko",
) -> tuple[list[TrapDefragFill], int, int, int]:
    """비어 있는 밴드 칸 — 랜덤 순서·랜덤 출발 위치에서 채움."""
    px = max(1, int(tile_px or game_tile_display_px(frame_width=int(frame_width))))
    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    y0, y1 = layout_tile_band_y(
        fh,
        margin_top_ratio=float(layout.margin_top_ratio),
        margin_bottom_ratio=float(layout.margin_bottom_ratio),
        tile_px=px,
    )
    if y1 <= y0:
        y1 = y0 + px
    row_count = max(1, int(math.ceil((y1 - y0) / float(px))))
    col_end = (fw + px - 1) // px
    cache_key = (
        fw,
        fh,
        px,
        float(layout.margin_top_ratio),
        float(layout.margin_bottom_ratio),
        row_count,
        col_end,
        _mining_snapshot_key(
            revealed_box_keys,
            revealed_rows_by_key,
        ),
    )
    cached = _defrag_schedule_cache.get(cache_key)
    if cached is not None:
        return cached, row_count, y0, col_end
    punched = _punched_band_cells(
        layout,
        band_y0=y0,
        row_count=row_count,
        col_end=col_end,
        tile_px=px,
        frame_width=fw,
        frame_height=fh,
        revealed_box_keys=revealed_box_keys,
        revealed_rows_by_key=revealed_rows_by_key,
        words_by_id=words_by_id,
        card_meaning_by_id=card_meaning_by_id,
        meaning_lang=meaning_lang,
    )
    cells = list(punched)
    rng = _defrag_schedule_seed(cache_key, punched)
    rng.shuffle(cells)
    count = len(cells)
    schedule: list[TrapDefragFill] = []
    span = max(1e-6, float(TRAP_DEFRAG_FILL_SEC) - float(TRAP_DEFRAG_TILE_SEC))
    for index, (col, row_index) in enumerate(cells):
        target_y = y0 + row_index * px
        start_col = rng.randint(0, max(0, col_end - 1))
        start_row = rng.randint(0, max(0, row_count - 1))
        start_x = float(start_col * px)
        start_y = float(y0 + start_row * px)
        if count <= 1:
            fill_start = rng.random() * TRAP_DEFRAG_START_JITTER_SEC * 0.35
        else:
            fill_start = (float(index) / float(count - 1)) * span
            fill_start += rng.random() * TRAP_DEFRAG_START_JITTER_SEC
        land_time = fill_start + float(TRAP_DEFRAG_TILE_SEC)
        schedule.append(
            TrapDefragFill(
                col=col,
                target_y=target_y,
                start_x=start_x,
                start_y=start_y,
                fill_start=fill_start,
                land_time=land_time,
            )
        )
    _defrag_schedule_cache[cache_key] = schedule
    return schedule, row_count, y0, col_end


def build_trap_gravity_schedule(
    layout: WordMemorizeLayout,
    *,
    frame_width: int,
    frame_height: int,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int],
    tile_px: int | None = None,
) -> tuple[list[TrapDefragFill], int, int, int]:
    """하위 호환 — 조각모음 스케줄."""
    return build_trap_defrag_schedule(
        layout,
        frame_width=frame_width,
        frame_height=frame_height,
        revealed_box_keys=revealed_box_keys,
        revealed_rows_by_key=revealed_rows_by_key,
        tile_px=tile_px,
    )


def trap_defrag_last_land_time(schedule: list[TrapDefragFill]) -> float:
    """마지막 타일 스냅 완료 시각."""
    if not schedule:
        return 0.0
    return max(item.land_time for item in schedule)


def trap_gravity_last_land_time(schedule: list[TrapDefragFill]) -> float:
    """하위 호환."""
    return trap_defrag_last_land_time(schedule)


def _restore_pristine_tile_band(
    layer: pygame.Surface,
    pristine_layer: pygame.Surface,
    *,
    band_y0: int,
    row_count: int,
    frame_width: int,
    frame_height: int,
    tile_px: int,
) -> None:
    """타일 밴드 전체를 최초(꽉 찬) 상태로 복원."""
    px = max(1, int(tile_px))
    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    band_h = min(row_count * px, max(0, fh - band_y0))
    if band_h <= 0:
        return
    src = pygame.Rect(0, band_y0, fw, band_h)
    layer.blit(pristine_layer, (0, band_y0), src)


def layout_trap_regrow_duration_sec(
    layout: WordMemorizeLayout,
    *,
    revealed_box_keys: set[str] | None = None,
    revealed_rows_by_key: dict[str, int] | None = None,
    words_by_id: dict[int, Word] | None = None,
    card_meaning_by_id: dict[int, str] | None = None,
    meaning_lang: str = "ko",
) -> float:
    """타일 채우기 구간 길이(초) — 연기 소멸 대기는 재생 로직에서 별도 처리."""
    keys = revealed_box_keys if revealed_box_keys is not None else set()
    rows = dict(revealed_rows_by_key or {})
    schedule, _, _, _ = build_trap_defrag_schedule(
        layout,
        frame_width=int(layout.frame_width),
        frame_height=int(layout.frame_height),
        revealed_box_keys=keys,
        revealed_rows_by_key=rows,
        words_by_id=words_by_id,
        card_meaning_by_id=card_meaning_by_id,
        meaning_lang=meaning_lang,
    )
    if not schedule:
        return float(TRAP_REGROW_SEC)
    last_land = trap_defrag_last_land_time(schedule)
    return min(
        TRAP_REGROW_SEC_MAX,
        max(TRAP_REGROW_SEC, last_land + float(TRAP_REGROW_HOLD_SEC)),
    )


def trap_defrag_cell_state(
    fill_start: float,
    land_time: float,
    *,
    start_x: float,
    start_y: float,
    target_x: int,
    target_y: int,
    elapsed_sec: float,
) -> TrapDefragCellState:
    """랜덤 출발 → 목표 칸 직선 보간(중력 없음)."""
    if elapsed_sec < fill_start:
        return TrapDefragCellState(
            current_x=start_x,
            current_y=start_y,
            target_x=target_x,
            target_y=target_y,
            is_landed=False,
            is_active=False,
            land_time_sec=land_time,
        )
    if elapsed_sec >= land_time:
        return TrapDefragCellState(
            current_x=float(target_x),
            current_y=float(target_y),
            target_x=target_x,
            target_y=target_y,
            is_landed=True,
            is_active=False,
            land_time_sec=land_time,
        )
    t = (elapsed_sec - fill_start) / max(1e-6, land_time - fill_start)
    eased = math.pow(max(0.0, min(1.0, t)), TRAP_DEFRAG_LERP_POWER)
    current_x = start_x + (float(target_x) - start_x) * eased
    current_y = start_y + (float(target_y) - start_y) * eased
    return TrapDefragCellState(
        current_x=current_x,
        current_y=current_y,
        target_x=target_x,
        target_y=target_y,
        is_landed=False,
        is_active=True,
        land_time_sec=land_time,
    )


def collect_trap_fall_land_impacts(
    layout: WordMemorizeLayout,
    *,
    prev_elapsed_sec: float,
    curr_elapsed_sec: float,
    frame_width: int,
    frame_height: int,
    revealed_box_keys: set[str] | None = None,
    revealed_rows_by_key: dict[str, int] | None = None,
    words_by_id: dict[int, Word] | None = None,
    card_meaning_by_id: dict[int, str] | None = None,
    meaning_lang: str = "ko",
) -> list[tuple[float, float]]:
    """이번 프레임에 착지한 타일 중심 — 연기 이펙트용."""
    if curr_elapsed_sec <= prev_elapsed_sec:
        return []
    keys = revealed_box_keys if revealed_box_keys is not None else set()
    rows = dict(revealed_rows_by_key or {})
    px = game_tile_display_px(frame_width=int(frame_width))
    schedule, _, _, _ = build_trap_defrag_schedule(
        layout,
        frame_width=frame_width,
        frame_height=frame_height,
        tile_px=px,
        revealed_box_keys=keys,
        revealed_rows_by_key=rows,
        words_by_id=words_by_id,
        card_meaning_by_id=card_meaning_by_id,
        meaning_lang=meaning_lang,
    )
    prev_t = max(0.0, float(prev_elapsed_sec))
    curr_t = max(0.0, float(curr_elapsed_sec))
    centers: list[tuple[float, float]] = []
    for fill in schedule:
        if prev_t < fill.land_time <= curr_t:
            cx = fill.col * px + px * 0.5
            cy = fill.target_y + px * 0.5
            centers.append((cx, cy))
    return centers


def _sprite_for_defrag_fill(
    pristine_layer: pygame.Surface,
    fill: TrapDefragFill,
    *,
    tile_px: int,
) -> pygame.Surface:
    """목표 칸 타일 조각 — pristine subsurface 캐시."""
    px = max(1, int(tile_px))
    cache_key = (id(pristine_layer), int(fill.col), int(fill.target_y), px)
    cached = _defrag_sprite_cache.get(cache_key)
    if cached is not None:
        return cached
    cell_x = fill.col * px
    src_rect = pygame.Rect(cell_x, fill.target_y, px, px)
    sprite = pristine_layer.subsurface(src_rect).copy()
    _defrag_sprite_cache[cache_key] = sprite
    return sprite


def apply_full_frame_trap_regrow(
    layer: pygame.Surface,
    layout: WordMemorizeLayout,
    *,
    pristine_layer: pygame.Surface,
    elapsed_sec: float,
    frame_width: int,
    frame_height: int,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int],
    regrow_sec: float = 0.0,
    words_by_id: dict[int, Word] | None = None,
    card_meaning_by_id: dict[int, str] | None = None,
    meaning_lang: str = "ko",
) -> None:
    """조각모음식 랜덤 채우기 후 최초 타일 밴드와 동일 화면."""
    _ = regrow_sec
    px = game_tile_display_px(frame_width=int(frame_width))
    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    schedule, row_count, band_y0, _col_end = build_trap_defrag_schedule(
        layout,
        frame_width=fw,
        frame_height=fh,
        tile_px=px,
        revealed_box_keys=revealed_box_keys,
        revealed_rows_by_key=revealed_rows_by_key,
        words_by_id=words_by_id,
        card_meaning_by_id=card_meaning_by_id,
        meaning_lang=meaning_lang,
    )
    last_land = trap_defrag_last_land_time(schedule)
    if not schedule or elapsed_sec >= last_land:
        _restore_pristine_tile_band(
            layer,
            pristine_layer,
            band_y0=band_y0,
            row_count=row_count,
            frame_width=fw,
            frame_height=fh,
            tile_px=px,
        )
        return

    for fill in schedule:
        cell_x = fill.col * px
        target_x = cell_x
        if cell_x + px > fw or fill.target_y + px > fh:
            continue
        state = trap_defrag_cell_state(
            fill.fill_start,
            fill.land_time,
            start_x=fill.start_x,
            start_y=fill.start_y,
            target_x=target_x,
            target_y=fill.target_y,
            elapsed_sec=elapsed_sec,
        )
        if not state.is_landed and not state.is_active:
            continue
        if state.is_landed:
            sprite = _sprite_for_defrag_fill(
                pristine_layer, fill, tile_px=px
            )
            layer.blit(sprite, (cell_x, fill.target_y))
            continue
        tile_copy = _sprite_for_defrag_fill(
            pristine_layer, fill, tile_px=px
        )
        draw_x = int(round(state.current_x))
        draw_y = int(round(state.current_y))
        if draw_x + px > 0 and draw_y < fh and draw_y + px > 0 and draw_x < fw:
            layer.blit(tile_copy, (draw_x, draw_y))


def load_trap_surface(path: Path, max_w: int, max_h: int) -> pygame.Surface | None:
    """trap 카드 PNG — 지정 inner(w×h)에 맞게 스케일."""
    if max_w <= 0 or max_h <= 0 or not path.is_file():
        return None
    try:
        surf = pygame.image.load(str(path))
        if surf.get_alpha() is None:
            surf = surf.convert_alpha()
        else:
            surf = surf.convert_alpha()
        w, h = surf.get_size()
        if w <= 0 or h <= 0:
            return None
        nw = max(1, int(max_w))
        nh = max(1, int(max_h))
        if (w, h) != (nw, nh):
            surf = pygame.transform.smoothscale(surf, (nw, nh))
        return surf
    except Exception:
        return None


def draw_trap_on_rect(
    surface: pygame.Surface,
    trap: pygame.Surface,
    rect: pygame.Rect,
    *,
    alpha: int = 255,
) -> None:
    """박스 inner 영역에 trap 이미지."""
    if alpha <= 0:
        return
    if alpha >= 255:
        surface.blit(trap, rect.topleft)
        return
    img = trap.copy()
    img.set_alpha(int(alpha))
    surface.blit(img, rect.topleft)


_mining_complete_elapsed_cache: dict[tuple[Any, ...], float] = {}


def estimate_trap_card_mining_complete_elapsed(
    box: WordMemorizeBox,
    *,
    tile_px: int,
) -> float:
    """채굴이 끝나는 시각(초) — fade 시작점."""
    px = max(1, int(tile_px))
    cache_key = (box_runtime_key(box), int(box.x), int(box.y), int(box.w), int(box.h), px)
    cached = _mining_complete_elapsed_cache.get(cache_key)
    if cached is not None:
        return cached
    reveal_sec = float(PICK_REVEAL_SEC)
    complete_at = reveal_sec
    for step in range(120):
        t = reveal_sec * float(step) / 119.0
        if card_mining_state(box, t, tile_px=px, stored_completed_rows=0).is_complete:
            complete_at = t
            break
    _mining_complete_elapsed_cache[cache_key] = complete_at
    return complete_at


def should_show_trap_card_image(
    box: WordMemorizeBox,
    *,
    pick_mining: bool,
    runtime_key: str,
    revealed_keys: set[str],
    revealed_rows_by_key: dict[str, int],
    is_active: bool,
    active_elapsed_sec: float,
    tile_px: int,
) -> bool:
    """구 trap 이미지 카드 — CTA 타입으로 대체되어 항상 False."""
    _ = (
        box,
        pick_mining,
        runtime_key,
        revealed_keys,
        revealed_rows_by_key,
        is_active,
        active_elapsed_sec,
        tile_px,
    )
    return False


def trap_card_mining_complete(
    box: WordMemorizeBox,
    *,
    runtime_key: str,
    revealed_keys: set[str],
    revealed_rows_by_key: dict[str, int],
    is_active: bool,
    active_elapsed_sec: float,
    tile_px: int,
) -> bool:
    """trap 카드 채굴이 끝났는지."""
    if runtime_key in revealed_keys:
        return True
    row_count = card_mining_row_count(box, tile_px)
    if int(revealed_rows_by_key.get(runtime_key, 0)) >= row_count:
        return True
    if is_active:
        stored = int(revealed_rows_by_key.get(runtime_key, 0))
        return card_mining_state(
            box,
            active_elapsed_sec,
            tile_px=tile_px,
            stored_completed_rows=stored,
        ).is_complete
    return False


def trap_card_reveal_scale(
    box: WordMemorizeBox,
    *,
    runtime_key: str,
    revealed_keys: set[str],
    revealed_rows_by_key: dict[str, int],
    is_active: bool,
    active_elapsed_sec: float,
    tile_px: int,
    trap_regrow_active: bool = False,
) -> float | None:
    """CTA 카드 — 채굴 완료 후 size-up 배율. 진행 전·비-regrow이면 None."""
    if not box_uses_mining_regrow(box):
        return None
    if trap_regrow_active:
        return float(TRAP_CARD_SCALE_END)
    if not trap_card_mining_complete(
        box,
        runtime_key=runtime_key,
        revealed_keys=revealed_keys,
        revealed_rows_by_key=revealed_rows_by_key,
        is_active=is_active,
        active_elapsed_sec=active_elapsed_sec,
        tile_px=tile_px,
    ):
        return None
    fade_sec = max(1e-6, float(TRAP_CARD_SIZE_UP_SEC))
    if is_active:
        complete_at = estimate_trap_card_mining_complete_elapsed(box, tile_px=tile_px)
        grow_t = max(0.0, float(active_elapsed_sec) - complete_at)
    else:
        grow_t = fade_sec
    ratio = max(0.0, min(1.0, grow_t / fade_sec))
    eased = 1.0 - (1.0 - ratio) ** 2.0
    start = float(TRAP_CARD_SCALE_START)
    end = float(TRAP_CARD_SCALE_END)
    return start + (end - start) * eased


_smoke_sprite_cache: pygame.Surface | None = None
_smoke_sprite_loaded = False


def word_memorize_trap_land_smoke_path() -> Path:
    """trap 타일 착지 연기 PNG."""
    return word_memorize_game_trap_dir() / "smoke.png"


def _prepare_smoke_sprite(surface: pygame.Surface) -> pygame.Surface:
    """검은 배경 PNG — 알파 없으면 colorkey 처리."""
    if surface.get_alpha() is not None:
        return surface.convert_alpha()
    keyed = surface.convert()
    keyed.set_colorkey((0, 0, 0))
    return keyed.convert_alpha()


def load_trap_land_smoke_sprite() -> pygame.Surface | None:
    """착지 연기 스프라이트 — 최초 1회 로드·캐시."""
    global _smoke_sprite_cache, _smoke_sprite_loaded
    if _smoke_sprite_loaded:
        return _smoke_sprite_cache
    _smoke_sprite_loaded = True
    path = word_memorize_trap_land_smoke_path()
    if not path.is_file():
        return None
    try:
        surf = pygame.image.load(str(path))
        _smoke_sprite_cache = _prepare_smoke_sprite(surf)
    except Exception:
        _smoke_sprite_cache = None
    return _smoke_sprite_cache


@dataclass
class TrapLandSmokePuff:
    """활성 착지 연기 한 덩어리."""

    x: float
    y: float
    sprite: pygame.Surface
    age_sec: float
    lifetime_sec: float
    fade_power: float


@dataclass
class TrapLandSmokeSystem:
    """trap 타일 착지 시 연기 — 위치·크기·페이드 속도 랜덤."""

    puffs: list[TrapLandSmokePuff] = field(default_factory=list)

    def clear(self) -> None:
        """모든 연기 제거."""
        self.puffs.clear()

    def tick(self, dt_sec: float) -> None:
        """수명 갱신."""
        if dt_sec <= 0.0 or not self.puffs:
            return
        alive: list[TrapLandSmokePuff] = []
        for puff in self.puffs:
            age = puff.age_sec + dt_sec
            if age >= puff.lifetime_sec:
                continue
            alive.append(
                TrapLandSmokePuff(
                    x=puff.x,
                    y=puff.y,
                    sprite=puff.sprite,
                    age_sec=age,
                    lifetime_sec=puff.lifetime_sec,
                    fade_power=puff.fade_power,
                )
            )
        self.puffs = alive

    def has_visible_puffs(self) -> bool:
        """화면에 그려지는 연기가 남아 있는지."""
        for puff in self.puffs:
            life = max(1e-6, puff.lifetime_sec)
            t = max(0.0, min(1.0, puff.age_sec / life))
            alpha = int(round(255.0 * (1.0 - t) ** puff.fade_power))
            if alpha > 0:
                return True
        return False

    def spawn_land_impacts(
        self,
        land_centers: list[tuple[float, float]],
        *,
        tile_px: int,
        rng: random.Random | None = None,
    ) -> None:
        """착지 좌표마다 연기 생성 — 큰 연기만, 착지 이벤트 중 일부만."""
        base = load_trap_land_smoke_sprite()
        if base is None or tile_px <= 0 or not land_centers:
            return
        randomizer = rng or random.Random()
        for center_x, center_y in land_centers:
            if randomizer.random() > TRAP_SMOKE_LAND_SAMPLE_CHANCE:
                continue
            self._spawn_puff(
                base,
                center_x,
                center_y,
                tile_px=tile_px,
                rng=randomizer,
            )

    def _spawn_puff(
        self,
        base: pygame.Surface,
        center_x: float,
        center_y: float,
        *,
        tile_px: int,
        rng: random.Random,
    ) -> None:
        if rng.random() > TRAP_SMOKE_PUFF_CHANCE:
            return
        noise = float(tile_px) * TRAP_SMOKE_POSITION_NOISE_RATIO
        x = center_x + rng.uniform(-noise, noise)
        y = center_y + rng.uniform(-noise * 0.42, noise * 0.38)
        size_ratio = rng.uniform(TRAP_SMOKE_SIZE_MIN_RATIO, TRAP_SMOKE_SIZE_MAX_RATIO)
        display_px = max(int(tile_px * TRAP_SMOKE_SIZE_MIN_RATIO), int(round(float(tile_px) * size_ratio)))
        scaled = pygame.transform.smoothscale(base, (display_px, display_px))
        self.puffs.append(
            TrapLandSmokePuff(
                x=x,
                y=y,
                sprite=scaled,
                age_sec=0.0,
                lifetime_sec=rng.uniform(
                    TRAP_SMOKE_LIFETIME_MIN_SEC, TRAP_SMOKE_LIFETIME_MAX_SEC
                ),
                fade_power=rng.uniform(
                    TRAP_SMOKE_FADE_POWER_MIN, TRAP_SMOKE_FADE_POWER_MAX
                ),
            )
        )

    def draw(self, surface: pygame.Surface) -> None:
        """알파 페이드와 함께 연기 그리기."""
        if not self.puffs:
            return
        for puff in self.puffs:
            life = max(1e-6, puff.lifetime_sec)
            t = max(0.0, min(1.0, puff.age_sec / life))
            alpha = int(round(255.0 * (1.0 - t) ** puff.fade_power))
            if alpha <= 0:
                continue
            img = puff.sprite.copy()
            img.set_alpha(alpha)
            rect = img.get_rect(
                center=(int(round(puff.x)), int(round(puff.y)))
            )
            surface.blit(img, rect)
