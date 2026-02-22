"""
스튜디오 패키지: 러너 + 스튜디오 구현체(회화, 단어장).
core.IStudio 계약을 따르며, 창·루프·녹화는 러너가 담당.
"""
from studio.runner import run, main
from studio.studios.conversation import ConversationStudio
from studio.studios.vocabulary import VocabularyStudio

__all__ = [
    "run",
    "main",
    "ConversationStudio",
    "VocabularyStudio",
]
