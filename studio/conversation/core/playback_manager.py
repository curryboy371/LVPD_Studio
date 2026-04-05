"""PlaybackManager: control layer for conversation studio."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

import pygame

from ..execution.base import IStep
from .step_transition import (
    PendingStepTransition,
    StepTransitionMode,
    blend_crossfade,
    blit_black_overlay,
    read_step_transition,
)
from .types import ConversationItemLike, FrameContext


class StepKind(str, Enum):
    VIDEO = "video"
    LEARNING = "learning"
    PRACTICE = "practice"


class LastStepSequencePolicy(str, Enum):
    """`step_sequence`의 마지막 Step에서 `transition_signal`이 올 때 동작."""

    STAY = "stay"
    """`transition_signal`만 소비하고 같은 Step·같은 item에 머무름(기본)."""

    ADVANCE_ITEM = "advance_item"
    """다음 item으로 넘긴 뒤 시퀀스 첫 Step으로(마지막 item이면 인덱스만 클램프)."""


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

    Step 간 전환은 나가는 Step의 `step_transition_mode`로 조절한다:
    - CUT: 즉시 전환 + bg_frame 스냅샷(기본)
    - CROSSFADE: 스냅샷과 다음 Step 합성
    - OVERLAY: 검정 오버레이 피크 시점에 Step 스위치

    마지막 Step에서 시그널이 올 때는 `last_step_sequence_policy`로 STAY vs ADVANCE_ITEM을 고른다.
    """

    def __init__(
        self,
        *,
        items: Sequence[ConversationItemLike],
        steps: Mapping[StepKind, IStep],
        video_player: Any,
        step_sequence: Sequence[StepKind] | None = None,
        last_step_sequence_policy: LastStepSequencePolicy = LastStepSequencePolicy.STAY,
    ) -> None:
        self._items = list(items)
        self._steps: dict[StepKind, IStep] = dict(steps)
        self._video_player = video_player
        # "컨텐츠(화면) 시퀀스" 정의.
        # - None이면 기본값: VIDEO → LEARNING
        # - step_sequence에 포함된 StepKind는 반드시 steps 매핑에 존재해야 정상 동작
        self._step_sequence: list[StepKind] = list(step_sequence) if step_sequence else [StepKind.VIDEO, StepKind.LEARNING]
        self._last_step_policy: LastStepSequencePolicy = last_step_sequence_policy
        self.state = PlaybackState()
        self._pending_transition: PendingStepTransition | None = None
        self._scratch: pygame.Surface | None = None

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
            self._cancel_pending_transition()
            self.state.step_kind = kind
            self._reset_step_done_flag(kind)

    def next_item(self) -> None:
        if not self._items:
            return
        self.state.item_index = min(len(self._items) - 1, self.state.item_index + 1)
        self._apply_item_to_video(self.current_item())
        self._cancel_pending_transition()
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
        self._cancel_pending_transition()
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

        if self._pending_transition is not None:
            self._update_pending_transition(ctx)
            return

        step = self._steps.get(self.state.step_kind)
        if step is None:
            return
        step.update(ctx, item=self.current_item())
        if step.transition_signal:
            self._begin_step_transition(ctx, step)

    def render(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        """현재 step 렌더."""
        if self._pending_transition is not None:
            self._render_pending_transition(screen, ctx)
            return

        step = self._steps.get(self.state.step_kind)
        if step is None:
            return
        step.render(screen, ctx, item=self.current_item())

    def _cancel_pending_transition(self) -> None:
        self._pending_transition = None

    def _clear_transition_signal(self, outgoing_step: IStep) -> None:
        try:
            outgoing_step.transition_signal = False
        except Exception:
            pass

    def _ensure_scratch(self, ctx: FrameContext) -> pygame.Surface:
        w, h = int(ctx.width), int(ctx.height)
        if self._scratch is None or self._scratch.get_size() != (w, h):
            self._scratch = pygame.Surface((w, h))
        return self._scratch

    def _update_pending_transition(self, ctx: FrameContext) -> None:
        p = self._pending_transition
        if p is None:
            return
        p.elapsed_sec += float(ctx.dt_sec)

        if p.mode == StepTransitionMode.OVERLAY:
            if not p.midpoint_committed and p.elapsed_sec >= p.duration_sec * 0.5:
                self.state.step_kind = p.to_kind
                self._reset_step_done_flag(p.to_kind)
                self._apply_snapshot_as_bg(p.to_kind, p.outgoing_snapshot)
                p.midpoint_committed = True

        step = self._steps.get(self.state.step_kind)
        if step is not None:
            step.update(ctx, item=self.current_item())

        if p.elapsed_sec >= p.duration_sec:
            self._pending_transition = None

    def _render_pending_transition(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        p = self._pending_transition
        if p is None:
            return
        if p.mode == StepTransitionMode.CROSSFADE:
            self._render_crossfade_transition(screen, ctx, p)
        elif p.mode == StepTransitionMode.OVERLAY:
            self._render_overlay_transition(screen, ctx, p)

    def _render_crossfade_transition(
        self,
        screen: pygame.Surface,
        ctx: FrameContext,
        p: PendingStepTransition,
    ) -> None:
        scratch = self._ensure_scratch(ctx)
        item = self.current_item()
        d = p.duration_sec if p.duration_sec > 1e-6 else 1e-6
        t = min(1.0, p.elapsed_sec / d)
        incoming = self._steps.get(self.state.step_kind)
        if incoming is None:
            return
        scratch.fill((0, 0, 0))
        incoming.render(scratch, ctx, item=item)
        blend_crossfade(screen, p.outgoing_snapshot, scratch, t)

    def _render_overlay_transition(
        self,
        screen: pygame.Surface,
        ctx: FrameContext,
        p: PendingStepTransition,
    ) -> None:
        scratch = self._ensure_scratch(ctx)
        item = self.current_item()
        d = p.duration_sec if p.duration_sec > 1e-6 else 1e-6
        peak = p.overlay_peak_alpha
        half = d * 0.5
        if p.elapsed_sec < half:
            hden = half if half > 1e-6 else 1e-6
            t = p.elapsed_sec / hden
            alpha = int(peak * t)
            if p.outgoing_snapshot is not None:
                screen.blit(p.outgoing_snapshot, (0, 0))
            else:
                screen.fill((0, 0, 0))
            blit_black_overlay(screen, ctx, alpha)
        else:
            hden = half if half > 1e-6 else 1e-6
            t2 = (p.elapsed_sec - half) / hden
            alpha = int(peak * max(0.0, 1.0 - t2))
            incoming = self._steps.get(self.state.step_kind)
            if incoming is not None:
                scratch.fill((0, 0, 0))
                incoming.render(scratch, ctx, item=item)
                screen.blit(scratch, (0, 0))
            else:
                screen.fill((0, 0, 0))
            blit_black_overlay(screen, ctx, alpha)

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
        try:
            step.is_done = False
        except Exception:
            pass
        try:
            step.transition_signal = False
        except Exception:
            pass

    def _snapshot_outgoing(self, ctx: FrameContext, outgoing_step: IStep) -> pygame.Surface | None:
        snap = None
        try:
            trans = outgoing_step.transition_bg_frame
            snap = trans.copy() if trans is not None else None
        except Exception:
            snap = None
        try:
            if snap is None:
                frame = self._video_player.get_frame(ctx.width, ctx.height)
                snap = frame.copy() if frame is not None else None
        except Exception:
            pass
        return snap

    def _capture_and_set_next_bg(self, ctx: FrameContext, next_kind: StepKind) -> None:
        """현재(나가는) step 기준 스냅샷을 다음 step의 bg_frame으로 주입."""
        cur_step = self._steps.get(self.state.step_kind)
        snap = self._snapshot_outgoing(ctx, cur_step) if cur_step is not None else None
        step = self._steps.get(next_kind)
        if step is None:
            return
        try:
            step.bg_frame = snap
        except Exception:
            pass

    def _apply_snapshot_as_bg(self, next_kind: StepKind, snap: pygame.Surface | None) -> None:
        step = self._steps.get(next_kind)
        if step is None or snap is None:
            return
        try:
            step.bg_frame = snap.copy() if hasattr(snap, "copy") else snap
        except Exception:
            try:
                step.bg_frame = snap
            except Exception:
                pass

    def _handle_cut(self, ctx: FrameContext, next_kind: StepKind) -> None:
        """CUT: 스냅샷을 다음 Step `bg_frame`에 넣고 즉시 `step_kind` 전환."""
        self._capture_and_set_next_bg(ctx, next_kind)
        self.state.step_kind = next_kind
        self._reset_step_done_flag(next_kind)

    def _handle_crossfade(
        self,
        ctx: FrameContext,
        outgoing_step: IStep,
        cur: StepKind,
        next_kind: StepKind,
        duration_sec: float,
        overlay_peak_alpha: int,
    ) -> None:
        """CROSSFADE: 나간 화면 스냅샷과 다음 Step 렌더를 `duration_sec` 동안 블렌드."""
        snap = self._snapshot_outgoing(ctx, outgoing_step)
        self.state.step_kind = next_kind
        self._reset_step_done_flag(next_kind)
        next_s = self._steps.get(next_kind)
        if next_s is not None:
            try:
                next_s.bg_frame = None
            except Exception:
                pass
        self._pending_transition = PendingStepTransition(
            mode=StepTransitionMode.CROSSFADE,
            duration_sec=duration_sec,
            elapsed_sec=0.0,
            outgoing_snapshot=snap,
            from_kind=cur,
            to_kind=next_kind,
            overlay_peak_alpha=overlay_peak_alpha,
        )
        if next_s is not None:
            try:
                next_s.update(ctx, item=self.current_item())
            except Exception:
                pass

    def _handle_overlay(
        self,
        ctx: FrameContext,
        outgoing_step: IStep,
        cur: StepKind,
        next_kind: StepKind,
        duration_sec: float,
        overlay_peak_alpha: int,
    ) -> None:
        """OVERLAY: 검정 오버레이 중간에 Step 스위치 후 페이드아웃."""
        snap = self._snapshot_outgoing(ctx, outgoing_step)
        self._pending_transition = PendingStepTransition(
            mode=StepTransitionMode.OVERLAY,
            duration_sec=duration_sec,
            elapsed_sec=0.0,
            outgoing_snapshot=snap,
            from_kind=cur,
            to_kind=next_kind,
            overlay_peak_alpha=overlay_peak_alpha,
        )

    def _on_last_step_transition_signal(self, outgoing_step: IStep) -> None:
        """시퀀스 끝에서 `transition_signal` 처리."""
        self._clear_transition_signal(outgoing_step)
        if self._last_step_policy == LastStepSequencePolicy.STAY:
            self._reset_step_done_flag(self.state.step_kind)
            return
        if self._last_step_policy == LastStepSequencePolicy.ADVANCE_ITEM:
            self.next_item()

    def _begin_step_transition(self, ctx: FrameContext, outgoing_step: IStep) -> None:
        """나가는 Step이 transition_signal을 올린 뒤 호출."""
        cur = self.state.step_kind
        seq = self._step_sequence
        if not seq:
            self._clear_transition_signal(outgoing_step)
            return
        try:
            idx = seq.index(cur)
        except ValueError:
            self.state.step_kind = seq[0]
            self._reset_step_done_flag(self.state.step_kind)
            self._clear_transition_signal(outgoing_step)
            return

        next_idx = min(len(seq) - 1, idx + 1)
        if next_idx == idx:
            self._on_last_step_transition_signal(outgoing_step)
            return

        next_kind = seq[next_idx]
        mode, duration, peak = read_step_transition(outgoing_step)

        if mode == StepTransitionMode.CUT or duration <= 0.0:
            self._handle_cut(ctx, next_kind)
        elif mode == StepTransitionMode.CROSSFADE:
            self._handle_crossfade(ctx, outgoing_step, cur, next_kind, duration, peak)
        elif mode == StepTransitionMode.OVERLAY:
            self._handle_overlay(ctx, outgoing_step, cur, next_kind, duration, peak)
        else:
            self._handle_cut(ctx, next_kind)

        self._clear_transition_signal(outgoing_step)

    def _clear_step_backgrounds(self) -> None:
        """item 이동 등으로 배경 스냅샷이 의미 없을 때 초기화."""
        self._cancel_pending_transition()
        for step in self._steps.values():
            try:
                step.bg_frame = None
            except Exception:
                pass
            try:
                step.transition_bg_frame = None
            except Exception:
                pass
