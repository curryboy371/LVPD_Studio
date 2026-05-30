"""Re-export FIELDNAMES from tools.csv_gen (single source of truth)."""
from __future__ import annotations

from tools.csv_gen.base_sentences_excel_to_csv import FIELDNAMES as BASE_FIELDNAMES
from tools.csv_gen.ko_narration_lines_excel_to_csv import (
    FIELDNAMES as KO_NARRATION_LINES_FIELDNAMES,
)
from tools.csv_gen.ko_narration_sets_excel_to_csv import (
    FIELDNAMES as KO_NARRATION_SETS_FIELDNAMES,
)
from tools.csv_gen.sub_sentences_excel_to_csv import FIELDNAMES as SUB_FIELDNAMES
from tools.csv_gen.vocabulary_word_rows_excel_to_csv import (
    FIELDNAMES as VOCABULARY_WORD_ROWS_FIELDNAMES,
)
from tools.csv_gen.words_table_excel_to_csv import FIELDNAMES as WORDS_FIELDNAMES

__all__ = [
    "BASE_FIELDNAMES",
    "SUB_FIELDNAMES",
    "WORDS_FIELDNAMES",
    "VOCABULARY_WORD_ROWS_FIELDNAMES",
    "KO_NARRATION_SETS_FIELDNAMES",
    "KO_NARRATION_LINES_FIELDNAMES",
]
