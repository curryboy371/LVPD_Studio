"""단어 외우기 배치 — 단어 목록 텍스트 정리."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from core.paths import get_repo_root
from extra.table_editor.services.word_lookup import lookup_word_details_for_box
from extra.table_editor.services.word_memorize_layout import (
    WordMemorizeLayout,
    _is_zh_meaning_lang,
    load_layout,
)


def format_word_pinyin(details: dict[str, str]) -> str:
    """단어장 병음 — 마스킹·성조 반영."""
    hanzi = (details.get("word") or "").strip()
    raw = (details.get("pinyin") or "").strip()
    masking = (details.get("masking") or "").strip()
    if raw and hanzi:
        try:
            from utils.pinyin_masking import word_pinyin_to_marks_spaced

            marks = word_pinyin_to_marks_spaced(hanzi, raw).strip()
            if marks:
                return marks
        except Exception:
            pass
        return raw
    if hanzi:
        try:
            from utils.pinyin_masking import (
                get_masked_pinyin_marks,
                normalize_word_masking,
            )

            marks = get_masked_pinyin_marks(
                hanzi, normalize_word_masking(masking)
            ).strip()
            if marks:
                return marks
        except Exception:
            pass
    return raw


def resolve_summary_topic(
    layout: WordMemorizeLayout,
    *,
    meaning_lang: str = "ko",
) -> str:
    """정리용 주제 문자열 — 줄바꿈은 공백으로."""
    if _is_zh_meaning_lang(meaning_lang):
        topic = (layout.title_zh or layout.title or "").strip()
    else:
        topic = (layout.title or layout.title_zh or "").strip()
    if not topic:
        return "—"
    return " ".join(ln.strip() for ln in topic.splitlines() if ln.strip())


def format_summary_word_line(details: dict[str, str]) -> str:
    """한국어뜻 (한자 / 병음 / 영어뜻) 한 줄."""
    meaning = (details.get("meaning") or "").strip()
    hanzi = (details.get("word") or "").strip()
    pinyin = format_word_pinyin(details).strip()
    en = (details.get("en_meaning") or "").strip()
    if not any((meaning, hanzi, pinyin, en)):
        return ""
    return f"{meaning} ({hanzi} / {pinyin} / {en})"


def build_word_memorize_summary_text(
    layout: WordMemorizeLayout,
    *,
    meaning_lang: str = "ko",
) -> str:
    """배치 단어를 정리 텍스트로 변환."""
    topic = resolve_summary_topic(layout, meaning_lang=meaning_lang)
    lines: list[str] = [f"주제 : {topic}", ""]
    for box in layout.sorted_boxes():
        row = format_summary_word_line(lookup_word_details_for_box(box))
        if row:
            lines.append(row)
    if len(lines) <= 2:
        lines.append("(등록된 단어가 없습니다)")
    return "\n".join(lines).rstrip() + "\n"


def build_word_memorize_summary_from_path(
    layout_path: str | Path,
    *,
    meaning_lang: str = "ko",
) -> str:
    """JSON 경로에서 정리 텍스트 생성."""
    layout = load_layout(Path(layout_path))
    return build_word_memorize_summary_text(layout, meaning_lang=meaning_lang)


def write_and_open_summary_text(text: str, *, stem: str) -> Path:
    """release 폴더에 저장 후 기본 텍스트 편집기로 연다."""
    safe_stem = (stem or "layout").strip() or "layout"
    release = get_repo_root() / "release"
    release.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = release / f"단어외우기_정리_{safe_stem}_{ts}.txt"
    path.write_text(text, encoding="utf-8")
    os.startfile(str(path))
    return path
