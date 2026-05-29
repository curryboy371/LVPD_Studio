"""Auto-fill words.csv fields from hanzi (word) on new-row editor."""
from __future__ import annotations

from extra.table_editor.config import (
    DEFAULT_WORD_TTS_TYPE,
    DEFAULT_WORD_TTS_VOICE,
    IMG_PATH_NONE,
)


def masking_for_hanzi(word: str) -> str:
    """한자 글자 수만큼 ``0`` (예: 苹果 → ``00``)."""
    text = (word or "").strip()
    if not text:
        return ""
    return "0" * len(text)


def media_path_stem_for_hanzi(word: str) -> str:
    """img_path·sound_path 에 넣을 stem(한자와 동일)."""
    return (word or "").strip()


def apply_new_word_defaults(row: dict[str, str], *, pos: str = "") -> dict[str, str]:
    """새 단어 편집창 초기값: TTS 기본·pos."""
    out = dict(row)
    if pos:
        out["pos"] = pos
    if not (out.get("tts_type") or "").strip():
        out["tts_type"] = DEFAULT_WORD_TTS_TYPE
    if not (out.get("tts_voice") or "").strip():
        out["tts_voice"] = DEFAULT_WORD_TTS_VOICE
    return out


def apply_hanzi_autofill(
    row: dict[str, str],
    hanzi: str,
    *,
    image_enabled: bool = True,
) -> dict[str, str]:
    """한자 입력 후 Enter 시 경로·masking·TTS 보조 채움."""
    word = (hanzi or "").strip()
    if not word:
        return row
    out = dict(row)
    stem = media_path_stem_for_hanzi(word)
    out["word"] = word
    out["img_path"] = stem if image_enabled else IMG_PATH_NONE
    out["sound_path"] = stem
    out["masking"] = masking_for_hanzi(word)
    if not (out.get("tts_type") or "").strip():
        out["tts_type"] = DEFAULT_WORD_TTS_TYPE
    if not (out.get("tts_voice") or "").strip():
        out["tts_voice"] = DEFAULT_WORD_TTS_VOICE
    return out
