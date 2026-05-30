"""미리보기용 topic 목록 (CSV 기준)."""
from __future__ import annotations

import csv
from pathlib import Path

from core.paths import (
    DEFAULT_BASE_SENTENCES_CSV,
    DEFAULT_VOCABULARY_WORD_ROWS_CSV,
)

from extra.table_editor.services.search import unique_topic_values


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(f)]


def topics_for_conversation_preview() -> list[str]:
    return unique_topic_values(_read_csv_rows(DEFAULT_BASE_SENTENCES_CSV))


def topics_for_vocabulary_preview() -> list[str]:
    return unique_topic_values(_read_csv_rows(DEFAULT_VOCABULARY_WORD_ROWS_CSV))
