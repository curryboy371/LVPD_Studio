"""숏츠 회화 편집기용 bg_path · ko_narration_id 선택 목록."""
from __future__ import annotations

from pathlib import Path

from core.paths import get_repo_root
from extra.table_editor.services.global_table_cache import GlobalTableCache

_BG_SOUND_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
BG_PATH_RANDOM_LABEL = "(랜덤 — 비움)"
_bg_path_choices_cache: list[str] | None = None


def _normalize_set_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        f = float(raw)
        if f == int(f):
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return raw


def list_bg_path_choices() -> list[str]:
    """`resource/sound/bg_short` 아래 오디오 — repo 상대 경로 (전역 캐시)."""
    global _bg_path_choices_cache
    if _bg_path_choices_cache is not None:
        return _bg_path_choices_cache
    repo = get_repo_root()
    bg_dir = repo / "resource" / "sound" / "bg_short"
    if not bg_dir.is_dir():
        return []
    out: list[str] = []
    for path in sorted(bg_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _BG_SOUND_EXTS:
            continue
        try:
            rel = path.relative_to(repo).as_posix()
        except ValueError:
            rel = path.as_posix()
        out.append(rel)
    _bg_path_choices_cache = out
    return out


def list_ko_narration_set_choices() -> list[tuple[str, str]]:
    """(set id, 콤보 표시 문자열) 목록 — 전역 캐시."""
    return GlobalTableCache.get().get_ko_narration_set_choices()


def bg_path_for_combo(stored: str) -> str:
    """저장값 → 콤보 선택 라벨."""
    if not (stored or "").strip():
        return BG_PATH_RANDOM_LABEL
    return stored.strip()


def bg_path_from_combo(selected: str) -> str:
    """콤보 선택 → 저장값."""
    text = (selected or "").strip()
    if not text or text == BG_PATH_RANDOM_LABEL:
        return ""
    return text


def ko_narration_label_maps(
    choices: list[tuple[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    """label → id, id → label."""
    label_to_id: dict[str, str] = {}
    id_to_label: dict[str, str] = {}
    for sid, label in choices:
        label_to_id[label] = sid
        id_to_label[sid] = label
    return label_to_id, id_to_label


def ko_narration_id_for_combo(
    stored_id: str,
    *,
    id_to_label: dict[str, str],
) -> str:
    sid = _normalize_set_id(stored_id)
    if not sid:
        return ""
    return id_to_label.get(sid, sid)


def ko_narration_id_from_combo(
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
            return _normalize_set_id(text.split(sep, 1)[0])
    return _normalize_set_id(text)
