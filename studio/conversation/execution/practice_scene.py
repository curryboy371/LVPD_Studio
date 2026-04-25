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
        title_fade_in_sec: float = 1.0,
    ) -> None:
        """연습용 Drawer·비디오·문장 스타일을 연결하고 제목 페이드인을 준비한다."""
        super().__init__()
        self.drawer = drawer
        self.video_player = video_player
        self.scene_transition_mode: SceneTransitionMode = SceneTransitionMode.CUT
        self.scene_transition_duration_sec: float = 0.4
        self.scene_transition_overlay_peak_alpha: int = 220
        self._style = style
        self.title_text = str(title_text or "연습")
        self.title_fade_in_sec = float(title_fade_in_sec)
        self._title_channel = "practice_title"
        self._sentence_channel = "practice_sentence"
        self._active_item_key = None
        self._title_wait_remaining_sec = 0.0
        self._content_visible = False
        self.drawer.hide_now(self._title_channel)
        self.drawer.hide_now(self._sentence_channel)

    def on_update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """아이템이 바뀌면 제목을 먼저 fade in 하고, 끝난 뒤 문장/단어를 노출한다."""
        # Drawer 내부 알파 애니메이션 타이머를 매 프레임 진행한다.
        dt = float(ctx.dt_sec)
        self.drawer.fade_tick(dt)

        key = (item.get("id"), item.get("start_time"), item.get("end_time"))
        if key != self._active_item_key:
            self._active_item_key = key
            # 새 아이템 진입 시에는 본문을 숨기고 제목 페이드부터 진행한다.
            self._content_visible = False
            self._title_wait_remaining_sec = self.title_fade_in_sec
            self.drawer.hide_now(self._sentence_channel)
            self.drawer.fade_on(self._title_channel, self.title_fade_in_sec)
            return

        # 제목 페이드 시간이 지난 뒤에 본문(문장/단어)을 표시한다.
        if not self._content_visible and self._title_wait_remaining_sec > 0.0:
            self._title_wait_remaining_sec = max(0.0, self._title_wait_remaining_sec - dt)
            if self._title_wait_remaining_sec <= 0.0:
                self._content_visible = True
                self.drawer.show_now(self._sentence_channel)
        return

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """비디오 위에 LEARNING과 동일 세로 배치(중앙·타이틀 밴드 여유)의 문장과 첫 단어(있으면)를 표시한다."""
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        self.drawer.draw_item_title(
            screen,
            self.title_text,
            ctx=ctx,
            channel=self._title_channel,
            style=self._style,
        )

        if not self._content_visible:
            return

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
