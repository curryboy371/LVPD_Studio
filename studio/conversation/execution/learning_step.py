"""Learning step: video + central sentence block."""

from __future__ import annotations

from enum import Enum

import pygame

from ..core.types import (
    ConversationItemLike,
    FrameContext,
    SentenceStyleConfig,
    build_sentence_render_data_with_tone_icons,
)
from .base import BaseStep


class LearningStep(BaseStep):
    """학습(중앙 문장 표시) Step.

    `style`은 `ConversationStudio.init`에서 폰트 로드와 같은 RGB 상수로 구성해 넘긴다.
    """

    def __init__(
        self,
        *,
        drawer,
        video_player,
        style: SentenceStyleConfig,
        hold_sec: float = 2.0,
        play_voice: callable | None = None,
    ) -> None:
        super().__init__(drawer=drawer, video_player=video_player)
        self._style = style
        self._hold_sec = max(0.0, float(hold_sec))
        self._play_voice = play_voice

        class _Stage(str, Enum):
            PLAY_L1 = "play_l1"
            WAIT = "wait"
            PLAY_L2 = "play_l2"
            DONE = "done"

        # LearningStep 기본 시퀀스:
        # 1) sound_l1 재생(없으면 스킵)
        # 2) 3초 대기
        # 3) sound_l2 재생(없으면 스킵)
        # 4) 3초 대기 후 다음 step으로 전환
        self._Stage = _Stage
        self._stage: _Stage = _Stage.PLAY_L1
        self._next_stage_after_wait: _Stage = _Stage.PLAY_L2
        self._stage_elapsed_sec: float = 0.0
        self._active_key: tuple[str, float, float] | None = None

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        # item이 바뀌면 상태 리셋
        try:
            key = (
                str(item.get("id") or ""),
                float(item.get("start_time", 0.0) or 0.0),
                float(item.get("end_time", -1.0) or -1.0),
            )
        except Exception:
            key = None
        if key != self._active_key:
            self._active_key = key
            self._stage = self._Stage.PLAY_L1
            self._next_stage_after_wait = self._Stage.PLAY_L2
            self._stage_elapsed_sec = 0.0
            self.transition_bg_frame = None
            self.transition_signal = False

        wait_sec = 3.0
        dt = float(ctx.dt_sec)

        if self._stage == self._Stage.PLAY_L1:
            path = str(item.get("sound_l1") or "").strip()
            if path and self._play_voice is not None:
                try:
                    self._play_voice(path, item=item)
                except Exception:
                    pass
            self._stage = self._Stage.WAIT
            self._stage_elapsed_sec = 0.0
            self._next_stage_after_wait = self._Stage.PLAY_L2
            return

        if self._stage == self._Stage.PLAY_L2:
            path = str(item.get("sound_l2") or "").strip()
            if path and self._play_voice is not None:
                try:
                    self._play_voice(path, item=item)
                except Exception:
                    pass
            self._stage = self._Stage.WAIT
            self._stage_elapsed_sec = 0.0
            self._next_stage_after_wait = self._Stage.DONE
            return

        if self._stage == self._Stage.WAIT:
            self._stage_elapsed_sec += dt
            if self._stage_elapsed_sec >= wait_sec:
                self._stage_elapsed_sec = 0.0
                self._stage = self._next_stage_after_wait
            return

        if self._stage == self._Stage.DONE:
            # 이전 step에서 받은 배경을 다음 step에도 그대로 전달
            if self.transition_bg_frame is None and self.bg_frame is not None:
                try:
                    self.transition_bg_frame = self.bg_frame.copy()
                except Exception:
                    self.transition_bg_frame = self.bg_frame
            self.transition_signal = True
            return

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        data = build_sentence_render_data_with_tone_icons(item)
        center_x = ctx.width // 2
        y_base = int(ctx.height * 0.43)
        self.drawer.draw_sentence(
            screen,
            data,
            center_x=center_x,
            y_base=y_base,
            style=self._style,
            alpha=255,
            align="center",
        )

