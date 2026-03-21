"""
base_sentences 엑셀 → base_sentences.csv 변환.
media는 플랫 컬럼: video_path, video_start_ms, video_end_ms, sound_lv1_path, sound_lv2_path, syllable_times_l1.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xls")

FIELDNAMES = [
    "id",
    "topic",
    "level",
    "raw_sentence",
    "translation",
    "life_tip",
    "video_path",
    "video_start_ms",
    "video_end_ms",
    "sound_lv1_path",
    "sound_lv2_path",
    "syllable_times_l1",
]


def _normalize(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _to_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _syllable_times_to_str(val: Any) -> str:
    """list[int] 또는 '1200,1500,2000' / '[1200,1500,2000]' → CSV용 문자열."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = _normalize(val)
    if not s:
        return ""
    s = s.strip()
    if s.startswith("["):
        return s  # 이미 JSON 배열 형태
    # 쉼표 구분 숫자면 그대로 (또는 JSON 배열로 감싸기)
    return s


def base_sentences_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> str:
    """base_sentences 엑셀을 읽어 플랫 media 컬럼으로 CSV 저장."""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    final_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        raw_sent = _normalize(row.get("raw_sentence", ""))
        if not raw_sent and _to_int(row.get("id"), -1) < 0:
            continue

        video_path = _normalize(row.get("video_path", ""))
        video_start_ms = _to_int(row.get("video_start_ms", row.get("video_start_ms")), 0)
        video_end_ms = _to_int(row.get("video_end_ms", row.get("video_end_ms")), 0)
        sound_lv1 = _normalize(row.get("sound_lv1_path", row.get("sound_level1_path", "")))
        sound_lv2 = _normalize(row.get("sound_lv2_path", row.get("sound_level2_path", "")))
        syllable_raw = row.get("syllable_times_l1", "")
        if isinstance(syllable_raw, (list, tuple)):
            syllable_times_l1 = json.dumps([int(x) for x in syllable_raw])
        else:
            syllable_times_l1 = _syllable_times_to_str(syllable_raw)

        final_rows.append({
            "id": _to_int(row.get("id"), 0),
            "topic": _normalize(row.get("topic", "")),
            "level": _to_int(row.get("level"), 1),
            "raw_sentence": raw_sent,
            "translation": _normalize(row.get("translation", "")),
            "life_tip": _normalize(row.get("life_tip", "")),
            "video_path": video_path,
            "video_start_ms": video_start_ms,
            "video_end_ms": video_end_ms,
            "sound_lv1_path": sound_lv1,
            "sound_lv2_path": sound_lv2,
            "syllable_times_l1": syllable_times_l1,
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("base_sentences 엑셀 → CSV 저장: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
