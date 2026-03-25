"""Video-only step."""

from __future__ import annotations

import pygame

from ..core.types import ConversationItemLike, FrameContext
from .base import BaseStep


class VideoStep(BaseStep):
    """비디오 프레임만 그리는 Step."""

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        _ = (ctx, item)
        return

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        _ = item
        frame = self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

