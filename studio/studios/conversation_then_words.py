"""회화 전체 재생 후 집계 단어 화면으로 이어지는 복합 IStudio."""
from __future__ import annotations

from typing import Any, Literal, Optional

import pygame

from data.models import VocabularyWordRow
from data.table_manager import (
    get_word_by_hanzi,
    select_vocabulary_word_rows_for_session_topics,
)
from studio.conversation.studio import ConversationStudio
from studio.studios.vocabulary import VocabularyStudio


def topics_from_conversation_items(items: list[Any]) -> list[str]:
    """재생 항목에서 topic을 등장 순으로 한 번씩만 모은다."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        t = str(item.get("topic") or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def build_vocabulary_word_rows_for_studio(
    items: list[Any],
    session_topics: Optional[list[str]] = None,
) -> list[VocabularyWordRow]:
    """`vocabulary_word_rows` CSV 테이블에서만 행을 가져온다. `topic` 컬럼이 아래 topic 집합과 일치하는 행만.

    - `session_topics`가 있으면(비어 있지 않으면): 그 문자열만 사용(예: CLI `--topic`).
    - 없으면: 재생 `items`에서 모은 topic(`topics_from_conversation_items`)을 사용한다.
    """
    if session_topics is not None and any(str(t).strip() for t in session_topics):
        topics = [str(t).strip() for t in session_topics if str(t).strip()]
    else:
        topics = topics_from_conversation_items(items)
    return select_vocabulary_word_rows_for_session_topics(topics)


def aggregate_vocabulary_word_rows_from_items(items: list[Any]) -> list[VocabularyWordRow]:
    """재생 항목 순서대로 단어를 모아 `VocabularyWordRow` 리스트로 만든다( words.id 참조 ).

    마스터에 없는 한자는 건너뛴다. 동일 (topic, word_id)는 한 번만 넣는다.
    표시 순서는 `id`(1부터 순번)로 정해진다.
    """
    seen_linked: set[tuple[str, int]] = set()
    out: list[VocabularyWordRow] = []
    seq = 0
    for item in items:
        topic = ""
        if isinstance(item, dict):
            topic = str(item.get("topic") or "").strip()
        words = item.get("words") if isinstance(item, dict) else None
        if words is None:
            words = []
        if isinstance(words, str):
            words = [p.strip() for p in words.split("|") if p.strip()]
        elif not isinstance(words, list):
            words = []
        for w in words:
            s = str(w).strip()
            if not s:
                continue
            master = get_word_by_hanzi(s)
            if master is None:
                continue
            key = (topic, master.id)
            if key in seen_linked:
                continue
            seen_linked.add(key)
            seq += 1
            out.append(
                VocabularyWordRow(
                    id=seq,
                    topic=topic,
                    word_id=master.id,
                    pronunciation_mask="",
                )
            )
    return out


Phase = Literal["conversation", "words"]


class ConversationThenWordsStudio:
    """1단계: ConversationStudio. 2단계: VocabularyStudio(집계 단어)."""

    def __init__(
        self,
        csv_path: str = "",
        content: Any = None,
        *,
        debug_start_in_words_phase: bool = False,
        session_topics: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        _ = kwargs
        self._debug_start_in_words_phase = bool(debug_start_in_words_phase)
        self._session_topics: Optional[list[str]] = session_topics
        self._conversation = ConversationStudio(
            csv_path=csv_path,
            content=content,
            session_topics=session_topics,
        )
        self._aggregated_word_rows = build_vocabulary_word_rows_for_studio(
            self._conversation.get_data_list(),
            session_topics=session_topics,
        )
        self._phase: Phase = "conversation"
        self._vocab: Optional[VocabularyStudio] = None
        self._pending_words_phase: bool = False
        self._inited: bool = False

    def init(self, config: Any = None) -> None:
        if self._inited:
            return
        self._conversation.init(config)
        self._inited = True
        if self._debug_start_in_words_phase:
            self._phase = "words"
            self._vocab = VocabularyStudio(word_rows=self._aggregated_word_rows)
            self._vocab.init(config)

    def get_title(self) -> str:
        if self._phase == "words" and self._vocab is not None:
            return self._vocab.get_title()
        return self._conversation.get_title()

    def handle_events(self, events: list, config: Any = None) -> bool:
        if self._phase == "conversation":
            return self._conversation.handle_events(events, config)
        if self._vocab is not None:
            return self._vocab.handle_events(events, config)
        return True

    def update(self, config: Any = None) -> None:
        if self._pending_words_phase:
            self._phase = "words"
            self._vocab = VocabularyStudio(word_rows=self._aggregated_word_rows)
            self._vocab.init(config)
            self._pending_words_phase = False

        if self._phase == "conversation":
            self._conversation.update(config)
            if not self._pending_words_phase and self._conversation.is_ready_for_aggregate_words_phase():
                self._pending_words_phase = True
        elif self._vocab is not None:
            self._vocab.update(config)

    def draw(self, screen: Any, config: Any) -> None:
        if self._phase == "conversation":
            self._conversation.draw(screen, config)
        elif self._vocab is not None:
            self._vocab.draw(screen, config)
        else:
            screen.fill(getattr(config, "bg_color", (20, 20, 25)))

    def get_recording_prefix(self) -> Optional[str]:
        return self._conversation.get_recording_prefix()

    def should_stop_recording(self) -> bool:
        if self._phase != "words" or self._vocab is None:
            return False
        return bool(self._vocab.should_stop_recording())

    def finalize_recording_audio_segments(self, *, timeline_end_sec: float) -> None:
        self._conversation.finalize_recording_audio_segments(timeline_end_sec=timeline_end_sec)
