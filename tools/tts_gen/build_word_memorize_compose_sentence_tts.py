"""
단어 외우기 조합형(단어 조합) — 결과 단어 활용 문장 TTS.

layout JSON의 word_id(결과 단어, boxes) → words.csv의 example_sentence(중국어 문장) +
example_translation(한국어 뜻) TTS.

산출 (word_id 기준, resource/sound/shorts):
  wm_sentence_ko_{word_id}_0.mp3   — 한국어 번역 문장
  wm_sentence_zh_{word_id}_0.mp3   — 중국어 문장

TTS 엔진·목소리: --tts / --tts-voice-ko / --tts-voice-zh CLI.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.word_memorize_compose_sentence import (
    DEFAULT_SENTENCE_KO_TTS_VOICE,
    DEFAULT_SENTENCE_ZH_TTS_VOICE,
    batch_build_compose_sentence_tts_for_layout,
)
from extra.table_editor.services.word_memorize_layout import DEFAULT_LAYOUTS_DIR

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _resolve_layout_arg(raw: str) -> Path:
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty layout")
    p = Path(s)
    if p.is_file():
        return p.resolve()
    by_name = DEFAULT_LAYOUTS_DIR / f"{s}.json"
    if by_name.is_file():
        return by_name.resolve()
    by_stem = DEFAULT_LAYOUTS_DIR / s
    if by_stem.is_file():
        return by_stem.resolve()
    raise FileNotFoundError(s)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="조합형 배치 JSON → 결과 단어 활용 문장(ZH) + 번역(KO) TTS"
    )
    parser.add_argument(
        "--layout",
        required=True,
        help="배치 JSON 경로 또는 파일명(예: 조합_예시1 / 조합_예시1.json)",
    )
    parser.add_argument("--tts", choices=("gtts", "edge"), default="edge")
    parser.add_argument(
        "--tts-voice-ko",
        default=DEFAULT_SENTENCE_KO_TTS_VOICE,
        help="한국어 번역 문장 TTS Edge 목소리",
    )
    parser.add_argument(
        "--tts-voice-zh",
        default=DEFAULT_SENTENCE_ZH_TTS_VOICE,
        help="중국어 문장 TTS Edge 목소리",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="기존 mp3·timeline이 있으면 재사용 (기본: 항상 재생성)",
    )
    parser.add_argument("--skip-ko", action="store_true", help="한국어 번역 TTS 생성 안 함")
    parser.add_argument("--skip-zh", action="store_true", help="중국어 문장 TTS 생성 안 함")
    args = parser.parse_args()

    try:
        layout_path = _resolve_layout_arg(args.layout)
    except FileNotFoundError:
        logger.error(
            "배치를 찾을 수 없습니다: %s (기본 폴더: %s)",
            args.layout,
            DEFAULT_LAYOUTS_DIR,
        )
        return 1
    except ValueError:
        logger.error("--layout 이 필요합니다.")
        return 1

    ok, skip, fail = batch_build_compose_sentence_tts_for_layout(
        layout_path,
        gen_ko=not args.skip_ko,
        gen_zh=not args.skip_zh,
        tts_ko=args.tts,
        tts_voice_ko=args.tts_voice_ko,
        tts_zh=args.tts,
        tts_voice_zh=args.tts_voice_zh,
        force_tts=not args.use_cache,
    )
    logger.info(
        "완료 layout=%s: 생성=%d 스킵=%d 실패=%d",
        layout_path.name,
        ok,
        skip,
        fail,
    )
    return 0 if fail == 0 and (ok > 0 or skip > 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
