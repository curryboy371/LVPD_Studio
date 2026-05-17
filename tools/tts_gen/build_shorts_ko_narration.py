"""
숏츠 클립의 ko_narration_id → ko_narration_lines 기준 문장별 TTS·타임라인 배치 생성.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.ko_narration import (
    batch_build_shorts_ko_narration,
    collect_ko_narration_set_ids_from_shorts_csv,
    format_tts_log_label,
    resolve_tts_config_for_set,
)
from data.ko_narration_loader import load_ko_narration_tables

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="숏츠 한국어 내레이션 TTS·타임라인 배치 생성")
    parser.add_argument(
        "--shorts-type",
        choices=("conversation", "vocabulary"),
        default="conversation",
        help="클립 CSV 종류",
    )
    parser.add_argument("--csv", default="", help="클립 CSV 경로(비우면 기본)")
    parser.add_argument("--topic", action="append", default=[], help="topic 필터(반복 가능)")
    parser.add_argument("--tts", choices=("gtts", "edge"), default="gtts", help="TTS 엔진(세트 tts 비어 있을 때)")
    parser.add_argument(
        "--tts-voice",
        default="",
        help="Edge 목소리 ID(세트 tts_voice 비어 있을 때). 예: ko-KR-InJoonNeural",
    )
    parser.add_argument("--force", action="store_true", help="캐시 무시하고 TTS 재생성")
    parser.add_argument("--clip-id", type=int, default=0, help="특정 clip_id만 처리")
    parser.add_argument(
        "--with-composite",
        action="store_true",
        help="문장별 mp3 외 composite mp3도 생성(MoviePy mux용)",
    )
    parser.add_argument("--set-id", type=int, default=0, help="ko_narration_sets.id 만 처리")
    args = parser.parse_args()

    topics = [t for t in args.topic if t.strip()] or None
    load_ko_narration_tables()
    target_ids = collect_ko_narration_set_ids_from_shorts_csv(
        shorts_mode=args.shorts_type,
        csv_path=args.csv or None,
        session_topics=topics,
        clip_id=args.clip_id,
        set_id=args.set_id,
    )
    if target_ids:
        logger.info("TTS 배치 대상 %d개 세트", len(target_ids))
        for sid in target_ids:
            engine, voice = resolve_tts_config_for_set(
                sid, tts_cli=args.tts, tts_voice_cli=args.tts_voice
            )
            logger.info("  set_id=%s 음성=%s", sid, format_tts_log_label(engine, voice))
    try:
        from studio.shorts.follow_along_tts import ensure_follow_along_mp3

        ensure_follow_along_mp3()
        logger.info("follow_along mp3 준비: resource/sound/shorts/follow_along.mp3")
    except Exception as ex:
        logger.warning("follow_along TTS 생성 실패: %s", ex)

    ok, skip, fail = batch_build_shorts_ko_narration(
        shorts_mode=args.shorts_type,
        csv_path=args.csv or None,
        session_topics=topics,
        tts=args.tts,
        tts_voice=args.tts_voice,
        force_tts=args.force,
        clip_id=args.clip_id,
        with_composite=args.with_composite,
        set_id=args.set_id,
    )
    logger.info("완료: 생성=%d 스킵=%d 실패=%d", ok, skip, fail)
    return 0 if fail == 0 and (ok > 0 or skip > 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
