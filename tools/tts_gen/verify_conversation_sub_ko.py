"""
회화 sub TTS가 sub_sentences.csv와 1:1로 맞는지 검증.

- 기대 파일: resource/sound/sentense/ko_sub_{base_id}_{sub_id}.mp3
- 각 행의 alt_translation 과 배치 로그/매니페스트 대조
- id만 중복·번역이 다른 행(구 ko_sub_{id} 충돌) 경고
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.conversation_sub_translation_ko import (
    collect_sub_translation_jobs_for_topic,
    list_conversation_topics_in_base_sentences,
)
from audio.ko_narration import cached_cue_audio_usable
from core.paths import (
    CONVERSATION_SUB_KO_SOUND_DIR,
    DEFAULT_SUB_SENTENCES_CSV,
    conversation_sub_ko_mp3_path,
    conversation_sub_ko_mp3_path_legacy,
    get_repo_root,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load_sub_rows(sub_csv: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(sub_csv, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append({k: str(v or "").strip() for k, v in row.items()})
    return rows


def _base_sub_collisions(rows: list[dict[str, str]]) -> list[tuple[int, int, list[str]]]:
    """같은 (base_id, sub_id)에 서로 다른 alt_translation."""
    by_key: dict[tuple[int, int], set[str]] = defaultdict(set)
    for row in rows:
        try:
            sub_id = int(float(row.get("id") or "0"))
            base_id = int(float(row.get("base_id") or "0"))
        except (TypeError, ValueError):
            continue
        text = str(row.get("alt_translation") or "").strip()
        if sub_id < 1 or base_id < 1 or not text:
            continue
        by_key[(base_id, sub_id)].add(text)
    return [
        (b, s, sorted(texts))
        for (b, s), texts in sorted(by_key.items())
        if len(texts) > 1
    ]


def _id_only_collisions(rows: list[dict[str, str]]) -> list[tuple[int, list[tuple[int, str]]]]:
    """sub id만 같고 base_id·번역이 다른 그룹."""
    by_sub_id: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for row in rows:
        try:
            sub_id = int(float(row.get("id") or "0"))
            base_id = int(float(row.get("base_id") or "0"))
        except (TypeError, ValueError):
            continue
        if sub_id < 1 or base_id < 1:
            continue
        text = str(row.get("alt_translation") or "").strip()
        if not text:
            continue
        by_sub_id[sub_id].append((base_id, text))
    out: list[tuple[int, list[tuple[int, str]]]] = []
    for sub_id, pairs in sorted(by_sub_id.items()):
        uniq = {(b, t) for b, t in pairs}
        bases = {b for b, _ in uniq}
        if len(bases) > 1 or len(uniq) > 1:
            out.append((sub_id, sorted(uniq)))
    return out


def verify_topic(
    topic: str,
    *,
    sub_csv: str | Path | None = None,
    base_csv: str | Path | None = None,
    write_manifest: str | Path | None = None,
) -> tuple[int, int, int]:
    """Returns (ok_rows, missing_mp3, legacy_only_rows)."""
    jobs = collect_sub_translation_jobs_for_topic(
        topic, base_csv=base_csv, sub_csv=sub_csv
    )
    if not jobs:
        logger.warning("topic=%s: 검증할 sub 행 없음", topic)
        return 0, 0, 0

    ok = missing = legacy_only = 0
    manifest: list[dict[str, object]] = []
    seen: set[tuple[int, int]] = set()

    for sub_id, base_id, text in jobs:
        key = (base_id, sub_id)
        if key in seen:
            continue
        seen.add(key)
        path = conversation_sub_ko_mp3_path(base_id, sub_id)
        leg = conversation_sub_ko_mp3_path_legacy(sub_id)
        has_new = path.is_file() and cached_cue_audio_usable(path)
        has_leg = leg.is_file() and cached_cue_audio_usable(leg)
        entry = {
            "topic": topic,
            "base_id": base_id,
            "sub_id": sub_id,
            "alt_translation": text,
            "expected_mp3": str(path.relative_to(get_repo_root())),
            "ok": has_new,
            "legacy_mp3": str(leg.relative_to(get_repo_root())) if has_leg else "",
            "legacy_only": bool(has_leg and not has_new),
        }
        manifest.append(entry)
        if has_new:
            ok += 1
            logger.info(
                "OK base_id=%s sub_id=%s → %s | %s",
                base_id,
                sub_id,
                path.name,
                text[:40],
            )
        elif has_leg:
            legacy_only += 1
            logger.warning(
                "LEGACY만 있음 base_id=%s sub_id=%s (구 ko_sub_%s.mp3) — 재배치 권장: %s",
                base_id,
                sub_id,
                sub_id,
                text[:40],
            )
        else:
            missing += 1
            logger.error(
                "MISSING base_id=%s sub_id=%s → %s | %s",
                base_id,
                sub_id,
                path.name,
                text[:40],
            )

    if write_manifest:
        out_p = Path(write_manifest)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(
            json.dumps(
                {"topic": topic, "rows": manifest},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("매니페스트 저장: %s", out_p)

    return ok, missing, legacy_only


def main() -> int:
    parser = argparse.ArgumentParser(
        description="회화 sub TTS ↔ sub_sentences.csv 매핑 검증"
    )
    parser.add_argument("--topic", default="", help="base_sentences.topic")
    parser.add_argument("--all-topics", action="store_true", help="등록된 topic 전부")
    parser.add_argument("--sub-csv", default="", help="sub_sentences.csv 경로")
    parser.add_argument("--base-csv", default="", help="base_sentences.csv 경로")
    parser.add_argument(
        "--check-id-collisions",
        action="store_true",
        help="sub id만 중복(서로 다른 base/번역) 목록 출력",
    )
    parser.add_argument(
        "--write-manifest",
        default="",
        help="검증 결과 JSON 경로 (예: output/ko_sub_manifest_fruit_store.json)",
    )
    args = parser.parse_args()

    sub_path = Path(args.sub_csv or DEFAULT_SUB_SENTENCES_CSV)
    collisions: list = []
    if args.check_id_collisions or (not args.topic and not args.all_topics):
        rows = _load_sub_rows(sub_path)
        base_sub = _base_sub_collisions(rows)
        if base_sub:
            logger.warning(
                "동일 (base_id, sub_id)에 서로 다른 alt_translation %d건 — mp3 1개로는 맞출 수 없음.",
                len(base_sub),
            )
            for base_id, sub_id, texts in base_sub[:15]:
                logger.warning(
                    "  base_id=%s sub_id=%s: %s",
                    base_id,
                    sub_id,
                    " | ".join(t[:28] for t in texts),
                )
        collisions = _id_only_collisions(rows)
        if collisions:
            logger.warning(
                "sub_sentences.id 단독 중복 %d건 — 구 ko_sub_{id}.mp3는 마지막 행만 남습니다.",
                len(collisions),
            )
            for sub_id, pairs in collisions[:20]:
                detail = ", ".join(f"base{b}={t[:24]!r}" for b, t in pairs)
                logger.warning("  id=%s: %s", sub_id, detail)
            if len(collisions) > 20:
                logger.warning("  ... 외 %d건", len(collisions) - 20)
        else:
            logger.info("sub id 단독 중복 없음(또는 동일 번역만 공유)")

    topics: list[str] = []
    if args.all_topics:
        topics = list_conversation_topics_in_base_sentences()
    elif args.topic.strip():
        topics = [args.topic.strip()]
    else:
        if not args.check_id_collisions:
            parser.error("--topic 또는 --all-topics 필요")
        return 0 if not collisions else 2

    total_ok = total_miss = total_leg = 0
    for topic in topics:
        logger.info("=== topic=%s ===", topic)
        manifest_path = args.write_manifest
        if manifest_path and len(topics) > 1:
            stem = Path(manifest_path).stem
            manifest_path = str(
                Path(manifest_path).with_name(f"{stem}_{topic}.json")
            )
        ok, miss, leg = verify_topic(
            topic,
            sub_csv=args.sub_csv or None,
            base_csv=args.base_csv or None,
            write_manifest=manifest_path or None,
        )
        total_ok += ok
        total_miss += miss
        total_leg += leg

    logger.info(
        "합계: OK=%d MISSING=%d LEGACY_ONLY=%d (산출 폴더=%s)",
        total_ok,
        total_miss,
        total_leg,
        CONVERSATION_SUB_KO_SOUND_DIR,
    )
    if total_miss > 0:
        return 1
    if total_leg > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
