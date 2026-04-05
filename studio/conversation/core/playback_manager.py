"""PlaybackManager: control layer for conversation studio."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

import pygame

from .conversation_step import IConversationStep
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
    """`scene_sequence`의 마지막 SceneKind에서 `transition_signal`이 올 때 동작."""

    STAY = "stay"
    """`transition_signal`만 소비하고 같은 SceneKind·같은 item에 머무름(기본)."""

    ADVANCE_ITEM = "advance_item"
    """다음 item으로 넘긴 뒤 시퀀스 첫 SceneKind로(마지막 item이면 인덱스만 클램프)."""


@dataclass
class PlaybackState:
    item_index: int = 0
    # 컨텐츠(화면) 시퀀스의 첫 화면은 VIDEO가 기본
    scene_kind: SceneKind = SceneKind.VIDEO


class PlaybackManager:
    """전체 재생 시나리오의 생명주기를 관리하는 관리자.

    여기서의 핵심 개념:
    - item: CSV/콘텐츠에서 로드된 "재생 단위" (video_path, start/end, sentence 등)
    - ConversationStep: SceneKind별 장면 구현체(VideoScene / LearningScene / PracticeScene 등). `scenes` 매핑으로 주입.
      LearningScene 안의 세부 진행은 Stage(FSM)로 따로 둔다(이름의 step 과 혼동 금지).
    - scene_sequence: item 1개를 어떤 SceneKind 순서로 보여줄지 선언하는 리스트
      예) [VIDEO, LEARNING] 이면
        1) VIDEO 화면 → 2) LEARNING 화면
      각 ConversationStep이 transition_signal=True를 올리면 다음 SceneKind로 넘어간다.

    SceneKind(장면) 전환 연출은 나가는 ConversationStep의 `scene_transition_*` 로 조절한다:
    - CUT: 즉시 전환 + bg_frame 스냅샷(기본)
    - CROSSFADE: 스냅샷과 다음 화면 합성
    - OVERLAY: 검정 오버레이 피크 시점에 SceneKind 스위치

    마지막 SceneKind에서 시그널이 올 때는 `last_scene_sequence_policy`로 STAY vs ADVANCE_ITEM을 고른다.
    """

    def __init__(
        self,
        *,
        items: Sequence[ConversationItemLike],
        scenes: Mapping[SceneKind, IConversationStep],
        video_player: Any,
        scene_sequence: Sequence[SceneKind] | None = None,
        last_scene_sequence_policy: LastSceneSequencePolicy = LastSceneSequencePolicy.STAY,
    ) -> None:
        """아이템·SceneKind→장면 매핑·시퀀스·정책으로 재생 상태를 초기화하고 첫 아이템을 비디오에 적용한다."""
        self._items = list(items)
        self._scenes: dict[SceneKind, IConversationStep] = dict(scenes)
        self._video_player = video_player
        # "컨텐츠(화면) 시퀀스" 정의.
        # - None이면 기본값: VIDEO → LEARNING
        # - scene_sequence에 포함된 SceneKind는 반드시 scenes 매핑에 존재해야 정상 동작
        self._scene_sequence: list[SceneKind] = list(scene_sequence) if scene_sequence else [SceneKind.VIDEO, SceneKind.LEARNING]
        self._last_scene_policy: LastSceneSequencePolicy = last_scene_sequence_policy
        self.state = PlaybackState()
        self._pending_transition: PendingSceneTransition | None = None
        self._scratch: pygame.Surface | None = None

        if self._items:
            self._apply_item_to_video(self._items[0])

    def has_items(self) -> bool:
        """재생할 아이템이 하나라도 있으면 True."""
        return bool(self._items)

    def current_item(self) -> ConversationItemLike:
        """현재 `item_index`에 해당하는 dict. 목록이 비면 빈 dict."""
        if not self._items:
            return {}
        idx = max(0, min(len(self._items) - 1, self.state.item_index))
        return self._items[idx]

    def set_scene_kind(self, kind: SceneKind) -> None:
        """사용자 입력 등으로 SceneKind를 직접 바꾼다. 진행 중 전환은 취소한다."""
        # 수동 전환(숫자키 등)도 허용: 단, 다음 프레임부터 해당 장면이 렌더/업데이트 된다.
        # 시퀀스 진행 중이라도 사용자가 직접 바꿀 수 있게 둔다.
        if kind in self._scenes:
            self._cancel_pending_transition()
            self.state.scene_kind = kind
            self._reset_scene_done_flag(kind)

    def next_item(self) -> None:
        """다음 콘텐츠 아이템으로 이동하고 비디오 소스·Step 시퀀스 시작으로 맞춘다."""
        if not self._items:
            return
        self.state.item_index = min(len(self._items) - 1, self.state.item_index + 1)
        self._apply_item_to_video(self.current_item())
        self._cancel_pending_transition()
        self._clear_scene_backgrounds()
        # item이 바뀌면 "컨텐츠 시퀀스"도 처음 화면으로 되돌린다.
        # (예: 새 문장/새 구간은 항상 VIDEO 화면부터 보여주기)
        if self._scene_sequence:
            self.state.scene_kind = self._scene_sequence[0]
            self._reset_scene_done_flag(self.state.scene_kind)

    def prev_item(self) -> None:
        """이전 콘텐츠 아이템으로 이동하고 비디오·Step을 초기 화면으로 되돌린다."""
        if not self._items:
            return
        self.state.item_index = max(0, self.state.item_index - 1)
        self._apply_item_to_video(self.current_item())
        self._cancel_pending_transition()
        self._clear_scene_backgrounds()
        if self._scene_sequence:
            self.state.scene_kind = self._scene_sequence[0]
            self._reset_scene_done_flag(self.state.scene_kind)

    def toggle_pause(self) -> None:
        """비디오 플레이어 일시정지/재생 토글."""
        try:
            self._video_player.toggle_pause()
        except Exception:
            pass

    def seek(self, delta_sec: float) -> None:
        """현재 PTS 기준 상대 시크(초)."""
        try:
            self._video_player.seek(float(delta_sec))
        except Exception:
            pass

    def restart_segment(self) -> None:
        """현재 아이템의 start_time으로 되감아 구간을 처음부터 재생."""
        item = self.current_item()
        start = float(item.get("start_time", 0.0) or 0.0)
        try:
            self._video_player.seek_to(start)
        except Exception:
            pass

    def update(self, ctx: FrameContext) -> None:
        """비디오 시간을 진행하고, SceneKind 전환 중이면 합성 업데이트, 아니면 현재 ConversationStep을 갱신한다."""
        try:
            self._video_player.tick(ctx.dt_sec)
        except Exception:
            pass

        if self._pending_transition is not None:
            self._update_pending_transition(ctx)
            return

        scene = self._scenes.get(self.state.scene_kind)
        if scene is None:
            return
        scene.update(ctx, item=self.current_item())
        if scene.transition_signal:
            self._begin_scene_transition(ctx, scene)

    def render(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        """전환 애니메이션 중이면 합성 렌더, 아니면 현재 ConversationStep의 `render`를 호출한다."""
        if self._pending_transition is not None:
            self._render_pending_transition(screen, ctx)
            return

        scene = self._scenes.get(self.state.scene_kind)
        if scene is None:
            return
        scene.render(screen, ctx, item=self.current_item())

    def _cancel_pending_transition(self) -> None:
        """진행 중 SceneKind 전환(크로스페이드·오버레이) 상태를 제거한다."""
        self._pending_transition = None

    def _clear_transition_signal(self, outgoing_scene: IConversationStep) -> None:
        """나가는 ConversationStep의 `transition_signal`을 False로 소비한다."""
        try:
            outgoing_scene.transition_signal = False
        except Exception:
            pass

    def _ensure_scratch(self, ctx: FrameContext) -> pygame.Surface:
        """전환 합성용 해상도에 맞는 임시 Surface를 준비한다."""
        w, h = int(ctx.width), int(ctx.height)
        if self._scratch is None or self._scratch.get_size() != (w, h):
            self._scratch = pygame.Surface((w, h))
        return self._scratch

    def _update_pending_transition(self, ctx: FrameContext) -> None:
        """전환 타이머를 진행하고 OVERLAY면 중간에 SceneKind를 바꾼 뒤 끝나면 pending을 해제한다."""
        p = self._pending_transition
        if p is None:
            return
        p.elapsed_sec += float(ctx.dt_sec)

        if p.mode == SceneTransitionMode.OVERLAY:
            if not p.midpoint_committed and p.elapsed_sec >= p.duration_sec * 0.5:
                self.state.scene_kind = p.to_kind
                self._reset_scene_done_flag(p.to_kind)
                self._apply_snapshot_as_bg(p.to_kind, p.outgoing_snapshot)
                p.midpoint_committed = True

        scene = self._scenes.get(self.state.scene_kind)
        if scene is not None:
            scene.update(ctx, item=self.current_item())

        if p.elapsed_sec >= p.duration_sec:
            self._pending_transition = None

    def _render_pending_transition(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        """pending 전환 모드에 따라 크로스페이드 또는 검정 오버레이 렌더를 수행한다."""
        p = self._pending_transition
        if p is None:
            return
        if p.mode == SceneTransitionMode.CROSSFADE:
            self._render_crossfade_transition(screen, ctx, p)
        elif p.mode == SceneTransitionMode.OVERLAY:
            self._render_overlay_transition(screen, ctx, p)

    def _render_crossfade_transition(
        self,
        screen: pygame.Surface,
        ctx: FrameContext,
        p: PendingSceneTransition,
    ) -> None:
        """이전 스냅샷과 들어오는 ConversationStep 화면을 알파 블렌드한다."""
        scratch = self._ensure_scratch(ctx)
        item = self.current_item()
        d = p.duration_sec if p.duration_sec > 1e-6 else 1e-6
        t = min(1.0, p.elapsed_sec / d)
        incoming_scene = self._scenes.get(self.state.scene_kind)
        if incoming_scene is None:
            return
        scratch.fill((0, 0, 0))
        incoming_scene.render(scratch, ctx, item=item)
        blend_crossfade(screen, p.outgoing_snapshot, scratch, t)

    def _render_overlay_transition(
        self,
        screen: pygame.Surface,
        ctx: FrameContext,
        p: PendingSceneTransition,
    ) -> None:
        """검정 오버레이로 이전·다음 화면을 전환하는 2단계 페이드를 그린다."""
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
            incoming_scene = self._scenes.get(self.state.scene_kind)
            if incoming_scene is not None:
                scratch.fill((0, 0, 0))
                incoming_scene.render(scratch, ctx, item=item)
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

    def _reset_scene_done_flag(self, kind: SceneKind) -> None:
        """해당 ConversationStep의 완료·전환 플래그를 초기화해 새 구간에서 즉시 스킵되지 않게 한다."""
        # SceneKind 전환 시 이전 완료 상태가 남아있으면 즉시 스킵되는 문제가 생길 수 있어서
        # 전환 시점에 플래그들을 리셋한다.
        scene = self._scenes.get(kind)
        if scene is None:
            return
        try:
            scene.is_done = False
        except Exception:
            pass
        try:
            scene.transition_signal = False
        except Exception:
            pass

    def _snapshot_outgoing(self, ctx: FrameContext, outgoing_scene: IConversationStep) -> pygame.Surface | None:
        """전환용으로 나가는 ConversationStep의 `transition_bg_frame` 또는 현재 비디오 프레임 스냅샷을 만든다."""
        snap = None
        try:
            trans = outgoing_scene.transition_bg_frame
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

    def _capture_and_set_next_bg(self, ctx: FrameContext, next_kind: SceneKind) -> None:
        """나가는 화면 스냅샷을 다음 ConversationStep의 `bg_frame`에 넣어 이어짐을 자연스럽게 한다."""
        cur_scene = self._scenes.get(self.state.scene_kind)
        snap = self._snapshot_outgoing(ctx, cur_scene) if cur_scene is not None else None
        next_scene = self._scenes.get(next_kind)
        if next_scene is None:
            return
        try:
            next_scene.bg_frame = snap
        except Exception:
            pass

    def _apply_snapshot_as_bg(self, next_kind: SceneKind, snap: pygame.Surface | None) -> None:
        scene = self._scenes.get(next_kind)
        if scene is None or snap is None:
            return
        try:
            scene.bg_frame = snap.copy() if hasattr(snap, "copy") else snap
        except Exception:
            try:
                scene.bg_frame = snap
            except Exception:
                pass

    def _handle_cut(self, ctx: FrameContext, next_kind: SceneKind) -> None:
        """CUT: 스냅샷을 다음 ConversationStep `bg_frame`에 넣고 즉시 `scene_kind` 전환."""
        self._capture_and_set_next_bg(ctx, next_kind)
        self.state.scene_kind = next_kind
        self._reset_scene_done_flag(next_kind)

    def _handle_crossfade(
        self,
        ctx: FrameContext,
        outgoing_scene: IConversationStep,
        cur: SceneKind,
        next_kind: SceneKind,
        duration_sec: float,
        overlay_peak_alpha: int,
    ) -> None:
        """CROSSFADE: 나간 화면 스냅샷과 다음 ConversationStep 렌더를 `duration_sec` 동안 블렌드."""
        snap = self._snapshot_outgoing(ctx, outgoing_scene)
        self.state.scene_kind = next_kind
        self._reset_scene_done_flag(next_kind)
        next_scene = self._scenes.get(next_kind)
        if next_scene is not None:
            try:
                next_scene.bg_frame = None
            except Exception:
                pass
        self._pending_transition = PendingSceneTransition(
            mode=SceneTransitionMode.CROSSFADE,
            duration_sec=duration_sec,
            elapsed_sec=0.0,
            outgoing_snapshot=snap,
            from_kind=cur,
            to_kind=next_kind,
            overlay_peak_alpha=overlay_peak_alpha,
        )
        if next_scene is not None:
            try:
                next_scene.update(ctx, item=self.current_item())
            except Exception:
                pass

    def _handle_overlay(
        self,
        ctx: FrameContext,
        outgoing_scene: IConversationStep,
        cur: SceneKind,
        next_kind: SceneKind,
        duration_sec: float,
        overlay_peak_alpha: int,
    ) -> None:
        """OVERLAY: 검정 오버레이 중간에 SceneKind 스위치 후 페이드아웃."""
        snap = self._snapshot_outgoing(ctx, outgoing_scene)
        self._pending_transition = PendingSceneTransition(
            mode=SceneTransitionMode.OVERLAY,
            duration_sec=duration_sec,
            elapsed_sec=0.0,
            outgoing_snapshot=snap,
            from_kind=cur,
            to_kind=next_kind,
            overlay_peak_alpha=overlay_peak_alpha,
        )

    def _on_last_scene_sequence_transition_signal(self, outgoing_scene: IConversationStep) -> None:
        """scene_sequence 끝 SceneKind에서 `transition_signal` 처리."""
        self._clear_transition_signal(outgoing_scene)
        if self._last_scene_policy == LastSceneSequencePolicy.STAY:
            self._reset_scene_done_flag(self.state.scene_kind)
            return
        if self._last_scene_policy == LastSceneSequencePolicy.ADVANCE_ITEM:
            self.next_item()

    def _begin_scene_transition(self, ctx: FrameContext, outgoing_scene: IConversationStep) -> None:
        """나가는 ConversationStep이 transition_signal을 올린 뒤 다음 장면(SceneKind)으로 진행하고 연출을 적용한다."""
        cur = self.state.scene_kind
        seq = self._scene_sequence
        if not seq:
            self._clear_transition_signal(outgoing_scene)
            return
        try:
            idx = seq.index(cur)
        except ValueError:
            self.state.scene_kind = seq[0]
            self._reset_scene_done_flag(self.state.scene_kind)
            self._clear_transition_signal(outgoing_scene)
            return

        next_idx = min(len(seq) - 1, idx + 1)
        if next_idx == idx:
            self._on_last_scene_sequence_transition_signal(outgoing_scene)
            return

        next_kind = seq[next_idx]
        mode, duration, peak = read_scene_transition(outgoing_scene)

        if mode == SceneTransitionMode.CUT or duration <= 0.0:
            self._handle_cut(ctx, next_kind)
        elif mode == SceneTransitionMode.CROSSFADE:
            self._handle_crossfade(ctx, outgoing_scene, cur, next_kind, duration, peak)
        elif mode == SceneTransitionMode.OVERLAY:
            self._handle_overlay(ctx, outgoing_scene, cur, next_kind, duration, peak)
        else:
            self._handle_cut(ctx, next_kind)

        self._clear_transition_signal(outgoing_scene)

    def _clear_scene_backgrounds(self) -> None:
        """item 이동 등으로 배경 스냅샷이 의미 없을 때 초기화."""
        self._cancel_pending_transition()
        for scene in self._scenes.values():
            try:
                scene.bg_frame = None
            except Exception:
                pass
            try:
                scene.transition_bg_frame = None
            except Exception:
                pass
