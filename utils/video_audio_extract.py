"""
resource/video 하위 비디오에서 오디오를 추출해 같은 이름의 MP3로 저장.
선행 작업: 스튜디오 녹화·오디오 분리 전에 모든 비디오에 대해 MP3를 미리 만들어 두는 데 사용.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from core.paths import (
    FFMPEG_CMD,
    STUDIO_AUDIO_SAMPLE_RATE,
    STUDIO_VIDEO_EXTRACT_MP3_LAME_Q,
)

# 추출 대상 비디오 확장자
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".flv", ".wmv")


def extract_audio_to_mp3(
    video_path: Path,
    ffmpeg_cmd: str = FFMPEG_CMD,
    overwrite: bool = True,
) -> Optional[Path]:
    """비디오 파일에서 오디오만 추출해 같은 디렉터리에 같은 이름의 MP3로 저장.

    Args:
        video_path: 비디오 파일 경로.
        ffmpeg_cmd: FFmpeg 실행 파일.
        overwrite: True면 기존 MP3가 있어도 덮어씀.

    Returns:
        저장된 MP3 경로. 실패 시 None.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        return None
    out_path = video_path.with_suffix(".mp3")
    if out_path.exists() and not overwrite:
        return out_path
    creationflags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    )
    lame_q = str(int(max(0, min(9, int(STUDIO_VIDEO_EXTRACT_MP3_LAME_Q)))))
    sr = str(int(STUDIO_AUDIO_SAMPLE_RATE))
    yflag = "-y" if overwrite else "-n"
    base_in = [ffmpeg_cmd, yflag, "-i", str(video_path), "-vn"]
    # 1) soxr로 스튜디오 샘플레이트·스테레오 맞춘 뒤 LAME 최고 VBR
    # 2) soxr 미지원 등 실패 시 동일 q만 적용(기존과 호환)
    attempts = [
        base_in
        + [
            "-af",
            "aresample=resampler=soxr",
            "-ar",
            sr,
            "-ac",
            "2",
            "-c:a",
            "libmp3lame",
            "-q:a",
            lame_q,
            str(out_path),
        ],
        base_in + ["-c:a", "libmp3lame", "-q:a", lame_q, str(out_path)],
    ]
    try:
        for cmd in attempts:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,
                creationflags=creationflags,
            )
            if result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                return out_path
    except Exception:
        pass
    return None


def extract_audio_under_dir(
    video_root: str | Path,
    ffmpeg_cmd: str = FFMPEG_CMD,
    overwrite: bool = True,
) -> List[Path]:
    """video_root 하위의 모든 비디오에서 오디오를 추출해 같은 이름의 MP3로 저장.

    Args:
        video_root: 비디오 루트 디렉터리 (예: resource/video).
        ffmpeg_cmd: FFmpeg 실행 파일.
        overwrite: True면 기존 MP3가 있어도 덮어씀.

    Returns:
        성공적으로 생성된 MP3 파일 경로 목록.
    """
    video_root = Path(video_root)
    if not video_root.is_dir():
        return []
    created: List[Path] = []
    for ext in VIDEO_EXTENSIONS:
        for video_path in video_root.rglob(f"*{ext}"):
            if not video_path.is_file():
                continue
            out = extract_audio_to_mp3(video_path, ffmpeg_cmd=ffmpeg_cmd, overwrite=overwrite)
            if out is not None:
                created.append(out)
    return created
