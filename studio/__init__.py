"""
스튜디오 패키지: 러너 + 스튜디오 구현체(회화, 단어장).
core.IStudio 계약을 따르며, 창·루프·녹화는 러너가 담당.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from studio.conversation import ConversationStudio
    from studio.runner import main, run
    from studio.studios.conversation_then_words import ConversationThenWordsStudio
    from studio.studios.vocabulary import VocabularyStudio

__all__ = [
    "run",
    "main",
    "ConversationStudio",
    "ConversationThenWordsStudio",
    "VocabularyStudio",
]


def __getattr__(name: str):
    if name == "run":
        from studio.runner import run

        return run
    if name == "main":
        from studio.runner import main

        return main
    if name == "ConversationStudio":
        from studio.conversation import ConversationStudio

        return ConversationStudio
    if name == "ConversationThenWordsStudio":
        from studio.studios.conversation_then_words import ConversationThenWordsStudio

        return ConversationThenWordsStudio
    if name == "VocabularyStudio":
        from studio.studios.vocabulary import VocabularyStudio

        return VocabularyStudio
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
