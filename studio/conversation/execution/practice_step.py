"""Practice step: video + sentence + current word (minimal)."""

from __future__ import annotations

import pygame

from ..core.step_transition import ConversationStepTransitionMode
from ..core.types import ConversationItemLike, FrameContext, SentenceStyleConfig
from ..core.step_base import IConversationStep


class PracticeStep(IConversationStep):
    """연습 화면 ConversationStep.

    render_only 범위에서는 '단어 리스트를 순회' 로직은 넣지 않고,
    words가 있으면 첫 단어만 화면에 표시하는 수준으로 단순화한다.

    `style`은 `ConversationStudio.init`에서 폰트 로드와 맞춘 RGB로 구성해 넘긴다.
    """

    def __init__(self, *, drawer, video_player, style: SentenceStyleConfig) -> None:
        """연습용 Drawer·비디오·문장 스타일을 연결하고 문장 채널 페이드를 켠다."""
        super().__init__()
        self.drawer = drawer
        self.video_player = video_player
        self.conversation_step_transition_mode: ConversationStepTransitionMode = ConversationStepTransitionMode.CUT
        self.conversation_step_transition_duration_sec: float = 0.4
        self.conversation_step_transition_overlay_peak_alpha: int = 220
        self._style = style
        self._sentence_channel = "practice_sentence"
        self.drawer.show_now(self._sentence_channel)

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """render_only 범위에서 상태 갱신 없음(정적 연습 화면)."""
        _ = (ctx, item)
        return

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """비디오 위에 상단 정렬 문장과 첫 단어(있으면)를 표시한다."""
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

