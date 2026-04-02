"""Learning step: video + central sentence block."""

from __future__ import annotations

from enum import Enum
from typing import Any

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

    class Stage(str, Enum):
        TITLE = "title"
        PLAY_L1 = "play_l1"
        WAIT_AFTER_L1 = "wait_after_l1"
        PLAY_L2 = "play_l2"
        WAIT_AFTER_L2 = "wait_after_l2"

    STAGE_SEQUENCE = (
        Stage.TITLE,
        Stage.PLAY_L1,
        Stage.WAIT_AFTER_L1,
        Stage.PLAY_L2,
        Stage.WAIT_AFTER_L2,
    )

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
        self._title_text: str = "학습"
        self._title_fade_in_sec: float = 1.0
        self._title_channel: str = "learning_title"
        self._sentence_channel: str = "learning_sentence"

        # 마지막 스테이지(WAIT_AFTER_L2) remain 만료 시 Step 종료는 BaseStep/엔진 공통 규칙으로 처리
        self.configure_stages(
            self.STAGE_SEQUENCE,
            finish_step_on_last_remain_expired=True,
        )
        self._current_item: ConversationItemLike = {}

    def register_stage_callbacks(self) -> None:
        """이 Step의 시나리오(진입·대기)를 정의한다."""
        S = self.Stage

        self.bind_enter(S.TITLE, lambda: self.set_timer(self._title_fade_in_sec))
        self.bind_enter(S.PLAY_L1, lambda: self._play_voice_and_advance("sound_l1"))
        self.bind_enter(S.PLAY_L2, lambda: self._play_voice_and_advance("sound_l2"))
        for _wait in (S.WAIT_AFTER_L1, S.WAIT_AFTER_L2):
            self.bind_enter(_wait, lambda: self.set_timer(self._hold_sec))

    def _play_voice_and_advance(self, key: str) -> None:
        self._try_play_item_voice(key)
        self.set_timer(0.0)

    def _item_identity_key(self, item: ConversationItemLike) -> Any:
        try:
            return (
                str(item.get("id") or ""),
                float(item.get("start_time", 0.0) or 0.0),
                float(item.get("end_time", -1.0) or -1.0),
            )
        except Exception:
            return None

    def _reset_step_on_item_change(self, item: ConversationItemLike) -> None:
        self.all_off()
        self.show_title(self._title_fade_in_sec)
        super()._reset_step_on_item_change(item)
        self._goto_stage(self.Stage.TITLE)

    def _try_play_item_voice(self, key: str) -> None:
        path = str(self._current_item.get(key) or "").strip()
        if not path or self._play_voice is None:
            return
        try:
            self._play_voice(path, item=self._current_item)
        except Exception:
            pass

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        self._current_item = item
        self.sync_item_identity(item)

        dt = float(ctx.dt_sec)
        self.drawer.fade_tick(dt)

        self._tick_stage(ctx)

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        center_x = ctx.width // 2
        y_base = int(ctx.height * 0.43)
        sentence_alpha = self.drawer.fade_alpha(self._sentence_channel)
        if sentence_alpha > 0:
            data = build_sentence_render_data_with_tone_icons(item)
            self.drawer.draw_sentence(
                screen,
                data,
                center_x=center_x,
                y_base=y_base,
                style=self._style,
                alpha=sentence_alpha,
                align="center",
            )

        title_alpha = self.drawer.fade_alpha(self._title_channel)
        if title_alpha > 0:
            try:
                self.drawer.draw_title(
                    screen,
                    self._title_text,
                    center_x=center_x,
                    y=int(ctx.height * 0.12),
                    color=self._style.hanzi_color,
                    alpha=title_alpha,
                    align="center",
                    min_margin_x=self._style.min_margin_x,
                )
            except Exception:
                pass

    def show_title(self, fade_in_sec: float = 0.0) -> None:
        self.drawer.fade_on(self._title_channel, fade_in_sec)

    def hide_title(self, fade_out_sec: float = 0.0) -> None:
        self.drawer.fade_off(self._title_channel, fade_out_sec)

    def show_sentence(self, fade_in_sec: float = 0.0) -> None:
        self.drawer.fade_on(self._sentence_channel, fade_in_sec)

    def hide_sentence(self, fade_out_sec: float = 0.0) -> None:
        self.drawer.fade_off(self._sentence_channel, fade_out_sec)

    def all_off(self, fade_out_sec: float = 0.0) -> None:
        self.drawer.fade_all_off([self._title_channel, self._sentence_channel], fade_out_sec)

    def on_stage_end(self, stage: Any) -> None:
        """스테이지가 바뀔 때의 UI 부수 효과."""
        if stage == self.Stage.TITLE:
            self.show_sentence()

    def on_main_end(self) -> None:
        if self.transition_bg_frame is None and self.bg_frame is not None:
            try:
                self.transition_bg_frame = self.bg_frame.copy()
            except Exception:
                self.transition_bg_frame = self.bg_frame
        self.transition_signal = True
