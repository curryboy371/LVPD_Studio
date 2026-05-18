"""
숏츠 단어 topic → words.csv 뜻 한국어 TTS 배치.

산출: resource/sound/shorts/ko_word_{word_id}_0.mp3, ko_word_{word_id}_timeline.json
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.vocab_meaning_ko import batch_build_vocab_meaning_ko_for_topic

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="숏츠 단어 topic: shorts_vocabulary_clips word_id → words 뜻 TTS"
    )
    parser.add_argument("--topic", required=True, help="예: fruit_store")
    parser.add_argument("--csv", default="", help="shorts_vocabulary_clips.csv 경로")
    parser.add_argument("--tts", choices=("gtts", "edge"), default="edge")
    parser.add_argument("--tts-voice", default="ko-KR-SunHiNeural")
    parser.add_argument("--force", action="store_true", help="캐시 무시 재생성")
    args = parser.parse_args()

    ok, skip, fail = batch_build_vocab_meaning_ko_for_topic(
        args.topic.strip(),
        csv_path=args.csv or None,
        tts=args.tts,
        tts_voice=args.tts_voice,
        force_tts=args.force,
    )
    logger.info("완료 topic=%s: 생성=%d 스킵=%d 실패=%d", args.topic, ok, skip, fail)
    return 0 if fail == 0 and (ok > 0 or skip > 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
