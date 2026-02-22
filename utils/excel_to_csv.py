"""
엑셀 → 테이블 CSV 변환 (pydantic/data.models 미사용).
create-csv 배치에서만 사용하여, numpy/pydantic 없이 동작하도록 함.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from utils.pinyin_processor import get_pinyin_processor

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xls")


def excel_to_csv(excel_path: str | Path, csv_path: str | Path, encoding: str = "utf-8-sig") -> str:
    """엑셀을 읽어 sentence 정제, words/life_tips 추출, 병음 3종 생성 후 CSV로 저장.
    data.models / data.table_manager 를 사용하지 않으므로 set_table 은 호출하지 않음.
    """
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    processor = get_pinyin_processor()
    final_rows = []

    for _, row in df.iterrows():
        raw_sent = str(row.get("sentence", ""))
        clean_sentence = re.sub(r"\{|\}", "", raw_sent)
        words_list = re.findall(r"\{(.*?)\}", raw_sent)

        raw_tip = str(row.get("life_tip", "")) if pd.notna(row.get("life_tip")) else ""
        tips_list = [t.strip() for t in raw_tip.split("|") if t.strip()] if raw_tip else []

        # 병음 3종: 1) 표기병음(성조 기호) 2) 표기병음숫자용 3) 발음용병음
        pinyin_marks = ""
        pinyin_lexical = ""
        pinyin_phonetic = ""
        if clean_sentence and processor.available:
            try:
                pinyin_marks = processor.full_convert(clean_sentence) or ""
                pinyin_lexical = " ".join(processor.get_lexical_pinyin(clean_sentence))
                pinyin_phonetic = " ".join(processor.get_phonetic_pinyin(clean_sentence))
            except Exception as e:
                logger.warning("Pinyin conversion skipped for row: %s", e)

        def _r(key: str, default: Any = ""):
            v = row.get(key, default)
            return v if pd.notna(v) else default

        final_rows.append({
            "topic": _r("topic"),
            "id": _r("id"),
            "level": _r("level"),
            "sentence": clean_sentence,
            "pinyin_marks": pinyin_marks,
            "pinyin_phonetic": pinyin_phonetic,
            "pinyin_lexical": pinyin_lexical,
            "translation": _r("translation"),
            "words": "|".join(words_list),
            "start_ms": _r("start_ms"),
            "end_ms": _r("end_ms"),
            "video_path": _r("video_path"),
            "sound_l1": _r("sound_level1_path"),
            "sound_l2": _r("sound_level2_path"),
            "life_tips": "|".join(tips_list),
        })

    result_df = pd.DataFrame(final_rows)
    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(out_path, index=False, encoding=encoding)
    logger.info("엑셀 → CSV 저장: %s (%d행)", csv_path, len(result_df))
    return str(out_path.resolve())
