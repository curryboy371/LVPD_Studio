"""
단어장 스튜디오: IStudio 스켈레톤.
텍스트/이미지 위주 연동 구조 검증용 최소 구현.
"""
from typing import Any, Optional

import pygame


class VocabularyStudio:
    """단어장 스튜디오 (스켈레톤): 제목 + 빈 화면 또는 고정 텍스트."""

    def __init__(self, **kwargs: Any) -> None:
        self._font: Optional[pygame.font.Font] = None

    def get_title(self) -> str:
        return "LVPD Studio - 단어장"

    def handle_events(self, events: list, config: Any = None) -> bool:
        for e in events:
            if e.type == pygame.KEYDOWN:
                pass
        return True

    def update(self, config: Any = None) -> None:
        pass

    def draw(self, screen: Any, config: Any) -> None:
        screen.fill(config.bg_color)
        if self._font is None:
            self._font = pygame.font.Font(None, 36)
        label = self._font.render("단어장 스튜디오 (스켈레톤)", True, (220, 220, 220))
        w, h = config.width, config.height
        screen.blit(label, (w // 2 - 120, h // 2 - 18))

    def get_recording_prefix(self) -> Optional[str]:
        return None
