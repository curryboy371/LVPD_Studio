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
        # VIDEO fade-out 등에서 이어진 배경을 Learning→Practice로 그대로 넘길 때 사용(합성 스냅샷과 분리).
        self._incoming_bg_handoff: pygame.Surface | None = None

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
        """나가는 장면을 캡처해 `_common_bg`·다음 씬용 배경 이어받기를 준비한다.

        - VideoScene: `transition_bg_frame`(fade-out 합성) → Learning `bg_frame`으로 그대로 전달(기존).
        - Learning/Practice: 전환 연출용 `_common_bg`는 `render` 합성(문장 포함).
          다음 씬 배경(`_incoming_bg_handoff`)은 **현재 씬이 쓰던 `bg_frame`**을 우선한다.
          즉 VIDEO에서 저장·fade 처리된 배경이 Learning을 거쳐 Practice까지 동일하게 이어진다.
          `bg_frame`이 없을 때만 `get_frame()`으로 폴백한다.
        """
        if scene.transition_bg_frame:
            self._common_bg = scene.transition_bg_frame.copy()
            self._incoming_bg_handoff = None
            return

        w, h = int(ctx.width), int(ctx.height)
        if w <= 0 or h <= 0:
            return
        if scene.bg_frame is not None:
            self._incoming_bg_handoff = scene.bg_frame.copy()
        else:
            vf = self._video_player.get_frame(w, h)
            self._incoming_bg_handoff = vf.copy() if vf is not None else None

        if self._scratch is None or self._scratch.get_size() != (w, h):
            self._scratch = pygame.Surface((w, h))
        self._scratch.fill((0, 0, 0))
        scene.render(self._scratch, ctx, item=self.current_item())
        self._common_bg = self._scratch.copy()

    def _reset_scene(self, kind: SceneKind) -> None:
        """씬을 리셋하고, 다음 씬 `bg_frame`에는 `_incoming_bg_handoff`(VIDEO fade 포함 연속 배경)를 넣는다.

        `_incoming_bg_handoff`가 없으면(예: VIDEO→Learning 직후) `_common_bg`를 쓴다.
        합성 스냅샷(`_common_bg`)은 OVERLAY/CROSSFADE 나가는 화면용이다.
        """
        scene = self._scenes.get(kind)
        if not scene:
            return
        scene.reset(clear_background=True)
        if self._incoming_bg_handoff is not None:
            scene.bg_frame = self._incoming_bg_handoff.copy()
            self._incoming_bg_handoff = None
        elif self._common_bg:
            scene.bg_frame = self._common_bg.copy()
        # VIDEO→Learning 등: 전환 프레임에서 아직 learning.update가 돌지 않아 옛 Stage(DONE)가 한 프레임 그려지는 깜빡임 방지
        self._prime_scene_after_reset(kind)

    def _prime_scene_after_reset(self, kind: SceneKind) -> None:
        """같은 프레임의 draw 전에 item·FSM을 맞춘다(이전 방문 Stage 잔상 1프레임 노출 방지)."""
        item = self.current_item()
        if kind == SceneKind.LEARNING:
            sc = self._scenes.get(SceneKind.LEARNING)
            if sc is not None and hasattr(sc, "sync_item"):
                setattr(sc, "current_item", item)
                getattr(sc, "sync_item")(item)
        elif kind == SceneKind.PRACTICE:
            sc = self._scenes.get(SceneKind.PRACTICE)
            if sc is not None:
                prime_ctx = FrameContext(
                    width=int(self._video_player.width()),
                    height=int(self._video_player.height()),
                    dt_sec=0.0,
                )
                sc.update(prime_ctx, item=item)

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
        next_index = self._find_next_item_index_same_topic_then_fallback()
        self.state.item_index = max(0, min(len(self._items) - 1, next_index))
        self._apply_item_to_video(self.current_item())
        self._pending_transition = None
        self.state.scene_kind = self._scene_sequence[0]
        self._reset_scene(self.state.scene_kind)

    def _find_next_item_index_same_topic_then_fallback(self) -> int:
        """현재 item 기준으로 같은 topic의 다음 id를 우선 탐색한다.

        - 우선순위 1: 같은 topic && id가 현재보다 큰 항목 중 id 최소값
        - 우선순위 2: 기존 동작(index + 1)
        """
        current_idx = max(0, min(len(self._items) - 1, int(self.state.item_index)))
        current = self._items[current_idx] if self._items else {}
        current_topic = str(current.get("topic") or "").strip()
        current_id = self._to_int_or_none(current.get("id"))

        if current_topic and current_id is not None:
            best_idx: int | None = None
            best_id: int | None = None
            for idx, item in enumerate(self._items):
                item_topic = str(item.get("topic") or "").strip()
                if item_topic != current_topic:
                    continue
                item_id = self._to_int_or_none(item.get("id"))
                if item_id is None or item_id <= current_id:
                    continue
                if best_id is None or item_id < best_id:
                    best_id = item_id
                    best_idx = idx
            if best_idx is not None:
                return best_idx

        return min(current_idx + 1, len(self._items) - 1)

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        """id 비교를 위해 값을 int로 안전 변환한다."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

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
        current_scene = self._scenes.get(self.state.scene_kind)
        if current_scene:
            ctx = FrameContext(
                dt_sec=0.0,
                width=int(self._video_player.width()),
                height=int(self._video_player.height()),
            )
            self._take_snapshot(ctx, current_scene)
        self._pending_transition = None
        self.state.scene_kind = kind
        self._reset_scene(kind)