"""완성형 중국어 문장 → resource/video·sound 경로 (테이블 편집기 자동 입력)."""
from __future__ import annotations

import re

VIDEO_PATH_PREFIX = "resource/video/"
SOUND_SENTENCE_PREFIX = "resource/sound/sentense/"
_STRIP_FOR_STEM_RE = re.compile(r"[,，\?\？\s]+")


def display_sentence_stem(display: str) -> str:
    """경로 파일명 stem: 완성형 문장에서 `,` 공백 `?` `？` 제거."""
    text = (display or "").strip()
    if not text:
        return ""
    return _STRIP_FOR_STEM_RE.sub("", text)


def is_valid_display_sentence(display: str) -> bool:
    text = (display or "").strip()
    if not text:
        return False
    if text.startswith("("):
        return False
    return bool(display_sentence_stem(text))


def build_sentence_video_path(display: str) -> str:
    stem = display_sentence_stem(display)
    if not stem:
        return ""
    return f"{VIDEO_PATH_PREFIX}{stem}.mp4"


def build_sentence_sound_path(display: str) -> str:
    stem = display_sentence_stem(display)
    if not stem:
        return ""
    return f"{SOUND_SENTENCE_PREFIX}{stem}.mp3"


def apply_base_sentence_media_paths(
    row: dict[str, str],
    *,
    display_sentence: str,
) -> dict[str, str]:
    out = dict(row)
    if not is_valid_display_sentence(display_sentence):
        return out
    out["video_path"] = build_sentence_video_path(display_sentence)
    out["sound_lv_path"] = build_sentence_sound_path(display_sentence)
    return out


def apply_sub_sentence_media_paths(
    row: dict[str, str],
    *,
    display_sentence: str,
) -> dict[str, str]:
    out = dict(row)
    if not is_valid_display_sentence(display_sentence):
        return out
    out["alt_sound_path"] = build_sentence_sound_path(display_sentence)
    return out
