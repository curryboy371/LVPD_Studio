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
    # 컨텐츠(화면) 시퀀스의 첫 화면은 VIDEO가 기본
    step_kind: StepKind = StepKind.VIDEO


class PlaybackManager:
    """전체 재생 시나리오의 생명주기를 관리하는 관리자.

    여기서의 핵심 개념:
    - item: CSV/콘텐츠에서 로드된 "재생 단위" (video_path, start/end, sentence 등)
    - step: 화면(컨텐츠) 하나를 그리는 단위(VideoStep/LearningStep/PracticeStep 등)
    - step_sequence: item 1개를 어떤 "컨텐츠 순서"로 보여줄지 선언하는 리스트
      예) [VIDEO, LEARNING] 이면
        1) VIDEO 화면(비디오만) → 2) LEARNING 화면(비디오+문장)
      처럼 자동 진행된다(각 step이 transition_signal=True를 올리면 다음 step으로 넘어감).
    """

    def __init__(
        self,
        *,
        items: Sequence[ConversationItemLike],
        steps: Mapping[StepKind, Any],
        video_player: Any,
        step_sequence: Sequence[StepKind] | None = None,
    ) -> None:
        self._items = list(items)
        self._steps = dict(steps)
        self._video_player = video_player
        # "컨텐츠(화면) 시퀀스" 정의.
        # - None이면 기본값: VIDEO → LEARNING
        # - step_sequence에 포함된 StepKind는 반드시 steps 매핑에 존재해야 정상 동작
        self._step_sequence: list[StepKind] = list(step_sequence) if step_sequence else [StepKind.VIDEO, StepKind.LEARNING]
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
        # 수동 전환(숫자키 등)도 허용: 단, 다음 프레임부터 해당 step이 렌더/업데이트 된다.
        # 시퀀스 진행 중이라도 사용자가 직접 바꿀 수 있게 둔다.
        if kind in self._steps:
            self.state.step_kind = kind
            self._reset_step_done_flag(kind)

    def next_item(self) -> None:
        if not self._items:
            return
        self.state.item_index = min(len(self._items) - 1, self.state.item_index + 1)
        self._apply_item_to_video(self.current_item())
        self._clear_step_backgrounds()
        # item이 바뀌면 "컨텐츠 시퀀스"도 처음 화면으로 되돌린다.
        # (예: 새 문장/새 구간은 항상 VIDEO 화면부터 보여주기)
        if self._step_sequence:
            self.state.step_kind = self._step_sequence[0]
            self._reset_step_done_flag(self.state.step_kind)

    def prev_item(self) -> None:
        if not self._items:
            return
        self.state.item_index = max(0, self.state.item_index - 1)
        self._apply_item_to_video(self.current_item())
        self._clear_step_backgrounds()
        if self._step_sequence:
            self.state.step_kind = self._step_sequence[0]
            self._reset_step_done_flag(self.state.step_kind)

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
        if getattr(step, "transition_signal", False):
            # step이 "전환 시그널"을 올리면 step_sequence에 따라 다음 화면으로 넘어간다.
            self._advance_step_in_sequence(ctx)

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

    def _reset_step_done_flag(self, kind: StepKind) -> None:
        # 컨텐츠(step) 전환 시 이전 완료 상태가 남아있으면 즉시 스킵되는 문제가 생길 수 있어서
        # 전환 시점에 플래그들을 리셋한다.
        step = self._steps.get(kind)
        if step is None:
            return
        if hasattr(step, "is_done"):
            try:
                step.is_done = False
            except Exception:
                pass
        if hasattr(step, "transition_signal"):
            try:
                step.transition_signal = False
            except Exception:
                pass

    def _advance_step_in_sequence(self, ctx: FrameContext) -> None:
        """현재 컨텐츠(step)가 완료되면 step_sequence에 따라 다음 컨텐츠로 이동."""
        cur = self.state.step_kind
        seq = self._step_sequence
        if not seq:
            return
        try:
            idx = seq.index(cur)
        except ValueError:
            # 시퀀스에 없으면 첫 화면으로 복귀
            self.state.step_kind = seq[0]
            self._reset_step_done_flag(self.state.step_kind)
            return
        next_idx = min(len(seq) - 1, idx + 1)
        if next_idx == idx:
            # 마지막 컨텐츠면 done만 리셋하고 유지
            self._reset_step_done_flag(cur)
            return
        next_kind = seq[next_idx]
        self._capture_and_set_next_bg(ctx, next_kind)
        self.state.step_kind = next_kind
        self._reset_step_done_flag(self.state.step_kind)

    def _capture_and_set_next_bg(self, ctx: FrameContext, next_kind: StepKind) -> None:
        """현재 프레임을 캡처해 다음 step의 배경(bg_frame)으로 주입."""
        cur_step = self._steps.get(self.state.step_kind)
        snap = None
        if cur_step is not None and hasattr(cur_step, "transition_bg_frame"):
            try:
                trans = cur_step.transition_bg_frame
                snap = trans.copy() if trans is not None else None
            except Exception:
                snap = None
        try:
            if snap is None:
                frame = self._video_player.get_frame(ctx.width, ctx.height)
                snap = frame.copy() if frame is not None else None
        except Exception:
            snap = None
        step = self._steps.get(next_kind)
        if step is None:
            return
        if hasattr(step, "bg_frame"):
            try:
                step.bg_frame = snap
            except Exception:
                pass

    def _clear_step_backgrounds(self) -> None:
        """item 이동 등으로 배경 스냅샷이 의미 없을 때 초기화."""
        for step in self._steps.values():
            if hasattr(step, "bg_frame"):
                try:
                    step.bg_frame = None
                except Exception:
                    pass
            if hasattr(step, "transition_bg_frame"):
                try:
                    step.transition_bg_frame = None
                except Exception:
                    pass

