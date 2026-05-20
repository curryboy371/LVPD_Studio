"""
숏츠 단어 뜻 TTS 배치 — words.csv 한국어 뜻 → resource/sound/shorts.

산출 (word_id 기준):
  resource/sound/shorts/ko_word_{word_id}_0.mp3
  resource/sound/shorts/ko_word_{word_id}_timeline.json

입력:
  --id N       shorts_vocabulary_clips.csv 행 id → word_id 목록
  --topic      topic 필터 (id·word-id 없을 때)
  --word-id    words.csv id 직접 (30123 또는 30123|30124)

TTS 엔진: words.csv `tts_type`(edge|gtts), `tts_voice`(Edge 목소리).
  비어 있으면 --tts / --tts-voice CLI 기본값.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.vocab_meaning_ko import (
    batch_build_vocab_meaning_ko_for_clip_row_id,
    batch_build_vocab_meaning_ko_for_topic,
    batch_build_vocab_meaning_ko_for_word_ids,
    parse_word_id_list_field,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="숏츠 단어: shorts_vocabulary_clips id 또는 topic → words.csv 뜻 TTS"
    )
    parser.add_argument(
        "--id",
        type=int,
        default=0,
        help="shorts_vocabulary_clips.csv 행 id (topic당 1행). word_id | 목록 처리",
    )
    parser.add_argument("--topic", default="", help="예: fruit_store (--id·--word-id 없을 때)")
    parser.add_argument(
        "--word-id",
        default="",
        help="words.csv id 직접. 예: 30123 또는 30123|30124 (숏츠 CSV 불필요)",
    )
    parser.add_argument("--csv", default="", help="shorts_vocabulary_clips.csv 경로")
    parser.add_argument("--tts", choices=("gtts", "edge"), default="edge")
    parser.add_argument("--tts-voice", default="ko-KR-SunHiNeural")
    parser.add_argument("--force", action="store_true", help="캐시 무시 재생성")
    args = parser.parse_args()

    csv_path = args.csv or None
    word_ids = parse_word_id_list_field(args.word_id or "")
    if word_ids:
        ok, skip, fail = batch_build_vocab_meaning_ko_for_word_ids(
            word_ids,
            tts=args.tts,
            tts_voice=args.tts_voice,
            force_tts=args.force,
        )
        label = f"word_id={args.word_id.strip()}"
    elif int(args.id) > 0:
        ok, skip, fail = batch_build_vocab_meaning_ko_for_clip_row_id(
            int(args.id),
            csv_path=csv_path,
            tts=args.tts,
            tts_voice=args.tts_voice,
            force_tts=args.force,
        )
        label = f"shorts_vocabulary_clips id={args.id}"
    elif (args.topic or "").strip():
        ok, skip, fail = batch_build_vocab_meaning_ko_for_topic(
            args.topic.strip(),
            csv_path=csv_path,
            tts=args.tts,
            tts_voice=args.tts_voice,
            force_tts=args.force,
        )
        label = f"topic={args.topic.strip()}"
    else:
        logger.error("--id, --topic, --word-id 중 하나가 필요합니다.")
        return 1

    logger.info("완료 %s: 생성=%d 스킵=%d 실패=%d", label, ok, skip, fail)
    return 0 if fail == 0 and (ok > 0 or skip > 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
