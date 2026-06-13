"""단어 외우기 — 곡괭이 채굴(타일 제거) 연출."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pygame

from extra.table_editor.services.word_memorize_layout import (
    PICK_REVEAL_SEC,
    WordMemorizeBox,
    box_runtime_key,
    game_tile_display_px,
    layout_uses_pick_mining,
    word_memorize_game_pick_path,
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


def pick_reveal_progress(elapsed_sec: float, *, reveal_sec: float = PICK_REVEAL_SEC) -> float:
    """0~1 채굴 진행률 (카드 전체)."""
    if reveal_sec <= 0:
        return 1.0
    return max(0.0, min(1.0, float(elapsed_sec) / float(reveal_sec)))


def card_mining_row_count(box: WordMemorizeBox, tile_px: int) -> int:
    """카드 높이 안의 타일 행 수 (맨 위 y부터 tile_px 간격)."""
    if tile_px <= 0:
        return 1
    h = max(1, int(box.h))
    return max(1, int(math.ceil(h / float(tile_px))))


def card_mining_row_band_y(box: WordMemorizeBox, row_index: int, tile_px: int) -> tuple[int, int]:
    """행 index의 [top, bottom) y (카드 클립)."""
    y0 = int(box.y)
    y1 = y0 + int(box.h)
    row_top = y0 + int(row_index) * tile_px
    row_bottom = min(y1, row_top + tile_px)
    return row_top, row_bottom


def card_mining_row_center_y(box: WordMemorizeBox, row_index: int, tile_px: int) -> int:
    """곡괭이 y — 해당 행 중앙."""
    row_top, row_bottom = card_mining_row_band_y(box, row_index, tile_px)
    if row_bottom <= row_top:
        return row_top
    return (row_top + row_bottom) // 2


def card_mining_state(
    box: WordMemorizeBox,
    elapsed_sec: float,
    *,
    tile_px: int,
    reveal_sec: float = PICK_REVEAL_SEC,
    stored_completed_rows: int = 0,
) -> CardMiningState:
    """x 중앙·맨 위 행부터 한 바퀴씩 — 행 전체 타일 제거 후 아래로 이동."""
    row_count = card_mining_row_count(box, tile_px)
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
                pick_y=card_mining_row_center_y(box, max(0, row_count - 1), tile_px),
                is_complete=True,
            )
        pick_y = card_mining_row_center_y(box, 0, tile_px)
        return CardMiningState(
            row_count=row_count,
            completed_rows=stored,
            active_row=0,
            row_progress=0.0,
            pick_rotation_deg=0.0,
            pick_x=pick_x,
            pick_y=pick_y,
            is_complete=False,
        )

    row_duration = reveal_sec / float(row_count) if row_count > 0 else reveal_sec
    row_units = float(elapsed_sec) / row_duration if row_duration > 0 else float(row_count)
    completed_from_elapsed = int(row_units)
    completed_rows = max(stored, min(completed_from_elapsed, row_count))
    row_progress = row_units - math.floor(row_units)
    if completed_rows >= row_count:
        return CardMiningState(
            row_count=row_count,
            completed_rows=row_count,
            active_row=max(0, row_count - 1),
            row_progress=1.0,
            pick_rotation_deg=360.0,
            pick_x=pick_x,
            pick_y=card_mining_row_center_y(box, max(0, row_count - 1), tile_px),
            is_complete=True,
        )

    active_row = completed_rows
    pick_y = card_mining_row_center_y(box, active_row, tile_px)
    return CardMiningState(
        row_count=row_count,
        completed_rows=completed_rows,
        active_row=active_row,
        row_progress=row_progress,
        pick_rotation_deg=max(0.0, min(360.0, row_progress * 360.0)),
        pick_x=pick_x,
        pick_y=pick_y,
        is_complete=False,
    )


def punch_card_full_hole(
    layer: pygame.Surface,
    box: WordMemorizeBox,
) -> None:
    """카드 전체 타일 제거."""
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
) -> None:
    """맨 위부터 completed_rows 만큼의 행 전체(x 구간) 타일 제거."""
    if tile_px <= 0 or completed_rows <= 0:
        return
    x0 = int(box.x)
    x1 = x0 + int(box.w)
    if x1 <= x0:
        return
    row_count = card_mining_row_count(box, tile_px)
    rows = max(0, min(int(completed_rows), row_count))
    for row in range(rows):
        row_top, row_bottom = card_mining_row_band_y(box, row, tile_px)
        if row_bottom <= row_top:
            continue
        layer.fill(
            (0, 0, 0, 0),
            pygame.Rect(x0, row_top, x1 - x0, row_bottom - row_top),
        )


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


def build_mining_tile_overlay(
    base_layer: pygame.Surface,
    layout: object,
    *,
    frame_width: int,
    revealed_box_keys: set[str],
    revealed_rows_by_key: dict[str, int] | None = None,
    active_box: WordMemorizeBox | None,
    active_elapsed_sec: float,
) -> pygame.Surface | None:
    """타일 오버레이 — 행 단위 구멍 유지."""
    from extra.table_editor.services.word_memorize_layout import WordMemorizeLayout

    if not isinstance(layout, WordMemorizeLayout):
        return None
    if not layout_uses_pick_mining(layout):
        return None
    layer = base_layer.copy()
    tile_px = game_tile_display_px(frame_width=frame_width)
    stored_rows = revealed_rows_by_key or {}
    for box in layout.sorted_boxes():
        key = box_runtime_key(box)
        if key in revealed_box_keys:
            punch_card_full_hole(layer, box)
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
            punch_card_full_hole(layer, box)
        elif completed > 0:
            punch_card_row_holes(layer, box, tile_px=tile_px, completed_rows=completed)
    return layer
