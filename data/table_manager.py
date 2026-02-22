"""
최종 테이블(generate_final_table 결과)을 보관하고, 재생 시 LoadedContent로 제공하는 모듈.
테이블의 비디오/사운드 경로는 resource/... 형태 → repo 루트 기준으로만 해석.
"""
from pathlib import Path
from typing import Any

import pandas as pd

from core.paths import get_repo_root
from data.models import (
    AudioTrack,
    LoadedContent,
    OverlayItem,
    VideoSegment,
)

# 모듈 단일 인스턴스: generate_final_table에서 저장, 재생 시 접근
_table: list[dict[str, Any]] | None = None


def _to_float(val: Any, default: float = 0.0) -> float:
    try:
        x = float(val)
    except (TypeError, ValueError):
        return default
    return max(0.0, x)


def set_table(rows: list[dict[str, Any]] | pd.DataFrame) -> None:
    """최종 테이블을 저장한다. generate_final_table 호출 후 결과를 넘긴다."""
    global _table
    if isinstance(rows, pd.DataFrame):
        _table = rows.to_dict("records")
    else:
        _table = list(rows) if rows else None


def get_table() -> list[dict[str, Any]] | None:
    """저장된 최종 테이블을 반환한다. 없으면 None."""
    return _table if _table is not None else None


def clear_table() -> None:
    """저장된 테이블을 비운다."""
    global _table
    _table = None


def get_loaded_content() -> LoadedContent:
    """저장된 최종 테이블에서 LoadedContent를 만들어 반환한다. 테이블이 없으면 빈 LoadedContent.
    비디오/사운드 경로는 테이블에 resource/... 로 들어 있으면 repo 루트 기준으로 해석.
    """
    rows = get_table()
    if not rows:
        return LoadedContent()

    repo = get_repo_root()
    video_segments: list[VideoSegment] = []
    overlay_items: list[OverlayItem] = []
    audio_tracks: list[AudioTrack] = []

    for row in rows:
        topic = str(row.get("topic") or "").strip()
        row_id = str(row.get("id") or "").strip()
        if not topic and not row_id:
            continue

        # VideoSegment: 테이블에 video_path가 resource/... 형태로 있으면 repo 기준 해석
        vpath = str(row.get("video_path") or "").strip()
        if not vpath:
            vpath = str(Path("resource", "video", topic, f"{row_id}.mp4"))
        if not Path(vpath).is_absolute():
            vpath = str(repo / vpath)
        start_sec = _to_float(row.get("start_ms"), 0.0)
        if start_sec > 1000:
            start_sec /= 1000.0
        raw_end = row.get("end_ms")
        end_sec = _to_float(raw_end, 0.0)
        if end_sec == -1:
            end_sec = -1.0  # 끝까지 재생
        elif end_sec > 1000:
            end_sec /= 1000.0
        video_segments.append(
            VideoSegment(
                file_path=vpath,
                start_time=start_sec,
                end_time=end_sec,
                volume=_to_float(row.get("volume", 1.0), 1.0),
            )
        )

        # OverlayItem: 문장/번역/병음 3종/words/life_tips 전부 저장 (font·위치 등은 모델 기본값)
        sentence = str(row.get("sentence") or "").strip() or None
        translation = str(row.get("translation") or "").strip() or None
        pinyin = str(row.get("pinyin_marks") or "").strip() or None
        pinyin_phonetic = str(row.get("pinyin_phonetic") or "").strip() or None
        pinyin_lexical = str(row.get("pinyin_lexical") or "").strip() or None
        words = str(row.get("words") or "").strip() or None
        life_tips = str(row.get("life_tips") or "").strip() or None
        overlay_items.append(
            OverlayItem(
                sentence=sentence,
                translation=translation,
                pinyin=pinyin,
                pinyin_phonetic=pinyin_phonetic,
                pinyin_lexical=pinyin_lexical,
                words=words,
                life_tips=life_tips,
            )
        )

        # AudioTrack: resource/... 경로면 repo 기준 해석
        sound_l1 = str(row.get("sound_l1") or "").strip()
        sound_l2 = str(row.get("sound_l2") or "").strip()
        if sound_l1:
            if not Path(sound_l1).is_absolute():
                sound_l1 = str(repo / sound_l1)
            audio_tracks.append(
                AudioTrack(sound_path=sound_l1, fade_in_sec=0.0, fade_out_sec=0.0)
            )
        if sound_l2:
            if not Path(sound_l2).is_absolute():
                sound_l2 = str(repo / sound_l2)
            audio_tracks.append(
                AudioTrack(sound_path=sound_l2, fade_in_sec=0.0, fade_out_sec=0.0)
            )

    return LoadedContent(
        video_segments=video_segments,
        overlay_items=overlay_items,
        audio_tracks=audio_tracks,
    )
