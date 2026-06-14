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
WORD_MEMORIZE_BG_CH_DIR = WORD_MEMORIZE_BG_DIR / "ch"
WORD_MEMORIZE_LASER_ICON_DIR = get_repo_root() / "resource" / "image" / "icon"
WORD_MEMORIZE_GAME_DIR = get_repo_root() / "resource" / "image" / "game"
WORD_MEMORIZE_GAME_TILES_DIR = WORD_MEMORIZE_GAME_DIR / "tiles"
WORD_MEMORIZE_GAME_TEXT_TILES_DIR = WORD_MEMORIZE_GAME_DIR / "text_tile"
WORD_MEMORIZE_GAME_PARTICLES_DIR = WORD_MEMORIZE_GAME_DIR / "particles"
WORD_MEMORIZE_GAME_PICKS_DIR = WORD_MEMORIZE_GAME_DIR / "picks"
WORD_MEMORIZE_GAME_EFFECT_DIR = WORD_MEMORIZE_GAME_DIR / "effect"
WORD_MEMORIZE_GAME_EFFECT_BLACK_DIR = WORD_MEMORIZE_GAME_EFFECT_DIR / "Black_background"
WORD_MEMORIZE_GAME_EFFECT_TRANSPARENT_DIR = (
    WORD_MEMORIZE_GAME_EFFECT_DIR / "Transparent"
)
# trap 카드 이미지 — resource/image/game/trap (또는 Trap)
_TRAP_DIR_CANDIDATES = ("trap", "Trap", "trab", "Trab")
GAME_ASSET_NONE_LABEL = "(없음)"
# trap 카드 채굴 완료 후 화면 전체 타일 낙하 연출 기준(초)
TRAP_REGROW_SEC = 1.2
TRAP_REGROW_SEC_PER_ROW = 0.035
TRAP_REGROW_SEC_MAX = 5.0
# trap 타일 채우기 완료 후 잠시 유지(초) — 연기 대기는 별도
TRAP_REGROW_HOLD_SEC = 0.45
# trap 타일 채우기 완료 후 연기가 모두 사라질 때까지 재확인 간격(초)
TRAP_REGROW_SMOKE_POLL_SEC = 0.05
# trap PNG — 인접 카드 채굴로 깨질 수 있는 가장자리 타일 링만큼 안쪽 여백
TRAP_CARD_EDGE_MARGIN_TILES = 1
# 재생·미리보기 타일링 시 한 칸 픽셀 크기 (FHD 기준, 프레임 너비에 비례)
GAME_TILE_DISPLAY_PX = 16
# 곡괭이 스윙으로 카드 타일 제거 — 카드당 총 채굴 시간(초). 타일 깨는 속도 기준.
PICK_REVEAL_SEC = 0.7
# 한 번 회전에 제거할 타일 행 수
MINING_ROWS_PER_SWING = 5
# 곡괭이 스윙 각도 — 매 스윙마다 시작각→목표각 (360° 연속 회전 없음)
PICK_SWING_START_DEG = -38.0
PICK_SWING_END_DEG = 52.0
# 곡괭이 표시 크기 — 카드 min(w,h) 대비 (기존 0.9의 1/2)
PICK_DISPLAY_CARD_RATIO = 0.45


def game_tile_display_px(*, frame_width: int = SHORTS_WIDTH) -> int:
    """타일 한 칸 표시 크기 — frame_width 기준으로 GAME_TILE_DISPLAY_PX 비례."""
    fw = max(1, int(frame_width))
    return max(1, int(round(GAME_TILE_DISPLAY_PX * fw / float(SHORTS_WIDTH))))


def trap_card_image_margin_px(
    *,
    frame_width: int = SHORTS_WIDTH,
    tile_px: int | None = None,
) -> int:
    """trap 카드 PNG가 카드 가장자리에서 떨어질 픽셀(타일 링)."""
    px = tile_px if tile_px is not None else game_tile_display_px(frame_width=frame_width)
    return max(0, int(px)) * max(0, int(TRAP_CARD_EDGE_MARGIN_TILES))


def trap_card_image_inner_dimensions(
    card_w: int,
    card_h: int,
    *,
    margin_px: int,
) -> tuple[int, int, int]:
    """(margin, inner_w, inner_h) — trap 이미지 배치용 내부 크기."""
    margin = max(0, int(margin_px))
    inner_w = max(1, int(card_w) - 2 * margin)
    inner_h = max(1, int(card_h) - 2 * margin)
    return margin, inner_w, inner_h


def layout_tile_band_y(
    frame_height: int,
    *,
    margin_top_ratio: float,
    margin_bottom_ratio: float,
    tile_px: int,
) -> tuple[int, int]:
    """타일이 깔리는 [y0, y1) 구간 — 상·하 여백과 타일 격자에 맞춘다."""
    fh = max(1, int(frame_height))
    px = max(1, int(tile_px))
    margin_top = int(round(max(0.0, float(margin_top_ratio)) * fh))
    content_bottom = int(
        round((1.0 - max(0.0, float(margin_bottom_ratio))) * fh)
    )
    content_bottom = max(0, min(fh, content_bottom))
    y0 = ((margin_top + px - 1) // px) * px
    y1 = (content_bottom // px) * px
    y0 = max(0, min(fh, y0))
    y1 = max(y0, min(fh, y1))
    return y0, y1


def snap_tile_coord(value: int, tile_px: int) -> int:
    """좌표를 타일 격자(내림)에 맞춘다."""
    px = max(1, int(tile_px))
    return (int(value) // px) * px


def tile_fits_in_band(
    row_top: int,
    tile_px: int,
    *,
    band_y0: int,
    band_y1: int,
    frame_width: int = 0,
) -> bool:
    """정사각형 타일 한 칸이 밴드·프레임 안에 온전히 들어가는지."""
    px = max(1, int(tile_px))
    rt = snap_tile_coord(row_top, px)
    if rt != int(row_top):
        return False
    if rt < int(band_y0) or rt + px > int(band_y1):
        return False
    fw = int(frame_width)
    if fw > 0 and px > fw:
        return False
    return rt >= 0


DEFAULT_LASER_VARIANT = "laser_b"
LASER_SELECTION_KEYS = frozenset({"laser_b", "laser_g", "laser_p", "laser_y"})
LASER_BORDER_COLORS: dict[str, tuple[int, int, int]] = {
    "laser_b": (0, 229, 255),
    "laser_g": (57, 255, 136),
    "laser_p": (186, 104, 255),
    "laser_y": (255, 235, 59),
}
LASER_PREVIEW_OUTLINE_HEX: dict[str, str] = {
    "laser_b": "#00e5ff",
    "laser_g": "#39ff88",
    "laser_p": "#ba68ff",
    "laser_y": "#ffeb3b",
}
DEFAULT_WORD_MEMORIZE_BG_STEM = "3and3"
# 배치 JSON stem 과 ch/ 폴더 파일명이 다른 경우 (예: mandara → mandala.mp4)
_BG_CH_VIDEO_STEM_ALIASES: dict[str, str] = {"mandara": "mandala"}


def word_memorize_laser_beam_path(variant: str | None = None) -> Path:
    """가로 빔 PNG — laser_b/g/p/y.png (왼쪽 꼬리, 오른쪽 머리)."""
    key = (variant or DEFAULT_LASER_VARIANT).strip().lower()
    if key == "laser":
        key = DEFAULT_LASER_VARIANT
    if key not in LASER_SELECTION_KEYS:
        key = DEFAULT_LASER_VARIANT
    return WORD_MEMORIZE_LASER_ICON_DIR / f"{key}.png"


def word_memorize_laser_sprite_path(variant: str | None = None) -> Path:
    return word_memorize_laser_beam_path(variant)


def word_memorize_laser_ready_path(variant: str | None = None) -> Path:
    return word_memorize_laser_beam_path(variant)


def word_memorize_dissolve_mask_path() -> Path:
    """레이저+base 유리 디졸브 마스크 — 흑백 노이즈(타일 가능). black=먼저 제거."""
    return WORD_MEMORIZE_GAME_DIR / "dissolve.png"


DissolveEffectVariant = Literal["black", "transparent"]


def _list_effect_asset_keys(directory: Path) -> set[str]:
    """effect PNG relative key (하위 폴더 포함, 확장자 제외)."""
    if not directory.is_dir():
        return set()
    keys: set[str] = set()
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.lower() in _BG_IMAGE_EXTS:
            key = path.relative_to(directory).with_suffix("").as_posix()
            if key:
                keys.add(key)
    return keys


def list_word_memorize_dissolve_effects() -> list[str]:
    """Black_background·Transparent 양쪽에 동일 key로 존재하는 effect PNG 목록."""
    black = _list_effect_asset_keys(WORD_MEMORIZE_GAME_EFFECT_BLACK_DIR)
    transparent = _list_effect_asset_keys(WORD_MEMORIZE_GAME_EFFECT_TRANSPARENT_DIR)
    return sorted(black & transparent)


def word_memorize_dissolve_effect_path(
    key: str,
    *,
    variant: DissolveEffectVariant = "transparent",
) -> Path:
    """디졸브 파티클 effect PNG — key 예: spark_01, Rotated/flame_05_rotated."""
    text = (key or "").strip().replace("\\", "/")
    base = (
        WORD_MEMORIZE_GAME_EFFECT_TRANSPARENT_DIR
        if variant == "transparent"
        else WORD_MEMORIZE_GAME_EFFECT_BLACK_DIR
    )
    if not text:
        return base / "_none.png"
    for ext in _BG_IMAGE_EXTS:
        path = base / f"{text}{ext}"
        if path.is_file():
            return path
    return base / f"{text}.png"


def normalize_word_memorize_dissolve_effect(raw: str) -> str:
    """dissolve effect key 정규화 — 없거나 유효하지 않으면 빈 문자열."""
    text = (raw or "").strip().replace("\\", "/")
    if not text or text == GAME_ASSET_NONE_LABEL:
        return ""
    if text in list_word_memorize_dissolve_effects():
        return text
    return ""


def layout_dissolve_effect(layout: WordMemorizeLayout) -> str:
    """레이아웃 첫 디졸브 effect key (레거시·없으면 '')."""
    stems = layout_dissolve_effects(layout, fallback_all=False)
    return stems[0] if stems else ""


def layout_dissolve_effects(
    layout: WordMemorizeLayout,
    *,
    fallback_all: bool = True,
) -> list[str]:
    """레이아웃 디졸브 파티클 effect key 목록 — 중복 제거, 순서 유지."""
    raw = getattr(layout, "dissolve_effects", None)
    if isinstance(raw, list):
        stems: list[str] = []
        seen: set[str] = set()
        for item in raw:
            stem = normalize_word_memorize_dissolve_effect(str(item or ""))
            if stem and stem not in seen:
                seen.add(stem)
                stems.append(stem)
        if stems:
            return stems
    legacy = normalize_word_memorize_dissolve_effect(
        str(getattr(layout, "dissolve_effect", "") or "")
    )
    if legacy:
        return [legacy]
    if fallback_all:
        return list_word_memorize_dissolve_effects()
    return []


def sync_layout_dissolve_effect_fields(layout: WordMemorizeLayout) -> None:
    """dissolve_effects → 레거시 dissolve_effect(첫 항목)."""
    stems = layout_dissolve_effects(layout, fallback_all=False)
    layout.dissolve_effects = list(stems)
    layout.dissolve_effect = stems[0] if stems else ""


_BG_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_BG_VIDEO_EXTS = (".mp4",)

BackgroundType = Literal["image", "video"]


def normalize_background_type(raw: str) -> BackgroundType:
    """배경 타입 정규화 — image·video, 기본 video."""
    text = (raw or "").strip().lower()
    if text == "image":
        return "image"
    return "video"
SelectionHighlightType = Literal[
    "gradient",
    "red_border",
    "laser_b",
    "laser_g",
    "laser_p",
    "laser_y",
]
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
DEFAULT_CARD_BACKGROUND_COLOR = "#ffffff"
CARD_BACKGROUND_COLOR_CHOICES = TITLE_COLOR_CHOICES

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

# 부제목 — 타일 마스크 글씨 (타일 밴드 정중앙, 상하좌우 5타일 여백 후 최대 크기)
SUBTITLE_MARGIN_TILES = 5
SUBTITLE_FONT_PT_MAX = 4096
SUBTITLE_FONT_PT_MIN = 24
SUBTITLE_LINE_GAP_TILES = 2
SUBTITLE_MIN_LINE_TILES = 4
# 부제목 글자 격자 한 칸 — FHD(배경 타일 16px) 기준 2px, 프레임에 비례 스케일
SUBTITLE_CELL_PX = 2


def subtitle_cell_px(*, tile_px: int) -> int:
    """부제목 마스크·text_tile blit에 쓰는 격자 한 칸 픽셀."""
    gpx = max(1, int(tile_px))
    ref = max(1, int(GAME_TILE_DISPLAY_PX))
    cell = max(1, int(round(gpx * float(SUBTITLE_CELL_PX) / ref)))
    return min(gpx, cell)


SELECTION_HIGHLIGHT_CHOICES: tuple[tuple[str, str], ...] = (
    ("그라데이션", "gradient"),
    ("빨간 테두리", "red_border"),
    ("레이저 (파랑)", "laser_b"),
    ("레이저 (초록)", "laser_g"),
    ("레이저 (보라)", "laser_p"),
    ("레이저 (노랑)", "laser_y"),
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


def layout_title_line_specs(
    layout: "WordMemorizeLayout",
    *,
    meaning_lang: str = "ko",
) -> list[TitleLineSpec]:
    if _is_zh_meaning_lang(meaning_lang) and layout.title_lines_zh:
        return [
            s
            for s in layout.title_lines_zh
            if (s.text or "").strip()
        ]
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


def sync_layout_title_fields_zh(layout: "WordMemorizeLayout") -> None:
    """title_lines_zh → title_zh 문자열."""
    specs = layout.title_lines_zh
    layout.title_zh = join_title_lines([s.text for s in specs])


@dataclass
class SubtitleLineSpec:
    """부제목 한 줄 — text_tile로 타일 격자에 글씨, 크기는 재생 시 자동 산출."""

    text: str = ""
    font: str = DEFAULT_TITLE_FONT
    text_tile: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": (self.text or "").strip(),
            "font": normalize_title_font(self.font),
            "text_tile": normalize_word_memorize_game_text_tile(self.text_tile),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SubtitleLineSpec:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            text=str(raw.get("text", "") or ""),
            font=normalize_title_font(
                str(raw.get("font", DEFAULT_TITLE_FONT) or DEFAULT_TITLE_FONT)
            ),
            text_tile=normalize_word_memorize_game_text_tile(
                str(raw.get("text_tile", "") or "")
            ),
        )


def subtitle_line_specs_from_legacy_layout(
    subtitle: str,
    *,
    font: str = DEFAULT_TITLE_FONT,
    text_tile: str = "",
) -> list[SubtitleLineSpec]:
    lines = split_title_lines(subtitle)
    if not any((ln or "").strip() for ln in lines):
        return []
    tile = normalize_word_memorize_game_text_tile(text_tile)
    return [
        SubtitleLineSpec(text=ln, font=font, text_tile=tile)
        for ln in lines
        if (ln or "").strip()
    ]


def layout_subtitle_line_specs(
    layout: "WordMemorizeLayout",
    *,
    meaning_lang: str = "ko",
) -> list[SubtitleLineSpec]:
    if _is_zh_meaning_lang(meaning_lang) and layout.subtitle_lines_zh:
        return [s for s in layout.subtitle_lines_zh if (s.text or "").strip()]
    if layout.subtitle_lines:
        return [s for s in layout.subtitle_lines if (s.text or "").strip()]
    return subtitle_line_specs_from_legacy_layout(
        layout.subtitle,
        font=layout.subtitle_font,
        text_tile=layout_subtitle_text_tile(layout),
    )


def sync_layout_subtitle_fields(layout: "WordMemorizeLayout") -> None:
    """subtitle_lines → subtitle 문자열·레거시 전역 필드(첫 줄 기준)."""
    specs = layout.subtitle_lines
    layout.subtitle = join_title_lines([s.text for s in specs])
    active = [s for s in specs if (s.text or "").strip()]
    first = active[0] if active else SubtitleLineSpec()
    layout.subtitle_font = first.font
    if first.text_tile and not layout_subtitle_text_tile(layout):
        layout.subtitle_text_tile = first.text_tile


def sync_layout_subtitle_fields_zh(layout: "WordMemorizeLayout") -> None:
    """subtitle_lines_zh → subtitle_zh 문자열."""
    specs = layout.subtitle_lines_zh
    layout.subtitle_zh = join_title_lines([s.text for s in specs])


def default_subtitle_position(
    frame_width: int = SHORTS_WIDTH,
    frame_height: int = SHORTS_HEIGHT,
    *,
    margin_top_ratio: float = DEFAULT_MARGIN_TOP_RATIO,
    margin_bottom_ratio: float = DEFAULT_MARGIN_BOTTOM_RATIO,
    tile_px: int = GAME_TILE_DISPLAY_PX,
    y_offset_px: int = 0,
) -> tuple[int, int]:
    """부제목 앵커(블록 중심) — 타일이 깔리는 밴드의 정중앙."""
    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    px = max(1, int(tile_px))
    band_y0, band_y1 = layout_tile_band_y(
        fh,
        margin_top_ratio=margin_top_ratio,
        margin_bottom_ratio=margin_bottom_ratio,
        tile_px=px,
    )
    cx = fw // 2
    cy = (band_y0 + band_y1) // 2 + int(y_offset_px)
    cy = max(band_y0 + px, min(cy, max(band_y0 + px, band_y1 - px)))
    return cx, cy


def resolve_subtitle_position(
    frame_width: int = SHORTS_WIDTH,
    frame_height: int = SHORTS_HEIGHT,
    *,
    margin_top_ratio: float = DEFAULT_MARGIN_TOP_RATIO,
    margin_bottom_ratio: float = DEFAULT_MARGIN_BOTTOM_RATIO,
    tile_px: int = GAME_TILE_DISPLAY_PX,
    y_offset_px: int = 0,
) -> tuple[int, int]:
    return default_subtitle_position(
        frame_width=frame_width,
        frame_height=frame_height,
        margin_top_ratio=margin_top_ratio,
        margin_bottom_ratio=margin_bottom_ratio,
        tile_px=tile_px,
        y_offset_px=y_offset_px,
    )


def subtitle_tile_band_rect(
    frame_width: int,
    frame_height: int,
    *,
    margin_top_ratio: float,
    margin_bottom_ratio: float,
    tile_px: int,
) -> tuple[int, int, int, int]:
    """타일 밴드 (x0, y0, x1, y1) — 부제목 배치·크기 산출용."""
    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    band_y0, band_y1 = layout_tile_band_y(
        fh,
        margin_top_ratio=margin_top_ratio,
        margin_bottom_ratio=margin_bottom_ratio,
        tile_px=max(1, int(tile_px)),
    )
    return 0, band_y0, fw, band_y1


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
    if lowered == "laser":
        return "laser_b"
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


def is_laser_selection_highlight(kind: str) -> bool:
    return normalize_selection_highlight(kind) in LASER_SELECTION_KEYS


def normalize_laser_variant(raw: str) -> str:
    key = normalize_selection_highlight(raw)
    if key in LASER_SELECTION_KEYS:
        return key
    return DEFAULT_LASER_VARIANT


def laser_border_color(kind: str) -> tuple[int, int, int]:
    key = normalize_selection_highlight(kind)
    return LASER_BORDER_COLORS.get(key, LASER_BORDER_COLORS[DEFAULT_LASER_VARIANT])


def laser_preview_outline_hex(kind: str) -> str:
    key = normalize_selection_highlight(kind)
    return LASER_PREVIEW_OUTLINE_HEX.get(
        key, LASER_PREVIEW_OUTLINE_HEX[DEFAULT_LASER_VARIANT]
    )


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


def list_card_background_color_labels() -> list[str]:
    return [label for label, _ in CARD_BACKGROUND_COLOR_CHOICES]


def normalize_card_background_color(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return DEFAULT_CARD_BACKGROUND_COLOR
    for label, hx in CARD_BACKGROUND_COLOR_CHOICES:
        if text == label:
            return hx
    lowered = text.lower().lstrip("#")
    if len(lowered) == 6 and all(c in "0123456789abcdef" for c in lowered):
        return f"#{lowered}"
    return DEFAULT_CARD_BACKGROUND_COLOR


def card_background_color_label_for_value(raw: str) -> str:
    norm = normalize_card_background_color(raw)
    for label, hx in CARD_BACKGROUND_COLOR_CHOICES:
        if normalize_card_background_color(hx) == norm:
            return label
    return CARD_BACKGROUND_COLOR_CHOICES[0][0]


def card_background_color_hex_for_label(label: str) -> str:
    for lbl, hx in CARD_BACKGROUND_COLOR_CHOICES:
        if lbl == label:
            return hx
    return DEFAULT_CARD_BACKGROUND_COLOR


def card_background_color_to_rgb(raw: str) -> tuple[int, int, int]:
    hx = normalize_card_background_color(raw).lstrip("#")
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
    """resource/BG 내 배경 stem 목록 (png·mp4 공통, 확장자 제외)."""
    d = WORD_MEMORIZE_BG_DIR
    if not d.is_dir():
        return [DEFAULT_WORD_MEMORIZE_BG_STEM]
    exts = _BG_IMAGE_EXTS + _BG_VIDEO_EXTS
    stems = sorted(
        {
            p.stem
            for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in exts
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


def _is_zh_meaning_lang(meaning_lang: str) -> bool:
    return (meaning_lang or "").strip().lower() in ("zh", "ch", "cn")


def _is_ko_meaning_lang(meaning_lang: str) -> bool:
    return (meaning_lang or "ko").strip().lower() == "ko"


def _card_meaning_font_bold(meaning_lang: str) -> bool:
    """카드 뜻(한국어) — ko·zh 모드에서 굵게."""
    return _is_ko_meaning_lang(meaning_lang) or _is_zh_meaning_lang(meaning_lang)


def _word_memorize_bg_ch_video_candidates(stem: str) -> list[Path]:
    """중국어 모드: resource/BG/ch/{stem}.mp4 후보 (동일 stem, 별칭 stem)."""
    base = normalize_word_memorize_bg_stem(stem)
    names: list[str] = [base]
    alias = _BG_CH_VIDEO_STEM_ALIASES.get(base)
    if alias and alias not in names:
        names.append(alias)
    return [WORD_MEMORIZE_BG_CH_DIR / f"{name}.mp4" for name in names]


def resolve_word_memorize_bg_video_path(
    stem: str, *, meaning_lang: str = "ko"
) -> Path:
    """재생·녹화·미리보기용 MP4 — zh 모드면 BG/ch/ 동일 파일명 우선."""
    if _is_zh_meaning_lang(meaning_lang):
        for path in _word_memorize_bg_ch_video_candidates(stem):
            if path.is_file():
                return path
    return word_memorize_bg_video_path(stem)


def resolve_word_memorize_bg_image_path(
    stem: str, *, meaning_lang: str = "ko"
) -> Path:
    """정지 배경 폴백 — zh 모드면 BG/ch/ 동일 stem 이미지 우선."""
    base = normalize_word_memorize_bg_stem(stem)
    if _is_zh_meaning_lang(meaning_lang):
        names = [base]
        alias = _BG_CH_VIDEO_STEM_ALIASES.get(base)
        if alias and alias not in names:
            names.append(alias)
        for name in names:
            for ext in _BG_IMAGE_EXTS:
                path = WORD_MEMORIZE_BG_CH_DIR / f"{name}{ext}"
                if path.is_file():
                    return path
    return word_memorize_bg_image_path(stem)


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


def _list_game_asset_stems(directory: Path) -> list[str]:
    """게임 PNG stem 목록 (확장자 제외, 정렬)."""
    if not directory.is_dir():
        return []
    stems: set[str] = set()
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() in _BG_IMAGE_EXTS:
            stem = path.stem.strip()
            if stem:
                stems.add(stem)
    return sorted(stems)


def list_word_memorize_game_text_tiles() -> list[str]:
    """resource/image/game/text_tile 내 글자 타일 PNG stem 목록."""
    return _list_game_asset_stems(WORD_MEMORIZE_GAME_TEXT_TILES_DIR)


def normalize_word_memorize_game_text_tile(raw: str) -> str:
    """text_tile stem 정규화 — 없거나 유효하지 않으면 빈 문자열."""
    text = (raw or "").strip().replace("\\", "/")
    if not text or text == GAME_ASSET_NONE_LABEL:
        return ""
    stem = Path(text).stem
    if stem in list_word_memorize_game_text_tiles():
        return stem
    return ""


def word_memorize_game_text_tile_path(stem: str) -> Path:
    """text_tile PNG 절대 경로."""
    name = normalize_word_memorize_game_text_tile(stem)
    if not name:
        return WORD_MEMORIZE_GAME_TEXT_TILES_DIR / "_none.png"
    for ext in _BG_IMAGE_EXTS:
        path = WORD_MEMORIZE_GAME_TEXT_TILES_DIR / f"{name}{ext}"
        if path.is_file():
            return path
    return WORD_MEMORIZE_GAME_TEXT_TILES_DIR / f"{name}.png"


def list_word_memorize_game_tiles() -> list[str]:
    """resource/image/game/tiles 내 타일 PNG stem 목록."""
    return _list_game_asset_stems(WORD_MEMORIZE_GAME_TILES_DIR)


def list_word_memorize_game_particles() -> list[str]:
    """resource/image/game/particles 내 파티클 PNG stem 목록."""
    return _list_game_asset_stems(WORD_MEMORIZE_GAME_PARTICLES_DIR)


def list_word_memorize_game_picks() -> list[str]:
    """resource/image/game/picks 내 곡괭이 PNG stem 목록."""
    return _list_game_asset_stems(WORD_MEMORIZE_GAME_PICKS_DIR)


def word_memorize_game_trap_dir() -> Path:
    """trap 카드 이미지 폴더 — trap/Trap/trab 등 후보 중 존재하는 경로."""
    for name in _TRAP_DIR_CANDIDATES:
        path = WORD_MEMORIZE_GAME_DIR / name
        if path.is_dir():
            return path
    return WORD_MEMORIZE_GAME_DIR / "trap"


_TRAP_CARD_EXCLUDE_STEMS = frozenset({"smoke"})


def list_word_memorize_game_traps() -> list[str]:
    """resource/image/game/trap 내 trap 카드 PNG stem 목록 (연기 등 이펙트 제외)."""
    stems = _list_game_asset_stems(word_memorize_game_trap_dir())
    return [stem for stem in stems if stem not in _TRAP_CARD_EXCLUDE_STEMS]


def normalize_word_memorize_game_tile(raw: str) -> str:
    """타일 stem 정규화 — 없거나 유효하지 않으면 빈 문자열."""
    text = (raw or "").strip().replace("\\", "/")
    if not text or text == GAME_ASSET_NONE_LABEL:
        return ""
    stem = Path(text).stem
    if stem in list_word_memorize_game_tiles():
        return stem
    return ""


def normalize_word_memorize_game_particle(raw: str) -> str:
    """파티클 stem 정규화 — 없거나 유효하지 않으면 빈 문자열."""
    text = (raw or "").strip().replace("\\", "/")
    if not text or text == GAME_ASSET_NONE_LABEL:
        return ""
    stem = Path(text).stem
    if stem in list_word_memorize_game_particles():
        return stem
    return ""


def normalize_word_memorize_game_pick(raw: str) -> str:
    """곡괭이 stem 정규화 — 없거나 유효하지 않으면 빈 문자열."""
    text = (raw or "").strip().replace("\\", "/")
    if not text or text == GAME_ASSET_NONE_LABEL:
        return ""
    stem = Path(text).stem
    if stem in list_word_memorize_game_picks():
        return stem
    return ""


def normalize_word_memorize_game_trap(raw: str) -> str:
    """trap 카드 stem 정규화 — 없거나 유효하지 않으면 빈 문자열."""
    text = (raw or "").strip().replace("\\", "/")
    if not text or text == GAME_ASSET_NONE_LABEL:
        return ""
    stem = Path(text).stem
    if stem in list_word_memorize_game_traps():
        return stem
    return ""


def word_memorize_game_tile_path(stem: str) -> Path:
    """타일 PNG 절대 경로."""
    name = normalize_word_memorize_game_tile(stem)
    if not name:
        return WORD_MEMORIZE_GAME_TILES_DIR / "_none.png"
    for ext in _BG_IMAGE_EXTS:
        path = WORD_MEMORIZE_GAME_TILES_DIR / f"{name}{ext}"
        if path.is_file():
            return path
    return WORD_MEMORIZE_GAME_TILES_DIR / f"{name}.png"


def word_memorize_game_particle_path(stem: str) -> Path:
    """파티클 PNG 절대 경로."""
    name = normalize_word_memorize_game_particle(stem)
    if not name:
        return WORD_MEMORIZE_GAME_PARTICLES_DIR / "_none.png"
    for ext in _BG_IMAGE_EXTS:
        path = WORD_MEMORIZE_GAME_PARTICLES_DIR / f"{name}{ext}"
        if path.is_file():
            return path
    return WORD_MEMORIZE_GAME_PARTICLES_DIR / f"{name}.png"


def word_memorize_game_pick_path(stem: str) -> Path:
    """곡괭이 PNG 절대 경로."""
    name = normalize_word_memorize_game_pick(stem)
    if not name:
        return WORD_MEMORIZE_GAME_PICKS_DIR / "_none.png"
    for ext in _BG_IMAGE_EXTS:
        path = WORD_MEMORIZE_GAME_PICKS_DIR / f"{name}{ext}"
        if path.is_file():
            return path
    return WORD_MEMORIZE_GAME_PICKS_DIR / f"{name}.png"


def word_memorize_game_trap_path(stem: str) -> Path:
    """trap 카드 PNG 절대 경로."""
    trap_dir = word_memorize_game_trap_dir()
    name = normalize_word_memorize_game_trap(stem)
    if not name:
        return trap_dir / "_none.png"
    for ext in _BG_IMAGE_EXTS:
        path = trap_dir / f"{name}{ext}"
        if path.is_file():
            return path
    return trap_dir / f"{name}.png"


def box_game_trap(box: WordMemorizeBox) -> str:
    """박스에 설정된 trap stem (없으면 '')."""
    return normalize_word_memorize_game_trap(
        str(getattr(box, "game_trap", "") or "")
    )


def box_uses_trap(box: WordMemorizeBox) -> bool:
    """하위 호환 — 채굴 후 타일 복구(조각모음) 카드."""
    return box_uses_mining_regrow(box)


MINING_MASK_NONE = ""
MINING_MASK_HANZI = "hanzi"
MINING_MASK_HANZI_PINYIN = "hanzi_pinyin"
MINING_MASK_HANZI_PINYIN_MEANING = "hanzi_pinyin_meaning"

CARD_TYPE_NONE = ""
CARD_TYPE_SUBSCRIBE = "subscribe"
CARD_TYPE_LIKE = "like"
CARD_TYPE_TOPIC_RECOMMEND = "topic_recommend"

CARD_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
    ("없음", CARD_TYPE_NONE),
    ("구독", CARD_TYPE_SUBSCRIBE),
    ("좋아요", CARD_TYPE_LIKE),
    ("주제추천", CARD_TYPE_TOPIC_RECOMMEND),
)
_VALID_CARD_TYPES = frozenset(value for _label, value in CARD_TYPE_CHOICES)
_LEGACY_TRAP_CARD_TYPE = CARD_TYPE_TOPIC_RECOMMEND
CARD_TYPE_CTA_HANZI: dict[str, str] = {
    CARD_TYPE_SUBSCRIBE: "订阅",
    CARD_TYPE_LIKE: "点赞",
}
CARD_TYPE_CTA_AUDIO_REL: dict[str, str] = {
    CARD_TYPE_SUBSCRIBE: "resource/sound/tts/구독.mp3",
    CARD_TYPE_LIKE: "resource/sound/tts/좋아.mp3",
    CARD_TYPE_TOPIC_RECOMMEND: "resource/sound/tts/주제추천.mp3",
}
CARD_TYPE_CTA_CAPTION: dict[str, str] = {
    CARD_TYPE_SUBSCRIBE: "구독 부탁드립니다",
    CARD_TYPE_LIKE: "좋아요 부탁드립니다",
    CARD_TYPE_TOPIC_RECOMMEND: "원하시는 주제를 댓글에 남겨주세요",
}
CARD_TYPE_CTA_CAPTION_ZH: dict[str, str] = {
    CARD_TYPE_SUBSCRIBE: "关注我学习更多的实用韩语。",
    CARD_TYPE_LIKE: "你们的点赞是我的动力。",
    CARD_TYPE_TOPIC_RECOMMEND: "评论里留言你想学习的韩语吧",
}
_LEGACY_MINING_MASK_TO_CARD_TYPE: dict[str, str] = {
    MINING_MASK_HANZI: CARD_TYPE_TOPIC_RECOMMEND,
    MINING_MASK_HANZI_PINYIN: CARD_TYPE_TOPIC_RECOMMEND,
    MINING_MASK_HANZI_PINYIN_MEANING: CARD_TYPE_TOPIC_RECOMMEND,
}


def normalize_card_type(raw: str) -> str:
    """카드 CTA 타입 정규화."""
    text = (raw or "").strip()
    if text in _VALID_CARD_TYPES:
        return text
    for label, value in CARD_TYPE_CHOICES:
        if text == label:
            return value
    return CARD_TYPE_NONE


def card_type_label_for_value(raw: str) -> str:
    """저장값 → UI 라벨."""
    norm = normalize_card_type(raw)
    for label, value in CARD_TYPE_CHOICES:
        if value == norm:
            return label
    return CARD_TYPE_CHOICES[0][0]


def card_type_value_for_label(label: str) -> str:
    """UI 라벨 → 저장값."""
    text = (label or "").strip()
    for lbl, value in CARD_TYPE_CHOICES:
        if lbl == text:
            return value
    return CARD_TYPE_NONE


def _legacy_card_type_from_mining_mask(raw: str) -> str:
    """구 mining_mask → card_type."""
    text = (raw or "").strip()
    if text in _LEGACY_MINING_MASK_TO_CARD_TYPE:
        return _LEGACY_MINING_MASK_TO_CARD_TYPE[text]
    for _label, value in (
        ("한자만 가리기", MINING_MASK_HANZI),
        ("한자·병음 가리기", MINING_MASK_HANZI_PINYIN),
        ("한자·병음·뜻 가리기", MINING_MASK_HANZI_PINYIN_MEANING),
    ):
        if text == _label:
            return _LEGACY_MINING_MASK_TO_CARD_TYPE[value]
    return CARD_TYPE_NONE


def box_card_type(box: WordMemorizeBox) -> str:
    """박스 CTA 타입 — 구 mining_mask·game_trap은 주제추천으로 이전."""
    explicit = normalize_card_type(str(getattr(box, "card_type", "") or ""))
    if explicit:
        return explicit
    legacy_mask = str(getattr(box, "mining_mask", "") or "").strip()
    migrated = _legacy_card_type_from_mining_mask(legacy_mask)
    if migrated:
        return migrated
    if box_game_trap(box):
        return _LEGACY_TRAP_CARD_TYPE
    return CARD_TYPE_NONE


def box_uses_mining_regrow(box: WordMemorizeBox) -> bool:
    """채굴 완료 후 화면 타일 조각모음 복구를 사용하는 카드."""
    return bool(box_card_type(box))


def card_type_cta_hanzi(card_type: str) -> str:
    """CTA 타입별 단어장 조회 한자 — 없으면 빈 문자열."""
    return CARD_TYPE_CTA_HANZI.get(normalize_card_type(card_type), "")


def box_cta_hanzi(box: WordMemorizeBox) -> str:
    """박스 CTA 고정 한자(구독→订阅, 좋아요→点赞)."""
    return card_type_cta_hanzi(box_card_type(box))


def card_type_cta_audio_rel(card_type: str, *, meaning_lang: str = "ko") -> str:
    """CTA 타입별 고정 음성 상대 경로 — zh는 stem_ch.mp3."""
    base = CARD_TYPE_CTA_AUDIO_REL.get(normalize_card_type(card_type), "")
    if not base:
        return ""
    if not _is_zh_meaning_lang(meaning_lang):
        return base
    p = Path(base.replace("\\", "/"))
    return str(p.with_name(f"{p.stem}_ch{p.suffix}"))


def box_cta_audio_path(
    box: WordMemorizeBox,
    *,
    meaning_lang: str = "ko",
) -> Path | None:
    """CTA 타입 박스 고정 mp3 절대 경로 — 일반 단어는 None."""
    rel = card_type_cta_audio_rel(box_card_type(box), meaning_lang=meaning_lang)
    if not rel:
        return None
    return get_repo_root() / rel.replace("\\", "/")


def card_type_cta_caption(card_type: str, *, meaning_lang: str = "ko") -> str:
    """CTA 음성 재생 시 하단 자막 문구 — zh 모드는 중국어."""
    norm = normalize_card_type(card_type)
    if _is_zh_meaning_lang(meaning_lang):
        return CARD_TYPE_CTA_CAPTION_ZH.get(norm, "")
    return CARD_TYPE_CTA_CAPTION.get(norm, "")


def box_cta_caption(box: WordMemorizeBox, *, meaning_lang: str = "ko") -> str:
    """박스 CTA 자막 — 없으면 빈 문자열."""
    return card_type_cta_caption(box_card_type(box), meaning_lang=meaning_lang)


def resolve_cta_caption_position(
    frame_width: int,
    frame_height: int,
    *,
    margin_bottom_ratio: float = DEFAULT_MARGIN_BOTTOM_RATIO,
    y_lift_px: int | None = None,
) -> tuple[int, int]:
    """CTA 자막 앵커 — 하단 가이드 띠 중앙에서 약간 위."""
    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    y_band_start = int(round((1.0 - float(margin_bottom_ratio)) * fh))
    lift = (
        int(y_lift_px)
        if y_lift_px is not None
        else max(48, int(90 * fh / 1920))
    )
    cx = fw // 2
    cy = y_band_start + (fh - y_band_start) // 2 - lift
    cy = max(y_band_start + 24, min(cy, fh - 24))
    return cx, cy


# CTA 자막 — FHD 기준 렌더 스케일
CTA_CAPTION_FONT_PT_FHD = 58
CTA_CAPTION_BG_PAD_X_FHD = 28
CTA_CAPTION_BG_PAD_Y_FHD = 16
CTA_CAPTION_BG_RADIUS_FHD = 12


def layout_subtitle_text_tile(layout: WordMemorizeLayout) -> str:
    """레이아웃 부제목 기본 text_tile stem (없으면 '')."""
    return normalize_word_memorize_game_text_tile(
        str(getattr(layout, "subtitle_text_tile", "") or "")
    )


def resolve_subtitle_line_text_tile(
    layout: WordMemorizeLayout, spec: SubtitleLineSpec
) -> str:
    """줄별 text_tile — 줄 설정 우선, 없으면 레이아웃 기본."""
    line_tile = normalize_word_memorize_game_text_tile(spec.text_tile)
    if line_tile:
        return line_tile
    return layout_subtitle_text_tile(layout)


def layout_game_tile(layout: WordMemorizeLayout) -> str:
    """레이아웃 첫 타일 stem (레거시·없으면 '')."""
    stems = layout_game_tiles(layout)
    return stems[0] if stems else ""


def layout_game_tiles(layout: WordMemorizeLayout) -> list[str]:
    """레이아웃 게임 타일 stem 목록 — 중복 제거, 순서 유지."""
    raw = getattr(layout, "game_tiles", None)
    if isinstance(raw, list):
        stems: list[str] = []
        seen: set[str] = set()
        for item in raw:
            stem = normalize_word_memorize_game_tile(str(item or ""))
            if stem and stem not in seen:
                seen.add(stem)
                stems.append(stem)
        if stems:
            return stems
    legacy = normalize_word_memorize_game_tile(
        str(getattr(layout, "game_tile", "") or "")
    )
    return [legacy] if legacy else []


def layout_game_tile_seed(layout: WordMemorizeLayout) -> int:
    """타일 격자 배치 시드 — 칸마다 타일 선택을 고정."""
    try:
        return int(getattr(layout, "game_tile_seed", 0) or 0) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return 0


def pick_game_tile_stem_for_cell(
    stems: list[str], col: int, row: int, seed: int
) -> str:
    """격자 (col, row)에 배치할 타일 stem — 시드·좌표로 결정(재현 가능)."""
    if not stems:
        return ""
    if len(stems) == 1:
        return stems[0]
    h = int(seed) & 0xFFFFFFFF
    h ^= (int(col) & 0xFFFF) * 374761393
    h ^= (int(row) & 0xFFFF) * 668265263
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return stems[h % len(stems)]


def sync_layout_game_tile_fields(layout: WordMemorizeLayout) -> None:
    """game_tiles → 레거시 game_tile(첫 항목)."""
    stems = layout_game_tiles(layout)
    layout.game_tiles = list(stems)
    layout.game_tile = stems[0] if stems else ""


def layout_game_particle(layout: WordMemorizeLayout) -> str:
    """레이아웃 첫 파티클 stem (레거시·없으면 '')."""
    stems = layout_game_particles(layout)
    return stems[0] if stems else ""


def layout_game_particles(layout: WordMemorizeLayout) -> list[str]:
    """레이아웃 파티클 stem 목록 — 중복 제거, 순서 유지."""
    raw = getattr(layout, "game_particles", None)
    if isinstance(raw, list):
        stems: list[str] = []
        seen: set[str] = set()
        for item in raw:
            stem = normalize_word_memorize_game_particle(str(item or ""))
            if stem and stem not in seen:
                seen.add(stem)
                stems.append(stem)
        if stems:
            return stems
    legacy = normalize_word_memorize_game_particle(
        str(getattr(layout, "game_particle", "") or "")
    )
    return [legacy] if legacy else []


def sync_layout_game_particle_fields(layout: WordMemorizeLayout) -> None:
    """game_particles → 레거시 game_particle(첫 항목)."""
    stems = layout_game_particles(layout)
    layout.game_particles = list(stems)
    layout.game_particle = stems[0] if stems else ""


def layout_game_pick(layout: WordMemorizeLayout) -> str:
    """레이아웃에 설정된 곡괭이 stem (없으면 '')."""
    return normalize_word_memorize_game_pick(
        str(getattr(layout, "game_pick", "") or "")
    )


def layout_uses_pick_mining(layout: WordMemorizeLayout) -> bool:
    """타일+곡괭이 채굴 연출 사용 여부."""
    return bool(layout_game_tiles(layout) and layout_game_pick(layout))


@dataclass
class WordMemorizeBox:
    word_id: str
    order: int
    x: int
    y: int
    w: int
    h: int
    box_key: str = ""
    # CTA 카드 타입 — subscribe / like / topic_recommend
    card_type: str = ""
    # 구 필드 — 로드 시 card_type으로만 이전
    mining_mask: str = ""
    game_trap: str = ""

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


def swap_box_rects(a: WordMemorizeBox, b: WordMemorizeBox) -> None:
    """두 word box의 위치·크기(x, y, w, h)만 교환한다. order·word_id 등은 유지."""
    a.x, b.x = b.x, a.x
    a.y, b.y = b.y, a.y
    a.w, b.w = b.w, a.w
    a.h, b.h = b.h, a.h


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
    background_type: BackgroundType = "video"
    background_value: str = DEFAULT_WORD_MEMORIZE_BG_STEM
    title: str = ""
    title_x: int = 0
    title_y: int = 0
    title_y_offset_px: int = 0
    title_color: str = DEFAULT_TITLE_COLOR
    title_font: str = DEFAULT_TITLE_FONT
    title_font_pt: int = DEFAULT_TITLE_FONT_PT
    title_lines: list[TitleLineSpec] = field(default_factory=list)
    title_zh: str = ""
    title_lines_zh: list[TitleLineSpec] = field(default_factory=list)
    subtitle: str = ""
    subtitle_text_tile: str = ""
    subtitle_font: str = DEFAULT_TITLE_FONT
    subtitle_y_offset_px: int = 0
    subtitle_lines: list[SubtitleLineSpec] = field(default_factory=list)
    subtitle_zh: str = ""
    subtitle_lines_zh: list[SubtitleLineSpec] = field(default_factory=list)
    selection_highlight: SelectionHighlightType = DEFAULT_SELECTION_HIGHLIGHT
    # 재생 중인 단어와 y·h가 같은 줄 강조 (카드 효과와 별도)
    row_highlight: RowHighlightType = DEFAULT_ROW_HIGHLIGHT
    # True: #1 카드는 이미지·테두리 없이 병음·한자·뜻만 크게
    use_base_slot: bool = False
    # True: 일반 word 카드 배경·테두리 (False면 글자·이미지만)
    use_card_background: bool = True
    # use_card_background=True 일 때 카드 채우기 색 (#RRGGBB 또는 팔레트 라벨)
    card_background_color: str = DEFAULT_CARD_BACKGROUND_COLOR
    # True: 카드에 단어 그림(img_path) 표시
    show_images: bool = True
    # resource/sound/bg_short 상대 경로. 비우면 재생 시 bg_short 랜덤.
    bg_music_path: str = ""
    # resource/image/game/tiles/{stem}.png — 화면 타일(복수·격자별 랜덤 배치)
    game_tile: str = ""
    game_tiles: list[str] = field(default_factory=list)
    game_tile_seed: int = 0
    # resource/image/game/particles/{stem}.png — 채굴 파편 (복수 선택 가능)
    game_particle: str = ""
    game_particles: list[str] = field(default_factory=list)
    # resource/image/game/effect — 레이저 디졸브 파티클 (복수·비우면 전체)
    dissolve_effect: str = ""
    dissolve_effects: list[str] = field(default_factory=list)
    # resource/image/game/picks/{stem}.png — 카드 중앙 스윙 채굴
    game_pick: str = ""
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
        sync_layout_title_fields_zh(self)
        sync_layout_subtitle_fields(self)
        sync_layout_subtitle_fields_zh(self)
        sync_layout_game_tile_fields(self)
        sync_layout_game_particle_fields(self)
        sync_layout_dissolve_effect_fields(self)
        self.title_x = int(self.frame_width) // 2
        return {
            "version": LAYOUT_VERSION,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "background": {
                "type": normalize_background_type(self.background_type),
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
            "title_zh": (self.title_zh or "").strip(),
            "title_lines_zh": [s.to_dict() for s in self.title_lines_zh],
            "subtitle": (self.subtitle or "").strip(),
            "subtitle_text_tile": layout_subtitle_text_tile(self),
            "subtitle_font": normalize_title_font(self.subtitle_font),
            "subtitle_y_offset_px": int(self.subtitle_y_offset_px),
            "subtitle_lines": [s.to_dict() for s in self.subtitle_lines],
            "subtitle_zh": (self.subtitle_zh or "").strip(),
            "subtitle_lines_zh": [s.to_dict() for s in self.subtitle_lines_zh],
            "selection_highlight": normalize_selection_highlight(self.selection_highlight),
            "row_highlight": normalize_row_highlight(self.row_highlight),
            "use_base_slot": bool(self.use_base_slot),
            "use_card_background": bool(self.use_card_background),
            "card_background_color": normalize_card_background_color(
                self.card_background_color
            ),
            "show_images": bool(self.show_images),
            "bg_music_path": (self.bg_music_path or "").strip(),
            "game_tile": layout_game_tile(self),
            "game_tiles": list(layout_game_tiles(self)),
            "game_tile_seed": int(layout_game_tile_seed(self)),
            "game_particle": layout_game_particle(self),
            "game_particles": list(layout_game_particles(self)),
            "dissolve_effect": layout_dissolve_effect(self),
            "dissolve_effects": list(
                layout_dissolve_effects(self, fallback_all=False)
            ),
            "game_pick": layout_game_pick(self),
            "boxes": [
                {
                    "word_id": b.word_id,
                    "order": b.order,
                    "x": b.x,
                    "y": b.y,
                    "w": b.w,
                    "h": b.h,
                    "box_key": b.box_key,
                    "card_type": box_card_type(b),
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
            background_type=normalize_background_type(str(bg.get("type", "video"))),
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
        layout.title_zh = str(data.get("title_zh", "") or "").strip()
        raw_lines_zh = data.get("title_lines_zh")
        if isinstance(raw_lines_zh, list) and raw_lines_zh:
            layout.title_lines_zh = [
                TitleLineSpec.from_dict(item)
                for item in raw_lines_zh
                if isinstance(item, dict)
            ]
        elif layout.title_zh:
            layout.title_lines_zh = title_line_specs_from_legacy_layout(
                layout.title_zh,
                color=layout.title_color,
                font=layout.title_font,
                font_pt=layout.title_font_pt,
            )
        sync_layout_title_fields_zh(layout)
        layout.subtitle = str(data.get("subtitle", "") or "").strip()
        layout.subtitle_text_tile = normalize_word_memorize_game_text_tile(
            str(data.get("subtitle_text_tile", "") or "")
        )
        layout.subtitle_font = normalize_title_font(
            str(data.get("subtitle_font", DEFAULT_TITLE_FONT) or DEFAULT_TITLE_FONT)
        )
        layout.subtitle_y_offset_px = int(data.get("subtitle_y_offset_px", 0) or 0)
        raw_sub_lines = data.get("subtitle_lines")
        if isinstance(raw_sub_lines, list) and raw_sub_lines:
            layout.subtitle_lines = [
                SubtitleLineSpec.from_dict(item)
                for item in raw_sub_lines
                if isinstance(item, dict)
            ]
        else:
            layout.subtitle_lines = subtitle_line_specs_from_legacy_layout(
                layout.subtitle,
                font=layout.subtitle_font,
                text_tile=layout.subtitle_text_tile,
            )
        sync_layout_subtitle_fields(layout)
        layout.subtitle_zh = str(data.get("subtitle_zh", "") or "").strip()
        raw_sub_lines_zh = data.get("subtitle_lines_zh")
        if isinstance(raw_sub_lines_zh, list) and raw_sub_lines_zh:
            layout.subtitle_lines_zh = [
                SubtitleLineSpec.from_dict(item)
                for item in raw_sub_lines_zh
                if isinstance(item, dict)
            ]
        elif layout.subtitle_zh:
            layout.subtitle_lines_zh = subtitle_line_specs_from_legacy_layout(
                layout.subtitle_zh,
                font=layout.subtitle_font,
                text_tile=layout.subtitle_text_tile,
            )
        sync_layout_subtitle_fields_zh(layout)
        raw_highlight = str(
            data.get("selection_highlight", DEFAULT_SELECTION_HIGHLIGHT) or ""
        ).strip()
        layout.selection_highlight = normalize_selection_highlight(raw_highlight)
        layout.row_highlight = normalize_row_highlight(data.get("row_highlight", "none"))
        layout.use_base_slot = bool(data.get("use_base_slot", False))
        layout.use_card_background = bool(data.get("use_card_background", True))
        layout.card_background_color = normalize_card_background_color(
            str(
                data.get("card_background_color", DEFAULT_CARD_BACKGROUND_COLOR)
                or DEFAULT_CARD_BACKGROUND_COLOR
            )
        )
        layout.show_images = bool(data.get("show_images", True))
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
                card_type=normalize_card_type(
                    str(raw.get("card_type", "") or "")
                ),
                mining_mask=str(raw.get("mining_mask", "") or "").strip(),
                game_trap=normalize_word_memorize_game_trap(
                    str(raw.get("game_trap", "") or "")
                ),
            )
            if not box.card_type:
                legacy = _legacy_card_type_from_mining_mask(box.mining_mask)
                if legacy:
                    box.card_type = legacy
                elif box.game_trap:
                    box.card_type = _LEGACY_TRAP_CARD_TYPE
            box.mining_mask = ""
            box.game_trap = ""
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
        raw_tiles = data.get("game_tiles")
        if isinstance(raw_tiles, list):
            layout.game_tiles = [
                normalize_word_memorize_game_tile(str(item or ""))
                for item in raw_tiles
            ]
            layout.game_tiles = [s for s in layout.game_tiles if s]
        else:
            single_tile = normalize_word_memorize_game_tile(
                str(data.get("game_tile", "") or "")
            )
            layout.game_tiles = [single_tile] if single_tile else []
        try:
            layout.game_tile_seed = int(data.get("game_tile_seed", 0) or 0) & 0xFFFFFFFF
        except (TypeError, ValueError):
            layout.game_tile_seed = 0
        sync_layout_game_tile_fields(layout)
        raw_particles = data.get("game_particles")
        if isinstance(raw_particles, list):
            layout.game_particles = [
                normalize_word_memorize_game_particle(str(item or ""))
                for item in raw_particles
            ]
            layout.game_particles = [
                s for s in layout.game_particles if s
            ]
        else:
            single = normalize_word_memorize_game_particle(
                str(data.get("game_particle", "") or "")
            )
            layout.game_particles = [single] if single else []
        sync_layout_game_particle_fields(layout)
        raw_dissolve = data.get("dissolve_effects")
        if isinstance(raw_dissolve, list):
            layout.dissolve_effects = [
                normalize_word_memorize_dissolve_effect(str(item or ""))
                for item in raw_dissolve
            ]
            layout.dissolve_effects = [s for s in layout.dissolve_effects if s]
        else:
            single_dissolve = normalize_word_memorize_dissolve_effect(
                str(data.get("dissolve_effect", "") or "")
            )
            layout.dissolve_effects = [single_dissolve] if single_dissolve else []
        sync_layout_dissolve_effect_fields(layout)
        layout.game_pick = normalize_word_memorize_game_pick(
            str(data.get("game_pick", "") or "")
        )
        return layout


def layout_use_base_slot(layout: WordMemorizeLayout) -> bool:
    return bool(getattr(layout, "use_base_slot", False))


def layout_use_card_background(layout: WordMemorizeLayout) -> bool:
    return bool(getattr(layout, "use_card_background", True))


def layout_card_background_rgb(layout: WordMemorizeLayout) -> tuple[int, int, int]:
    return card_background_color_to_rgb(
        getattr(layout, "card_background_color", DEFAULT_CARD_BACKGROUND_COLOR)
    )


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
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("layout JSON must be an object")
    return WordMemorizeLayout.from_dict(data)
