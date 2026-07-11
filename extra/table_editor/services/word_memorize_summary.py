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
    layout_uses_compose,
    load_layout,
)

_HASHTAGS_LINE = (
    "#중국어 #중국어회화 #중국어단어 #중국어기초 #중국어독학 "
    "#쇼츠 #shorts #여포판다 #shorts_중국어"
)
_DIVIDER = "━" * 32


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
    if not topic and layout_uses_compose(layout):
        # 조합형은 별도 제목 타일이 없고, "조합 단어 만들기" 화면에서 입력한
        # 주제(compose_topic)를 화면 자막으로 쓰므로 이걸 그대로 재사용한다.
        topic = str(getattr(layout, "compose_topic", "") or "").strip()
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
    """배치 단어를 정리 텍스트로 변환 — 맨 위 제목 줄, 단어 요약, 해시태그 순."""
    topic = resolve_summary_topic(layout, meaning_lang=meaning_lang)
    title_prefix = "[중국어 단어 조합]" if layout_uses_compose(layout) else "[중국어 단어]"
    title_line = f"🐼 {title_prefix} {topic}"

    lines: list[str] = []
    for box in layout.sorted_boxes():
        row = format_summary_word_line(lookup_word_details_for_box(box))
        if row:
            lines.append(row)
    if not lines:
        lines.append("(등록된 단어가 없습니다)")
    body = "\n".join(lines).rstrip()

    return (
        f"{title_line}\n{_DIVIDER}\n\n"
        f"{body}\n\n"
        f"{_DIVIDER}\n{_HASHTAGS_LINE}\n"
    )


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
