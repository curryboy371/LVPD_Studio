"""Pygame font bundle for Conversation drawers.

Drawer가 `ConversationStudio` 내부 속성에 직접 의존하지 않도록 폰트 핸들을 묶는다.
글자색 RGB는 `COLOR_TABLE`에만 정의하고, `utils.fonts.load_font_*`에는 아래 `RED`, `WHITE` 같은
튜플 상수를 두 번째 인자로만 넘긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..core.types import SentenceStyleConfig

# pygame 텍스트 색 (R, G, B)
RGB = tuple[int, int, int]


class ColorName(Enum):
    """색상 테이블 키. 실제 RGB는 `COLOR_TABLE`에서만 수정한다."""

    WHITE = "WHITE"
    BLACK = "BLACK"
    RED = "RED"
    GREEN = "GREEN"
    BLUE = "BLUE"
    GRAY = "GRAY"
    GRAY_LIGHT = "GRAY_LIGHT"
    GRAY_MUTED = "GRAY_MUTED"
    AMBER = "AMBER"
    CYAN_LIGHT = "CYAN_LIGHT"
    YELLOW_PALE = "YELLOW_PALE"


# 이름 → RGB (색 값은 여기만 편집)
COLOR_TABLE: dict[ColorName, RGB] = {
    ColorName.WHITE: (255, 255, 255),
    ColorName.BLACK: (0, 0, 0),
    ColorName.RED: (255, 60, 60),
    ColorName.GREEN: (80, 220, 120),
    ColorName.BLUE: (100, 170, 255),
    ColorName.GRAY: (128, 128, 128),
    ColorName.GRAY_LIGHT: (220, 220, 220),
    ColorName.GRAY_MUTED: (200, 200, 200),
    ColorName.AMBER: (255, 230, 120),
    ColorName.CYAN_LIGHT: (180, 255, 255),
    ColorName.YELLOW_PALE: (255, 255, 160),
}

# load_font_chinese(size, RED) 형태 — RGB 튜플 상수만 사용
RED = COLOR_TABLE[ColorName.RED]
BLACK = COLOR_TABLE[ColorName.BLACK]
WHITE = COLOR_TABLE[ColorName.WHITE]
GREEN = COLOR_TABLE[ColorName.GREEN]
BLUE = COLOR_TABLE[ColorName.BLUE]
GRAY = COLOR_TABLE[ColorName.GRAY]
GRAY_LIGHT = COLOR_TABLE[ColorName.GRAY_LIGHT]
GRAY_MUTED = COLOR_TABLE[ColorName.GRAY_MUTED]
AMBER = COLOR_TABLE[ColorName.AMBER]
CYAN_LIGHT = COLOR_TABLE[ColorName.CYAN_LIGHT]
YELLOW_PALE = COLOR_TABLE[ColorName.YELLOW_PALE]


@dataclass(frozen=True)
class ConversationFontSizes:
    """`_load_fonts`에서 쓰는 pt 크기. 필드 순서는 CLI `--font-sizes`와 동일."""

    cn_big: int = 36
    cn: int = 28
    cn_step1_hanzi: int = 124
    cn_step1_pinyin: int = 66
    kr: int = 28
    kr_step1: int = 56


@dataclass(frozen=True)
class ConversationRenderSettings:
    """회화 스튜디오: 폰트 크기만. 색은 `load_font_*` 인자로만 지정한다."""

    font_sizes: ConversationFontSizes


DEFAULT_CONVERSATION_RENDER_SETTINGS = ConversationRenderSettings(
    font_sizes=ConversationFontSizes(),
)

DEFAULT_LEARNING_STYLE = SentenceStyleConfig(
    hanzi_color=WHITE,
    pinyin_color=RED,
    translation_color=GRAY_MUTED,
)
DEFAULT_PRACTICE_STYLE = SentenceStyleConfig(
    hanzi_color=AMBER,
    pinyin_color=RED,
    translation_color=GRAY_MUTED,
)


@dataclass(frozen=True)
class FontBundle:
    """텍스트 렌더링에 필요한 pygame/freeType 폰트 묶음.

    사용처는 `CommonDrawer.draw_sentence` 한 곳이다.
    - hanzi_ft / hanzi_pg: 한자 문장 줄 (freetype 우선, 실패 시 pygame 폰트)
    - pinyin_ft / pinyin_pg: 병음 줄
    - translation_pg: 한국어 번역 줄 (pygame.font만 사용)
    """

    hanzi_ft: Any
    hanzi_pg: Any
    pinyin_ft: Any
    pinyin_pg: Any
    translation_pg: Any
