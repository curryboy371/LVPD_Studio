"""
녹화 이벤트 로그로 오디오 WAV를 생성하고 비디오와 mux.
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import List

from studio.recording_events import (
    InsertSound,
    RecordingEvent,
    VideoSegmentEnd,
    VideoSegmentStart,
)


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
        print("⏹️ 오디오 mux 완료:", out_path)


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
    # (path, output_start_sec, duration_sec, source_start_sec) — 비디오는 source_start_sec부터 추출, insert는 0
    segments_to_mix: List[tuple[str, float, float, float]] = []
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
                    segments_to_mix.append((
                        current_video_path,
                        segment_start_timeline,
                        dur,
                        current_video_start_pts,
                    ))
            current_video_path = None
        elif isinstance(ev, InsertSound):
            if os.path.exists(ev.path) and ev.duration_sec > 0:
                segments_to_mix.append((ev.path, ev.timeline_sec, ev.duration_sec, 0.0))

    # 마지막 세그먼트: 녹화 끝까지 재생 중이었으면
    if current_video_path and os.path.exists(current_video_path):
        dur = duration_sec - segment_start_timeline
        if dur > 0.01:
            segments_to_mix.append((
                current_video_path,
                segment_start_timeline,
                dur,
                current_video_start_pts,
            ))

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

    # FFmpeg으로 무음 + 각 세그먼트를 해당 시점에 mix
    # 입력: [0] silence base, [1] segment0, [2] segment1, ...
    # filter: [0] as is; [1] adelay=start0*1000|start0*1000,atrim=0:duration0,volume=1; ... then amix=inputs=N
    # 단순화: 두 개씩 mix. [0]aformat=channel_layouts=stereo[s0]; [1]adelay=...|...,atrim=0:d1,volume=1[a1]; [s0][a1]amix=inputs=2[s0]; [2]...
    # 더 단순: 무음 위에 각 오디오를 adelay+atrim 해서 덮어쓰는 방식은 amix로 가능.
    # amix = mix multiple inputs with same duration.所以我们用 apad 把每个输入 pad 到 duration_sec 然后 adelay 再 amix.
    inputs = ["-i", str(base_silence)]
    filter_parts = []
    for idx, (path, start_sec, dur, src_start) in enumerate(segments_to_mix):
        inputs.extend(["-i", path])
        delay_ms = int(start_sec * 1000)
        # 비디오는 src_start부터 dur만큼 추출. atrim=start:end (초)
        atrim = f"atrim={src_start}:{src_start + dur}"
        filter_parts.append(
            f"[{idx + 1}]{atrim},adelay={delay_ms}|{delay_ms},apad=whole_len={int(duration_sec * sr)}[a{idx}]"
        )
    # [0][a0][a1]...amix=inputs=N
    n_seg = len(segments_to_mix)
    mix_inputs = "[0]" + "".join(f"[a{i}]" for i in range(n_seg))
    filter_parts.append(f"{mix_inputs}amix=inputs={n_seg + 1}:duration=longest[aout]")
    filter_parts.append("[aout]aformat=sample_fmts=s16:channel_layouts=stereo")
    filter_str = ";".join(filter_parts)

    cmd = [ffmpeg_cmd, "-y"] + inputs + ["-filter_complex", filter_str, "-map", "[aout]", "-ac", str(ch), "-ar", str(sr), str(output_wav)]
    subprocess.run(cmd, capture_output=True, timeout=60, creationflags=creationflags)

    try:
        if base_silence.exists():
            os.remove(base_silence)
    except OSError:
        pass
