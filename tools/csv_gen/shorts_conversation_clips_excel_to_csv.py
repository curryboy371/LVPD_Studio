"""
shorts_conversation_clips(숏츠·회화) 엑셀 → shorts_conversation_clips.csv 변환.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

EXCEL_EXTENSIONS = (".xlsx", ".xls")

FIELDNAMES = [
    "id",
    "topic",
    "base_id",
    "hook_title",
    "situation_subtitle",
    "ko_narration_id",
    "ko_narration_line_id",
    "sub_sentence_id",
    "sound_repeat_count",
    "last_hold_sec",
    "bg_path",
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


def _parse_pipe_ints(raw: Any) -> list[int]:
    """`1|2|3` -> [1,2,3] (중복/0/음수는 제외)."""
    s = str(raw or "").strip().replace("，", "|")
    if not s:
        return []
    out: list[int] = []
    seen: set[int] = set()
    for part in s.split("|"):
        p = part.strip()
        if not p:
            continue
        try:
            n = int(float(p))
        except (TypeError, ValueError):
            continue
        if n < 1 or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def _parse_sub_ids_from_script(script: str) -> list[int]:
    ids: list[int] = []
    for part in script.replace("，", "|").split("|"):
        token = part.strip().lower()
        if token.startswith("sub:"):
            try:
                ids.append(int(token.split(":", 1)[1].strip()))
            except (TypeError, ValueError, IndexError):
                pass
    return ids


def _parse_ko_ids_from_script(script: str) -> list[int]:
    ids: list[int] = []
    for part in script.replace("，", "|").split("|"):
        token = part.strip().lower()
        if token.startswith("ko:"):
            try:
                ids.append(int(token.split(":", 1)[1].strip()))
            except (TypeError, ValueError, IndexError):
                pass
    return ids


def shorts_conversation_clips_excel_to_csv(
    excel_path: str | Path,
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> str:
    """회화 숏츠 엑셀을 CSV로 저장."""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"입력 파일 없음: {excel_path}")
    if path.suffix.lower() not in EXCEL_EXTENSIONS:
        raise ValueError(f"엑셀 파일이 아님: {path.suffix}")

    df = pd.read_excel(path).dropna(axis=1, how="all")
    final_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        clip_id = _to_int(row.get("id"), 0)
        base_id = _to_int(row.get("base_id"), 0)
        hook_title = _normalize(row.get("hook_title"))
        if clip_id < 1 or base_id < 1 or not hook_title:
            continue

        script_norm = _normalize(row.get("script"))

        # sub_sentence_id: 없으면 레거시 script의 sub:N만 추출한다.
        sub_raw = _normalize(row.get("sub_sentence_id"))
        sub_ids = _parse_pipe_ints(sub_raw) if sub_raw else []
        if not sub_ids and script_norm:
            sub_ids = _parse_sub_ids_from_script(script_norm)
        sub_sentence_id = "|".join(str(x) for x in sub_ids) if sub_ids else ""

        # ko_narration_line_id: 있으면 사용, 없으면 레거시 script에서 ko:N 추출,
        # 최종적으로 CN(base+sub) 개수에 맞춰 1..N 자동 채움.
        ko_line_raw = _normalize(row.get("ko_narration_line_id"))
        ko_ids = _parse_pipe_ints(ko_line_raw) if ko_line_raw else []
        if not ko_ids and script_norm:
            ko_ids = _parse_ko_ids_from_script(script_norm)
        if not ko_ids:
            cn_count = 1 + len(sub_ids)
            ko_ids = list(range(1, cn_count + 1))
        ko_narration_line_id = "|".join(str(x) for x in ko_ids) if ko_ids else ""

        final_rows.append({
            "id": clip_id,
            "topic": _normalize(row.get("topic")),
            "base_id": base_id,
            "hook_title": hook_title,
            "situation_subtitle": _normalize(row.get("situation_subtitle")),
            "ko_narration_id": _to_int(row.get("ko_narration_id"), 0),
            "ko_narration_line_id": ko_narration_line_id,
            "sub_sentence_id": sub_sentence_id,
            "sound_repeat_count": _normalize(row.get("sound_repeat_count")) or "1",
            "last_hold_sec": _normalize(row.get("last_hold_sec")),
            "bg_path": _normalize(row.get("bg_path")),
        })

    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(final_rows)

    logger.info("shorts_conversation_clips → CSV: %s (%d행)", out_path, len(final_rows))
    return str(out_path.resolve())
