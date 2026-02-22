"""
FFmpeg로 VideoSegment와 OverlayItem을 결합해 프레임을 생성하는 렌더러.
core.BaseRenderer를 상속하며, audio 모듈은 참조하지 않는다.
"""
import logging
import os
import subprocess
import sys
from typing import Any, Optional

import numpy as np

from core.interfaces import BaseRenderer
from core.paths import FFMPEG_CMD
from data.models import OverlayItem, VideoSegment

logger = logging.getLogger(__name__)


def _escape_drawtext(s: str) -> str:
    """drawtext 필터용 텍스트: 작은따옴표를 이스케이프."""
    if not s:
        return ""
    return s.replace("\\", "\\\\").replace("'", "'\\''")


class FFmpegSegmentOverlayRenderer(BaseRenderer):
    """VideoSegment와 OverlayItem을 FFmpeg로 결합해 한 프레임을 생성하는 렌더러. 비디오는 화면/렌더 전용으로 영상 스트림만 사용(-an)."""

    def __init__(self, ffmpeg_cmd: Optional[str] = None) -> None:
        """FFmpeg 경로를 지정할 수 있다. None이면 환경 변수 또는 기본 ffmpeg 사용."""
        self._ffmpeg = ffmpeg_cmd or FFMPEG_CMD

    def render_segment_overlay(
        self,
        segment: Any,
        overlay: Any,
        timestamp_sec: float,
        width: int,
        height: int,
    ) -> np.ndarray:
        """세그먼트 영상에서 해당 시점의 프레임을 추출하고, 오버레이(이미지·텍스트)를 합성한다.

        Args:
            segment: VideoSegment. file_path, start_time, end_time, volume 사용.
            overlay: OverlayItem. text, font_name, font_size, position_x/y, image_path 사용.
            timestamp_sec: 추출할 시점(초).
            width: 출력 프레임 너비.
            height: 출력 프레임 높이.

        Returns:
            RGB numpy (height, width, 3), dtype uint8. 실패 시 검정 프레임 반환.
        """
        seg = segment if isinstance(segment, VideoSegment) else VideoSegment.model_validate(segment)
        ov = overlay if isinstance(overlay, OverlayItem) else OverlayItem.model_validate(overlay)

        if not seg.file_path or not os.path.exists(seg.file_path):
            logger.warning("영상 파일 없음: %s", seg.file_path)
            return np.zeros((height, width, 3), dtype=np.uint8)

        try:
            return self._render_ffmpeg(seg, ov, timestamp_sec, width, height)
        except Exception as e:
            logger.exception("FFmpeg 프레임 생성 실패: %s", e)
            return np.zeros((height, width, 3), dtype=np.uint8)

    def _render_ffmpeg(
        self,
        segment: VideoSegment,
        overlay: OverlayItem,
        timestamp_sec: float,
        width: int,
        height: int,
    ) -> np.ndarray:
        """FFmpeg subprocess로 한 프레임 추출 + 오버레이 합성 후 raw RGB bytes를 numpy로 반환.
        비디오는 화면/렌더 전용이므로 영상 스트림만 사용(-an), 오디오는 디코딩하지 않음.
        요청 시각은 세그먼트 [start_time, end_time] 구간으로 클램프하여 정확히 해당 구간만 렌더."""
        inputs: list[str] = []
        filter_parts: list[str] = []
        vid_label = "0:v"

        # 세그먼트 구간 내로 클램프 (end_time < 0 이면 끝까지이므로 상한 없음)
        ts = max(segment.start_time, timestamp_sec)
        if segment.end_time >= 0:
            ts = min(segment.end_time, ts)

        # 1) 영상에서 -ss 로 시점 이동 후 한 프레임, scale (비디오만 사용, 오디오 미디코딩)
        inputs.extend(["-ss", str(ts), "-i", segment.file_path])
        filter_parts.append(f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[base]")
        vid_label = "base"

        # 2) 이미지 오버레이 (있으면)
        if overlay.image_path and os.path.exists(overlay.image_path):
            inputs.extend(["-i", overlay.image_path])
            filter_parts.append(f"[{vid_label}][1:v]scale2ref=w=iw:h=ih[bg][img];[bg][img]overlay=0:0[v1]")
            vid_label = "v1"

        # 3) drawtext (텍스트 있으면)
        if overlay.text:
            # drawtext: text='...', x, y, fontsize, fontfile(선택)
            x, y = int(overlay.position_x), int(overlay.position_y)
            fontsize = overlay.font_size
            text_esc = _escape_drawtext(overlay.text)
            fontfile = f":fontfile='{overlay.font_name}'" if overlay.font_name else ""
            filter_parts.append(
                f"[{vid_label}]drawtext=text='{text_esc}':x={x}:y={y}:fontsize={fontsize}{fontfile}:fontcolor=white:borderw=2:bordercolor=black[out]"
            )
            vid_label = "out"

        filter_complex = ";".join(filter_parts)
        cmd = [
            self._ffmpeg,
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            f"[{vid_label}]",
            "-an",
            "-vframes",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            creationflags=creationflags,
        )
        if result.returncode != 0 or not result.stdout:
            logger.warning("FFmpeg 반환 코드 %s, stderr: %s", result.returncode, (result.stderr or b"")[:500])
            return np.zeros((height, width, 3), dtype=np.uint8)
        out = np.frombuffer(result.stdout, dtype=np.uint8)
        expected = height * width * 3
        if out.size < expected:
            return np.zeros((height, width, 3), dtype=np.uint8)
        return out[:expected].reshape((height, width, 3))
