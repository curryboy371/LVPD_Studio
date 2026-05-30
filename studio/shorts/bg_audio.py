"""숏츠 배경음 — resource/sound/bg_short (지정 없으면 랜덤)."""

from __future__ import annotations

import logging

from core.paths import get_repo_root
from studio.conversation.bg_audio import (
    ConversationBackgroundPlayer,
    load_background_sound_file,
    load_shorts_background_sounds,
)

logger = logging.getLogger(__name__)

_SHORTS_BG_DIR = get_repo_root() / "resource" / "sound" / "bg_short"


class ShortsBackgroundPlayer(ConversationBackgroundPlayer):
    """숏츠 전용: 랜덤·폴백은 bg_short, bg_path 지정 시 해당 파일."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._sounds = []
        self._last_index = None

    def reload_sounds(self) -> None:
        if self._fixed_bg_path:
            self._sounds = load_background_sound_file(self._fixed_bg_path)
            if not self._sounds:
                logger.warning(
                    "지정 bg_path 재생 불가 → bg_short 랜덤: %s",
                    self._fixed_bg_path,
                )
                self._fixed_bg_path = None
        if not self._fixed_bg_path:
            self._sounds = load_shorts_background_sounds()

    def start_session(
        self,
        *,
        duration_hint_sec: float = 3600.0,
        reload: bool = False,
        restart: bool = True,
    ) -> None:
        if reload or not self._sounds:
            self.reload_sounds()
        if not self._sounds:
            logger.warning("숏츠 배경음 없음: %s", _SHORTS_BG_DIR)
            return
        super().start_session(
            duration_hint_sec=duration_hint_sec,
            reload=False,
            restart=restart,
        )


load_background_sounds = load_shorts_background_sounds

__all__ = ["ShortsBackgroundPlayer", "load_background_sounds", "load_shorts_background_sounds"]
