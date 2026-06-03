"""Resolve words.img_path to filesystem paths under repo root."""
from __future__ import annotations

from pathlib import Path

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
WORD_IMAGE_REL = "resource/image/word"


def word_image_dir(repo_root: Path) -> Path:
    """단어 이미지 기본 저장 디렉터리 (resource/image/word)."""
    return (repo_root.resolve() / "resource" / "image" / "word").resolve()


def build_image_stem_index(repo_root: Path) -> dict[str, Path]:
    """resource/image 하위 stem → 절대 경로 (word/ 하위가 동일 stem이면 우선)."""
    base = repo_root / "resource" / "image"
    if not base.exists():
        return {}
    out: dict[str, Path] = {}
    for fp in sorted(base.rglob("*"), key=lambda p: p.as_posix()):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        key = fp.stem.strip()
        if not key:
            continue
        resolved = fp.resolve()
        prev = out.get(key)
        if prev is None:
            out[key] = resolved
            continue
        prev_is_word = WORD_IMAGE_REL in prev.as_posix()
        new_is_word = WORD_IMAGE_REL in resolved.as_posix()
        if new_is_word and not prev_is_word:
            out[key] = resolved
    return out


def _default_word_image_path(repo_root: Path, stem: str) -> Path:
    return (word_image_dir(repo_root) / f"{stem}.png").resolve()


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
        return _default_word_image_path(repo_root, raw)

    wid = (word_id or "").strip()
    if wid:
        return _default_word_image_path(repo_root, wid)
    w = (word or "").strip()
    if w:
        return _default_word_image_path(repo_root, w)
    return _default_word_image_path(repo_root, "clipboard_new")


def img_path_value_for_table(repo_root: Path, target: Path) -> str:
    """CSV/엑셀에 넣을 img_path 문자열 (resource/image/word/ 는 stem만 저장)."""
    target = target.resolve()
    repo_root = repo_root.resolve()
    try:
        rel = target.relative_to(repo_root)
    except ValueError:
        return target.as_posix()
    rel_posix = rel.as_posix()
    if (
        rel_posix.startswith(f"{WORD_IMAGE_REL}/")
        or rel_posix.startswith("resource/image/")
    ) and target.suffix.lower() in _IMAGE_SUFFIXES:
        return target.stem
    return rel_posix


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = p.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        out.append(p.resolve())
    return out


def resolve_existing_word_image_path(
    repo_root: Path,
    img_path_raw: str,
    *,
    word_id: str = "",
    word: str = "",
    sound_path: str = "",
    pending_tmp: Path | None = None,
) -> Path | None:
    """미리보기·클립보드 복사용 — 실제 존재하는 이미지 파일 경로."""
    if pending_tmp is not None and pending_tmp.is_file():
        return pending_tmp.resolve()

    repo_root = repo_root.resolve()
    raw = (img_path_raw or "").strip()
    candidates: list[Path] = []

    if raw and raw.lower() != "none":
        candidates.append(
            resolve_image_absolute(
                repo_root, raw, word_id=word_id, word=word
            )
        )

    index = build_image_stem_index(repo_root)
    stems: list[str] = []
    for stem in (raw, (sound_path or "").strip(), (word or "").strip(), (word_id or "").strip()):
        if not stem or stem.lower() == "none" or stem in stems:
            continue
        stems.append(stem)
        hit = index.get(stem)
        if hit is not None:
            candidates.append(hit)
        candidates.append(_default_word_image_path(repo_root, stem))

    for path in _dedupe_paths(candidates):
        if path.is_file():
            return path
    return None


def preview_image_path(
    repo_root: Path,
    img_path_raw: str,
    *,
    word_id: str = "",
    word: str = "",
    sound_path: str = "",
    pending_tmp: Path | None = None,
) -> Path | None:
    """미리보기용 파일 경로 (임시·img_path·sound_path·한자·id 순 탐색)."""
    raw = (img_path_raw or "").strip()
    if not raw or raw.lower() == "none":
        if not (word or word_id or sound_path or pending_tmp):
            return None
    return resolve_existing_word_image_path(
        repo_root,
        img_path_raw,
        word_id=word_id,
        word=word,
        sound_path=sound_path,
        pending_tmp=pending_tmp,
    )
