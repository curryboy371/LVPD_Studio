"""
배치 전용: resource/video 하위 비디오 → 같은 이름 MP3 추출 (extract_audio.bat 에서만 실행).
"""
import logging
import sys
from pathlib import Path

# repo root
_REPO = Path(__file__).resolve().parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    from core.paths import get_repo_root
    from utils.video_audio_extract import extract_audio_under_dir

    video_root = get_repo_root() / "resource" / "video"
    if not video_root.is_dir():
        logger.error("비디오 루트 디렉터리가 없습니다: %s", video_root)
        sys.exit(1)
    logger.info("오디오 추출 대상: %s", video_root)
    created = extract_audio_under_dir(video_root, overwrite=True)
    if created:
        logger.info("오디오 추출 완료: %d개 MP3 생성", len(created))
        for p in created:
            print("  ", p)
    else:
        logger.info("추출할 비디오가 없습니다.")


if __name__ == "__main__":
    main()
