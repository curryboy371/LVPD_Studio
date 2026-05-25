"""
회화 모드 TTS 배치 — topic별 sub_sentences.alt_translation.

산출: resource/sound/sentense/ko_sub_{base_id}_{sub_id}.mp3
기본: 해당 topic mp3 삭제 후 전부 재생성. 기존 유지만 할 때 --skip-existing
검증: python -m tools.tts_gen.verify_conversation_sub_ko --topic <topic>
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.conversation_sub_translation_ko import batch_build_conversation_sub_ko_for_topic

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="회화 모드: topic → sub_sentences 한국어 번역(alt_translation) TTS"
    )
    parser.add_argument("--topic", required=True, help="base_sentences.topic (예: fruit_store)")
    parser.add_argument("--base-csv", default="", help="base_sentences.csv 경로")
    parser.add_argument("--sub-csv", default="", help="sub_sentences.csv 경로")
    parser.add_argument("--tts", choices=("gtts", "edge"), default="edge")
    parser.add_argument("--tts-voice", default="ko-KR-SunHiNeural")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="기존 mp3가 있으면 스킵 (기본: topic mp3 삭제 후 전부 재생성)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="--skip-existing 과 함께: 삭제 없이 덮어쓰기만",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="(기본 동작과 동일) topic mp3 삭제 후 재생성. --skip-existing 과 함께 쓰지 않음",
    )
    args = parser.parse_args()

    if args.skip_existing:
        rebuild = False
        force_tts = bool(args.force)
    else:
        rebuild = True
        force_tts = True

    ok, skip, fail = batch_build_conversation_sub_ko_for_topic(
        args.topic.strip(),
        tts=args.tts,
        tts_voice=args.tts_voice,
        force_tts=force_tts,
        rebuild=rebuild,
        base_csv=args.base_csv or None,
        sub_csv=args.sub_csv or None,
    )
    logger.info(
        "완료 topic=%s: 생성=%d 스킵=%d 실패=%d",
        args.topic.strip(),
        ok,
        skip,
        fail,
    )
    return 0 if fail == 0 and (ok > 0 or skip > 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
