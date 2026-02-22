"""
CSV 파일을 읽어 ContentRow 리스트로 반환하는 로더.
"""
import csv
from pathlib import Path
from typing import Any

from data.models import ContentRow


def load_csv_rows(csv_path: str | Path, encoding: str = "utf-8-sig") -> list[ContentRow]:
    """CSV 파일을 읽어 각 행을 ContentRow로 파싱한 리스트를 반환한다.

    Args:
        csv_path: CSV 파일 경로.
        encoding: 파일 인코딩.

    Returns:
        파싱된 ContentRow 리스트. 컬럼명은 text, image_path, sound_path, start_time, end_time, video_path 등과
        매핑되도록 CSV 헤더를 snake_case로 맞추거나, 행 딕셔너리 키를 모델 필드에 맞춘다.
    """
    path = Path(csv_path)
    if not path.exists():
        return []

    rows: list[ContentRow] = []
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # CSV 컬럼명을 ContentRow 필드명에 맞춤. 필요 시 alias 또는 수동 매핑.
            normalized: dict[str, Any] = {
                "text": row.get("text", row.get("sentence", "")) or "",
                "image_path": row.get("image_path") or None,
                "sound_path": row.get("sound_path") or None,
                "start_time": _to_float(row.get("start_time", row.get("split_ms", 0)), as_sec=True),
                "end_time": _to_float(row.get("end_time", 0), as_sec=True),
                "video_path": row.get("video_path") or None,
            }
            try:
                rows.append(ContentRow.model_validate(normalized))
            except Exception:
                continue
    return rows


def _to_float(val: Any, as_sec: bool = False) -> float:
    """값을 float으로 변환. as_sec이 True이고 값이 ms 단위면 초로 변환."""
    try:
        x = float(val)
    except (TypeError, ValueError):
        return 0.0
    if as_sec and x > 1000:
        x = x / 1000.0
    return max(0.0, x)
