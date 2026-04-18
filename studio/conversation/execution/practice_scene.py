"""연습 장면(Scene): 비디오 + 문장 + 현재 단어(최소)."""

from __future__ import annotations

import pygame

from ..core.scene_transition import SceneTransitionMode
from ..core.types import ConversationItemLike, FrameContext, SentenceStyleConfig
from ..core.conversation_step import IConversationStep


class PracticeScene(IConversationStep):
    """연습 장면.

    render_only 범위에서는 '단어 리스트를 순회' 로직은 넣지 않고,
    words가 있으면 첫 단어만 화면에 표시하는 수준으로 단순화한다.

    `style`은 `ConversationStudio.init`에서 폰트 로드와 맞춘 RGB로 구성해 넘긴다.
    """

    def __init__(
        self,
        *,
        drawer,
        video_player,
        style: SentenceStyleConfig,
        title_text: str = "연습",
    ) -> None:
        """연습용 Drawer·비디오·문장 스타일을 연결하고 문장 채널 페이드를 켠다."""
        super().__init__()
        self.drawer = drawer
        self.video_player = video_player
        self.scene_transition_mode: SceneTransitionMode = SceneTransitionMode.CUT
        self.scene_transition_duration_sec: float = 0.4
        self.scene_transition_overlay_peak_alpha: int = 220
        self._style = style
        self.title_text = str(title_text or "연습")
        self._sentence_channel = "practice_sentence"
        self.drawer.show_now(self._sentence_channel)

    def on_update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """render_only 범위에서 상태 갱신 없음(정적 연습 화면)."""
        _ = (ctx, item)
        return

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """비디오 위에 LEARNING과 동일 세로 배치(중앙·타이틀 밴드 여유)의 문장과 첫 단어(있으면)를 표시한다."""
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        self.drawer.draw_item_sentence(
            screen,
            item,
            ctx=ctx,
            channel=self._sentence_channel,
            style=self._style,
            title_clearance=(self.title_text, 0.12, 12),
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
