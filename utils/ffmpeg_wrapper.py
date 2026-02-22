"""
FFmpeg 래퍼: 비디오와 오디오를 합쳐(Muxing) 최종 파일로 저장한다.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from core.paths import FFMPEG_CMD

logger = logging.getLogger(__name__)


def mux_video_audio(
    video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    ffmpeg_cmd: Optional[str] = None,
) -> str:
    """비디오 파일과 오디오 파일을 합쳐 하나의 컨테이너에 저장한다.

    Args:
        video_path: 비디오 파일 경로.
        audio_path: 오디오 파일 경로 (WAV, MP3 등).
        output_path: 출력 파일 경로 (예: output/rendered.mp4).
        ffmpeg_cmd: FFmpeg 실행 파일. None이면 환경 변수 또는 ffmpeg.

    Returns:
        저장된 출력 파일의 절대 경로(str).

    Raises:
        FileNotFoundError: video_path 또는 audio_path가 없을 때.
        RuntimeError: FFmpeg 실행 실패 시.
    """
    video_path = Path(video_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise FileNotFoundError(f"비디오 파일 없음: {video_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"오디오 파일 없음: {audio_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_cmd or FFMPEG_CMD,
        "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    result = subprocess.run(cmd, capture_output=True, timeout=600, creationflags=creationflags)
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", errors="replace")[:800]
        logger.error("FFmpeg mux stderr: %s", err)
        raise RuntimeError(f"FFmpeg mux 실패 (코드 {result.returncode}): {err}")
    return str(output_path.resolve())
