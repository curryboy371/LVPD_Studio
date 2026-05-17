"""CSV가 있고 엑셀이 없을 때 resource/table/*.xlsx 템플릿 생성."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def bootstrap_excel_from_csv(excel_path: Path, csv_path: Path) -> bool:
    """엑셀 없음 + CSV 있음 → 엑셀 생성. 생성했으면 True."""
    if excel_path.is_file() or not csv_path.is_file():
        return False
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        excel_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(excel_path, index=False)
        logger.info("엑셀 템플릿 생성(CSV 복사): %s", excel_path)
        return True
    except Exception as ex:
        logger.warning("엑셀 템플릿 생성 실패 %s: %s", excel_path, ex)
        return False
