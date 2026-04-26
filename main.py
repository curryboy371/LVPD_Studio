"""
단일 진입점. 명령별 실행:

  python main.py studio  → 스튜디오 (디버그: 집계 단어 화면부터). 기본 topic은 fruit store. --mode record 로 오프스크린 녹화
  python main.py batch   → CSV 기반 배치 렌더 → output/ 저장

테이블 CSV 생성은 배치 파일에서만 실행 (create_all_csv.bat → run_create_new_tables_csv.py).
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from core.paths import (
    DEFAULT_OUTPUT_DIR,
    FFMPEG_CMD,
    RENDER_FPS,
    RENDER_HEIGHT,
    RENDER_WIDTH,
)

if TYPE_CHECKING:
    from core.interfaces import IAudioMixer, IVideoRenderer
    from data.models import LoadedContent, VideoSegment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# `python main.py studio` / F5: `--topic` 생략 시 사용. CSV의 topic·vocabulary_word_rows.topic과 동일한 문자열이어야 한다.
DEFAULT_STUDIO_TOPIC = "fruit_store"

# =============================================================================
# 배치 파이프라인: 영상 길이·렌더·mux
# =============================================================================

def _get_video_duration_sec(file_path: str | Path) -> float:
    """영상 파일 재생 길이(초). 실패 시 0.0. end_time=-1(끝까지)일 때 사용."""
    path = Path(file_path)
    if not path.exists():
        return 0.0
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True,
            timeout=10,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
        if result.returncode == 0 and result.stdout:
            return max(0.0, float(result.stdout.strip()))
    except Exception:
        pass
    return 0.0


def _effective_end_time(seg: "VideoSegment") -> float:
    """세그먼트의 실제 종료 시각(초). end_time이 -1이면 영상 길이까지."""
    from data.models import VideoSegment
    seg = seg if isinstance(seg, VideoSegment) else seg
    if seg.end_time < 0:
        duration = _get_video_duration_sec(seg.file_path)
        return seg.start_time + duration if duration > 0 else seg.start_time
    return seg.end_time


def _render_content_to_video(
    renderer: "IVideoRenderer",
    content: "LoadedContent",
    output_path: str | Path,
    width: int = RENDER_WIDTH,
    height: int = RENDER_HEIGHT,
    fps: int = RENDER_FPS,
) -> str:
    """LoadedContent의 segment/overlay 쌍으로 프레임을 생성해 FFmpeg으로 인코딩한 비디오 파일을 만든다."""
    from data.models import LoadedContent
    segments = content.video_segments
    overlays = content.overlay_items
    n = min(len(segments), len(overlays))

    ffmpeg_cmd = FFMPEG_CMD
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if n == 0:
        # 세그먼트 없으면 1초 검정 영상 생성
        cmd = [
            ffmpeg_cmd, "-y",
            "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d=1",
            "-r", str(fps),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        subprocess.run(cmd, capture_output=True, timeout=60, creationflags=creationflags, check=True)
        return str(out_path.resolve())

    # 한 번에 모든 프레임을 pipe로 FFmpeg에 전달
    cmd = [
        ffmpeg_cmd, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    assert proc.stdin is not None
    try:
        frame_dt = 1.0 / fps
        for i in range(n):
            seg = segments[i]
            ov = overlays[i]
            start = seg.start_time
            end = _effective_end_time(seg)
            if end <= start:
                continue
            duration_sec = end - start
            num_frames = max(0, int(round(duration_sec * fps)))
            for k in range(num_frames):
                t = start + k * frame_dt
                frame = renderer.render_frame(
                    timestamp_sec=t,
                    width=width,
                    height=height,
                    segment=seg,
                    overlay=ov,
                )
                proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
    _, stderr = proc.communicate(timeout=600)
    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"비디오 인코딩 실패 (코드 {proc.returncode}): {err}")
    return str(out_path.resolve())


def run_pipeline(
    renderer: "IVideoRenderer",
    mixer: "IAudioMixer",
    content: "LoadedContent",
    output_dir: str | Path,
    width: int = RENDER_WIDTH,
    height: int = RENDER_HEIGHT,
    fps: int = RENDER_FPS,
) -> str:
    """배치 전용: CSV 로드 콘텐츠를 렌더 → 오디오 믹싱 → mux 후 output_dir에 저장.

    비디오는 세그먼트별로만 렌더한다. 전체 재생시간을 따로 계산하지 않음.
    오디오/무음 길이는 비디오 세그먼트 합산으로만 결정(FFmpeg용).

    Returns:
        최종 저장된 MP4 파일 경로.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    segments = content.video_segments
    overlays = content.overlay_items
    n = min(len(segments), len(overlays))
    # 오디오/무음 출력 길이용 (FFmpeg anullsrc 등은 양수만 허용)
    if n > 0:
        audio_duration_sec = sum(
            max(0.0, _effective_end_time(segments[i]) - segments[i].start_time) for i in range(n)
        )
    else:
        audio_duration_sec = 0.0
    if audio_duration_sec <= 0:
        audio_duration_sec = 1.0

    with tempfile.TemporaryDirectory(prefix="lvpd_") as tmp:
        tmp_path = Path(tmp)
        temp_video = tmp_path / "video.mp4"
        temp_audio = tmp_path / "audio.wav"

        logger.info("비디오 렌더링 중...")
        video_path = _render_content_to_video(
            renderer, content, temp_video, width=width, height=height, fps=fps
        )

        logger.info("오디오 믹싱 중...")
        mixer.mix_from_tracks(
            content.audio_tracks,
            output_path=str(temp_audio),
            duration_sec=audio_duration_sec,
        )

        if not temp_audio.exists():
            # 오디오 파일이 없으면 무음 생성 (mux 필수, d는 양수만 허용)
            silence_duration = max(0.01, audio_duration_sec)
            logger.info("오디오 없음, 무음 생성 중... (%.2fs)", silence_duration)
            cmd = [
                FFMPEG_CMD, "-y",
                "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={silence_duration}",
                str(temp_audio),
            ]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            subprocess.run(cmd, capture_output=True, timeout=30, creationflags=creationflags, check=True)

        final_path = output_dir / "rendered.mp4"
        logger.info("비디오·오디오 합성 중: %s", final_path)
        from utils.ffmpeg_wrapper import mux_video_audio
        mux_video_audio(video_path, str(temp_audio), final_path)
    return str(final_path.resolve())


# =============================================================================
# 콘텐츠 테이블 생성 (studio / batch 공통)
# =============================================================================


def generate_content_table(content_label: str = "new tables") -> "LoadedContent":
    """콘텐츠 테이블 생성. table_manager에 저장된 테이블로 LoadedContent 생성 (테이블 로드 후 set_table 호출 필요)."""
    from data.table_manager import get_loaded_content, get_table

    rows = get_table()
    if not rows:
        return LoadedContent()
    content = get_loaded_content()
    n_seg = len(content.video_segments)
    n_ov = len(content.overlay_items)
    n_aud = len(content.audio_tracks)
    logger.info("테이블 생성: %s → 세그먼트 %d, 오버레이 %d, 오디오 %d", content_label, n_seg, n_ov, n_aud)
    return content


# =============================================================================
# 명령 핸들러: studio / extract-audio / batch
# =============================================================================


def _cmd_studio(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """스튜디오: 신규 테이블 CSV 로드 후 `studio.runner.run` (debug 또는 record)."""
    from core.paths import (
        DEFAULT_BASE_SENTENCES_CSV,
        DEFAULT_SUB_SENTENCES_CSV,
        DEFAULT_VOCABULARY_WORD_ROWS_CSV,
        DEFAULT_WORDS_TABLE_CSV,
    )
    from data.table_manager import (
        load_base_sentences_from_csv,
        load_sub_sentences_from_csv,
        load_vocabulary_word_rows_from_csv,
        load_words_table_from_csv,
        get_table_rows,
    )
    from data.table_manager import set_table
    from studio.runner import (
        run,
        _create_studio,
        _conversation_render_from_cli_args,
        _parse_session_topics_arg,
    )

    load_base_sentences_from_csv(DEFAULT_BASE_SENTENCES_CSV)
    load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
    load_sub_sentences_from_csv(DEFAULT_SUB_SENTENCES_CSV)
    load_vocabulary_word_rows_from_csv(DEFAULT_VOCABULARY_WORD_ROWS_CSV)
    set_table(get_table_rows())

    content = generate_content_table("new tables")
    if not content.video_segments and not content.overlay_items:
        logger.error("콘텐츠가 없습니다. create_all_csv.bat으로 CSV를 생성한 뒤 resource/csv/ 에 base_sentences.csv 등이 있는지 확인하세요.")
        sys.exit(1)
    # F5 / `python main.py studio`: 디버깅용으로 집계 단어(voca) 화면부터 시작(회화 생략)
    session_topics = _parse_session_topics_arg(getattr(args, "topic", "") or "")
    studio = _create_studio(
        "conversation_then_words",
        "",
        content=content,
        debug_start_in_words_phase=True,
        **({"session_topics": session_topics} if session_topics else {}),
    )
    run(
        studio,
        mode=args.mode,
        record_duration=args.record_duration,
        record_frames=args.record_frames,
        conversation_render=_conversation_render_from_cli_args(args),
        record_until_content_done=bool(args.record_until_content_done),
        record_max_sec=float(args.record_max_sec),
    )


def _cmd_batch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """배치 모드: 신규 테이블 로드 → 렌더 → mux → output/ 저장."""
    from core.paths import (
        DEFAULT_BASE_SENTENCES_CSV,
        DEFAULT_SUB_SENTENCES_CSV,
        DEFAULT_VOCABULARY_WORD_ROWS_CSV,
        DEFAULT_WORDS_TABLE_CSV,
    )
    from data.table_manager import (
        load_base_sentences_from_csv,
        load_sub_sentences_from_csv,
        load_vocabulary_word_rows_from_csv,
        load_words_table_from_csv,
        get_table_rows,
    )
    from data.table_manager import set_table
    from core.interfaces import IAudioMixer, IVideoRenderer

    load_base_sentences_from_csv(DEFAULT_BASE_SENTENCES_CSV)
    load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
    load_sub_sentences_from_csv(DEFAULT_SUB_SENTENCES_CSV)
    load_vocabulary_word_rows_from_csv(DEFAULT_VOCABULARY_WORD_ROWS_CSV)
    set_table(get_table_rows())

    content = generate_content_table("new tables")
    if not content.video_segments and not content.overlay_items:
        logger.warning("콘텐츠가 없습니다. create_all_csv.bat으로 CSV를 생성하세요.")
        return
    from video.renderer import FFmpegSegmentOverlayRenderer
    from audio.mixer import FFmpegAudioMixer
    renderer: IVideoRenderer = FFmpegSegmentOverlayRenderer()
    mixer: IAudioMixer = FFmpegAudioMixer()
    output_dir = (args.output_dir or str(DEFAULT_OUTPUT_DIR)).strip() or "output"
    final_path = run_pipeline(
        renderer=renderer,
        mixer=mixer,
        content=content,
        output_dir=output_dir,
    )
    print("파이프라인 완료. 출력 파일:", final_path)


# =============================================================================
# main: subparser 등록 → parse → 선택된 cmd에 따라 args.func(parser, args) 호출
# =============================================================================


def _add_studio_parser(subparsers: argparse._SubParsersAction) -> None:
    from studio.runner import _parse_conversation_font_sizes

    p = subparsers.add_parser(
        "studio",
        help="스튜디오: 화면(debug) 또는 오프스크린 녹화(record). CSV 로드는 runner와 동일.",
    )
    p.set_defaults(func=_cmd_studio)
    p.add_argument(
        "--mode",
        type=str,
        default="debug",
        choices=("debug", "record"),
        help="debug=창 출력만, record=오프스크린 MP4( release/ )",
    )
    p.add_argument(
        "--record-duration",
        type=float,
        default=10.0,
        help="record 모드: 녹화 시간(초). --record-frames 지정 시 무시.",
    )
    p.add_argument(
        "--record-frames",
        type=int,
        default=None,
        metavar="N",
        help="record 모드: 프레임 수. 지정 시 --record-duration 무시.",
    )
    p.add_argument(
        "--record-until-content-done",
        action="store_true",
        help="record: 마지막 아이템·마지막 장면까지 끝나면 종료. 상한은 --record-max-sec.",
    )
    p.add_argument(
        "--record-max-sec",
        type=float,
        default=3600.0,
        help="--record-until-content-done 시 루프 상한(초). 기본 3600.",
    )

    def _font_sizes_arg(s: str) -> object:
        try:
            return _parse_conversation_font_sizes(s)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e)) from e

    p.add_argument(
        "--font-sizes",
        type=_font_sizes_arg,
        default=None,
        metavar="A,B,C,D,E,F",
        help=(
            "conversation: 폰트 pt 6개: cn_big,cn,cn_step1_hanzi,cn_step1_pinyin,kr,kr_step1 "
            "(예: 36,28,124,66,28,56)"
        ),
    )
    p.add_argument(
        "--topic",
        type=str,
        default=DEFAULT_STUDIO_TOPIC,
        metavar="TOPIC",
        help=(
            "회화+단어 디버그: topic이 일치하는 회화 항목·vocabulary_word_rows만 사용. "
            f"기본값: {DEFAULT_STUDIO_TOPIC!r}. 여러 개는 쉼표 또는 |."
        ),
    )


def _add_batch_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("batch", help="신규 테이블 CSV 기반 배치 영상 제작 → output/")
    p.add_argument("--csv", type=str, default="", help="(미사용, 호환용)")
    p.add_argument("--output-dir", type=str, default="", help="출력 디렉터리. 비우면 output.")
    p.set_defaults(func=_cmd_batch)


def main() -> None:
    parser = argparse.ArgumentParser(description="LVPD: studio / batch")
    subparsers = parser.add_subparsers(dest="cmd", required=True, help="실행 모드")

    _add_studio_parser(subparsers)
    _add_batch_parser(subparsers)

    args = parser.parse_args()
    args.func(parser, args)


if __name__ == "__main__":
    main()
