"""Learning step: video + central sentence block."""

from __future__ import annotations

import pygame

from ..core.types import ConversationItemLike, FrameContext, SentenceStyleConfig, extract_sentence_render_data
from .base import BaseStep


class LearningStep(BaseStep):
    """학습(중앙 문장 표시) Step."""

    def __init__(self, *, drawer, video_player, style: SentenceStyleConfig | None = None) -> None:
        super().__init__(drawer=drawer, video_player=video_player)
        self._style = style or SentenceStyleConfig()

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        _ = (ctx, item)
        return

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        data = extract_sentence_render_data(item)
        center_x = ctx.width // 2
        y_base = int(ctx.height * 0.38)
        self.drawer.draw_sentence(
            screen,
            data,
            center_x=center_x,
            y_base=y_base,
            style=self._style,
            alpha=255,
            align="center",
        )

