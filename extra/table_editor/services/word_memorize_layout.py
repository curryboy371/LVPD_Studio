"""단어 외우기 모드 — word box 배치 JSON (FHD 1080×1920 좌표)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from core.paths import SHORTS_HEIGHT, SHORTS_WIDTH, get_repo_root

LAYOUT_VERSION = 1
# 편집기 가이드 기본 (숏츠 ZONE 상 6% · 하 24%)
DEFAULT_MARGIN_TOP_RATIO = 0.30 * 0.20
DEFAULT_MARGIN_BOTTOM_RATIO = 0.30 * 0.80
DEFAULT_LAYOUTS_DIR = get_repo_root() / "resource" / "table" / "word_memorize_layouts"

BackgroundType = Literal["color", "image"]


@dataclass
class WordMemorizeBox:
    word_id: str
    order: int
    x: int
    y: int
    w: int
    h: int
    box_key: str = ""

    def clamp_to_frame(
        self,
        frame_w: int = SHORTS_WIDTH,
        frame_h: int = SHORTS_HEIGHT,
        min_w: int = 80,
        min_h: int = 60,
    ) -> None:
        self.w = max(min_w, int(self.w))
        self.h = max(min_h, int(self.h))
        self.x = max(0, min(int(self.x), frame_w - self.w))
        self.y = max(0, min(int(self.y), frame_h - self.h))


def boxes_overlap(a: WordMemorizeBox, b: WordMemorizeBox) -> bool:
    """축 정렬 사각형이 겹치면 True (변만 맞닿는 것은 겹침 아님)."""
    if a.box_key and b.box_key and a.box_key == b.box_key:
        return False
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    return not (ax2 <= b.x or bx2 <= a.x or ay2 <= b.y or by2 <= a.y)


def box_overlaps_any(
    box: WordMemorizeBox,
    others: list[WordMemorizeBox],
    *,
    ignore_key: str = "",
) -> bool:
    for other in others:
        if other.box_key == ignore_key:
            continue
        if boxes_overlap(box, other):
            return True
    return False


def layout_has_overlaps(layout: WordMemorizeLayout) -> bool:
    boxes = layout.boxes
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            if boxes_overlap(a, b):
                return True
    return False


def find_non_overlapping_position(
    layout: WordMemorizeLayout,
    w: int,
    h: int,
    *,
    prefer_x: int = 40,
    prefer_y: int = 120,
    step: int = 40,
) -> tuple[int, int]:
    """프레임 안에서 기존 박스와 겹치지 않는 (x, y)를 찾는다."""
    fw, fh = layout.frame_width, layout.frame_height
    w = max(80, int(w))
    h = max(60, int(h))
    if w > fw or h > fh:
        return 0, 0

    candidates: list[tuple[int, int]] = [(prefer_x, prefer_y)]
    for y in range(40, max(41, fh - h + 1), step):
        for x in range(40, max(41, fw - w + 1), step):
            if (x, y) not in candidates:
                candidates.append((x, y))

    trial = WordMemorizeBox(
        word_id="",
        order=0,
        x=0,
        y=0,
        w=w,
        h=h,
        box_key="__placement_trial__",
    )
    for x, y in candidates:
        trial.x = x
        trial.y = y
        trial.clamp_to_frame(fw, fh)
        if not box_overlaps_any(trial, layout.boxes, ignore_key=trial.box_key):
            return trial.x, trial.y
    return max(0, fw - w - 40), max(0, fh - h - 40)


@dataclass
class WordMemorizeLayout:
    frame_width: int = SHORTS_WIDTH
    frame_height: int = SHORTS_HEIGHT
    background_type: BackgroundType = "color"
    background_value: str = "#ffffff"
    # resource/sound/bg_short 상대 경로. 비우면 재생 시 bg_short 랜덤.
    bg_music_path: str = ""
    boxes: list[WordMemorizeBox] = field(default_factory=list)
    holding_word_ids: list[str] = field(default_factory=list)
    margin_top_ratio: float = DEFAULT_MARGIN_TOP_RATIO
    margin_bottom_ratio: float = DEFAULT_MARGIN_BOTTOM_RATIO

    def sorted_boxes(self) -> list[WordMemorizeBox]:
        return sorted(self.boxes, key=lambda b: (b.order, b.word_id))

    def renumber_orders(self) -> None:
        for idx, box in enumerate(self.sorted_boxes(), start=1):
            box.order = idx

    def next_order(self) -> int:
        if not self.boxes:
            return 1
        return max(b.order for b in self.boxes) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": LAYOUT_VERSION,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "background": {
                "type": self.background_type,
                "value": self.background_value,
            },
            "bg_music_path": (self.bg_music_path or "").strip(),
            "boxes": [
                {
                    "word_id": b.word_id,
                    "order": b.order,
                    "x": b.x,
                    "y": b.y,
                    "w": b.w,
                    "h": b.h,
                    "box_key": b.box_key,
                }
                for b in self.sorted_boxes()
            ],
            "holding_word_ids": list(self.holding_word_ids),
            "margin_top_ratio": self.margin_top_ratio,
            "margin_bottom_ratio": self.margin_bottom_ratio,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WordMemorizeLayout:
        bg = data.get("background") or {}
        bg_type = bg.get("type", "color")
        if bg_type not in ("color", "image"):
            bg_type = "color"
        layout = cls(
            frame_width=int(data.get("frame_width", SHORTS_WIDTH)),
            frame_height=int(data.get("frame_height", SHORTS_HEIGHT)),
            background_type=bg_type,  # type: ignore[arg-type]
            background_value=str(bg.get("value", "#ffffff")),
        )
        boxes: list[WordMemorizeBox] = []
        for raw in data.get("boxes") or []:
            if not isinstance(raw, dict):
                continue
            wid = str(raw.get("word_id", "")).strip()
            if not wid:
                continue
            box = WordMemorizeBox(
                word_id=wid,
                order=int(raw.get("order", len(boxes) + 1)),
                x=int(raw.get("x", 0)),
                y=int(raw.get("y", 0)),
                w=int(raw.get("w", 280)),
                h=int(raw.get("h", 160)),
                box_key=str(raw.get("box_key", "")).strip(),
            )
            box.clamp_to_frame(layout.frame_width, layout.frame_height)
            boxes.append(box)
        layout.boxes = boxes
        layout.renumber_orders()
        holding: list[str] = []
        for raw_id in data.get("holding_word_ids") or []:
            wid = str(raw_id).strip()
            if wid and wid not in holding:
                holding.append(wid)
        layout.holding_word_ids = holding
        try:
            layout.margin_top_ratio = float(
                data.get("margin_top_ratio", DEFAULT_MARGIN_TOP_RATIO)
            )
            layout.margin_bottom_ratio = float(
                data.get("margin_bottom_ratio", DEFAULT_MARGIN_BOTTOM_RATIO)
            )
        except (TypeError, ValueError):
            layout.margin_top_ratio = DEFAULT_MARGIN_TOP_RATIO
            layout.margin_bottom_ratio = DEFAULT_MARGIN_BOTTOM_RATIO
        layout.margin_top_ratio = max(0.0, min(0.45, layout.margin_top_ratio))
        layout.margin_bottom_ratio = max(0.0, min(0.45, layout.margin_bottom_ratio))
        from extra.table_editor.services.shorts_editor_choices import (
            normalize_vocab_bg_path,
        )

        layout.bg_music_path = normalize_vocab_bg_path(
            str(data.get("bg_music_path", "") or "")
        )
        return layout


def save_layout(path: Path, layout: WordMemorizeLayout) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(layout.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_layout(path: Path) -> WordMemorizeLayout:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("layout JSON must be an object")
    return WordMemorizeLayout.from_dict(data)
