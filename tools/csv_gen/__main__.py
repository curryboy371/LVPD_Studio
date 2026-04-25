"""
배치/CLI: 테이블 엑셀 → CSV 일괄 생성.
resource/table/*.xlsx → resource/csv/*.csv
실행: python -m tools.csv_gen (또는 create_all_csv.bat)
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
        DEFAULT_SUB_SENTENCES_CSV,
        DEFAULT_SUB_SENTENCES_EXCEL,
        DEFAULT_WORDS_TABLE_CSV,
        DEFAULT_WORDS_TABLE_EXCEL,
    )
    from tools.csv_gen import (
        base_sentences_excel_to_csv,
        sub_sentences_excel_to_csv,
        words_table_excel_to_csv,
    )

    results: list[str] = []

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
                DEFAULT_WORDS_TABLE_EXCEL, DEFAULT_WORDS_TABLE_CSV
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

    if results:
        logger.info("테이블 CSV 생성 완료: %s", results)
        for r in results:
            print("CSV 경로:", r)
    else:
        logger.warning("생성된 CSV 없음 (3개 엑셀 모두 없음)")


if __name__ == "__main__":
    main()
