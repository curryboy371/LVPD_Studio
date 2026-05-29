"""Table editor defaults."""
from __future__ import annotations

from pathlib import Path

from core.paths import (
    DEFAULT_BASE_SENTENCES_CSV,
    DEFAULT_BASE_SENTENCES_EXCEL,
    DEFAULT_SUB_SENTENCES_CSV,
    DEFAULT_SUB_SENTENCES_EXCEL,
    DEFAULT_WORDS_TABLE_CSV,
    DEFAULT_WORDS_TABLE_EXCEL,
    get_repo_root,
)
from extra.table_editor.data.fields import BASE_FIELDNAMES, SUB_FIELDNAMES

APP_TITLE = "LVPD Table Editor"
POS_FILTER_ALL = "(전체)"
TOPIC_FILTER_ALL = "(전체)"
IMG_PATH_FIELD = "img_path"
IMG_PATH_NONE = "none"
MASKING_FIELD = "masking"
IMG_PREVIEW_MAX_SIZE = (240, 240)
# 단어 편집(필드 많음 + 이미지 미리보기)
ROW_EDITOR_GEOMETRY_WORDS = "900x880"
ROW_EDITOR_MINSIZE_WORDS = (640, 560)
ROW_EDITOR_GEOMETRY_DEFAULT = "760x640"
ROW_EDITOR_MINSIZE_DEFAULT = (520, 420)


def get_table_editor_tmp_dir() -> Path:
    """클립보드 이미지 임시 저장 (.table_editor_tmp/clipboard)."""
    return get_repo_root() / ".table_editor_tmp" / "clipboard"

# 한 줄씩 +/− 로 편집 후 \n 으로 저장
MULTILINE_LINES_FIELDS = frozenset({"tip"})

RAW_SENTENCE_FIELD = "raw_sentence"
BASE_EDITOR_FIELDNAMES: list[str] = [
    f for f in BASE_FIELDNAMES if f != RAW_SENTENCE_FIELD
]

SUB_SLOT_ORDER_FIELD = "target_slot_order"
SUB_ALT_WORD_ID_FIELD = "alt_word_id"
SUB_EDITOR_FIELDNAMES: list[str] = [
    f
    for f in SUB_FIELDNAMES
    if f not in (SUB_SLOT_ORDER_FIELD, SUB_ALT_WORD_ID_FIELD)
]

LONG_TEXT_FIELDS = frozenset({
    "translation",
    "meaning",
    "alt_translation",
    "situation_subtitle",
    "hook_title",
    "last_hold_text",
})

# words.csv · ko_narration_sets — TTS 엔진/목소리 (배치·런타임과 동일)
TTS_TYPE_CHOICES: tuple[str, ...] = ("", "edge", "gtts")
EDGE_TTS_VOICE_CHOICES: tuple[str, ...] = (
    "",
    "ko-KR-SunHiNeural",
    "ko-KR-InJoonNeural",
)
DEFAULT_WORD_TTS_TYPE = "edge"
DEFAULT_WORD_TTS_VOICE = "ko-KR-SunHiNeural"

COMBOBOX_FIELD_CHOICES: dict[str, tuple[str, ...]] = {
    "tts_type": TTS_TYPE_CHOICES,
    "tts": TTS_TYPE_CHOICES,
    "tts_voice": EDGE_TTS_VOICE_CHOICES,
}

__all__ = [
    "APP_TITLE",
    "POS_FILTER_ALL",
    "TOPIC_FILTER_ALL",
    "RAW_SENTENCE_FIELD",
    "BASE_EDITOR_FIELDNAMES",
    "SUB_SLOT_ORDER_FIELD",
    "SUB_ALT_WORD_ID_FIELD",
    "SUB_EDITOR_FIELDNAMES",
    "LONG_TEXT_FIELDS",
    "MULTILINE_LINES_FIELDS",
    "TTS_TYPE_CHOICES",
    "EDGE_TTS_VOICE_CHOICES",
    "DEFAULT_WORD_TTS_TYPE",
    "DEFAULT_WORD_TTS_VOICE",
    "COMBOBOX_FIELD_CHOICES",
    "DEFAULT_BASE_SENTENCES_CSV",
    "DEFAULT_BASE_SENTENCES_EXCEL",
    "DEFAULT_SUB_SENTENCES_CSV",
    "DEFAULT_SUB_SENTENCES_EXCEL",
    "DEFAULT_WORDS_TABLE_CSV",
    "DEFAULT_WORDS_TABLE_EXCEL",
    "get_repo_root",
    "get_table_editor_tmp_dir",
    "IMG_PATH_FIELD",
    "IMG_PATH_NONE",
    "MASKING_FIELD",
    "IMG_PREVIEW_MAX_SIZE",
    "ROW_EDITOR_GEOMETRY_WORDS",
    "ROW_EDITOR_MINSIZE_WORDS",
    "ROW_EDITOR_GEOMETRY_DEFAULT",
    "ROW_EDITOR_MINSIZE_DEFAULT",
]
