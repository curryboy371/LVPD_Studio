"""PlaybackManager: control layer for conversation studio."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

import pygame

from .types import ConversationItemLike, FrameContext


class StepKind(str, Enum):
    VIDEO = "video"
    LEARNING = "learning"
    PRACTICE = "practice"


@dataclass
class PlaybackState:
    item_index: int = 0
    step_kind: StepKind = StepKind.LEARNING


class PlaybackManager:
    """전체 재생 시나리오의 생명주기를 관리하는 관리자."""

    def __init__(
        self,
        *,
        items: Sequence[ConversationItemLike],
        steps: Mapping[StepKind, Any],
        video_player: Any,
    ) -> None:
        self._items = list(items)
        self._steps = dict(steps)
        self._video_player = video_player
        self.state = PlaybackState()

        if self._items:
            self._apply_item_to_video(self._items[0])

    def has_items(self) -> bool:
        return bool(self._items)

    def current_item(self) -> ConversationItemLike:
        if not self._items:
            return {}
        idx = max(0, min(len(self._items) - 1, self.state.item_index))
        return self._items[idx]

    def set_step(self, kind: StepKind) -> None:
        if kind in self._steps:
            self.state.step_kind = kind

    def next_item(self) -> None:
        if not self._items:
            return
        self.state.item_index = min(len(self._items) - 1, self.state.item_index + 1)
        self._apply_item_to_video(self.current_item())

    def prev_item(self) -> None:
        if not self._items:
            return
        self.state.item_index = max(0, self.state.item_index - 1)
        self._apply_item_to_video(self.current_item())

    def toggle_pause(self) -> None:
        try:
            self._video_player.toggle_pause()
        except Exception:
            pass

    def seek(self, delta_sec: float) -> None:
        try:
            self._video_player.seek(float(delta_sec))
        except Exception:
            pass

    def restart_segment(self) -> None:
        item = self.current_item()
        start = float(item.get("start_time", 0.0) or 0.0)
        try:
            self._video_player.seek_to(start)
        except Exception:
            pass

    def update(self, ctx: FrameContext) -> None:
        """프레임 업데이트."""
        try:
            self._video_player.tick(ctx.dt_sec)
        except Exception:
            pass
        step = self._steps.get(self.state.step_kind)
        if step is None:
            return
        step.update(ctx, item=self.current_item())

    def render(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        """현재 step 렌더."""
        step = self._steps.get(self.state.step_kind)
        if step is None:
            return
        step.render(screen, ctx, item=self.current_item())

    def _apply_item_to_video(self, item: ConversationItemLike) -> None:
        """item의 video_path/start/end를 video_player에 적용."""
        path = str(item.get("video_path") or "").strip()
        st = float(item.get("start_time", 0.0) or 0.0)
        et = float(item.get("end_time", -1.0) if item.get("end_time", -1.0) is not None else -1.0)
        try:
            self._video_player.set_source(path, st, et)
        except Exception:
            pass

