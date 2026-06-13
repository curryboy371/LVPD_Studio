"""단어 외우기 — 곡괭이 채굴(타일 제거) 연출."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pygame

from core.paths import get_repo_root
from extra.table_editor.services.word_memorize_layout import (
    MINING_ROWS_PER_SWING,
    PICK_REVEAL_SEC,
    PICK_ROTATION_STRETCH,
    TRAP_REGROW_SEC,
    WordMemorizeBox,
    WordMemorizeLayout,
    box_runtime_key,
    game_tile_display_px,
    layout_tile_band_y,
    layout_uses_pick_mining,
    snap_tile_coord,
    tile_fits_in_band,
    word_memorize_game_pick_path,
)

# 곡괭이 타격 효과음 — resource/sound/effect/pick.mp3
WORD_MEMORIZE_PICK_SOUND_REL = "resource/sound/effect/pick.mp3"
# 타일 파괴 — resource/sound/effect/fall/*.mp3 랜덤
WORD_MEMORIZE_FALL_SOUND_DIR_REL = "resource/sound/effect/fall"
# 타일 재생성(hamer) — resource/sound/effect/hamer/*.mp3 랜덤
WORD_MEMORIZE_HAMER_SOUND_DIR_REL = "resource/sound/effect/hamer"
_EFFECT_SOUND_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
_effect_sound_dir_cache: dict[str, list[Path]] = {}
# 카드 밖 빈 영역으로 퍼지는 타일 칸 수
MINING_FRINGE_TILES = 5
# 카드 가장자리 타일 — 남길 확률(불규칙 윤곽)
MINING_EDGE_KEEP_CHANCE = 0.24
# 채굴 전선(맨 아래 완료 행) — 일부 남기기 / 한 칸 더 파기
MINING_FRONTIER_KEEP_CHANCE = 0.30
MINING_OVERDIG_CHANCE = 0.34
# 카드 밖 인접 타일 — 거리별 제거 확률(멀수록 감소)
MINING_VOID_FRINGE_CHANCE = (0.70, 0.54, 0.40, 0.26, 0.15)
# 카드 전체 완료 시 상·하 빈 영역 제거 확률
MINING_VERTICAL_VOID_FRINGE_CHANCE = (0.60, 0.46, 0.32, 0.18)
_punch_rect_cache: dict[tuple[Any, ...], list[pygame.Rect]] = {}


def clear_mining_punch_rect_cache() -> None:
    """채굴 타일 제거 캐시 무효화."""
    _punch_rect_cache.clear()


def _box_punch_cache_key(box: WordMemorizeBox) -> tuple[int, int, int, int, str]:
    return (
        int(box.x),
        int(box.y),
        int(box.w),
        int(box.h),
        str(getattr(box, "box_key", "") or ""),
    )


@dataclass(frozen=True)
class CardMiningState:
    """카드 한 장의 행 단위 채굴 상태."""

    row_count: int
    completed_rows: int
    active_row: int
    row_progress: float
    pick_rotation_deg: float
    pick_x: int
    pick_y: int
    is_complete: bool


def word_memorize_pick_sound_path() -> Path:
    """곡괭이 타격 효과음 절대 경로."""
    return get_repo_root() / WORD_MEMORIZE_PICK_SOUND_REL.replace("\\", "/")


def _list_effect_sound_paths(dir_rel: str, *, refresh: bool = False) -> list[Path]:
    """effect 하위 폴더 오디오 목록 (dir_rel 키 캐시)."""
    key = dir_rel.replace("\\", "/")
    if not refresh and key in _effect_sound_dir_cache:
        return list(_effect_sound_dir_cache[key])
    sound_dir = get_repo_root() / key
    paths: list[Path] = []
    if sound_dir.is_dir():
        for path in sorted(sound_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in _EFFECT_SOUND_EXTS:
                paths.append(path.resolve())
    _effect_sound_dir_cache[key] = paths
    return list(paths)


def list_word_memorize_fall_sound_paths(*, refresh: bool = False) -> list[Path]:
    """타일 파괴 효과음 목록 — resource/sound/effect/fall."""
    return _list_effect_sound_paths(WORD_MEMORIZE_FALL_SOUND_DIR_REL, refresh=refresh)


def pick_random_word_memorize_fall_sound_path() -> Path | None:
    """타일 파괴 — fall 폴더에서 무작위 1개."""
    paths = list_word_memorize_fall_sound_paths()
    if not paths:
        return None
    return random.choice(paths)


def list_word_memorize_hamer_sound_paths(*, refresh: bool = False) -> list[Path]:
    """타일 재생성용 hammer 효과음 목록 — resource/sound/effect/hamer."""
    return _list_effect_sound_paths(WORD_MEMORIZE_HAMER_SOUND_DIR_REL, refresh=refresh)


def pick_random_word_memorize_hamer_sound_path() -> Path | None:
    """타일 재생성(hamer) — hamer 폴더에서 무작위 1개."""
    paths = list_word_memorize_hamer_sound_paths()
    if not paths:
        return None
    return random.choice(paths)


def pick_reveal_progress(elapsed_sec: float, *, reveal_sec: float = PICK_REVEAL_SEC) -> float:
    """0~1 채굴 진행률 (카드 전체)."""
    if reveal_sec <= 0:
        return 1.0
    return max(0.0, min(1.0, float(elapsed_sec) / float(reveal_sec)))


def card_mining_swing_index(
    box: WordMemorizeBox,
    elapsed_sec: float,
    *,
    tile_px: int,
    reveal_sec: float = PICK_REVEAL_SEC,
    rows_per_swing: int = MINING_ROWS_PER_SWING,
) -> int:
    """현재 곡괭이 스윙 인덱스 (0부터, 채굴 완료 시 마지막 스윙)."""
    row_count = card_mining_row_count(box, tile_px)
    if row_count <= 0:
        return 0
    per_swing = max(1, int(rows_per_swing))
    swing_count = card_mining_swing_count(row_count, rows_per_swing=per_swing)
    if swing_count <= 0:
        return 0
    swing_duration = reveal_sec / float(swing_count)
    swing_units = (
        max(0.0, float(elapsed_sec)) / swing_duration if swing_duration > 0 else 0.0
    )
    return max(0, min(swing_count - 1, int(swing_units)))


def card_mining_row_count(box: WordMemorizeBox, tile_px: int) -> int:
    """카드와 겹치는 전역 타일 행 수 (격자 정렬)."""
    px = max(1, int(tile_px))
    card_top = int(box.y)
    card_bottom = card_top + max(1, int(box.h))
    grid_top = snap_tile_coord(card_top, px)
    if card_bottom <= grid_top:
        return 1
    return max(1, (card_bottom - grid_top + px - 1) // px)


def card_mining_row_band_y(box: WordMemorizeBox, row_index: int, tile_px: int) -> tuple[int, int]:
    """행 index의 [top, bottom) y — 전역 격자상 정사각형 타일 한 칸."""
    px = max(1, int(tile_px))
    grid_top = snap_tile_coord(int(box.y), px)
    row_top = grid_top + int(row_index) * px
    return row_top, row_top + px


def card_mining_row_center_y(box: WordMemorizeBox, row_index: int, tile_px: int) -> int:
    """곡괭이 y — 해당 행 중앙."""
    row_top, row_bottom = card_mining_row_band_y(box, row_index, tile_px)
    if row_bottom <= row_top:
        return row_top
    return (row_top + row_bottom) // 2


def card_mining_swing_count(
    row_count: int, *, rows_per_swing: int = MINING_ROWS_PER_SWING
) -> int:
    """곡괭이 스윙 횟수 — rows_per_swing 행씩 제거."""
    rows = max(1, int(row_count))
    per = max(1, int(rows_per_swing))
    return max(1, int(math.ceil(rows / float(per))))


def card_mining_band_center_y(
    box: WordMemorizeBox,
    top_row: int,
    *,
    tile_px: int,
    row_count: int,
    rows_per_swing: int = MINING_ROWS_PER_SWING,
) -> int:
    """현재 스윙 밴드(최대 rows_per_swing 행)의 y 중앙."""
    top = max(0, min(int(top_row), row_count - 1))
    bottom = min(row_count - 1, top + max(1, int(rows_per_swing)) - 1)
    y_top, _ = card_mining_row_band_y(box, top, tile_px)
    _, y_bottom = card_mining_row_band_y(box, bottom, tile_px)
    return (y_top + y_bottom) // 2


def card_mining_state(
    box: WordMemorizeBox,
    elapsed_sec: float,
    *,
    tile_px: int,
    reveal_sec: float = PICK_REVEAL_SEC,
    stored_completed_rows: int = 0,
    rows_per_swing: int = MINING_ROWS_PER_SWING,
) -> CardMiningState:
    """맨 위부터 rows_per_swing 행씩 — 타일은 reveal_sec 유지, 곡괭이는 더 천천히 회전."""
    row_count = card_mining_row_count(box, tile_px)
    per_swing = max(1, int(rows_per_swing))
    pick_x = int(box.x) + int(box.w) // 2
    stored = max(0, min(int(stored_completed_rows), row_count))

    if stored >= row_count or elapsed_sec <= 0.0:
        if stored >= row_count:
            return CardMiningState(
                row_count=row_count,
                completed_rows=row_count,
                active_row=max(0, row_count - 1),
                row_progress=1.0,
                pick_rotation_deg=360.0,
                pick_x=pick_x,
                pick_y=card_mining_band_center_y(
                    box, max(0, row_count - 1), tile_px=tile_px, row_count=row_count
                ),
                is_complete=True,
            )
        return CardMiningState(
            row_count=row_count,
            completed_rows=stored,
            active_row=0,
            row_progress=0.0,
            pick_rotation_deg=0.0,
            pick_x=pick_x,
            pick_y=card_mining_band_center_y(
                box, 0, tile_px=tile_px, row_count=row_count, rows_per_swing=per_swing
            ),
            is_complete=False,
        )

    swing_count = card_mining_swing_count(row_count, rows_per_swing=per_swing)
    swing_duration = reveal_sec / float(swing_count) if swing_count > 0 else reveal_sec
    swing_units = (
        float(elapsed_sec) / swing_duration if swing_duration > 0 else float(swing_count)
    )
    swing_index = int(swing_units)
    swing_progress = swing_units - math.floor(swing_units)

    completed_from_elapsed = min(
        row_count,
        swing_index * per_swing + int(swing_progress * per_swing),
    )
    completed_rows = max(stored, completed_from_elapsed)
    row_progress = swing_progress

    if completed_rows >= row_count:
        return CardMiningState(
            row_count=row_count,
            completed_rows=row_count,
            active_row=max(0, row_count - 1),
            row_progress=1.0,
            pick_rotation_deg=360.0,
            pick_x=pick_x,
            pick_y=card_mining_band_center_y(
                box, max(0, row_count - 1), tile_px=tile_px, row_count=row_count
            ),
            is_complete=True,
        )

    active_row = min(row_count - 1, completed_rows)
    stretch = max(1.0, float(PICK_ROTATION_STRETCH))
    pick_rotation_deg = max(
        0.0, min(360.0, swing_progress * 360.0 / stretch)
    )
    return CardMiningState(
        row_count=row_count,
        completed_rows=completed_rows,
        active_row=active_row,
        row_progress=row_progress,
        pick_rotation_deg=pick_rotation_deg,
        pick_x=pick_x,
        pick_y=card_mining_band_center_y(
            box,
            active_row,
            tile_px=tile_px,
            row_count=row_count,
            rows_per_swing=per_swing,
        ),
        is_complete=False,
    )


def _overlap_len(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _tile_col_range(
    box: WordMemorizeBox, tile_px: int, *, fringe_tiles: int
) -> tuple[int, int]:
    px = max(1, int(tile_px))
    fringe = max(0, int(fringe_tiles)) * px
    x0 = int(box.x)
    x1 = x0 + int(box.w)
    col_start = max(0, (x0 - fringe) // px)
    col_end = (x1 + fringe + px - 1) // px
    return col_start, col_end


def _horizontal_void_distance(
    cell_x0: int, cell_x1: int, card_x0: int, card_x1: int
) -> int:
    """카드 x 구간 밖이면 가장 가까운 타일 거리(1부터), 안이면 0."""
    if cell_x1 <= card_x0:
        gap = card_x0 - cell_x1
    elif cell_x0 >= card_x1:
        gap = cell_x0 - card_x1
    else:
        return 0
    return max(1, int(math.ceil(gap / max(1, cell_x1 - cell_x0))))


def _cell_punch_chance(
    *,
    col: int,
    row_top: int,
    tile_px: int,
    box: WordMemorizeBox,
    card_row_index: int,
    completed_rows: int,
    row_count: int,
    is_overdig_row: bool,
) -> float:
    """타일 칸 제거 확률 — 카드 안/가장자리/인접 빈 영역."""
    px = max(1, int(tile_px))
    cell_x0 = col * px
    cell_x1 = cell_x0 + px
    row_bottom = row_top + px
    card_x0 = int(box.x)
    card_y0 = int(box.y)
    card_x1 = card_x0 + int(box.w)
    card_y1 = card_y0 + int(box.h)

    overlap_x = _overlap_len(cell_x0, cell_x1, card_x0, card_x1)
    overlap_y = _overlap_len(row_top, row_bottom, card_y0, card_y1)
    inside_card = overlap_x >= px // 2 and overlap_y >= px // 2

    if inside_card:
        if is_overdig_row:
            return MINING_OVERDIG_CHANCE
        # 루프에 포함된 행 = 곡괭이가 이미 지나간 구간 → 카드 안은 전부 제거
        return 1.0

    void_dist = _horizontal_void_distance(cell_x0, cell_x1, card_x0, card_x1)
    if void_dist <= 0:
        return 0.0
    chances = MINING_VOID_FRINGE_CHANCE
    if void_dist > len(chances):
        return 0.0
    base = chances[void_dist - 1]
    # 카드 행 y 밴드와 겹치지 않으면 확률만 소폭 감소
    if overlap_y <= 0:
        base *= 0.72
    elif overlap_y < px // 2:
        base *= 0.88
    return base


def _unrevealed_peer_card_rects(
    layout: WordMemorizeLayout,
    *,
    exclude_box_key: str,
    revealed_box_keys: set[str],
) -> list[pygame.Rect]:
    """채굴 전인 다른 카드 영역 — 테두리 노이즈가 침범하지 않도록."""
    rects: list[pygame.Rect] = []
    for peer in layout.sorted_boxes():
        peer_key = box_runtime_key(peer)
        if peer_key == exclude_box_key or peer_key in revealed_box_keys:
            continue
        w = int(peer.w)
        h = int(peer.h)
        if w <= 0 or h <= 0:
            continue
        rects.append(pygame.Rect(int(peer.x), int(peer.y), w, h))
    return rects


def _cell_blocked_by_unrevealed_card(
    col: int,
    row_top: int,
    tile_px: int,
    protected_cards: list[pygame.Rect],
) -> bool:
    """타일 칸이 아직 깨지 않은 다른 카드 위인지."""
    if not protected_cards:
        return False
    px = max(1, int(tile_px))
    cell_x0 = col * px
    cell_x1 = cell_x0 + px
    row_bottom = row_top + px
    half = px // 2
    for card in protected_cards:
        overlap_x = _overlap_len(cell_x0, cell_x1, card.left, card.right)
        overlap_y = _overlap_len(row_top, row_bottom, card.top, card.bottom)
        if overlap_x >= half and overlap_y >= half:
            return True
    return False


def _should_punch_cell(
    *,
    box_key: str,
    col: int,
    row_top: int,
    tile_px: int,
    box: WordMemorizeBox,
    card_row_index: int,
    completed_rows: int,
    row_count: int,
    is_overdig_row: bool,
) -> bool:
    chance = _cell_punch_chance(
        col=col,
        row_top=row_top,
        tile_px=tile_px,
        box=box,
        card_row_index=card_row_index,
        completed_rows=completed_rows,
        row_count=row_count,
        is_overdig_row=is_overdig_row,
    )
    if chance >= 1.0:
        return True
    if chance <= 0.0:
        return False
    tag = f"{box_key}:{col}:{row_top}:{'od' if is_overdig_row else 'row'}"
    cell_rng = random.Random(hash(tag) & 0xFFFFFFFF)
    return cell_rng.random() < chance


def iter_mining_punch_tile_centers(
    box: WordMemorizeBox,
    *,
    tile_px: int,
    completed_rows: int,
    frame_width: int,
    frame_height: int,
    box_key: str | None = None,
    include_vertical_fringe: bool = False,
) -> list[tuple[float, float]]:
    """제거되는 타일 칸 중심 — 파티클 스폰용."""
    rects = collect_mining_punch_rects(
        box,
        tile_px=tile_px,
        completed_rows=completed_rows,
        frame_width=frame_width,
        frame_height=frame_height,
        box_key=box_key,
        include_vertical_fringe=include_vertical_fringe,
    )
    px = max(1, int(tile_px))
    return [(rect.centerx, rect.centery) for rect in rects]


def collect_mining_punch_rects(
    box: WordMemorizeBox,
    *,
    tile_px: int,
    completed_rows: int,
    frame_width: int,
    frame_height: int,
    box_key: str | None = None,
    include_vertical_fringe: bool = False,
    tile_band_y0: int | None = None,
    tile_band_y1: int | None = None,
    layout: WordMemorizeLayout | None = None,
    revealed_box_keys: set[str] | None = None,
) -> list[pygame.Rect]:
    """불규칙 채굴로 제거할 타일 칸 목록 — 정사각형 격자 칸만."""
    px = max(1, int(tile_px))
    rows = max(0, int(completed_rows))
    if rows <= 0:
        return []
    key = box_key or box_runtime_key(box)
    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    band_y0 = 0 if tile_band_y0 is None else int(tile_band_y0)
    band_y1 = (fh // px) * px if tile_band_y1 is None else int(tile_band_y1)
    protected_cards: list[pygame.Rect] = []
    peer_sig: tuple[Any, ...] = ()
    if layout is not None and revealed_box_keys is not None:
        protected_cards = _unrevealed_peer_card_rects(
            layout,
            exclude_box_key=key,
            revealed_box_keys=revealed_box_keys,
        )
        peer_sig = tuple(
            (
                box_runtime_key(peer),
                int(peer.x),
                int(peer.y),
                int(peer.w),
                int(peer.h),
            )
            for peer in layout.sorted_boxes()
        )
    cache_key = (
        _box_punch_cache_key(box),
        rows,
        fw,
        fh,
        key,
        bool(include_vertical_fringe),
        px,
        band_y0,
        band_y1,
        frozenset(revealed_box_keys or ()),
        peer_sig,
    )
    cached = _punch_rect_cache.get(cache_key)
    if cached is not None:
        return cached
    row_count = card_mining_row_count(box, px)
    col_start, col_end = _tile_col_range(box, px, fringe_tiles=MINING_FRINGE_TILES)
    punched: list[pygame.Rect] = []
    seen: set[tuple[int, int]] = set()

    def add_cell(col: int, row_top: int) -> None:
        rt = snap_tile_coord(row_top, px)
        if not tile_fits_in_band(
            rt, px, band_y0=band_y0, band_y1=band_y1, frame_width=fw
        ):
            return
        cell_x = col * px
        if cell_x < 0 or cell_x + px > fw:
            return
        if protected_cards and _cell_blocked_by_unrevealed_card(
            col, rt, px, protected_cards
        ):
            return
        stamp = (col, rt)
        if stamp in seen:
            return
        seen.add(stamp)
        punched.append(pygame.Rect(cell_x, rt, px, px))

    for card_row in range(min(rows, row_count)):
        row_top, row_bottom = card_mining_row_band_y(box, card_row, px)
        if row_bottom <= row_top:
            continue
        for col in range(col_start, col_end):
            if _should_punch_cell(
                box_key=key,
                col=col,
                row_top=row_top,
                tile_px=px,
                box=box,
                card_row_index=card_row,
                completed_rows=rows,
                row_count=row_count,
                is_overdig_row=False,
            ):
                add_cell(col, row_top)

        if card_row == rows - 1 and rows < row_count:
            overdig_top = row_bottom
            if overdig_top + px <= fh:
                for col in range(col_start, col_end):
                    if _should_punch_cell(
                        box_key=key,
                        col=col,
                        row_top=overdig_top,
                        tile_px=px,
                        box=box,
                        card_row_index=card_row,
                        completed_rows=rows,
                        row_count=row_count,
                        is_overdig_row=True,
                    ):
                        add_cell(col, overdig_top)

    if include_vertical_fringe:
        card_x0 = int(box.x)
        card_x1 = card_x0 + int(box.w)
        card_y0 = int(box.y)
        card_y1 = card_y0 + int(box.h)
        grid_top = snap_tile_coord(card_y0, px)
        grid_bottom = snap_tile_coord(card_y1 - 1, px) + px
        for dist, chance in enumerate(MINING_VERTICAL_VOID_FRINGE_CHANCE, start=1):
            for row_top in (grid_top - dist * px, grid_bottom + (dist - 1) * px):
                if not tile_fits_in_band(
                    row_top, px, band_y0=band_y0, band_y1=band_y1, frame_width=fw
                ):
                    continue
                for col in range(col_start, col_end):
                    cell_x0 = col * px
                    if _overlap_len(cell_x0, cell_x0 + px, card_x0, card_x1) <= 0:
                        continue
                    tag = f"{key}:v:{col}:{row_top}:{dist}"
                    cell_rng = random.Random(hash(tag) & 0xFFFFFFFF)
                    if cell_rng.random() < chance:
                        add_cell(col, row_top)

    _punch_rect_cache[cache_key] = punched
    return punched


def punch_mining_rects(layer: pygame.Surface, rects: list[pygame.Rect]) -> None:
    """타일 칸 단위로 투명 구멍."""
    for rect in rects:
        if rect.width <= 0 or rect.height <= 0:
            continue
        layer.fill((0, 0, 0, 0), rect)


def punch_card_irregular_holes(
    layer: pygame.Surface,
    box: WordMemorizeBox,
    *,
    tile_px: int,
    completed_rows: int,
    frame_width: int,
    frame_height: int,
    box_key: str | None = None,
    tile_band_y0: int | None = None,
    tile_band_y1: int | None = None,
    layout: WordMemorizeLayout | None = None,
    revealed_box_keys: set[str] | None = None,
) -> None:
    """불규칙 윤곽·인접 빈 영역까지 타일 제거."""
    rects = collect_mining_punch_rects(
        box,
        tile_px=tile_px,
        completed_rows=completed_rows,
        frame_width=frame_width,
        frame_height=frame_height,
        box_key=box_key,
        include_vertical_fringe=False,
        tile_band_y0=tile_band_y0,
        tile_band_y1=tile_band_y1,
        layout=layout,
        revealed_box_keys=revealed_box_keys,
    )
    punch_mining_rects(layer, rects)


def punch_card_full_hole(
    layer: pygame.Surface,
    box: WordMemorizeBox,
    *,
    tile_px: int = 0,
    frame_width: int = 0,
    frame_height: int = 0,
    box_key: str | None = None,
    tile_band_y0: int | None = None,
    tile_band_y1: int | None = None,
    layout: WordMemorizeLayout | None = None,
    revealed_box_keys: set[str] | None = None,
) -> None:
    """카드 전체 타일 제거 — 격자 정사각형 칸만."""
    if tile_px > 0 and frame_width > 0 and frame_height > 0:
        row_count = card_mining_row_count(box, tile_px)
        punch_card_irregular_holes(
            layer,
            box,
            tile_px=tile_px,
            completed_rows=row_count,
            frame_width=frame_width,
            frame_height=frame_height,
            box_key=box_key,
            tile_band_y0=tile_band_y0,
            tile_band_y1=tile_band_y1,
            layout=layout,
            revealed_box_keys=revealed_box_keys,
        )
        return
    x0 = int(box.x)
    y0 = int(box.y)
    w = int(box.w)
    h = int(box.h)
    if w <= 0 or h <= 0:
        return
    layer.fill((0, 0, 0, 0), pygame.Rect(x0, y0, w, h))


def punch_card_row_holes(
    layer: pygame.Surface,
    box: WordMemorizeBox,
    *,
    tile_px: int,
    completed_rows: int,
    frame_width: int = 0,
    frame_height: int = 0,
    box_key: str | None = None,
    tile_band_y0: int | None = None,
    tile_band_y1: int | None = None,
    layout: WordMemorizeLayout | None = None,
    revealed_box_keys: set[str] | None = None,
) -> None:
    """맨 위부터 completed_rows 만큼 격자 타일 제거."""
    if frame_width > 0 and frame_height > 0:
        punch_card_irregular_holes(
            layer,
            box,
            tile_px=tile_px,
            completed_rows=completed_rows,
            frame_width=frame_width,
            frame_height=frame_height,
            box_key=box_key,
            tile_band_y0=tile_band_y0,
            tile_band_y1=tile_band_y1,
            layout=layout,
            revealed_box_keys=revealed_box_keys,
        )
        return
    if tile_px <= 0 or completed_rows <= 0:
        return
    rects = collect_mining_punch_rects(
        box,
        tile_px=tile_px,
        completed_rows=completed_rows,
        frame_width=max(1, int(layer.get_width())),
        frame_height=max(1, int(layer.get_height())),
        box_key=box_key,
        tile_band_y0=tile_band_y0,
        tile_band_y1=tile_band_y1,
        layout=layout,
        revealed_box_keys=revealed_box_keys,
    )
    punch_mining_rects(layer, rects)


def load_pick_surface(path: Path, max_px: int) -> pygame.Surface | None:
    """곡괭이 PNG — max_px 안에 맞춰 스케일."""
    if max_px <= 0 or not path.is_file():
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
        scale = min(max_px / w, max_px / h, 1.0)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        if (nw, nh) != (w, h):
            surf = pygame.transform.smoothscale(surf, (nw, nh))
        return surf
    except Exception:
        return None


def draw_rotating_pick_at(
    surface: pygame.Surface,
    pick: pygame.Surface,
    *,
    center_x: int,
    center_y: int,
    rotation_deg: float,
) -> None:
    """지정 위치에서 곡괭이 회전."""
    rotated = pygame.transform.rotate(pick, -float(rotation_deg))
    rect = rotated.get_rect(center=(int(center_x), int(center_y)))
    surface.blit(rotated, rect)


def collect_layout_mining_punch_rects(
    layout: WordMemorizeLayout,
    *,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int],
    tile_px: int,
    frame_width: int,
    frame_height: int,
) -> list[pygame.Rect]:
    """레이아웃 전체 채굴 구멍 — trap 시작 시 타일 상태 계산용."""
    fh = max(1, int(frame_height))
    band_y0, band_y1 = layout_tile_band_y(
        fh,
        margin_top_ratio=float(layout.margin_top_ratio),
        margin_bottom_ratio=float(layout.margin_bottom_ratio),
        tile_px=tile_px,
    )
    rects: list[pygame.Rect] = []
    for box in layout.sorted_boxes():
        key = box_runtime_key(box)
        row_count = card_mining_row_count(box, tile_px)
        if key in revealed_box_keys:
            completed = row_count
        else:
            completed = int(revealed_rows_by_key.get(key, 0))
        if completed <= 0:
            continue
        rects.extend(
            collect_mining_punch_rects(
                box,
                tile_px=tile_px,
                completed_rows=completed,
                frame_width=frame_width,
                frame_height=frame_height,
                box_key=key,
                include_vertical_fringe=False,
                tile_band_y0=band_y0,
                tile_band_y1=band_y1,
                layout=layout,
                revealed_box_keys=revealed_box_keys,
            )
        )
    return rects


def apply_mining_overlay_holes(
    layer: pygame.Surface,
    layout: WordMemorizeLayout,
    *,
    frame_width: int,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int] | None,
    active_box: WordMemorizeBox | None,
    active_elapsed_sec: float,
) -> None:
    """채굴 진행 상태를 타일 오버레이에 반영."""
    tile_px = game_tile_display_px(frame_width=frame_width)
    frame_height = int(layer.get_height())
    band_y0, band_y1 = layout_tile_band_y(
        frame_height,
        margin_top_ratio=float(layout.margin_top_ratio),
        margin_bottom_ratio=float(layout.margin_bottom_ratio),
        tile_px=tile_px,
    )
    stored_rows = revealed_rows_by_key or {}

    def _punch_kw() -> dict[str, Any]:
        return {
            "tile_px": tile_px,
            "frame_width": frame_width,
            "frame_height": frame_height,
            "tile_band_y0": band_y0,
            "tile_band_y1": band_y1,
            "layout": layout,
            "revealed_box_keys": revealed_box_keys,
        }

    for box in layout.sorted_boxes():
        key = box_runtime_key(box)
        if key in revealed_box_keys:
            punch_card_full_hole(
                layer,
                box,
                box_key=key,
                **_punch_kw(),
            )
            continue
        completed = int(stored_rows.get(key, 0))
        if active_box is not None and box_runtime_key(active_box) == key:
            state = card_mining_state(
                box,
                active_elapsed_sec,
                tile_px=tile_px,
                stored_completed_rows=completed,
            )
            completed = max(completed, state.completed_rows)
        row_count = card_mining_row_count(box, tile_px)
        if completed >= row_count:
            punch_card_full_hole(
                layer,
                box,
                box_key=key,
                **_punch_kw(),
            )
        elif completed > 0:
            punch_card_row_holes(
                layer,
                box,
                completed_rows=completed,
                box_key=key,
                **_punch_kw(),
            )


# trap_regrow — 채굴 구멍이 뚫린 베이스 레이어 캐시 (스냅샷당 1회)
_regrow_holed_layer_cache: dict[tuple[Any, ...], pygame.Surface] = {}


def clear_regrow_overlay_cache() -> None:
    """trap_regrow 채굴 구멍 레이어 캐시 무효화."""
    _regrow_holed_layer_cache.clear()


def _regrow_holed_layer_cache_key(
    base_layer: pygame.Surface,
    *,
    frame_width: int,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int],
) -> tuple[Any, ...]:
    return (
        id(base_layer),
        int(frame_width),
        frozenset(revealed_box_keys),
        tuple(sorted((k, int(v)) for k, v in revealed_rows_by_key.items())),
    )


def _copy_regrow_holed_layer(
    base_layer: pygame.Surface,
    layout: WordMemorizeLayout,
    *,
    frame_width: int,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int],
) -> pygame.Surface:
    """채굴 구멍이 뚫린 타일 레이어 — 스냅샷별 캐시 후 복사."""
    cache_key = _regrow_holed_layer_cache_key(
        base_layer,
        frame_width=frame_width,
        revealed_box_keys=revealed_box_keys,
        revealed_rows_by_key=revealed_rows_by_key,
    )
    holed = _regrow_holed_layer_cache.get(cache_key)
    if holed is None:
        holed = base_layer.copy()
        apply_mining_overlay_holes(
            holed,
            layout,
            frame_width=frame_width,
            revealed_box_keys=revealed_box_keys,
            revealed_rows_by_key=revealed_rows_by_key,
            active_box=None,
            active_elapsed_sec=0.0,
        )
        _regrow_holed_layer_cache[cache_key] = holed
    return holed.copy()


def build_mining_tile_overlay(
    base_layer: pygame.Surface,
    layout: object,
    *,
    frame_width: int,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int] | None = None,
    active_box: WordMemorizeBox | None,
    active_elapsed_sec: float,
    trap_regrow_active: bool = False,
    trap_regrow_elapsed_sec: float = 0.0,
    trap_regrow_duration_sec: float = 0.0,
    trap_regrow_box_key: str | None = None,
    trap_regrow_revealed_keys: set[str] | None = None,
    trap_regrow_revealed_rows: dict[str, int] | None = None,
) -> pygame.Surface | None:
    """타일 오버레이 — 행 단위 구멍 유지."""
    from extra.table_editor.services.word_memorize_layout import WordMemorizeLayout
    from studio.studios.word_memorize_trap import apply_full_frame_trap_regrow

    if not isinstance(layout, WordMemorizeLayout):
        return None
    if not layout_uses_pick_mining(layout):
        return None
    tile_px = game_tile_display_px(frame_width=frame_width)
    frame_height = int(base_layer.get_height())
    if trap_regrow_active:
        regrow_keys = trap_regrow_revealed_keys if trap_regrow_revealed_keys is not None else revealed_box_keys
        regrow_rows = (
            trap_regrow_revealed_rows
            if trap_regrow_revealed_rows is not None
            else dict(revealed_rows_by_key or {})
        )
        layer = _copy_regrow_holed_layer(
            base_layer,
            layout,
            frame_width=frame_width,
            revealed_box_keys=regrow_keys,
            revealed_rows_by_key=regrow_rows,
        )
        regrow_sec = trap_regrow_duration_sec if trap_regrow_duration_sec > 0 else TRAP_REGROW_SEC
        apply_full_frame_trap_regrow(
            layer,
            layout,
            pristine_layer=base_layer,
            elapsed_sec=trap_regrow_elapsed_sec,
            frame_width=frame_width,
            frame_height=frame_height,
            revealed_box_keys=regrow_keys,
            revealed_rows_by_key=regrow_rows,
            regrow_sec=regrow_sec,
        )
        return layer
    layer = base_layer.copy()
    apply_mining_overlay_holes(
        layer,
        layout,
        frame_width=frame_width,
        revealed_box_keys=revealed_box_keys,
        revealed_rows_by_key=revealed_rows_by_key,
        active_box=active_box,
        active_elapsed_sec=active_elapsed_sec,
    )
    return layer
