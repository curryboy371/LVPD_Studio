"""숏츠 녹화 썸네일: 전체 화면 PNG 저장 후 MP4 첫 프레임 교체."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from core.paths import FFMPEG_CMD

logger = logging.getLogger(__name__)


def shorts_thumbnail_png_path(video_path: Path) -> Path:
    """녹화 MP4와 같은 stem의 `_thumb.png`."""
    return video_path.with_name(f"{video_path.stem}_thumb.png")


def apply_thumbnail_as_first_frame(
    video_path: Path,
    image_path: Path,
    *,
    ffmpeg_cmd: str = FFMPEG_CMD,
) -> bool:
    """MP4의 0번 프레임을 image_path로 교체(길이·오디오 스트림 유지, 비디오만 재인코딩)."""
    video_path = Path(video_path)
    image_path = Path(image_path)
    if not video_path.is_file() or not image_path.is_file():
        return False

    tmp = video_path.with_name(f"{video_path.stem}_thumbfx{video_path.suffix}")
    filter_complex = (
        "[1:v][0:v]scale2ref=w=iw:h=ih[thumb][base];"
        "[base][thumb]overlay=shortest=1:enable='eq(n,0)'[v]"
    )
    cmd = [
        ffmpeg_cmd,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(image_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        str(tmp),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,
            creationflags=creationflags,
        )
    except (OSError, subprocess.TimeoutExpired) as ex:
        logger.warning("썸네일 첫 프레임 교체 실패: %s", ex)
        return False

    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", errors="replace")[:800]
        logger.warning("FFmpeg 썸네일 교체 stderr: %s", err)
        return False
    if not tmp.is_file() or tmp.stat().st_size < 128:
        logger.warning("썸네일 교체 출력 없음: %s", tmp)
        return False

    try:
        tmp.replace(video_path)
    except OSError as ex:
        logger.warning("썸네일 교체 파일 교체 실패: %s", ex)
        return False
    return True


def apply_shorts_thumbnail_if_present(
    video_path: Optional[Path],
    *,
    ffmpeg_cmd: str = FFMPEG_CMD,
) -> bool:
    """`{stem}_thumb.png`가 있으면 video_path 첫 프레임에 반영."""
    if video_path is None:
        return False
    video_path = Path(video_path)
    image_path = shorts_thumbnail_png_path(video_path)
    if not image_path.is_file():
        return False
    ok = apply_thumbnail_as_first_frame(video_path, image_path, ffmpeg_cmd=ffmpeg_cmd)
    if ok:
        print("[rec] 썸네일 첫 프레임 반영:", video_path, flush=True)
        print("[rec] 썸네일 PNG:", image_path, flush=True)
    else:
        print("[!] 썸네일 첫 프레임 반영 실패 (PNG는 유지):", image_path, flush=True)
    return ok
