"""숏츠 단어 편집: words 조회·파이프 필드 (전역 캐시 위임)."""
from __future__ import annotations

from extra.table_editor.services.global_table_cache import (
    SelectOption,
    GlobalTableCache,
    warm_shorts_vocab_editor_cache,
)
from extra.table_editor.services.shorts_moment_data import parse_pipe_ids


def normalize_word_id(value: str) -> str:
    """words.id — 1 이상 정수 문자열."""
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        n = int(float(raw))
        return str(n) if n >= 1 else ""
    except (TypeError, ValueError):
        return ""


def parse_pipe_tokens(raw: str) -> list[str]:
    """`| ` 구분 토큰 (빈 칸 유지)."""
    text = (raw or "").strip().replace("，", "|")
    if not text:
        return []
    return [p.strip() for p in text.split("|")]


def join_pipe_tokens(tokens: list[str]) -> str:
    out = list(tokens)
    while out and not out[-1].strip():
        out.pop()
    return "|".join(out)


def topic_sound_repeat_for_editor(raw: str, *, default: str = "1") -> str:
    """편집기 표시용 — topic 공통 repeat (pipe 첫 값)."""
    parts = parse_pipe_tokens(raw)
    token = parts[0].strip() if parts else ""
    if not token:
        return default
    try:
        return str(max(1, int(float(token))))
    except (TypeError, ValueError):
        return default


def normalize_topic_sound_repeat(raw: str, *, default: str = "1") -> str:
    """저장용 — 단일 정수 문자열."""
    return topic_sound_repeat_for_editor(raw, default=default)


def topic_bool_for_editor(raw: str, *, default: str = "true") -> str:
    """편집기 표시용 — topic 공통 bool (pipe 첫 값)."""
    parts = parse_pipe_tokens(raw)
    token = (parts[0] if parts else str(raw or "")).strip().lower()
    if token in ("", "1", "true", "yes", "y", "on", "t"):
        return "true"
    if token in ("0", "false", "no", "n", "off", "f"):
        return "false"
    return default if default in ("true", "false") else "true"


def normalize_topic_bool(raw: str, *, default: str = "true") -> str:
    """저장용 — true/false 단일 값."""
    return topic_bool_for_editor(raw, default=default)


def topic_hook_title_for_editor(raw: str) -> str:
    """편집기 표시용 — topic 공통 hook (legacy `|` per-word 는 첫 값만)."""
    from extra.table_editor.ui.multiline_lines_editor import normalize_multiline_input

    text = str(raw or "").strip()
    if not text:
        return ""
    parts = parse_pipe_tokens(text)
    if len(parts) > 1:
        text = parts[0]
    return normalize_multiline_input(text)


def list_word_options() -> list[SelectOption]:
    return GlobalTableCache.get().get_word_options()


def option_maps(
    options: list[SelectOption],
) -> tuple[list[str], dict[str, str], dict[str, str], dict[str, str]]:
    labels: list[str] = []
    label_to_id: dict[str, str] = {}
    id_to_label: dict[str, str] = {}
    id_to_preview: dict[str, str] = {}
    for opt in options:
        labels.append(opt.label)
        label_to_id[opt.label] = opt.id
        id_to_label[opt.id] = opt.label
        id_to_preview[opt.id] = opt.preview
    return labels, label_to_id, id_to_label, id_to_preview


def id_from_combo_label(
    selected: str,
    *,
    label_to_id: dict[str, str],
) -> str:
    text = (selected or "").strip()
    if not text:
        return ""
    if text in label_to_id:
        return label_to_id[text]
    for sep in (" - ", " — "):
        if sep in text:
            head = text.split(sep, 1)[0].strip()
            try:
                return str(int(float(head)))
            except (ValueError, TypeError):
                return head
    try:
        return str(int(float(text)))
    except (ValueError, TypeError):
        return text


def label_for_id(
    item_id: str,
    *,
    id_to_label: dict[str, str],
) -> str:
    iid = (item_id or "").strip()
    if not iid:
        return ""
    try:
        iid = str(int(float(iid)))
    except (ValueError, TypeError):
        pass
    return id_to_label.get(iid, f"{iid} - (목록에 없음)")


__all__ = [
    "normalize_word_id",
    "parse_pipe_ids",
    "parse_pipe_tokens",
    "join_pipe_tokens",
    "list_word_options",
    "option_maps",
    "id_from_combo_label",
    "label_for_id",
    "warm_shorts_vocab_editor_cache",
    "SelectOption",
]
