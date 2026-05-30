"""Conversation studio tools layer (drawers/utilities)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .playback_bar import (
        CONVERSATION_PLAYBACK_BAR_MARGIN_BOTTOM_PX,
        CONVERSATION_TIP_BOX_Y_OFFSET_FROM_BAR_TOP_PX,
        PlaybackBarLayout,
        PlaybackBarRenderer,
        PlaybackBarStyle,
        format_playback_time,
    )

__all__ = [
    "CONVERSATION_PLAYBACK_BAR_MARGIN_BOTTOM_PX",
    "CONVERSATION_TIP_BOX_Y_OFFSET_FROM_BAR_TOP_PX",
    "PlaybackBarStyle",
    "PlaybackBarLayout",
    "PlaybackBarRenderer",
    "format_playback_time",
]


def __getattr__(name: str):
    if name in __all__:
        from . import playback_bar

        return getattr(playback_bar, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
