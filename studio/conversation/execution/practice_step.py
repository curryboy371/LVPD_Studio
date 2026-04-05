"""Practice step: video + sentence + current word (minimal)."""

from __future__ import annotations

import pygame

from ..core.step_transition import StepTransitionMode
from ..core.types import ConversationItemLike, FrameContext, SentenceStyleConfig
from .base import IStep


class PracticeStep(IStep):
    """연습 Step.

    render_only 범위에서는 '단어 리스트를 순회' 로직은 넣지 않고,
    words가 있으면 첫 단어만 화면에 표시하는 수준으로 단순화한다.

    `style`은 `ConversationStudio.init`에서 폰트 로드와 맞춘 RGB로 구성해 넘긴다.
    """

    def __init__(self, *, drawer, video_player, style: SentenceStyleConfig) -> None:
        super().__init__()
        self.drawer = drawer
        self.video_player = video_player
        self.step_transition_mode: StepTransitionMode = StepTransitionMode.CUT
        self.step_transition_duration_sec: float = 0.4
        self.step_transition_overlay_peak_alpha: int = 220
        self._style = style
        self._sentence_channel = "practice_sentence"
        self.drawer.fade_on(self._sentence_channel, 0.0)

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        _ = (ctx, item)
        return

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        self.drawer.draw_item_sentence(
            screen,
            item,
            ctx=ctx,
            channel=self._sentence_channel,
            style=self._style,
            align_v="top",
            top_y_ratio=0.34,
        )

        words = item.get("words") or []
        word = str(words[0]) if words else ""
        if word:
            # 현재 단어 표시(최소)
            try:
                font = pygame.font.Font(None, 44)
                surf = font.render(word[:24], True, (255, 210, 80))
                center_x = ctx.width // 2
                screen.blit(surf, (max(20, center_x - surf.get_width() // 2), int(ctx.height * 0.72)))
            except Exception:
                pass

