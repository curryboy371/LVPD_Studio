"""resource/table/word_memorize_layouts/*.json 목록·word_id 수집."""
from __future__ import annotations

from pathlib import Path

from extra.table_editor.services.word_memorize_layout import (
    DEFAULT_LAYOUTS_DIR,
    load_layout,
)


def list_layout_files() -> list[tuple[str, Path]]:
    """(JSON 파일명, 절대 경로) — 예: 요일.json"""
    root = DEFAULT_LAYOUTS_DIR
    if not root.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for path in sorted(root.glob("*.json"), key=lambda p: p.name.lower()):
        if path.is_file():
            out.append((path.name, path.resolve()))
    return out


def normalize_layout_filename(raw: str) -> str:
    """stem 또는 파일명 → 요일.json 형태."""
    s = (raw or "").strip()
    if not s:
        return ""
    if s.lower().endswith(".json"):
        return s
    return f"{s}.json"


def word_ids_from_layout(path: str | Path) -> list[int]:
    """배치 JSON에 등장하는 word_id (order 순, 중복 제거)."""
    layout = load_layout(Path(path))
    seen: set[int] = set()
    out: list[int] = []
    for box in layout.sorted_boxes():
        try:
            wid = int(box.word_id)
        except (TypeError, ValueError):
            continue
        if wid < 1 or wid in seen:
            continue
        seen.add(wid)
        out.append(wid)
    return out
