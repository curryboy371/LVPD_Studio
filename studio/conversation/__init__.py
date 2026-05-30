"""
회화 스튜디오: IStudio 구현.
LoadedContent 또는 CSV 로드·비디오 재생·문장/병음/번역 표시.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from .studio import ConversationStudio

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


def __getattr__(name: str):
    if name == "ConversationStudio":
        from .studio import ConversationStudio

        return ConversationStudio
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
