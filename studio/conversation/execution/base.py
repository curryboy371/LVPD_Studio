"""Step 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pygame

from ..core.types import ConversationItemLike, FrameContext


class IStep(ABC):
    """단계별 실행 로직 인터페이스.

    PlaybackManager와 전환 합성에서 참조하는 공통 필드.
    """

    is_done: bool
    transition_signal: bool
    bg_frame: pygame.Surface | None
    transition_bg_frame: pygame.Surface | None

    def __init__(self) -> None:
        self.is_done: bool = False
        # 다음 Step으로 넘어가도 된다는 "전환 시그널".
        # PlaybackManager는 이 값이 True일 때만 step_sequence를 진행한다.
        self.transition_signal: bool = False
        # 직전 step의 마지막 프레임 등(다음 step 배경으로 쓸 수 있음).
        self.bg_frame: pygame.Surface | None = None
        # 전환 직전에 다음 step으로 넘길 합성 프레임(있으면 스냅샷 우선).
        self.transition_bg_frame: pygame.Surface | None = None

    @abstractmethod
    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """프레임당 로직 업데이트."""

    @abstractmethod
    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """프레임 렌더링."""
