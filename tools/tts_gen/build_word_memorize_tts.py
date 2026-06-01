"""
단어 외우기 배치 TTS — layout JSON의 word_id → 한국어 뜻 + 한자 + 영문 en_meaning.

산출 (word_id 기준, resource/sound/shorts):
  ko_word_{word_id}_0.mp3          — 한국어 뜻
  wm_zh_word_{word_id}_0.mp3       — 중국어 한자 (words.sound_path 와 별도)
  en_word_{word_id}_0.mp3          — 영문 en_meaning

TTS 엔진: words.csv tts_type(edge|gtts). 목소리: --tts-voice / --tts-voice-zh / --tts-voice-en.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.word_memorize_en import DEFAULT_EN_TTS_VOICE
from audio.word_memorize_tts import batch_build_word_memorize_tts_for_layout
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
        description="단어 외우기 배치 JSON → 뜻(KO) + 한자(ZH) + en_meaning(EN) TTS"
    )
    parser.add_argument(
        "--layout",
        required=True,
        help="배치 JSON 경로 또는 파일명(예: 요일 / 요일.json)",
    )
    parser.add_argument("--tts", choices=("gtts", "edge"), default="edge")
    parser.add_argument(
        "--tts-voice",
        default="ko-KR-SunHiNeural",
        help="한국어 뜻 TTS Edge 목소리(비우면 words.csv tts_voice)",
    )
    parser.add_argument(
        "--tts-voice-zh",
        default="zh-CN-XiaoxiaoNeural",
        help="중국어 한자(word) TTS Edge 목소리 (shorts/wm_zh_word_* 경로)",
    )
    parser.add_argument(
        "--tts-voice-en",
        default=DEFAULT_EN_TTS_VOICE,
        help="영문 en_meaning TTS Edge 목소리",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="기존 mp3·timeline이 있으면 재사용 (기본: 선택한 언어는 항상 재생성)",
    )
    parser.add_argument("--skip-ko", action="store_true", help="한국어 뜻 TTS 생성 안 함")
    parser.add_argument("--skip-zh", action="store_true", help="중국어 한자 TTS 생성 안 함")
    parser.add_argument("--skip-en", action="store_true", help="영문 en_meaning TTS 생성 안 함")
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

    ok, skip, fail = batch_build_word_memorize_tts_for_layout(
        layout_path,
        gen_ko=not args.skip_ko,
        gen_zh=not args.skip_zh,
        gen_en=not args.skip_en,
        tts_ko=args.tts,
        tts_voice_ko=args.tts_voice,
        tts_zh=args.tts,
        tts_voice_zh=args.tts_voice_zh,
        tts_en=args.tts,
        tts_voice_en=args.tts_voice_en,
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
