"""
배치 전용: 엑셀 → 테이블 CSV 생성 (create_csv.bat 에서만 실행).
resource/table/video_data.xlsx → resource/csv/video_data.csv
"""
import logging
import sys
from pathlib import Path

# repo root
_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    from core.paths import DEFAULT_CSV_PATH, DEFAULT_EXCEL_PATH
    from utils.excel_to_csv import excel_to_csv

    excel_path = Path(DEFAULT_EXCEL_PATH).resolve()
    csv_path = Path(DEFAULT_CSV_PATH).resolve()
    if not excel_path.exists():
        logger.error("엑셀 파일이 없습니다: %s", excel_path)
        sys.exit(1)
    try:
        result = excel_to_csv(excel_path, csv_path)
        logger.info("테이블 CSV 생성 완료: %s", result)
        print("CSV 경로:", result)
    except Exception as e:
        logger.error("CSV 생성 실패: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
