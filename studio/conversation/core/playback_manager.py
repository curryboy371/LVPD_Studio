"""PlaybackManager: 정제된 장면 전환 및 재생 제어 로직."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence, Any

import pygame

from .conversation_step import IConversationStep  # 인터페이스 경로에 맞춰 수정하세요
from .scene_transition import (
    PendingSceneTransition,
    SceneTransitionMode,
    read_scene_transition,
)
from .types import ConversationItemLike, FrameContext


class SceneKind(str, Enum):
    VIDEO = "video"
    LEARNING = "learning"
    PRACTICE = "practice"


class LastSceneSequencePolicy(str, Enum):
    STAY = "stay"
    ADVANCE_ITEM = "advance_item"


@dataclass
class PlaybackState:
    item_index: int = 0
    scene_kind: SceneKind = SceneKind.VIDEO


class PlaybackManager:
    """전체 재생 시나리오와 장면(SceneKind) 간 전환을 관리합니다."""

    def __init__(
        self,
        *,
        items: Sequence[ConversationItemLike],
        scenes: Mapping[SceneKind, IConversationStep],
        video_player: Any,
        scene_sequence: Sequence[SceneKind] | None = None,
        last_scene_sequence_policy: LastSceneSequencePolicy = LastSceneSequencePolicy.STAY,
    ) -> None:
        self._items = list(items)
        self._scenes: dict[SceneKind, IConversationStep] = dict(scenes)
        self._video_player = video_player
        
        # 기본 시퀀스 설정: VIDEO -> LEARNING
        self._scene_sequence = list(scene_sequence) if scene_sequence else [SceneKind.VIDEO, SceneKind.LEARNING]
        self._last_scene_policy = last_scene_sequence_policy
        
        self.state = PlaybackState()
        self._pending_transition: PendingSceneTransition | None = None
        self._scratch: pygame.Surface | None = None

        if self._items:
            self._apply_item_to_video(self.current_item())

    # ---------------------------------------------------------
    # Public APIs
    # ---------------------------------------------------------
    def current_item(self) -> ConversationItemLike:
        if not self._items: return {}
        idx = max(0, min(len(self._items) - 1, self.state.item_index))
        return self._items[idx]

    def update(self, ctx: FrameContext) -> None:
        self._video_player.tick(ctx.dt_sec)

        # 1. 전환 애니메이션 중인 경우
        if self._pending_transition:
            self._update_pending_transition(ctx)
            return

        # 2. 일반 장면 업데이트
        scene = self._scenes.get(self.state.scene_kind)
        if not scene: return

        scene.update(ctx, item=self.current_item())
        
        # 전환 신호가 오면 프로세스 시작
        if scene.transition_signal:
            self._begin_scene_transition(ctx, scene)

    def render(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        if self._pending_transition:
            self._render_pending_transition(screen, ctx)
            return

        scene = self._scenes.get(self.state.scene_kind)
        if scene:
            scene.render(screen, ctx, item=self.current_item())

    # ---------------------------------------------------------
    # Core Transition Logic (Simplified)
    # ---------------------------------------------------------
    def _begin_scene_transition(self, ctx: FrameContext, outgoing_scene: IConversationStep) -> None:
        """장면 전환의 시작점. 다음 SceneKind를 결정하고 모드에 따라 핸들링합니다."""
        cur_kind = self.state.scene_kind
        
        try:
            curr_idx = self._scene_sequence.index(cur_kind)
        except ValueError:
            self._on_sequence_error(outgoing_scene)
            return

        # 마지막 장면인지 확인
        if curr_idx >= len(self._scene_sequence) - 1:
            self._handle_last_scene(outgoing_scene)
            return

        next_kind = self._scene_sequence[curr_idx + 1]
        mode, duration, peak = read_scene_transition(outgoing_scene)

        # 스냅샷 촬영 (인터페이스 신뢰)
        snapshot = self._take_snapshot(ctx, outgoing_scene)

        if mode == SceneTransitionMode.CUT or duration <= 0:
            self._apply_cut_transition(next_kind, snapshot)
        else:
            # 시각적 전환 예약 (CROSSFADE / OVERLAY)
            self._pending_transition = PendingSceneTransition(
                mode=mode,
                duration_sec=duration,
                elapsed_sec=0.0,
                outgoing_snapshot=snapshot,
                from_kind=cur_kind,
                to_kind=next_kind,
                overlay_peak_alpha=peak
            )
            # CROSSFADE는 즉시 다음 장면으로 상태 변경
            if mode == SceneTransitionMode.CROSSFADE:
                self.state.scene_kind = next_kind
                self._reset_scene(next_kind)

        outgoing_scene.transition_signal = False

    def _update_pending_transition(self, ctx: FrameContext) -> None:
        p = self._pending_transition
        if not p: return

        p.elapsed_sec += ctx.dt_sec
        
        # OVERLAY 모드: 절반 시점에 장면 교체
        if p.mode == SceneTransitionMode.OVERLAY and not p.midpoint_committed:
            if p.elapsed_sec >= p.duration_sec * 0.5:
                self.state.scene_kind = p.to_kind
                self._reset_scene(p.to_kind, p.outgoing_snapshot)
                p.midpoint_committed = True

        # 현재 장면(이미 바뀐 상태일 수 있음) 업데이트 유지
        scene = self._scenes.get(self.state.scene_kind)
        if scene:
            scene.update(ctx, item=self.current_item())

        if p.elapsed_sec >= p.duration_sec:
            self._pending_transition = None

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _take_snapshot(self, ctx: FrameContext, scene: IConversationStep) -> pygame.Surface | None:
        """인터페이스를 사용하여 안전하게 스냅샷을 가져옵니다."""
        if scene.transition_bg_frame:
            return scene.transition_bg_frame.copy()
        
        frame = self._video_player.get_frame(ctx.width, ctx.height)
        return frame.copy() if frame else None

    def _reset_scene(self, kind: SceneKind, bg: pygame.Surface | None = None) -> None:
        """씬의 상태를 초기화하고 필요한 경우 배경을 주입합니다."""
        scene = self._scenes.get(kind)
        if scene:
            scene.reset() # 인터페이스의 reset 활용
            if bg:
                scene.bg_frame = bg

    def _apply_cut_transition(self, next_kind: SceneKind, snapshot: pygame.Surface | None) -> None:
        self.state.scene_kind = next_kind
        self._reset_scene(next_kind, snapshot)

    def _apply_item_to_video(self, item: ConversationItemLike) -> None:
        path = str(item.get("video_path", "")).strip()
        st = float(item.get("start_time", 0.0))
        et = float(item.get("end_time", -1.0))
        self._video_player.set_source(path, st, et)

    def _handle_last_scene(self, scene: IConversationStep) -> None:
        scene.transition_signal = False
        if self._last_scene_policy == LastSceneSequencePolicy.ADVANCE_ITEM:
            self.next_item()
        else:
            scene.is_done = False # 다시 머무름