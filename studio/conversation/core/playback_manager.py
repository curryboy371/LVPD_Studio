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
    blend_crossfade,
    blit_black_overlay,
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
        self._common_bg: pygame.Surface | None = None

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

        self._take_snapshot(ctx, outgoing_scene)

        if mode == SceneTransitionMode.CUT or duration <= 0:
            self.state.scene_kind = next_kind
            self._reset_scene(next_kind)
        else:
            self._pending_transition = PendingSceneTransition(
                mode=mode,
                duration_sec=duration,
                elapsed_sec=0.0,
                outgoing_snapshot=self._common_bg,
                from_kind=cur_kind,
                to_kind=next_kind,
                overlay_peak_alpha=peak,
            )
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
                self._reset_scene(p.to_kind)
                p.midpoint_committed = True

        # 현재 장면(이미 바뀐 상태일 수 있음) 업데이트 유지
        scene = self._scenes.get(self.state.scene_kind)
        if scene:
            scene.update(ctx, item=self.current_item())

        if p.elapsed_sec >= p.duration_sec:
            self._pending_transition = None

    def _render_pending_transition(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        p = self._pending_transition
        if not p:
            return
        w, h = int(ctx.width), int(ctx.height)
        if self._scratch is None or self._scratch.get_size() != (w, h):
            self._scratch = pygame.Surface((w, h))

        scene = self._scenes.get(self.state.scene_kind)
        item = self.current_item()
        t_raw = p.elapsed_sec / p.duration_sec if p.duration_sec > 1e-6 else 1.0
        t = max(0.0, min(1.0, t_raw))

        if p.mode == SceneTransitionMode.CROSSFADE:
            if not scene:
                screen.fill((0, 0, 0))
                return
            self._scratch.fill((0, 0, 0))
            scene.render(self._scratch, ctx, item=item)
            blend_crossfade(screen, p.outgoing_snapshot, self._scratch, t)
            return

        if p.mode == SceneTransitionMode.OVERLAY:
            if t <= 0.5:
                if p.outgoing_snapshot:
                    screen.blit(p.outgoing_snapshot, (0, 0))
                else:
                    screen.fill((0, 0, 0))
                u = t / 0.5 if 0.5 > 1e-6 else 1.0
                alpha = int(p.overlay_peak_alpha * max(0.0, min(1.0, u)))
                blit_black_overlay(screen, ctx, alpha)
            else:
                if scene:
                    scene.render(screen, ctx, item=item)
                else:
                    screen.fill((0, 0, 0))
                u = (t - 0.5) / 0.5 if 0.5 > 1e-6 else 1.0
                alpha = int(p.overlay_peak_alpha * (1.0 - max(0.0, min(1.0, u))))
                blit_black_overlay(screen, ctx, alpha)

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _take_snapshot(self, ctx: FrameContext, scene: IConversationStep) -> None:
        """나가는 장면을 캡처해 `_common_bg`를 최신화한다."""
        snap: pygame.Surface | None = None
        if scene.transition_bg_frame:
            snap = scene.transition_bg_frame.copy()
        else:
            frame = self._video_player.get_frame(ctx.width, ctx.height)
            if frame:
                snap = frame.copy()
        if snap:
            self._common_bg = snap

    def _reset_scene(self, kind: SceneKind) -> None:
        """씬을 리셋하고 `_common_bg`가 있으면 해당 씬의 `bg_frame`으로 복사해 넣는다."""
        scene = self._scenes.get(kind)
        if scene:
            scene.reset(clear_background=True)
            if self._common_bg:
                scene.bg_frame = self._common_bg.copy()

    def _on_sequence_error(self, outgoing_scene: IConversationStep) -> None:
        outgoing_scene.transition_signal = False

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

    def next_item(self) -> None:
        """다음 아이템으로 이동하고 시퀀스 첫 장면으로 돌린다. `common_bg` 잔상은 `_reset_scene`으로 유지."""
        if not self._items:
            return
        self.state.item_index = min(self.state.item_index + 1, len(self._items) - 1)
        self._apply_item_to_video(self.current_item())
        self._pending_transition = None
        self.state.scene_kind = self._scene_sequence[0]
        self._reset_scene(self.state.scene_kind)

    def prev_item(self) -> None:
        if not self._items:
            return
        self.state.item_index = max(0, self.state.item_index - 1)
        self._apply_item_to_video(self.current_item())
        self._pending_transition = None
        self.state.scene_kind = self._scene_sequence[0]
        self._reset_scene(self.state.scene_kind)

    def toggle_pause(self) -> None:
        self._video_player.toggle_pause()

    def restart_segment(self) -> None:
        item = self.current_item()
        st = float(item.get("start_time", 0.0) or 0.0)
        self._video_player.seek_to(st)

    def seek(self, delta_sec: float) -> None:
        self._video_player.seek(delta_sec)

    def set_scene_kind(self, kind: SceneKind) -> None:
        if kind not in self._scenes:
            return
        self._pending_transition = None
        self.state.scene_kind = kind
        self._reset_scene(kind)