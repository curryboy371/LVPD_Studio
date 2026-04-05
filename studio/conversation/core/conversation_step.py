"""IConversationStep — SceneKind 슬롯별 장면(VideoScene / LearningScene 등) 공통 베이스.

내부 FSM 단계는 `conversation_step_fsm` 의 Stage / StageConfig 로 표현한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pygame

from .types import ConversationItemLike, FrameContext


class IConversationStep(ABC):
    """재생 파이프라인의 화면 단위(VideoScene / LearningScene / PracticeScene 등) 공통 인터페이스.

    PlaybackManager·SceneKind 시퀀스 전환 합성에서 참조한다.
    (한 화면 안의 세부 FSM 단계는 `conversation_step_fsm` 의 Stage / StageConfig.)
    """

    is_done: bool
    transition_signal: bool
    bg_frame: pygame.Surface | None
    transition_bg_frame: pygame.Surface | None

    def __init__(self) -> None:
        self.is_done: bool = False
        # 다음 ConversationStep(SceneKind 슬롯)으로 넘어가도 된다는 시그널.
        self.transition_signal: bool = False
        # 이전 프레임을 다음 ConversationStep 배경으로 쓰기 위한 스냅샷.
        self.bg_frame: pygame.Surface | None = None
        # 장면(Scene) 전환 합성용 배경 프레임.
        self.transition_bg_frame: pygame.Surface | None = None

    def reset(self, *, clear_background: bool = False) -> None:
        """ConversationStep 상태를 초기로 리셋한다.

        clear_background: True면 bg_frame까지 비운다. False면 이전 장면에서 넘어온
        배경 스냅샷(bg_frame)은 유지하고 시그널·완료 상태만 초기화한다.
        transition_bg_frame은 항상 비운다.
        """
        self.is_done = False
        self.transition_signal = False
        self.transition_bg_frame = None
        if clear_background:
            self.bg_frame = None

    def complete(self) -> None:
        """현재 ConversationStep을 완료로 표시한다."""
        self.is_done = True

    def allow_transition(self) -> None:
        """다음 ConversationStep으로 전환 가능하도록 설정한다."""
        self.transition_signal = True

    def can_transition(self) -> bool:
        """SceneKind 시퀀스상 다음 화면으로 넘어갈 수 있는지."""
        return self.is_done and self.transition_signal

    def capture_bg(self, screen: pygame.Surface) -> None:
        """현재 화면을 배경 프레임으로 캡처한다."""
        self.bg_frame = screen.copy()

    def capture_transition_bg(self, screen: pygame.Surface) -> None:
        """전환용 배경 프레임을 캡처한다."""
        self.transition_bg_frame = screen.copy()

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """프레임 단위로 상태를 갱신하고 내부 로직을 실행한다."""
        if self.is_done:
            return

        self.on_update(ctx, item=item)

    @abstractmethod
    def on_update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """ConversationStep별 업데이트 로직."""
        pass

    @abstractmethod
    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """현재 상태를 화면에 렌더링한다."""
        pass
