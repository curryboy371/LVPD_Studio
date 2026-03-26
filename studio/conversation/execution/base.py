"""Step interfaces and base implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pygame

from ..core.types import ConversationItemLike, FrameContext


class IStep(ABC):
    """단계별 실행 로직 인터페이스."""

    def __init__(self) -> None:
        self.is_done: bool = False
        # 다음 Step으로 넘어가도 된다는 "전환 시그널".
        # PlaybackManager는 이 값이 True일 때만 step_sequence를 진행한다.
        self.transition_signal: bool = False

    @abstractmethod
    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """프레임당 로직 업데이트."""

    @abstractmethod
    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """프레임 렌더링."""


class BaseStep(IStep):
    """공통 편의 기능을 제공하는 기본 Step."""

    def __init__(self, *, drawer: Any, video_player: Any) -> None:
        super().__init__()
        self.drawer = drawer
        self.video_player = video_player
        # 직전 step의 마지막 프레임을 다음 step의 배경으로 쓰기 위한 스냅샷.
        # PlaybackManager가 step 전환 시점에 캡처해서 주입할 수 있다.
        self.bg_frame: pygame.Surface | None = None
        # step이 전환 직전에 "다음 step으로 넘길 프레임"을 직접 합성했을 때 사용.
        self.transition_bg_frame: pygame.Surface | None = None

