"""Practice step: video + sentence + current word (minimal)."""

from __future__ import annotations

import pygame

from ..core.types import ConversationItemLike, FrameContext, SentenceStyleConfig, extract_sentence_render_data
from .base import BaseStep


class PracticeStep(BaseStep):
    """연습 Step.

    render_only 범위에서는 '단어 리스트를 순회' 로직은 넣지 않고,
    words가 있으면 첫 단어만 화면에 표시하는 수준으로 단순화한다.
    """

    def __init__(self, *, drawer, video_player, style: SentenceStyleConfig | None = None) -> None:
        super().__init__(drawer=drawer, video_player=video_player)
        self._style = style or SentenceStyleConfig(hanzi_color=(255, 230, 120))

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        _ = (ctx, item)
        return

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        data = extract_sentence_render_data(item)
        center_x = ctx.width // 2
        y_base = int(ctx.height * 0.34)
        self.drawer.draw_sentence(
            screen,
            data,
            center_x=center_x,
            y_base=y_base,
            style=self._style,
            alpha=255,
            align="center",
        )

        words = item.get("words") or []
        word = str(words[0]) if words else ""
        if word:
            # 현재 단어 표시(최소)
            try:
                font = pygame.font.Font(None, 44)
                surf = font.render(word[:24], True, (255, 210, 80))
                screen.blit(surf, (max(20, center_x - surf.get_width() // 2), int(ctx.height * 0.72)))
            except Exception:
                pass

