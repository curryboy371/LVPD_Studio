"""Conversation core shared types.

식별자/기술 용어는 English, 설명은 Korean 규칙을 따른다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Optional, Protocol, Sequence

from utils.tone_icon_layout import ToneIconSlot, build_tone_icon_slots


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
    # 병음 음절 수와 동일 길이; None이면 해당 음절에 아이콘 없음
    tone_icon_slots: tuple[Optional[ToneIconSlot], ...] = ()


@dataclass(frozen=True)
class ColorStyle:
    """한자·병음·번역 줄 RGB."""

    hanzi_color: tuple[int, int, int] = (255, 255, 255)
    pinyin_color: tuple[int, int, int] = (220, 220, 220)
    translation_color: tuple[int, int, int] = (200, 200, 200)


@dataclass(frozen=True)
class LayoutStyle:
    """줄 간격·여백."""

    line_gap_px: int = 110
    # 한자 줄 다음, 번역 줄만 추가로 내릴 픽셀(병음↔한자 간격은 그대로)
    translation_extra_gap_px: int = 0
    # 화면 중앙 정렬 기준용 최소 좌우 여백
    min_margin_x: int = 20


@dataclass(frozen=True)
class TextStyle:
    """줄별 최대 글자 수(잘림)."""

    max_hanzi: int = 80
    max_pinyin: int = 120
    max_translation: int = 80


@dataclass(frozen=True)
class SentenceStyleConfig:
    """Config-driven 문장 렌더링 스타일(색 / 레이아웃 / 텍스트 한도 분리)."""

    colors: ColorStyle = field(default_factory=ColorStyle)
    layout: LayoutStyle = field(default_factory=LayoutStyle)
    text: TextStyle = field(default_factory=TextStyle)


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
    # 데이터 소스에 따라 병음 키가 다를 수 있어 fallback 순서로 조회.
    pinyin_raw = (
        item.get("pinyin")
        or item.get("pinyin_marks")
        or item.get("pinyin_phonetic")
        or item.get("pinyin_lexical")
        or ""
    )
    if isinstance(pinyin_raw, (list, tuple)):
        pinyin_text = " ".join(str(x) for x in pinyin_raw if str(x).strip()).strip()
    else:
        pinyin_text = str(pinyin_raw).strip()

    sentence = " ".join(str(x) for x in list(sentences)[:3]).strip() if sentences else ""
    translation = " ".join(str(x) for x in list(translations)[:3]).strip() if translations else ""
    if not sentence:
        sentence = "(문장 없음)"
    return SentenceRenderData(sentence=sentence, pinyin=pinyin_text, translation=translation)


def build_sentence_render_data_with_tone_icons(item: ConversationItemLike) -> SentenceRenderData:
    """문장 렌더 데이터 + 표기/발음 성조 비교 아이콘 슬롯."""
    base = extract_sentence_render_data(item)
    slots = build_tone_icon_slots(item, base.pinyin)
    return replace(base, tone_icon_slots=slots)


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

