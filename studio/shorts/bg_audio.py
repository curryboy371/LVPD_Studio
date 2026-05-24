"""숏츠 배경음 — resource/sound/bg (회화·단어장과 동일)."""

from __future__ import annotations

from studio.conversation.bg_audio import (
    ConversationBackgroundPlayer as ShortsBackgroundPlayer,
    load_conversation_background_sounds as load_background_sounds,
)

__all__ = ["ShortsBackgroundPlayer", "load_background_sounds"]
