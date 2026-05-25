from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _build_stem_index(base_dir: Path, *, audio_only: bool) -> dict[str, Path]:
    if not base_dir.exists():
        return {}
    out: dict[str, Path] = {}
    for fp in base_dir.rglob("*"):
        if not fp.is_file():
            continue
        if audio_only and fp.suffix.lower() not in _AUDIO_EXTS:
            continue
        key = fp.stem.strip()
        if key and key not in out:
            out[key] = fp
    return out


def _resolve_resource_path(raw: str, repo: Path, stem_index: dict[str, Path]) -> Path | None:
    value = (raw or "").strip()
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        return p
    if "/" in value or "\\" in value:
        return (repo / value.replace("\\", "/")).resolve()
    if p.suffix:
        return (repo / value).resolve()
    hit = stem_index.get(value)
    if hit is not None:
        return hit.resolve()
    return (repo / value).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check missing resources for selected topic.")
    parser.add_argument("--topic", type=str, default="", help="Topic name. Empty means all topics.")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    csv_dir = repo / "resource" / "csv"
    base_csv = csv_dir / "base_sentences.csv"
    words_csv = csv_dir / "words.csv"
    sub_csv = csv_dir / "sub_sentences.csv"
    vocab_rows_csv = csv_dir / "vocabulary_word_rows.csv"

    base_rows = _read_csv_rows(base_csv)
    words_rows = _read_csv_rows(words_csv)
    sub_rows = _read_csv_rows(sub_csv)
    vocab_rows = _read_csv_rows(vocab_rows_csv)

    topic = (args.topic or "").strip()
    if topic:
        selected_base = [r for r in base_rows if (r.get("topic") or "").strip() == topic]
    else:
        selected_base = list(base_rows)

    if not selected_base:
        print(f"[check] 대상 topic 데이터 없음: {topic or '(all)'}")
        return 1

    image_index = _build_stem_index(repo / "resource" / "image", audio_only=False)
    sound_index = _build_stem_index(repo / "resource" / "sound", audio_only=True)

    missing: list[tuple[str, str, str]] = []

    selected_base_ids: set[str] = {(r.get("id") or "").strip() for r in selected_base}
    selected_vocab_word_ids: set[str] = set()
    if topic:
        selected_vocab_word_ids = {
            (r.get("word_id") or "").strip()
            for r in vocab_rows
            if (r.get("topic") or "").strip() == topic
        }
    else:
        selected_vocab_word_ids = {(r.get("word_id") or "").strip() for r in vocab_rows}

    words_by_id = {(r.get("id") or "").strip(): r for r in words_rows}

    for row in selected_base:
        sid = (row.get("id") or "").strip()
        for key in ("video_path", "sound_lv_path"):
            raw = row.get(key) or ""
            if key == "sound_lv_path" and not str(raw).strip():
                raw = row.get("sound_lv1_path") or row.get("sound_lv2_path") or ""
            idx = sound_index if "sound_" in key else image_index
            resolved = _resolve_resource_path(raw, repo, idx)
            if resolved is None:
                continue
            if not resolved.exists():
                missing.append((f"base_sentences(id={sid})", key, str(resolved)))

    for row in sub_rows:
        base_id = (row.get("base_id") or "").strip()
        if base_id not in selected_base_ids:
            continue
        raw = row.get("alt_sound_path") or ""
        from core.paths import resolve_conversation_sub_cn_sound_path

        resolved = resolve_conversation_sub_cn_sound_path(raw)
        if resolved is None:
            continue
        if not resolved.exists():
            rid = (row.get("id") or "").strip()
            missing.append((f"sub_sentences(id={rid},base_id={base_id})", "alt_sound_path", str(resolved)))

    for wid in selected_vocab_word_ids:
        if not wid:
            continue
        w = words_by_id.get(wid)
        if w is None:
            missing.append((f"vocabulary_word_rows(word_id={wid})", "word_id", "words.csv에 해당 id 없음"))
            continue
        img_path = _resolve_resource_path(w.get("img_path") or "", repo, image_index)
        if img_path is not None and not img_path.exists():
            missing.append((f"words(id={wid})", "img_path", str(img_path)))
        snd_path = _resolve_resource_path(w.get("sound_path") or "", repo, sound_index)
        if snd_path is not None and not snd_path.exists():
            missing.append((f"words(id={wid})", "sound_path", str(snd_path)))

    print(f"[check] topic={topic or '(all)'}  base_rows={len(selected_base)}")
    if missing:
        print(f"[check] 누락 리소스 {len(missing)}건")
        for owner, field, path in missing:
            print(f" - {owner} | {field} | {path}")
        return 1

    print("[check] 누락 리소스 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
