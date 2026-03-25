"""Pygame font bundle for Conversation drawers.

Drawer가 `ConversationStudio` 내부 속성에 직접 의존하지 않도록 폰트 핸들을 묶는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FontBundle:
    """텍스트 렌더링에 필요한 pygame/freeType 폰트 묶음.

    - *_ft: pygame.freetype 스타일(가능하면 중국어 네모 방지)
    - *_pg: pygame.font.Font 스타일 폴백
    """

    hanzi_ft: Any
    hanzi_pg: Any
    pinyin_ft: Any
    pinyin_pg: Any
    translation_pg: Any

