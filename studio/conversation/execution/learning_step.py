"""Learning step: video + central sentence block."""

from __future__ import annotations

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

    def __init__(self, *, drawer, video_player, style: SentenceStyleConfig) -> None:
        super().__init__(drawer=drawer, video_player=video_player)
        self._style = style

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        _ = (ctx, item)
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

