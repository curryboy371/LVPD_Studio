"""숏츠 회화 편집: sub 완성문·ko_narration line 조회 (전역 캐시 위임)."""
from __future__ import annotations

from extra.table_editor.services.global_table_cache import (
    SelectOption,
    GlobalTableCache,
    clear_global_table_cache,
    warm_shorts_editor_cache,
)


def clear_shorts_moment_data_cache() -> None:
    clear_global_table_cache()


def parse_pipe_ids(raw: str) -> list[str]:
    text = (raw or "").strip().replace("，", "|")
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for part in text.split("|"):
        p = part.strip()
        if not p:
            continue
        try:
            nid = str(int(float(p)))
        except (ValueError, TypeError):
            nid = p
        if nid in seen:
            continue
        seen.add(nid)
        out.append(nid)
    return out


def get_base_raw_sentence(base_id: str) -> str:
    return GlobalTableCache.get().get_base_raw(base_id)


def list_base_options() -> list[SelectOption]:
    return GlobalTableCache.get().get_base_options()


def list_sub_options(base_id: str) -> list[SelectOption]:
    return GlobalTableCache.get().get_sub_options(base_id)


def list_ko_line_options(set_id: str) -> list[SelectOption]:
    return GlobalTableCache.get().get_ko_line_options(set_id)


def option_maps(
    options: list[SelectOption],
) -> tuple[list[str], dict[str, str], dict[str, str], dict[str, str]]:
    """labels, label→id, id→label, id→preview."""
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
    labels: list[str],
) -> str:
    iid = (item_id or "").strip()
    if not iid:
        return ""
    try:
        iid = str(int(float(iid)))
    except (ValueError, TypeError):
        pass
    if iid in id_to_label:
        return id_to_label[iid]
    custom = f"{iid} - (목록에 없음)"
    return custom if custom not in labels else iid


__all__ = [
    "SelectOption",
    "clear_shorts_moment_data_cache",
    "parse_pipe_ids",
    "get_base_raw_sentence",
    "list_base_options",
    "list_sub_options",
    "list_ko_line_options",
    "option_maps",
    "id_from_combo_label",
    "label_for_id",
    "warm_shorts_editor_cache",
]
