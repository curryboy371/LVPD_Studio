"""SceneKind 전환 시각 효과 — PlaybackManager가 합성.

시스템 전체 화면이 바뀌는 연출(Scene). LearningScene 내부 Stage(FSM) 전환과는 무관하다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import pygame

from .types import FrameContext


class SceneTransitionMode(str, Enum):
    """나가는 ConversationStep이 `transition_signal`을 올릴 때 다음 장면(SceneKind)으로 넘어가는 연출."""

    CUT = "cut"
    """즉시 전환 + `bg_frame` 스냅샷 주입(기존 동작)."""

    CROSSFADE = "crossfade"
    """이전 장면 스냅샷과 다음 ConversationStep 렌더를 알파 블렌드."""

    OVERLAY = "overlay"
    """검정 오버레이가 올라갔다가(중간에 SceneKind 스위치) 내려가며 다음 장면을 드러냄."""


def read_scene_transition(conversation_step: Any) -> tuple[SceneTransitionMode, float, int]:
    """ConversationStep에 없으면 CUT / 기본 시간 / 기본 피크 알파."""
    mode = getattr(conversation_step, "scene_transition_mode", SceneTransitionMode.CUT)
    if not isinstance(mode, SceneTransitionMode):
        try:
            mode = SceneTransitionMode(str(mode))
        except ValueError:
            mode = SceneTransitionMode.CUT
    duration = float(getattr(conversation_step, "scene_transition_duration_sec", 0.4) or 0.0)
    peak = int(getattr(conversation_step, "scene_transition_overlay_peak_alpha", 220) or 0)
    peak = max(0, min(255, peak))
    return mode, duration, peak


@dataclass
class PendingSceneTransition:
    mode: SceneTransitionMode
    duration_sec: float
    elapsed_sec: float
    outgoing_snapshot: pygame.Surface | None
    from_kind: Any  # SceneKind
    to_kind: Any  # SceneKind
    overlay_peak_alpha: int = 220
    midpoint_committed: bool = False


def blend_crossfade(
    screen: pygame.Surface,
    outgoing: pygame.Surface | None,
    incoming: pygame.Surface,
    t: float,
) -> None:
    """이전·다음 화면을 t에 따라 알파 합성한다(t=0 이전만, t=1 다음만)."""
    t = max(0.0, min(1.0, float(t)))
    w, h = screen.get_size()
    if outgoing is not None and t < 1.0 - 1e-6:
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        layer.blit(outgoing, (0, 0))
        layer.set_alpha(int(255 * (1.0 - t)))
        screen.blit(layer, (0, 0))
    if t > 1e-6:
        layer_in = pygame.Surface((w, h), pygame.SRCALPHA)
        layer_in.blit(incoming, (0, 0))
        layer_in.set_alpha(int(255 * t))
        screen.blit(layer_in, (0, 0))


def blit_black_overlay(screen: pygame.Surface, ctx: FrameContext, alpha: int) -> None:
    """화면 전체에 지정 알파의 검정 레이어를 한 겹 올린다(OVERLAY 전환용)."""
    a = max(0, min(255, int(alpha)))
    if a <= 0:
        return
    overlay = pygame.Surface((int(ctx.width), int(ctx.height)), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, a))
    screen.blit(overlay, (0, 0))
