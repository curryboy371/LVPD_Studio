"""
녹화 이벤트 로그로 오디오 WAV를 생성하고 비디오와 mux.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List

from core.paths import STUDIO_MUX_EMBEDDED_AUDIO_LINEAR_GAIN
from studio.recording_events import (
    InsertSound,
    RecordingEvent,
    VideoSegmentEnd,
    VideoSegmentStart,
)

logger = logging.getLogger(__name__)

# 녹화 mux 시 이 확장자는 멀티플렉스 영상(내장 AAC 등)으로 간주.
_EMBEDDED_VIDEO_AUDIO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".wmv")


def _is_embedded_video_audio_path(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in _EMBEDDED_VIDEO_AUDIO_EXTS)


def _mux_segment_audio_role(path: str) -> str:
    """내장 영상 구간은 embedded, 동명 mp3·wav 등은 sidecar."""
    return "embedded" if _is_embedded_video_audio_path(path) else "sidecar"


def _mux_volume_prefix(role: str) -> str:
    """embedded만 STUDIO_MUX_EMBEDDED_AUDIO_LINEAR_GAIN. sidecar(MP3 등)·삽입음은 부스트 없음(디버그 재생과 레벨 맞춤, 클리핑 방지)."""
    if role == "embedded":
        g = max(0.0, min(2.0, float(STUDIO_MUX_EMBEDDED_AUDIO_LINEAR_GAIN)))
        return f"volume={g},"
    return ""


def _is_background_insert_path(path: str) -> bool:
    norm = str(path or "").replace("\\", "/").lower()
    return "/resource/sound/background/" in norm


def _preextract_embedded_audio_to_wav(
    ffmpeg_cmd: str,
    video_path: str,
    src_start: float,
    dur: float,
    out_wav: Path,
    sample_rate: int,
    creationflags: int,
) -> bool:
    """필터 그래프에서 AAC에 바로 atrim 하는 대신, 구간만 PCM으로 뽑아 디코드 품질을 올린다."""
    ss = max(0.0, float(src_start))
    t = max(0.02, float(dur))
    base = [
        ffmpeg_cmd,
        "-y",
        "-i",
        video_path,
        "-ss",
        str(ss),
        "-t",
        str(t),
        "-vn",
        "-map",
        "0:a:0",
    ]
    hq = base + [
        "-af",
        "aresample=resampler=soxr",
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]
    fb = base + [
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]
    last_err = ""
    for cmd in (hq, fb):
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
                creationflags=creationflags,
            )
        except (OSError, subprocess.SubprocessError) as e:
            last_err = str(e)
            continue
        last_err = (r.stderr or b"").decode("utf-8", errors="replace")[:400]
        if r.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 44:
            return True
    logger.warning("내장 오디오 구간 추출 실패(필터 경로로 폴백): %s — %s", video_path, last_err)
    try:
        if out_wav.exists():
            out_wav.unlink()
    except OSError:
        pass
    return False


def build_audio_and_mux(
    video_path: Path,
    recording_events: List[RecordingEvent],
    fps: float,
    duration_sec: float,
) -> None:
    """이벤트 로그로 오디오 트랙을 만들고 video_path와 합쳐 최종 MP4로 저장.
    video_path는 갱신되지 않고, 오디오가 추가된 새 파일을 video_path와 같은 디렉터리에 저장한다.
    duration_sec: 녹화 길이(초). 러너에서 target_frames/fps로 전달.
    """
    if not recording_events or duration_sec <= 0:
        return
    try:
        from utils.ffmpeg_wrapper import mux_video_audio
    except ImportError:
        return
    import tempfile
    from core.paths import FFMPEG_CMD

    with tempfile.TemporaryDirectory(prefix="lvpd_mux_") as tmp:
        tmp_path = Path(tmp)
        audio_wav = tmp_path / "audio.wav"
        _build_audio_from_events(
            recording_events, duration_sec, fps, audio_wav, ffmpeg_cmd=FFMPEG_CMD
        )
        if not audio_wav.exists():
            return
        # 출력: video_path와 같은 디렉터리, 확장자 앞에 _with_audio
        out_path = video_path.parent / f"{video_path.stem}_with_audio{video_path.suffix}"
        mux_video_audio(str(video_path), str(audio_wav), str(out_path))
        try:
            os.replace(str(out_path), str(video_path))
        except OSError as e:
            logger.warning("녹화 원본 MP4 교체 실패(_with_audio만 남음): %s", e)
            print("[audio] mux 완료(원본 유지):", out_path)
            return
        print("[audio] 녹화 MP4에 오디오 반영(원본 파일 갱신):", video_path)


def _build_audio_from_events(
    events: List[RecordingEvent],
    duration_sec: float,
    fps: float,
    output_wav: Path,
    ffmpeg_cmd: str = "ffmpeg",
) -> None:
    """이벤트 리스트를 해석해 비디오 오디오 구간 추출 + 삽입 사운드 믹싱 → 단일 WAV."""
    import subprocess
    import sys
    import tempfile
    import os

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    # 48kHz stereo WAV로 통일 (mux 시 aac 변환)
    sr, ch = 48000, 2

    # 1) 전체 길이만큼 무음 베이스 생성
    base_silence = output_wav.parent / "silence.wav"
    cmd_silence = [
        ffmpeg_cmd, "-y", "-f", "lavfi",
        "-i", f"anullsrc=r={sr}:cl=stereo:d={max(0.01, duration_sec)}",
        str(base_silence),
    ]
    subprocess.run(cmd_silence, capture_output=True, timeout=30, creationflags=creationflags)
    if not base_silence.exists():
        return

    # 2) 비디오 세그먼트: VideoSegmentStart ~ VideoSegmentEnd 구간을 해당 비디오에서 추출해 mix
    # 3) InsertSound: 해당 시점에 사운드 파일 mix
    # FFmpeg filter_complex로 하려면 복잡하므로, 간단히:
    # - 각 비디오 세그먼트에 대해: -i video -ss start -t duration → segment_N.wav
    # - 각 insert_sound에 대해: -i sound -ss 0 -t duration → insert_N.wav
    # - 그 다음 amerge/amix로 타임라인에 맞춰 합성. 더 단순하게: concat demuxer로 여러 조각을 이어붙이기.
    # 더 단순: 무음 위에 adelay+volume으로 각 소스를 올린 뒤 amix. adelay는 밀리초 단위.
    # adelay=delay_ms|delay_ms (stereo)
    # (path, output_start_sec, duration_sec, source_start_sec, audio_role)
    segments_to_mix: List[tuple[str, float, float, float, str]] = []
    current_video_path: str | None = None
    current_video_start_pts: float = 0.0
    segment_start_timeline: float = 0.0

    for ev in events:
        if isinstance(ev, VideoSegmentStart):
            current_video_path = ev.video_path
            current_video_start_pts = ev.video_pts_sec
            segment_start_timeline = ev.timeline_sec
        elif isinstance(ev, VideoSegmentEnd):
            if current_video_path and os.path.exists(current_video_path):
                dur = ev.timeline_sec - segment_start_timeline
                if dur > 0.01:
                    segments_to_mix.append(
                        (
                            current_video_path,
                            segment_start_timeline,
                            dur,
                            current_video_start_pts,
                            _mux_segment_audio_role(current_video_path),
                        )
                    )
            current_video_path = None
        elif isinstance(ev, InsertSound):
            if os.path.exists(ev.path) and ev.duration_sec > 0:
                role = "bg_insert" if _is_background_insert_path(ev.path) else "sidecar"
                segments_to_mix.append((ev.path, ev.timeline_sec, ev.duration_sec, 0.0, role))

    # 마지막 세그먼트: 녹화 끝까지 재생 중이었으면
    if current_video_path and os.path.exists(current_video_path):
        dur = duration_sec - segment_start_timeline
        if dur > 0.01:
            segments_to_mix.append(
                (
                    current_video_path,
                    segment_start_timeline,
                    dur,
                    current_video_start_pts,
                    _mux_segment_audio_role(current_video_path),
                )
            )

    if not segments_to_mix:
        # 무음만 복사
        import shutil
        shutil.copy(base_silence, output_wav)
        if base_silence.exists():
            try:
                os.remove(base_silence)
            except OSError:
                pass
        return

    # 내장 영상 오디오: 필터에서 AAC+atrim 대신 구간 PCM으로 선추출(디코드·리샘플 품질)
    resolved: List[tuple[str, float, float, float, str]] = []
    for idx, row in enumerate(segments_to_mix):
        path, start_sec, dur, src_start, role = row
        if _is_embedded_video_audio_path(path):
            seg_wav = output_wav.parent / f"preseg_{idx}.wav"
            if _preextract_embedded_audio_to_wav(
                ffmpeg_cmd, path, src_start, dur, seg_wav, sr, creationflags
            ):
                resolved.append((str(seg_wav), start_sec, dur, 0.0, "embedded"))
            else:
                resolved.append(row)
        else:
            resolved.append(row)
    segments_to_mix = resolved

    # FFmpeg으로 무음 + 각 세그먼트를 해당 시점에 mix
    # 입력: [0] silence base, [1] segment0, [2] segment1, ...
    # filter: [0] as is; [1] adelay=start0*1000|start0*1000,atrim=0:duration0,volume=1; ... then amix=inputs=N
    # 단순화: 두 개씩 mix. [0]aformat=channel_layouts=stereo[s0]; [1]adelay=...|...,atrim=0:d1,volume=1[a1]; [s0][a1]amix=inputs=2[s0]; [2]...
    # 더 단순: 무음 위에 각 오디오를 adelay+atrim 해서 덮어쓰는 방식은 amix로 가능.
    # amix = mix multiple inputs with same duration.所以我们用 apad 把每个输入 pad 到 duration_sec 然后 adelay 再 amix.
    inputs = ["-i", str(base_silence)]
    filter_parts = []
    whole_len = max(1, int(round(duration_sec * sr)))
    for idx, (path, start_sec, dur, src_start, role) in enumerate(segments_to_mix):
        inputs.extend(["-i", path])
        delay_ms = int(start_sec * 1000)
        # 선추출 WAV는 이미 구간만 담음 → atrim=0:dur. 컨테이너 직입력은 src_start~
        atrim = f"atrim={src_start}:{src_start + dur}"
        gain = _mux_volume_prefix(role)
        fade = ""
        if role == "bg_insert":
            fade_sec = min(1.0, max(0.1, dur * 0.45))
            out_start = max(0.0, dur - fade_sec)
            fade = f"afade=t=in:st=0:d={fade_sec},afade=t=out:st={out_start}:d={fade_sec},"
        filter_parts.append(
            f"[{idx + 1}:a]{atrim},{gain}{fade}adelay={delay_ms}|{delay_ms},"
            f"apad=whole_len={whole_len}[a{idx}]"
        )
    # [0][a0][a1]...amix → aformat 체인으로 [aout]까지 연결
    n_seg = len(segments_to_mix)
    mix_inputs = "[0]" + "".join(f"[a{i}]" for i in range(n_seg))
    # normalize=0: 무음 베이스+음성 합성 시 음성이 1/N로 죽지 않게 한다.
    filter_parts.append(
        f"{mix_inputs}amix=inputs={n_seg + 1}:duration=longest:normalize=0[mixraw]"
    )
    filter_parts.append("[mixraw]aformat=sample_fmts=s16:channel_layouts=stereo[aout]")
    filter_str = ";".join(filter_parts)

    cmd = [ffmpeg_cmd, "-y"] + inputs + ["-filter_complex", filter_str, "-map", "[aout]", "-ac", str(ch), "-ar", str(sr), str(output_wav)]
    r = subprocess.run(cmd, capture_output=True, timeout=120, creationflags=creationflags)
    if r.returncode != 0 or not output_wav.exists():
        err = (r.stderr or b"").decode("utf-8", errors="replace")[:1200]
        logger.warning("recorded_audio_mux FFmpeg 실패(rc=%s): %s", r.returncode, err)

    try:
        if base_silence.exists():
            os.remove(base_silence)
    except OSError:
        pass
