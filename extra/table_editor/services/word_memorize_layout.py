"""단어 외우기 모드 — word box 배치 JSON (FHD 1080×1920 좌표)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from core.paths import SHORTS_HEIGHT, SHORTS_WIDTH, get_repo_root

LAYOUT_VERSION = 1
# 편집기 가이드 기본 — resource/table/word_memorize_layouts/요일.json 과 동일
DEFAULT_MARGIN_TOP_RATIO = 0.1125
DEFAULT_MARGIN_BOTTOM_RATIO = 0.13177083333333334
DEFAULT_LAYOUTS_DIR = get_repo_root() / "resource" / "table" / "word_memorize_layouts"
WORD_MEMORIZE_BG_DIR = get_repo_root() / "resource" / "BG"
WORD_MEMORIZE_LASER_BEAM = get_repo_root() / "resource" / "image" / "icon" / "laser.png"
DEFAULT_WORD_MEMORIZE_BG_STEM = "3and3"


def word_memorize_laser_beam_path() -> Path:
    """가로 빔 PNG — 왼쪽 꼬리, 오른쪽 머리 (0° 기준)."""
    return WORD_MEMORIZE_LASER_BEAM


def word_memorize_laser_sprite_path() -> Path:
    return word_memorize_laser_beam_path()


def word_memorize_laser_ready_path() -> Path:
    return word_memorize_laser_beam_path()
_BG_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

BackgroundType = Literal["image"]
SelectionHighlightType = Literal["gradient", "red_border", "laser"]
RowHighlightType = Literal["none", "neon_glow", "brackets", "bracket_one", "left_bar"]
TITLE_DEFAULT_MIN_Y = 40
TITLE_RAISE_PX = 24

TITLE_COLOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("흰색", "#ffffff"),
    ("노랑", "#ffeb3b"),
    ("주황", "#ff9800"),
    ("빨강", "#f44336"),
    ("분홍", "#ff4081"),
    ("하늘", "#4fc3f7"),
    ("민트", "#69f0ae"),
    ("연보라", "#b388ff"),
    ("검정", "#212121"),
    ("회색", "#9e9e9e"),
)
DEFAULT_TITLE_COLOR = "#ffffff"

TITLE_FONT_CHOICES: tuple[tuple[str, str], ...] = (
    ("한글+한자", "kr_cn"),
    ("한자 (Noto SC)", "noto_sc"),
    ("한글", "korean"),
)
DEFAULT_TITLE_FONT = "kr_cn"
DEFAULT_TITLE_FONT_PT = 68
TITLE_FONT_PT_MIN = 20
TITLE_FONT_PT_MAX = 120
TITLE_LINE_GAP_FHD = 10

SELECTION_HIGHLIGHT_CHOICES: tuple[tuple[str, str], ...] = (
    ("그라데이션", "gradient"),
    ("빨간 테두리", "red_border"),
    ("레이저", "laser"),
)
DEFAULT_SELECTION_HIGHLIGHT: SelectionHighlightType = "gradient"
ROW_HIGHLIGHT_CHOICES: tuple[tuple[str, str], ...] = (
    ("없음", "none"),
    ("네온 글로우", "neon_glow"),
    ("양쪽 대괄호", "brackets"),
    ("한쪽 대괄호", "bracket_one"),
    ("왼쪽 세로 바", "left_bar"),
)
DEFAULT_ROW_HIGHLIGHT: RowHighlightType = "none"
# 카드 선택 하이라이트(레이저·그라데이션·확대)가 프레임 밖으로 나가지 않도록 좌우 여백
FRAME_SIDE_GUTTER = 10
# 배치 편집기 미리보기 캔버스 스케일 (word_memorize_layout_editor.PREVIEW_WIDTH / SHORTS_WIDTH)
TITLE_EDITOR_PREVIEW_SCALE = 504 / float(SHORTS_WIDTH)

# Word card — 항목(병음·한자·뜻·이미지) 크기는 고정, 박스 높이가 줄면 항목 간격만 비율로 축소
CARD_LINE_GAP_FHD = 4
CARD_CONTENT_REFERENCE_INNER_H = 140
CARD_IMG_BOTTOM_PAD_FHD = 8
CARD_ITEM_GAP_MIN = 0
# Base 슬롯(#1 카드) — 병음·한자·뜻만, 일반 카드보다 큰 글자
BASE_SLOT_PINYIN_PT_FHD = 42
BASE_SLOT_HANZI_PT_FHD = 104
BASE_SLOT_MEANING_PT_FHD = 44
BASE_SLOT_LINE_GAP_FHD = 0
# base 슬롯 전용 글자색 (RGB)
BASE_SLOT_PINYIN_COLOR = (255, 255, 255)
BASE_SLOT_PINYIN_BG_COLOR = (255, 152, 0)
BASE_SLOT_PINYIN_BG_PAD_X_FHD = 16
BASE_SLOT_PINYIN_BG_PAD_Y_FHD = 5
BASE_SLOT_PINYIN_BG_RADIUS_FHD = 10
BASE_SLOT_HANZI_COLOR = (255, 235, 59)
BASE_SLOT_MEANING_COLOR = (255, 255, 255)
BASE_SLOT_MEANING_BG_COLOR = (76, 175, 80)
BASE_SLOT_MEANING_PAD_X_FHD = 16
BASE_SLOT_MEANING_PAD_Y_FHD = 3
BASE_SLOT_MEANING_BG_RADIUS_FHD = 10


def default_card_item_gap(inner_height: int) -> float:
    """기준 박스 높이 대비 inner 높이로 기본 항목 간격 산출."""
    if inner_height < 1:
        return float(CARD_LINE_GAP_FHD)
    return max(
        float(CARD_ITEM_GAP_MIN),
        CARD_LINE_GAP_FHD * inner_height / CARD_CONTENT_REFERENCE_INNER_H,
    )


def layout_card_content_vertical(
    inner_height: int,
    text_line_heights: list[int],
    image_height: int = 0,
    *,
    pad_top: int = 0,
    bottom_pad: int = 0,
    default_gap: float | None = None,
    min_gap: float = CARD_ITEM_GAP_MIN,
) -> tuple[int, list[int], int | None]:
    """박스 inner 기준 세로 배치. 반환: (첫 y 오프셋, 텍스트 줄 y들, 이미지 y).

    항목 높이는 그대로 두고, 항목 사이 간격만 줄어들 공간이 부족하면 동일 비율로 축소한다.
    """
    line_hs = [max(0, int(h)) for h in text_line_heights if h > 0]
    img_h = max(0, int(image_height))
    item_heights = list(line_hs)
    if img_h > 0:
        item_heights.append(img_h)
    if not item_heights:
        return pad_top, [], None

    n_items = len(item_heights)
    n_gaps = n_items - 1
    sum_items = sum(item_heights)
    gap_default = (
        float(default_gap)
        if default_gap is not None
        else default_card_item_gap(inner_height)
    )
    reserve_bottom = bottom_pad if img_h > 0 else 0
    usable = max(0, inner_height - pad_top - reserve_bottom)

    if n_gaps == 0:
        block_h = sum_items
        start = pad_top + max(0, (usable - block_h) // 2)
        if img_h > 0:
            return pad_top, [], start
        return start, [start], None

    needed = sum_items + n_gaps * gap_default
    if needed > usable:
        gap = max(min_gap, (usable - sum_items) / n_gaps)
    else:
        gap = gap_default

    block_h = sum_items + n_gaps * gap
    start_y = pad_top + max(0, (usable - block_h) // 2)

    line_ys: list[int] = []
    image_y: int | None = None
    y = float(start_y)
    n_lines = len(line_hs)
    for i, h in enumerate(item_heights):
        y_int = int(round(y))
        if i < n_lines:
            line_ys.append(y_int)
        else:
            image_y = y_int
        if i < n_items - 1:
            y += h + gap

    return int(round(start_y)), line_ys, image_y


@dataclass
class TitleLineSpec:
    text: str = ""
    color: str = DEFAULT_TITLE_COLOR
    font: str = DEFAULT_TITLE_FONT
    font_pt: int = DEFAULT_TITLE_FONT_PT

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": (self.text or "").strip(),
            "color": normalize_title_color(self.color),
            "font": normalize_title_font(self.font),
            "font_pt": normalize_title_font_pt(self.font_pt),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> TitleLineSpec:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            text=str(raw.get("text", "") or ""),
            color=normalize_title_color(
                str(raw.get("color", DEFAULT_TITLE_COLOR) or DEFAULT_TITLE_COLOR)
            ),
            font=normalize_title_font(
                str(raw.get("font", DEFAULT_TITLE_FONT) or DEFAULT_TITLE_FONT)
            ),
            font_pt=normalize_title_font_pt(raw.get("font_pt", DEFAULT_TITLE_FONT_PT)),
        )


def title_preview_font_pt(font_pt: int | None = None) -> int:
    """편집기 미리보기 캔버스 픽셀 높이 — FHD pygame size × SCALE (pt = 픽셀)."""
    return max(
        6,
        int(
            round(
                normalize_title_font_pt(font_pt) * TITLE_EDITOR_PREVIEW_SCALE
            )
        ),
    )


def title_preview_font_for_key(
    raw: str, *, font_pt: int | None = None
) -> tuple[str, int, str]:
    """tk 폰트: (family, size, weight). size는 음수 = 픽셀 (pygame과 동일 단위)."""
    key = normalize_title_font(raw)
    family, _, weight = TITLE_PREVIEW_FONTS.get(
        key, TITLE_PREVIEW_FONTS[DEFAULT_TITLE_FONT]
    )
    px = title_preview_font_pt(font_pt)
    return family, -px, weight


def title_line_specs_from_legacy_layout(
    title: str,
    *,
    color: str = DEFAULT_TITLE_COLOR,
    font: str = DEFAULT_TITLE_FONT,
    font_pt: int = DEFAULT_TITLE_FONT_PT,
) -> list[TitleLineSpec]:
    lines = split_title_lines(title)
    if not any((ln or "").strip() for ln in lines):
        return [TitleLineSpec(color=color, font=font, font_pt=font_pt)]
    return [
        TitleLineSpec(
            text=ln,
            color=color,
            font=font,
            font_pt=font_pt,
        )
        for ln in lines
        if (ln or "").strip() or len(lines) == 1
    ]


def layout_title_line_specs(layout: "WordMemorizeLayout") -> list[TitleLineSpec]:
    if layout.title_lines:
        return [
            s
            for s in layout.title_lines
            if (s.text or "").strip()
        ]
    return title_line_specs_from_legacy_layout(
        layout.title,
        color=layout.title_color,
        font=layout.title_font,
        font_pt=layout.title_font_pt,
    )


def sync_layout_title_fields(layout: "WordMemorizeLayout") -> None:
    """title_lines → title 문자열·레거시 전역 필드(첫 줄 기준)."""
    specs = layout.title_lines
    layout.title = join_title_lines([s.text for s in specs])
    active = [s for s in specs if (s.text or "").strip()]
    first = active[0] if active else TitleLineSpec()
    layout.title_color = first.color
    layout.title_font = first.font
    layout.title_font_pt = first.font_pt


TITLE_PREVIEW_FONTS: dict[str, tuple[str, int, str]] = {
    "kr_cn": ("Noto Sans CJK KR", 11, "bold"),
    "noto_sc": ("Noto Sans SC", 11, "bold"),
    "korean": ("Malgun Gothic", 11, "bold"),
}


def list_title_font_labels() -> list[str]:
    return [label for label, _ in TITLE_FONT_CHOICES]


def list_selection_highlight_labels() -> list[str]:
    return [label for label, _ in SELECTION_HIGHLIGHT_CHOICES]


def normalize_selection_highlight(raw: str) -> SelectionHighlightType:
    text = (raw or "").strip()
    if not text:
        return DEFAULT_SELECTION_HIGHLIGHT
    lowered = text.lower()
    if lowered == "row_band" or text == "가로줄":
        return DEFAULT_SELECTION_HIGHLIGHT
    valid_keys = {key for _, key in SELECTION_HIGHLIGHT_CHOICES}
    if lowered in valid_keys:
        return lowered  # type: ignore[return-value]
    for label, key in SELECTION_HIGHLIGHT_CHOICES:
        if text == label:
            return key  # type: ignore[return-value]
    return DEFAULT_SELECTION_HIGHLIGHT


def selection_highlight_label_for_value(raw: str) -> str:
    key = normalize_selection_highlight(raw)
    for label, k in SELECTION_HIGHLIGHT_CHOICES:
        if k == key:
            return label
    return SELECTION_HIGHLIGHT_CHOICES[0][0]


def list_row_highlight_labels() -> list[str]:
    return [label for label, _ in ROW_HIGHLIGHT_CHOICES]


def normalize_row_highlight(raw: str | bool | None) -> RowHighlightType:
    if isinstance(raw, bool):
        return "neon_glow" if raw else "none"
    text = (raw or "").strip()
    if not text:
        return DEFAULT_ROW_HIGHLIGHT
    lowered = text.lower()
    valid = {key for _, key in ROW_HIGHLIGHT_CHOICES}
    if lowered in valid:
        return lowered  # type: ignore[return-value]
    for label, key in ROW_HIGHLIGHT_CHOICES:
        if text == label:
            return key  # type: ignore[return-value]
    if lowered in ("row_band", "true", "1", "yes"):
        return "neon_glow"
    return DEFAULT_ROW_HIGHLIGHT


def row_highlight_label_for_value(raw: str | bool | None) -> str:
    key = normalize_row_highlight(raw)
    for label, k in ROW_HIGHLIGHT_CHOICES:
        if k == key:
            return label
    return ROW_HIGHLIGHT_CHOICES[0][0]


def box_runtime_key(box: WordMemorizeBox) -> str:
    """재생·렌더에서 쓰는 박스 식별자."""
    key = (box.box_key or "").strip()
    if key:
        return key
    return f"{box.word_id}:{box.order}"


def box_row_group_key(box: WordMemorizeBox) -> tuple[int, int]:
    """같은 가로줄 그룹 — y·h(FHD)가 동일한 박스."""
    return (int(box.y), int(box.h))


def find_box_by_runtime_key(
    layout: WordMemorizeLayout, active_key: str
) -> WordMemorizeBox | None:
    target = (active_key or "").strip()
    if not target:
        return None
    for box in layout.boxes:
        if box_runtime_key(box) == target:
            return box
    return None


def boxes_in_row_group(
    layout: WordMemorizeLayout, anchor: WordMemorizeBox
) -> list[WordMemorizeBox]:
    group = box_row_group_key(anchor)
    return [b for b in layout.boxes if box_row_group_key(b) == group]


def normalize_title_font(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return DEFAULT_TITLE_FONT
    lowered = text.lower()
    valid_keys = {key for _, key in TITLE_FONT_CHOICES}
    if lowered in valid_keys:
        return lowered
    for label, key in TITLE_FONT_CHOICES:
        if text == label:
            return key
    return DEFAULT_TITLE_FONT


def normalize_title_font_pt(raw: str | int | float | None) -> int:
    try:
        n = int(float(raw))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_TITLE_FONT_PT
    return max(TITLE_FONT_PT_MIN, min(TITLE_FONT_PT_MAX, n))


def split_title_lines(title: str) -> list[str]:
    if not (title or "").strip() and "\n" not in (title or ""):
        return [""]
    parts = (title or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return parts if parts else [""]


def join_title_lines(lines: list[str]) -> str:
    trimmed = list(lines)
    while trimmed and not (trimmed[-1] or "").strip():
        trimmed.pop()
    return "\n".join(trimmed)


def title_lines_non_empty(title: str) -> list[str]:
    return [ln.strip() for ln in split_title_lines(title) if ln.strip()]


def title_font_key_for_label(label: str) -> str:
    return normalize_title_font(label)


def title_font_label_for_value(raw: str) -> str:
    key = normalize_title_font(raw)
    for label, k in TITLE_FONT_CHOICES:
        if k == key:
            return label
    return TITLE_FONT_CHOICES[0][0]


def list_title_color_labels() -> list[str]:
    return [label for label, _ in TITLE_COLOR_CHOICES]


def normalize_title_color(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return DEFAULT_TITLE_COLOR
    for label, hx in TITLE_COLOR_CHOICES:
        if text == label:
            return hx
    lowered = text.lower().lstrip("#")
    if len(lowered) == 6 and all(c in "0123456789abcdef" for c in lowered):
        return f"#{lowered}"
    return DEFAULT_TITLE_COLOR


def title_color_label_for_value(raw: str) -> str:
    norm = normalize_title_color(raw)
    for label, hx in TITLE_COLOR_CHOICES:
        if normalize_title_color(hx) == norm:
            return label
    return TITLE_COLOR_CHOICES[0][0]


def title_color_hex_for_label(label: str) -> str:
    for lbl, hx in TITLE_COLOR_CHOICES:
        if lbl == label:
            return hx
    return DEFAULT_TITLE_COLOR


def title_color_to_rgb(raw: str) -> tuple[int, int, int]:
    hx = normalize_title_color(raw).lstrip("#")
    return int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)


def default_title_position(
    frame_width: int = SHORTS_WIDTH,
    frame_height: int = SHORTS_HEIGHT,
    margin_top_ratio: float = DEFAULT_MARGIN_TOP_RATIO,
    y_offset_px: int = 0,
) -> tuple[int, int]:
    """제목 앵커(중심) FHD 좌표 — 상단 중앙, margin_top 구간 기준."""
    band_h = int(margin_top_ratio * frame_height)
    if band_h > TITLE_DEFAULT_MIN_Y * 2:
        y = max(TITLE_DEFAULT_MIN_Y, band_h // 2)
    else:
        y = TITLE_DEFAULT_MIN_Y
    y = max(TITLE_DEFAULT_MIN_Y, y - TITLE_RAISE_PX + int(y_offset_px))
    return frame_width // 2, y


def clamp_title_position(
    x: int, y: int, frame_width: int = SHORTS_WIDTH, frame_height: int = SHORTS_HEIGHT
) -> tuple[int, int]:
    """제목 앵커 — 가로는 항상 중앙, 세로만 조정."""
    _ = x
    cx = int(frame_width) // 2
    cy = max(TITLE_DEFAULT_MIN_Y, min(int(y), int(frame_height)))
    return cx, cy


def resolve_title_position(
    frame_width: int = SHORTS_WIDTH,
    frame_height: int = SHORTS_HEIGHT,
    margin_top_ratio: float = DEFAULT_MARGIN_TOP_RATIO,
    y_offset_px: int = 0,
    title_x: int = 0,
    title_y: int = 0,
) -> tuple[int, int]:
    cx = int(frame_width) // 2
    if int(title_y) <= 0:
        _, y = default_title_position(
            frame_width=frame_width,
            frame_height=frame_height,
            margin_top_ratio=margin_top_ratio,
            y_offset_px=y_offset_px,
        )
        return cx, y
    y = int(title_y) + int(y_offset_px)
    y = max(TITLE_DEFAULT_MIN_Y, min(y, int(frame_height)))
    return cx, y


def list_word_memorize_bg_stems() -> list[str]:
    """resource/BG 내 배경 이미지 stem 목록 (확장자 제외)."""
    d = WORD_MEMORIZE_BG_DIR
    if not d.is_dir():
        return [DEFAULT_WORD_MEMORIZE_BG_STEM]
    stems = sorted(
        {
            p.stem
            for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in _BG_IMAGE_EXTS
        }
    )
    return stems if stems else [DEFAULT_WORD_MEMORIZE_BG_STEM]


def normalize_word_memorize_bg_stem(raw: str) -> str:
    """배경 stem 정규화 — resource/BG 에 있으면 그대로, 없으면 기본값."""
    text = (raw or "").strip().replace("\\", "/")
    if not text or text.startswith("#"):
        return DEFAULT_WORD_MEMORIZE_BG_STEM
    if "/" in text:
        stem = Path(text).stem
    else:
        stem = Path(text).stem
    choices = list_word_memorize_bg_stems()
    if stem in choices:
        return stem
    return DEFAULT_WORD_MEMORIZE_BG_STEM


def word_memorize_bg_image_path(stem: str) -> Path:
    """미리보기·폴백용 PNG(등) 절대 경로."""
    name = normalize_word_memorize_bg_stem(stem)
    for ext in _BG_IMAGE_EXTS:
        path = WORD_MEMORIZE_BG_DIR / f"{name}{ext}"
        if path.is_file():
            return path
    return WORD_MEMORIZE_BG_DIR / f"{DEFAULT_WORD_MEMORIZE_BG_STEM}.png"


def word_memorize_bg_video_path(stem: str) -> Path:
    """재생·녹화용 MP4 절대 경로 (이미지와 동일 stem)."""
    name = normalize_word_memorize_bg_stem(stem)
    return WORD_MEMORIZE_BG_DIR / f"{name}.mp4"


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
        side = FRAME_SIDE_GUTTER
        max_x = max(side, frame_w - self.w - side)
        self.x = max(side, min(int(self.x), max_x))
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
    prefer_x: int | None = None,
    prefer_y: int = 120,
    step: int = 40,
) -> tuple[int, int]:
    """프레임 안에서 기존 박스와 겹치지 않는 (x, y)를 찾는다."""
    fw, fh = layout.frame_width, layout.frame_height
    side = FRAME_SIDE_GUTTER
    if prefer_x is None:
        prefer_x = side
    w = max(80, int(w))
    h = max(60, int(h))
    if w > fw - 2 * side or h > fh:
        return side, 0

    candidates: list[tuple[int, int]] = [(prefer_x, prefer_y)]
    for y in range(40, max(41, fh - h + 1), step):
        for x in range(side, max(side + 1, fw - w - side + 1), step):
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
    return max(side, fw - w - side), max(0, fh - h - 40)


@dataclass
class WordMemorizeLayout:
    frame_width: int = SHORTS_WIDTH
    frame_height: int = SHORTS_HEIGHT
    background_type: BackgroundType = "image"
    background_value: str = DEFAULT_WORD_MEMORIZE_BG_STEM
    title: str = ""
    title_x: int = 0
    title_y: int = 0
    title_y_offset_px: int = 0
    title_color: str = DEFAULT_TITLE_COLOR
    title_font: str = DEFAULT_TITLE_FONT
    title_font_pt: int = DEFAULT_TITLE_FONT_PT
    title_lines: list[TitleLineSpec] = field(default_factory=list)
    selection_highlight: SelectionHighlightType = DEFAULT_SELECTION_HIGHLIGHT
    # 재생 중인 단어와 y·h가 같은 줄 강조 (카드 효과와 별도)
    row_highlight: RowHighlightType = DEFAULT_ROW_HIGHLIGHT
    # True: #1 카드는 이미지·테두리 없이 병음·한자·뜻만 크게
    use_base_slot: bool = False
    # True: 일반 word 카드 흰 배경·테두리 (False면 글자·이미지만)
    use_card_background: bool = True
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
        sync_layout_title_fields(self)
        self.title_x = int(self.frame_width) // 2
        return {
            "version": LAYOUT_VERSION,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "background": {
                "type": "image",
                "value": normalize_word_memorize_bg_stem(self.background_value),
            },
            "title": (self.title or "").strip(),
            "title_x": int(self.title_x),
            "title_y": int(self.title_y),
            "title_y_offset_px": int(self.title_y_offset_px),
            "title_color": normalize_title_color(self.title_color),
            "title_font": normalize_title_font(self.title_font),
            "title_font_pt": normalize_title_font_pt(self.title_font_pt),
            "title_lines": [s.to_dict() for s in self.title_lines],
            "selection_highlight": normalize_selection_highlight(self.selection_highlight),
            "row_highlight": normalize_row_highlight(self.row_highlight),
            "use_base_slot": bool(self.use_base_slot),
            "use_card_background": bool(self.use_card_background),
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
        layout = cls(
            frame_width=int(data.get("frame_width", SHORTS_WIDTH)),
            frame_height=int(data.get("frame_height", SHORTS_HEIGHT)),
            background_type="image",
            background_value=normalize_word_memorize_bg_stem(
                str(bg.get("value", DEFAULT_WORD_MEMORIZE_BG_STEM))
            ),
            title=str(data.get("title", "") or "").strip(),
            title_x=int(data.get("title_x", 0) or 0),
            title_y=int(data.get("title_y", 0) or 0),
            title_y_offset_px=int(data.get("title_y_offset_px", 0) or 0),
            title_color=normalize_title_color(
                str(data.get("title_color", DEFAULT_TITLE_COLOR) or DEFAULT_TITLE_COLOR)
            ),
            title_font=normalize_title_font(
                str(data.get("title_font", DEFAULT_TITLE_FONT) or DEFAULT_TITLE_FONT)
            ),
            title_font_pt=normalize_title_font_pt(
                data.get("title_font_pt", DEFAULT_TITLE_FONT_PT)
            ),
        )
        raw_lines = data.get("title_lines")
        if isinstance(raw_lines, list) and raw_lines:
            layout.title_lines = [
                TitleLineSpec.from_dict(item)
                for item in raw_lines
                if isinstance(item, dict)
            ]
        else:
            layout.title_lines = title_line_specs_from_legacy_layout(
                layout.title,
                color=layout.title_color,
                font=layout.title_font,
                font_pt=layout.title_font_pt,
            )
        sync_layout_title_fields(layout)
        layout.title_x = int(layout.frame_width) // 2
        raw_highlight = str(
            data.get("selection_highlight", DEFAULT_SELECTION_HIGHLIGHT) or ""
        ).strip()
        layout.selection_highlight = normalize_selection_highlight(raw_highlight)
        layout.row_highlight = normalize_row_highlight(data.get("row_highlight", "none"))
        layout.use_base_slot = bool(data.get("use_base_slot", False))
        layout.use_card_background = bool(data.get("use_card_background", True))
        if raw_highlight.lower() in ("row_band",) or raw_highlight == "가로줄":
            if layout.row_highlight == "none":
                layout.row_highlight = "neon_glow"
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


def layout_use_base_slot(layout: WordMemorizeLayout) -> bool:
    return bool(getattr(layout, "use_base_slot", False))


def layout_use_card_background(layout: WordMemorizeLayout) -> bool:
    return bool(getattr(layout, "use_card_background", True))


def base_slot_order(layout: WordMemorizeLayout) -> int | None:
    if not layout.boxes:
        return None
    return min(b.order for b in layout.boxes)


def is_base_slot_box(box: WordMemorizeBox, layout: WordMemorizeLayout) -> bool:
    """가장 앞선 순번(order 최소) 카드 — base 슬롯 레이아웃 대상."""
    if not layout_use_base_slot(layout):
        return False
    first = base_slot_order(layout)
    return first is not None and int(box.order) == int(first)


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
