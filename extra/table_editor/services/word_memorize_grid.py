"""단어 외우기 배치 — 격자 정렬·콘텐츠 여백."""
from __future__ import annotations

from extra.table_editor.services.word_memorize_layout import (
    FRAME_SIDE_GUTTER,
    WordMemorizeLayout,
)

GRID_GAP = 16
MARGIN_SHRINK_STEP_PX = 48
MIN_USABLE_HEIGHT = 120


def content_rect_fhd(layout: WordMemorizeLayout) -> tuple[int, int, int, int]:
    """배치 가능 영역 (x0, y0, x1, y1) FHD 좌표."""
    fw, fh = layout.frame_width, layout.frame_height
    y0 = int(round(layout.margin_top_ratio * fh))
    y1 = int(round((1.0 - layout.margin_bottom_ratio) * fh))
    y1 = max(y0 + MIN_USABLE_HEIGHT, min(y1, fh))
    x0 = FRAME_SIDE_GUTTER
    x1 = max(x0 + 80, fw - FRAME_SIDE_GUTTER)
    return x0, y0, x1, y1


def shrink_margin_top(layout: WordMemorizeLayout, step_px: int = MARGIN_SHRINK_STEP_PX) -> None:
    fh = max(1, layout.frame_height)
    layout.margin_top_ratio = max(
        0.0, layout.margin_top_ratio - step_px / fh
    )


def shrink_margin_bottom(layout: WordMemorizeLayout, step_px: int = MARGIN_SHRINK_STEP_PX) -> None:
    fh = max(1, layout.frame_height)
    layout.margin_bottom_ratio = max(
        0.0, layout.margin_bottom_ratio - step_px / fh
    )


def apply_grid_layout(
    layout: WordMemorizeLayout,
    rows: int,
    cols: int,
    *,
    uniform: bool,
    min_box_w: int = 80,
    min_box_h: int = 60,
) -> str | None:
    """order 순으로 행×열 격자 배치. uniform 이면 칸 크기에 맞춰 w·h 통일."""
    boxes = layout.sorted_boxes()
    if not boxes:
        return "표시 중인 word box가 없습니다."

    rows = max(1, int(rows))
    cols = max(1, int(cols))
    x0, y0, x1, y1 = content_rect_fhd(layout)
    usable_w = x1 - x0
    usable_h = y1 - y0
    gap = GRID_GAP

    inner_w = usable_w - (cols + 1) * gap
    inner_h = usable_h - (rows + 1) * gap
    if inner_w < cols * min_box_w or inner_h < rows * min_box_h:
        return (
            "격자 칸이 너무 작습니다. 행·열을 줄이거나 "
            "「위/아래 여백 줄이기」로 배치 영역을 넓히세요."
        )

    cell_w = inner_w // cols
    cell_h = inner_h // rows
    capacity = rows * cols
    placed = min(len(boxes), capacity)

    for i in range(placed):
        box = boxes[i]
        row, col = divmod(i, cols)
        cell_x = x0 + gap + col * (cell_w + gap)
        cell_y = y0 + gap + row * (cell_h + gap)
        if uniform:
            box.w = max(min_box_w, cell_w)
            box.h = max(min_box_h, cell_h)
            box.x = cell_x
            box.y = cell_y
        else:
            w = min(box.w, cell_w)
            h = min(box.h, cell_h)
            box.w = max(min_box_w, w)
            box.h = max(min_box_h, h)
            box.x = cell_x + max(0, (cell_w - box.w) // 2)
            box.y = cell_y + max(0, (cell_h - box.h) // 2)
        box.clamp_to_frame(
            layout.frame_width,
            layout.frame_height,
            min_box_w,
            min_box_h,
        )

    if len(boxes) > placed:
        return (
            f"order 순 {placed}개만 {rows}행×{cols}열에 배치했습니다. "
            f"나머지 {len(boxes) - placed}개는 위치가 그대로입니다. "
            "행·열을 늘리세요."
        )
    return None
