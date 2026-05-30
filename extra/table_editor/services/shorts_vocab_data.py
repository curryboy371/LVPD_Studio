"""숏츠 단어 편집: words 조회·파이프 필드 (전역 캐시 위임)."""
from __future__ import annotations

from extra.table_editor.services.global_table_cache import (
    SelectOption,
    GlobalTableCache,
    warm_shorts_vocab_editor_cache,
)
from extra.table_editor.services.shorts_moment_data import parse_pipe_ids


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
