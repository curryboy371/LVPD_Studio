"""
FFmpeg로 AudioTrack 리스트를 믹싱하는 오디오 믹서.
IAudioMixer를 구현하며, video 모듈은 참조하지 않는다.
"""
import logging
import os
import subprocess
import sys
from typing import Any, Optional

from core.interfaces import IAudioMixer
from core.paths import FFMPEG_CMD
from data.models import AudioTrack

logger = logging.getLogger(__name__)


class FFmpegAudioMixer(IAudioMixer):
    """AudioTrack 리스트를 FFmpeg filter_complex(afade, amix)로 믹싱하는 믹서."""

    def __init__(self, ffmpeg_cmd: Optional[str] = None) -> None:
        """FFmpeg 경로를 지정할 수 있다. None이면 환경 변수 또는 기본 ffmpeg 사용."""
        self._ffmpeg = ffmpeg_cmd or FFMPEG_CMD

    def mix(
        self,
        sound_paths: list[str],
        start_time_sec: float,
        end_time_sec: float,
        **kwargs: Any,
    ) -> bytes | str:
        """여러 사운드 파일을 지정 구간으로 믹싱한다. 출력 경로가 kwargs에 있으면 파일로 저장하고 경로 반환.

        Args:
            sound_paths: 사운드 파일 경로 목록.
            start_time_sec: 출력 구간 시작(초).
            end_time_sec: 출력 구간 종료(초).
            **kwargs: output_path=str 이면 해당 경로에 저장. sample_rate, channels 등.

        Returns:
            output_path가 있으면 해당 경로(str), 없으면 믹싱된 PCM bytes(또는 빈 bytes).
        """
        output_path: Optional[str] = kwargs.get("output_path")
        duration = max(0.0, end_time_sec - start_time_sec) if end_time_sec > start_time_sec else None
        valid_paths = [p for p in sound_paths if p and os.path.exists(p)]
        if not valid_paths:
            logger.warning("유효한 사운드 경로 없음")
            return output_path if output_path else b""

        try:
            return self._mix_impl(
                valid_paths,
                start_time_sec=start_time_sec,
                duration_sec=duration,
                output_path=output_path,
                **kwargs,
            )
        except Exception as e:
            logger.exception("FFmpeg 믹싱 실패: %s", e)
            return output_path if output_path else b""

    def mix_from_tracks(
        self,
        tracks: list[AudioTrack],
        output_path: Optional[str] = None,
        duration_sec: Optional[float] = None,
        sample_rate: int = 48000,
        channels: int = 2,
    ) -> bytes | str:
        """AudioTrack 리스트를 배경음·비디오 사운드 순으로 믹싱한다. 각 트랙에 fade_in_sec, fade_out_sec 적용.

        Args:
            tracks: 오디오 트랙 목록. sound_path, fade_in_sec, fade_out_sec 사용.
            output_path: 지정 시 해당 경로에 WAV 등으로 저장하고 경로 반환.
            duration_sec: 출력 길이(초). None이면 입력 중 최대 길이.
            sample_rate: 샘플레이트(Hz).
            channels: 채널 수.

        Returns:
            output_path가 있으면 경로(str), 없으면 PCM bytes.
        """
        valid = [t for t in tracks if t.sound_path and os.path.exists(t.sound_path)]
        if not valid:
            logger.warning("유효한 AudioTrack 없음")
            return output_path if output_path else b""

        sound_paths = [t.sound_path for t in valid]
        # 단일 트랙이면 afade만 적용; 다중 트랙이면 amix로 합침
        try:
            return self._mix_tracks_with_fade(
                valid,
                output_path=output_path,
                duration_sec=duration_sec,
                sample_rate=sample_rate,
                channels=channels,
            )
        except Exception as e:
            logger.exception("mix_from_tracks 실패: %s", e)
            return output_path if output_path else b""

    def _mix_impl(
        self,
        sound_paths: list[str],
        start_time_sec: float = 0.0,
        duration_sec: Optional[float] = None,
        output_path: Optional[str] = None,
        **kwargs: Any,
    ) -> bytes | str:
        """FFmpeg로 여러 입력을 amix한 뒤 구간 잘라내기. 출력은 파일 또는 pipe."""
        if len(sound_paths) == 1:
            # 단일 입력: -ss -t 로 구간 추출
            cmd = [
                self._ffmpeg,
                "-y",
                "-ss", str(start_time_sec),
                "-i", sound_paths[0],
            ]
            if duration_sec is not None:
                cmd.extend(["-t", str(duration_sec)])
        else:
            # 다중 입력: filter_complex amix
            inputs: list[str] = []
            for p in sound_paths:
                inputs.extend(["-i", p])
            n = len(sound_paths)
            mix_inputs = "".join(f"[{i}:a]" for i in range(n))
            filter_c = f"{mix_inputs}amix=inputs={n}:duration=longest[a]"
            cmd = [
                self._ffmpeg,
                "-y",
                *inputs,
                "-filter_complex", filter_c,
                "-map", "[a]",
                "-ss", str(start_time_sec),
            ]
            if duration_sec is not None:
                cmd.extend(["-t", str(duration_sec)])

        if output_path:
            cmd.extend(["-ac", "2", "-ar", "48000", output_path])
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            subprocess.run(cmd, check=True, capture_output=True, timeout=300, creationflags=creationflags)
            return output_path
        cmd.extend(["-f", "s16le", "-ac", "2", "-ar", "48000", "-"])
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        result = subprocess.run(cmd, capture_output=True, timeout=300, creationflags=creationflags)
        if result.returncode != 0:
            logger.warning("FFmpeg mix stderr: %s", (result.stderr or b"")[:500])
            return b""
        return result.stdout or b""

    def _mix_tracks_with_fade(
        self,
        tracks: list[AudioTrack],
        output_path: Optional[str] = None,
        duration_sec: Optional[float] = None,
        sample_rate: int = 48000,
        channels: int = 2,
    ) -> bytes | str:
        """각 트랙에 afade 적용 후 amix. 임시 파일 또는 pipe 사용."""
        inputs: list[str] = []
        for p in [t.sound_path for t in tracks]:
            inputs.extend(["-i", p])

        # [0:a]afade=t=in:st=0:d=fade_in,afade=t=out:st=...:d=fade_out[a0]; [1:a]... [a1]; ... [a0][a1]...amix[a]
        filters: list[str] = []
        for i, tr in enumerate(tracks):
            # 해당 트랙 길이를 모르므로 duration_sec 또는 999로 st= 설정. fade_out은 끝에서 d초
            fade_in = f"afade=t=in:st=0:d={tr.fade_in_sec}" if tr.fade_in_sec > 0 else ""
            fade_out = f"afade=t=out:st={duration_sec - tr.fade_out_sec if duration_sec and tr.fade_out_sec else 999}:d={tr.fade_out_sec}" if tr.fade_out_sec > 0 else ""
            parts = [p for p in [fade_in, fade_out] if p]
            label = f"[a{i}]"
            if parts:
                filters.append(f"[{i}:a]{','.join(parts)}{label}")
            else:
                filters.append(f"[{i}:a]anull{label}")
        n = len(tracks)
        mix_in = "".join(f"[a{i}]" for i in range(n))
        filters.append(f"{mix_in}amix=inputs={n}:duration=longest[a]")
        filter_complex = ";".join(filters)

        cmd = [
            self._ffmpeg,
            "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[a]",
            "-ar", str(sample_rate),
            "-ac", str(channels),
        ]
        if duration_sec is not None:
            cmd.extend(["-t", str(duration_sec)])

        if output_path:
            cmd.append(output_path)
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            subprocess.run(cmd, check=True, capture_output=True, timeout=300, creationflags=creationflags)
            return output_path
        cmd.extend(["-f", "s16le", "-"])
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        result = subprocess.run(cmd, capture_output=True, timeout=300, creationflags=creationflags)
        if result.returncode != 0:
            logger.warning("FFmpeg mix_from_tracks stderr: %s", (result.stderr or b"")[:500])
            return b""
        return result.stdout or b""