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

