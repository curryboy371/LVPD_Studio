"""
녹화/베이스 MP4 + ko timeline JSON → TTS·자막 합성 영상.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.ko_mux_moviepy import mux_from_timeline_json
from audio.ko_narration import cached_timeline_json_path_for_set

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="숏츠 한국어 TTS·자막 MoviePy mux")
    parser.add_argument("--input", required=True, help="베이스 영상 경로")
    parser.add_argument("--output", required=True, help="출력 MP4 경로")
    parser.add_argument("--timeline", default="", help="timeline JSON (비우면 clip-type/id로 추론)")
    parser.add_argument("--set-id", type=int, required=True, help="ko_narration_sets.id")
    parser.add_argument(
        "--no-base-audio",
        action="store_true",
        help="베이스 영상 오디오 제거 후 TTS만",
    )
    args = parser.parse_args()

    timeline = args.timeline.strip()
    if not timeline:
        timeline = str(cached_timeline_json_path_for_set(args.set_id))

    out = mux_from_timeline_json(
        args.input,
        timeline,
        args.output,
        keep_base_audio=not args.no_base_audio,
    )
    logger.info("저장: %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
