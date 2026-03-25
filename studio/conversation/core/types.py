"""Conversation core shared types.

식별자/기술 용어는 English, 설명은 Korean 규칙을 따른다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


class ConversationItem(Protocol):
    """회화 스튜디오에서 재생/표시할 데이터 한 단위.

    현재는 dict 기반(`data_loading.build_data_list()` 결과)을 그대로 받을 수 있게
    `Mapping[str, Any]`로도 취급 가능하도록 설계한다.
    """

    def get(self, key: str, default: Any = None) -> Any:  # pragma: no cover
        ...


ConversationItemLike = ConversationItem | Mapping[str, Any]


@dataclass(frozen=True)
class SentenceRenderData:
    """CommonDrawer에 전달할 문장 데이터 묶음."""

    sentence: str
    pinyin: str
    translation: str


@dataclass(frozen=True)
class SentenceStyleConfig:
    """Config-driven 문장 렌더링 스타일."""

    hanzi_color: tuple[int, int, int] = (255, 255, 255)
    pinyin_color: tuple[int, int, int] = (220, 220, 220)
    translation_color: tuple[int, int, int] = (200, 200, 200)

    line_gap_px: int = 110
    max_hanzi: int = 80
    max_pinyin: int = 120
    max_translation: int = 80

    # 화면 중앙 정렬 기준용 최소 좌우 여백
    min_margin_x: int = 20


@dataclass(frozen=True)
class FrameContext:
    """프레임 렌더링/업데이트 컨텍스트."""

    width: int
    height: int
    dt_sec: float


def extract_sentence_render_data(item: ConversationItemLike) -> SentenceRenderData:
    """dict 기반 item에서 문장/병음/번역을 안전하게 추출."""
    sentences: Sequence[Any] = item.get("sentence") or []
    translations: Sequence[Any] = item.get("translation") or []
    pinyin_text = str(item.get("pinyin") or "").strip()

    sentence = " ".join(str(x) for x in list(sentences)[:3]).strip() if sentences else ""
    translation = " ".join(str(x) for x in list(translations)[:3]).strip() if translations else ""
    if not sentence:
        sentence = "(문장 없음)"
    return SentenceRenderData(sentence=sentence, pinyin=pinyin_text, translation=translation)


def conversation_item_min_keys() -> tuple[str, ...]:
    """render_only 모드에서 최소로 기대하는 키 목록(문서/검증용)."""
    return (
        "video_path",
        "start_time",
        "end_time",
        "sentence",
        "translation",
        "pinyin",
        "words",
    )

