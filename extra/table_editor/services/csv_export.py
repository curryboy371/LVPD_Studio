"""CSV export via existing tools.csv_gen converters."""
from __future__ import annotations

from pathlib import Path

from tools.csv_gen.base_sentences_excel_to_csv import base_sentences_excel_to_csv
from tools.csv_gen.ko_narration_lines_excel_to_csv import ko_narration_lines_excel_to_csv
from tools.csv_gen.ko_narration_sets_excel_to_csv import ko_narration_sets_excel_to_csv
from tools.csv_gen.sub_sentences_excel_to_csv import sub_sentences_excel_to_csv
from tools.csv_gen.vocabulary_word_rows_excel_to_csv import (
    vocabulary_word_rows_excel_to_csv,
)
from tools.csv_gen.words_table_excel_to_csv import words_table_excel_to_csv


def export_base_csv(excel_path: Path, csv_path: Path) -> str:
    return base_sentences_excel_to_csv(excel_path, csv_path)


def export_sub_csv(excel_path: Path, csv_path: Path) -> str:
    return sub_sentences_excel_to_csv(excel_path, csv_path)


def export_words_csv(excel_path: Path, csv_path: Path) -> str:
    return words_table_excel_to_csv(
        excel_path, csv_path, merge_all_sheets=True
    )


def export_vocabulary_word_rows_csv(excel_path: Path, csv_path: Path) -> str:
    return vocabulary_word_rows_excel_to_csv(excel_path, csv_path)


def export_ko_narration_sets_csv(excel_path: Path, csv_path: Path) -> str:
    return ko_narration_sets_excel_to_csv(excel_path, csv_path)


def export_ko_narration_lines_csv(excel_path: Path, csv_path: Path) -> str:
    return ko_narration_lines_excel_to_csv(excel_path, csv_path)
