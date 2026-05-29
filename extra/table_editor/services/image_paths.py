"""Resolve words.img_path to filesystem paths under repo root."""
from __future__ import annotations

from pathlib import Path

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def build_image_stem_index(repo_root: Path) -> dict[str, Path]:
    """resource/image 하위 stem → 절대 경로."""
    base = repo_root / "resource" / "image"
    if not base.exists():
        return {}
    out: dict[str, Path] = {}
    for fp in base.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        key = fp.stem.strip()
        if key and key not in out:
            out[key] = fp.resolve()
    return out


def resolve_image_absolute(
    repo_root: Path,
    img_path_raw: str,
    *,
    word_id: str = "",
    word: str = "",
) -> Path:
    """img_path·id·word로 저장 대상 절대 경로를 정한다."""
    repo_root = repo_root.resolve()
    raw = (img_path_raw or "").strip()
    if raw and raw.lower() != "none":
        if "/" in raw or "\\" in raw:
            return (repo_root / raw.replace("\\", "/")).resolve()
        path = Path(raw)
        if path.suffix.lower() in _IMAGE_SUFFIXES:
            return (repo_root / raw).resolve()
        index = build_image_stem_index(repo_root)
        hit = index.get(raw)
        if hit is not None:
            return hit
        return (repo_root / "resource" / "image" / f"{raw}.png").resolve()

    wid = (word_id or "").strip()
    if wid:
        return (repo_root / "resource" / "image" / f"{wid}.png").resolve()
    w = (word or "").strip()
    if w:
        return (repo_root / "resource" / "image" / f"{w}.png").resolve()
    return (repo_root / "resource" / "image" / "clipboard_new.png").resolve()


def img_path_value_for_table(repo_root: Path, target: Path) -> str:
    """CSV/엑셀에 넣을 img_path 문자열 (기존 stem 관례 유지)."""
    target = target.resolve()
    repo_root = repo_root.resolve()
    try:
        rel = target.relative_to(repo_root)
    except ValueError:
        return target.as_posix()
    rel_posix = rel.as_posix()
    if rel_posix.startswith("resource/image/") and target.suffix.lower() in _IMAGE_SUFFIXES:
        return target.stem
    return rel_posix


def preview_image_path(
    repo_root: Path,
    img_path_raw: str,
    *,
    word_id: str = "",
    word: str = "",
    pending_tmp: Path | None = None,
) -> Path | None:
    """미리보기용 파일 경로 (임시 클립보드 이미지 우선)."""
    if pending_tmp is not None and pending_tmp.is_file():
        return pending_tmp
    raw = (img_path_raw or "").strip()
    if not raw or raw.lower() == "none":
        return None
    target = resolve_image_absolute(
        repo_root, raw, word_id=word_id, word=word
    )
    return target if target.is_file() else None
