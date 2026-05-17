"""
배치/CLI: 테이블 엑셀 → CSV 일괄 생성.
resource/table/*.xlsx → resource/csv/*.csv

포함 테이블: base_sentences, words, sub_sentences, vocabulary_word_rows,
ko_narration_sets, ko_narration_lines, shorts_conversation_clips, shorts_vocabulary_clips

실행: python -m tools.csv_gen (또는 create_all_csv.bat / create_csv.bat)
"""
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    from core.paths import (
        DEFAULT_BASE_SENTENCES_CSV,
        DEFAULT_BASE_SENTENCES_EXCEL,
        DEFAULT_KO_NARRATION_LINES_CSV,
        DEFAULT_KO_NARRATION_LINES_EXCEL,
        DEFAULT_KO_NARRATION_SETS_CSV,
        DEFAULT_KO_NARRATION_SETS_EXCEL,
        DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV,
        DEFAULT_SHORTS_CONVERSATION_CLIPS_EXCEL,
        DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV,
        DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL,
        DEFAULT_SUB_SENTENCES_CSV,
        DEFAULT_SUB_SENTENCES_EXCEL,
        DEFAULT_VOCABULARY_WORD_ROWS_CSV,
        DEFAULT_VOCABULARY_WORD_ROWS_EXCEL,
        DEFAULT_WORDS_TABLE_CSV,
        DEFAULT_WORDS_TABLE_EXCEL,
    )
    from tools.csv_gen._bootstrap_excel import bootstrap_excel_from_csv
    from tools.csv_gen import (
        ko_narration_lines_excel_to_csv,
        ko_narration_sets_excel_to_csv,
        base_sentences_excel_to_csv,
        shorts_conversation_clips_excel_to_csv,
        shorts_vocabulary_clips_excel_to_csv,
        sub_sentences_excel_to_csv,
        vocabulary_word_rows_excel_to_csv,
        words_table_excel_to_csv,
    )

    results: list[str] = []

    bootstrap_excel_from_csv(DEFAULT_KO_NARRATION_SETS_EXCEL, DEFAULT_KO_NARRATION_SETS_CSV)
    bootstrap_excel_from_csv(DEFAULT_KO_NARRATION_LINES_EXCEL, DEFAULT_KO_NARRATION_LINES_CSV)

    if DEFAULT_BASE_SENTENCES_EXCEL.exists():
        try:
            p = base_sentences_excel_to_csv(
                DEFAULT_BASE_SENTENCES_EXCEL, DEFAULT_BASE_SENTENCES_CSV
            )
            results.append(p)
        except Exception as e:
            logger.exception("base_sentences CSV 생성 실패: %s", e)
            sys.exit(1)
    else:
        logger.info("엑셀 없음, 건너뜀: %s", DEFAULT_BASE_SENTENCES_EXCEL)

    if DEFAULT_WORDS_TABLE_EXCEL.exists():
        try:
            p = words_table_excel_to_csv(
                DEFAULT_WORDS_TABLE_EXCEL,
                DEFAULT_WORDS_TABLE_CSV,
                merge_all_sheets=True,
            )
            results.append(p)
        except Exception as e:
            logger.exception("words CSV 생성 실패: %s", e)
            sys.exit(1)
    else:
        logger.info("엑셀 없음, 건너뜀: %s", DEFAULT_WORDS_TABLE_EXCEL)

    if DEFAULT_SUB_SENTENCES_EXCEL.exists():
        try:
            p = sub_sentences_excel_to_csv(
                DEFAULT_SUB_SENTENCES_EXCEL, DEFAULT_SUB_SENTENCES_CSV
            )
            results.append(p)
        except Exception as e:
            logger.exception("sub_sentences CSV 생성 실패: %s", e)
            sys.exit(1)
    else:
        logger.info("엑셀 없음, 건너뜀: %s", DEFAULT_SUB_SENTENCES_EXCEL)

    if DEFAULT_VOCABULARY_WORD_ROWS_EXCEL.exists():
        try:
            p = vocabulary_word_rows_excel_to_csv(
                DEFAULT_VOCABULARY_WORD_ROWS_EXCEL, DEFAULT_VOCABULARY_WORD_ROWS_CSV
            )
            results.append(p)
        except Exception as e:
            logger.exception("vocabulary_word_rows CSV 생성 실패: %s", e)
            sys.exit(1)
    else:
        logger.info("엑셀 없음, 건너뜀: %s", DEFAULT_VOCABULARY_WORD_ROWS_EXCEL)

    if DEFAULT_KO_NARRATION_SETS_EXCEL.exists():
        try:
            p = ko_narration_sets_excel_to_csv(
                DEFAULT_KO_NARRATION_SETS_EXCEL, DEFAULT_KO_NARRATION_SETS_CSV
            )
            results.append(p)
        except Exception as e:
            logger.exception("ko_narration_sets CSV 생성 실패: %s", e)
            sys.exit(1)
    else:
        logger.info("엑셀 없음, 건너뜀: %s", DEFAULT_KO_NARRATION_SETS_EXCEL)

    if DEFAULT_KO_NARRATION_LINES_EXCEL.exists():
        try:
            p = ko_narration_lines_excel_to_csv(
                DEFAULT_KO_NARRATION_LINES_EXCEL, DEFAULT_KO_NARRATION_LINES_CSV
            )
            results.append(p)
        except Exception as e:
            logger.exception("ko_narration_lines CSV 생성 실패: %s", e)
            sys.exit(1)
    else:
        logger.info("엑셀 없음, 건너뜀: %s", DEFAULT_KO_NARRATION_LINES_EXCEL)

    if DEFAULT_SHORTS_CONVERSATION_CLIPS_EXCEL.exists():
        try:
            p = shorts_conversation_clips_excel_to_csv(
                DEFAULT_SHORTS_CONVERSATION_CLIPS_EXCEL,
                DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV,
            )
            results.append(p)
        except Exception as e:
            logger.exception("shorts_conversation_clips CSV 생성 실패: %s", e)
            sys.exit(1)
    else:
        logger.info("엑셀 없음, 건너뜀: %s", DEFAULT_SHORTS_CONVERSATION_CLIPS_EXCEL)

    if DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL.exists():
        try:
            p = shorts_vocabulary_clips_excel_to_csv(
                DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL,
                DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV,
            )
            results.append(p)
        except Exception as e:
            logger.exception("shorts_vocabulary_clips CSV 생성 실패: %s", e)
            sys.exit(1)
    else:
        logger.info("엑셀 없음, 건너뜀: %s", DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL)

    if results:
        logger.info("테이블 CSV 생성 완료: %s", results)
        for r in results:
            print("CSV 경로:", r)
    else:
        logger.warning("생성된 CSV 없음 (엑셀 원본이 resource\\table\\ 에 없음)")


if __name__ == "__main__":
    main()
