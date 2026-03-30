"""
회화 스튜디오: IStudio 구현.
LoadedContent 또는 CSV 로드·비디오 재생·문장/병음/번역 표시.
"""
from .studio import ConversationStudio
from .tools.fonts import (
    RGB,
    COLOR_TABLE,
    ColorName,
    ConversationFontSizes,
    ConversationRenderSettings,
    DEFAULT_CONVERSATION_RENDER_SETTINGS,
    FontBundle,
    AMBER,
    BLACK,
    BLUE,
    CYAN_LIGHT,
    GRAY,
    GRAY_LIGHT,
    GRAY_MUTED,
    GREEN,
    RED,
    WHITE,
    YELLOW_PALE,
)

__all__ = [
    "ConversationStudio",
    "RGB",
    "COLOR_TABLE",
    "ColorName",
    "ConversationFontSizes",
    "ConversationRenderSettings",
    "DEFAULT_CONVERSATION_RENDER_SETTINGS",
    "FontBundle",
    "AMBER",
    "BLACK",
    "BLUE",
    "CYAN_LIGHT",
    "GRAY",
    "GRAY_LIGHT",
    "GRAY_MUTED",
    "GREEN",
    "RED",
    "WHITE",
    "YELLOW_PALE",
]
