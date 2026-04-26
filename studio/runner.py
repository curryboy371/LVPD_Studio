"""
공통 스튜디오 러너: pygame 초기화, 창/Config/녹화/Clock 관리, IStudio 구현체 실행.
- debug: 화면 출력만, 녹화 없음 (상태/타이밍/UI/인터랙션 확인).
- record: 오프스크린 버퍼만 렌더링 후 프레임 인코딩 (품질·결정론·프레임 정확성).
"""
from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Literal, Optional

try:
    import numpy as np
except ImportError:
    np = None

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.interfaces import IStudio
from core.paths import (
    DEFAULT_BASE_SENTENCES_CSV,
    DEFAULT_SUB_SENTENCES_CSV,
    DEFAULT_WORDS_TABLE_CSV,
    STUDIO_FPS,
    STUDIO_HEIGHT,
    STUDIO_WIDTH,
)
from data.table_manager import (
    get_loaded_content,
    get_table,
    set_table,
    load_base_sentences_from_csv,
    load_sub_sentences_from_csv,
    load_words_table_from_csv,
    get_table_rows,
)


# ----- 공통 인프라 -----


class StudioConfig:
    """해상도·좌표 변환. 디버그 모드에서 dt_sec, actual_fps 등이 매 프레임 설정됨."""
    def __init__(self, width: int = STUDIO_WIDTH, height: int = STUDIO_HEIGHT, fps: int = STUDIO_FPS):
        """창/버퍼 크기, FPS, 배경색, 기본 dt를 설정한다."""
        self.width = width
        self.height = height
        self.fps = fps
        self.bg_color = (20, 20, 25)
        self.dt_sec: float = 1.0 / float(fps)
        self.actual_fps: float = 0.0

    def get_pos(self, rx: float, ry: float) -> tuple[int, int]:
        """0.0~1.0 비율 좌표를 절대 좌표로."""
        return (int(self.width * rx), int(self.height * ry))

    def get_size(self, rw: float, rh: float) -> tuple[int, int]:
        """비율 크기를 절대 크기로."""
        return (int(self.width * rw), int(self.height * rh))


class SimpleRecordingManager:
    """녹화: 프레임 큐 + 스레드에서 비디오만 저장 (opencv). 프레임 드랍 방지를 위해 블로킹 put 사용."""
    # put() 대기 최대 시간(초). writer가 느릴 때 메인 루프가 이만큼만 대기.
    _PUT_TIMEOUT_SEC = 30.0

    def __init__(self, output_dir: str | Path | None = None):
        """출력 디렉터리를 만들고 녹화 상태·큐·스레드 핸들을 초기화한다."""
        self.output_dir = Path(output_dir or _REPO_ROOT / "release")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.is_recording = False
        self._frame_queue: queue.Queue | None = None
        self._thread: threading.Thread | None = None
        self._fps = float(STUDIO_FPS)
        self._size = (STUDIO_WIDTH, STUDIO_HEIGHT)
        self._last_video_path: Optional[Path] = None

    def start(self, filename_prefix: str = "rec", fps: float = STUDIO_FPS, size: tuple[int, int] = (STUDIO_WIDTH, STUDIO_HEIGHT)) -> None:
        """프레임 큐와 writer 스레드를 시작해 녹화 상태로 만든다."""
        if self.is_recording:
            return
        self._fps = fps
        self._size = size
        # 큐 크기 확대: 프레임 드랍 가능성 감소 (최소 10초치 + 여유)
        max_q = max(120, int(fps * 12))
        self._frame_queue = queue.Queue(maxsize=max_q)
        self.is_recording = True
        self._thread = threading.Thread(
            target=self._record_loop,
            args=(filename_prefix,),
            daemon=True,
        )
        self._thread.start()

    def submit_frame(self, frame_rgb) -> None:
        """RGB 프레임을 큐에 넣어 백그라운드 인코더가 소비하게 한다."""
        if not self.is_recording or self._frame_queue is None or np is None:
            return
        frame = np.asarray(frame_rgb, dtype=np.uint8)
        try:
            self._frame_queue.put(frame, timeout=self._PUT_TIMEOUT_SEC)
        except queue.Full:
            # 타임아웃 후에도 Full이면 프레임 보존 우선으로 한 번 더 시도 후 포기
            try:
                self._frame_queue.put(frame, timeout=5.0)
            except queue.Full:
                pass

    def stop(self) -> None:
        """녹화 플래그를 내리고 writer 스레드가 끝날 때까지 대기한다."""
        self.is_recording = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        self._frame_queue = None

    def _record_loop(self, filename_prefix: str) -> None:
        """스레드 진입점: 비디오만 파일로 저장한다."""
        try:
            self._record_video_only(filename_prefix)
        except Exception as e:
            print("[!] 녹화 저장 중 오류:", e)

    def _record_video_only(self, filename_prefix: str) -> None:
        """큐에서 프레임을 꺼내 OpenCV VideoWriter로 MP4를 쓴다."""
        try:
            import cv2
        except ImportError:
            print("[!] opencv-python 없음. 녹화 비디오 저장을 건너뜁니다.")
            return
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"{filename_prefix}_{stamp}.mp4"
        w, h = self._size[0], self._size[1]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(path), fourcc, self._fps, (w, h))
        try:
            while self.is_recording and self._frame_queue is not None:
                try:
                    frame = self._frame_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if frame.shape[0] != h or frame.shape[1] != w:
                    frame = cv2.resize(frame, (w, h))
                bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(bgr)
        finally:
            while self._frame_queue and not self._frame_queue.empty():
                try:
                    frame = self._frame_queue.get_nowait()
                    if frame.shape[0] != h or frame.shape[1] != w:
                        frame = cv2.resize(frame, (w, h))
                    out.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                except queue.Empty:
                    break
            out.release()
        self._last_video_path = path
        print("[rec] 녹화 저장:", path)

    def get_last_video_path(self) -> Optional[Path]:
        """녹화 종료 후 저장된 비디오 파일 경로. 오디오 mux 전에 사용."""
        return getattr(self, "_last_video_path", None)


def _parse_conversation_font_sizes(text: str) -> Any:
    """`cn_big,cn,step1_hanzi,step1_pinyin,kr,kr_step1` 여섯 크기."""
    from studio.conversation.tools.fonts import ConversationFontSizes

    parts = [int(x.strip()) for x in text.split(",")]
    if len(parts) != 6:
        raise ValueError(
            "폰트 크기 6개 필요: cn_big,cn,cn_step1_hanzi,cn_step1_pinyin,kr,kr_step1 "
            "(예: 36,28,124,66,28,56)"
        )
    return ConversationFontSizes(
        cn_big=parts[0],
        cn=parts[1],
        cn_step1_hanzi=parts[2],
        cn_step1_pinyin=parts[3],
        kr=parts[4],
        kr_step1=parts[5],
    )


def _conversation_render_from_cli_args(args: Any) -> Optional[Any]:
    """CLI에서 `--font-sizes`가 있으면 `ConversationRenderSettings` 생성."""
    from studio.conversation.tools.fonts import ConversationRenderSettings

    if args.font_sizes is None:
        return None
    return ConversationRenderSettings(font_sizes=args.font_sizes)


def run(
    studio: IStudio,
    mode: Literal["debug", "record"] = "debug",
    record_duration: float = 10.0,
    record_frames: Optional[int] = None,
    *,
    conversation_render: Optional[Any] = None,
) -> None:
    """IStudio 실행. debug=화면만(녹화 없음), record=오프스크린 버퍼→인코딩만.

    conversation 스튜디오: `conversation_render`(`ConversationRenderSettings`)를
    `config.conversation_render`로 넘기면 폰트 크기가 적용된다. 색은 스튜디오 `load_font_*` 인자로만 지정한다.
    """
    if mode == "record":
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame

    pygame.init()
    config = StudioConfig(STUDIO_WIDTH, STUDIO_HEIGHT, STUDIO_FPS)
    if conversation_render is not None:
        config.conversation_render = conversation_render
    clock = pygame.time.Clock()
    studio.init(config)

    if mode == "debug":
        _run_debug(studio, config, clock, pygame)
    else:
        _run_record(studio, config, clock, pygame, record_duration, record_frames)
    pygame.quit()


def _run_debug(studio: IStudio, config: StudioConfig, clock, pygame) -> None:
    """디버그 모드: 창에만 출력, 녹화 없음. FPS 등 디버그 정보는 config에 설정됨."""
    screen = pygame.display.set_mode((config.width, config.height))
    pygame.display.set_caption(studio.get_title())

    running = True
    while running:
        config.dt_sec = clock.get_time() / 1000.0 if clock.get_time() > 0 else 1.0 / config.fps
        config.actual_fps = clock.get_fps()

        events = list(pygame.event.get())
        for e in events:
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                running = False
                break
        if not running:
            break
        if not studio.handle_events(events, config):
            running = False
            break
        studio.update(config)
        studio.draw(screen, config)
        pygame.display.flip()
        clock.tick(config.fps)


def _run_record(
    studio: IStudio,
    config: StudioConfig,
    clock,
    pygame,
    record_duration: float,
    record_frames: Optional[int],
) -> None:
    """녹화 모드: 오프스크린 버퍼만 렌더링 후 인코딩, 창 없음. 타임라인 기준 오디오 이벤트 수집 후 사후 mux."""
    pygame.display.set_mode((1, 1))  # 최소 디스플레이 (폰트 등 동작용)
    buffer = pygame.Surface((config.width, config.height))
    recorder = SimpleRecordingManager()
    prefix = studio.get_recording_prefix() or "rec"
    recorder.start(prefix, float(config.fps), (config.width, config.height))

    # 녹화 타임라인: 0 기준, 매 프레임 현재 시간 전달. 오디오 이벤트 로그 수집.
    recording_events: list = []
    config.recording_time_sec = 0.0
    config.recording_log_event = lambda ev: recording_events.append(ev)

    target_frames = (
        record_frames
        if record_frames is not None
        else int(record_duration * config.fps)
    )

    try:
        for frame_index in range(target_frames):
            config.dt_sec = 1.0 / config.fps
            config.recording_time_sec = frame_index / config.fps
            studio.handle_events([], config)
            studio.update(config)
            studio.draw(buffer, config)
            if np is not None:
                buf = pygame.surfarray.array3d(buffer)
                frame = np.transpose(buf, (1, 0, 2))
                recorder.submit_frame(frame)
            clock.tick(config.fps)
    finally:
        recorder.stop()
        config.recording_log_event = None
        config.recording_time_sec = 0.0

    print("[rec] 녹화 완료:", target_frames, "프레임")
    video_path = recorder.get_last_video_path()
    duration_sec = target_frames / config.fps
    if video_path is not None and recording_events:
        print("[audio] 녹화 오디오 분리: 이벤트", len(recording_events), "개 -> WAV 생성 후 mux")
        _mux_recorded_audio(video_path, recording_events, config.fps, duration_sec)
    elif video_path is not None and not recording_events:
        print("[!] 녹화 오디오 mux 건너뜀: 오디오 이벤트 없음 (스튜디오에서 이벤트 로그 필요)")


def _mux_recorded_audio(
    video_path: Path,
    recording_events: list,
    fps: int,
    duration_sec: float,
) -> None:
    """녹화 이벤트 로그로 오디오 WAV 생성 후 비디오와 mux. 실패 시 경고만 출력."""
    try:
        from studio.recorded_audio_mux import build_audio_and_mux
        build_audio_and_mux(video_path, recording_events, float(fps), duration_sec)
    except Exception as e:
        print("[!] 녹화 오디오 mux 건너뜀:", e)


def _create_studio(
    name: str,
    csv_path: str | None,
    content: Optional[Any] = None,
    **kwargs,
) -> IStudio:
    """이름에 맞는 IStudio 인스턴스를 만든다(conversation / vocabulary)."""
    if name == "conversation":
        from studio.conversation import ConversationStudio
        return ConversationStudio(
            csv_path=csv_path or "",
            content=content,
            **kwargs,
        )
    if name == "vocabulary":
        from studio.studios.vocabulary import VocabularyStudio
        return VocabularyStudio(**kwargs)
    raise ValueError(f"알 수 없는 스튜디오: {name}")


def main() -> None:
    """CLI 인자 파싱 후 콘텐츠 로드·스튜디오 생성·run() 호출."""
    parser = argparse.ArgumentParser(description="LVPD 스튜디오 러너 (IStudio 구현체 실행)")
    parser.add_argument(
        "--studio",
        type=str,
        default="conversation",
        choices=("conversation", "vocabulary"),
        help="실행할 스튜디오 (기본: conversation)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="",
        help="CSV 파일 경로 (conversation 스튜디오용). 비우면 기본 경로 사용.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="debug",
        choices=("debug", "record"),
        help="실행 모드: debug=화면 출력만(녹화 없음), record=오프스크린 녹화만.",
    )
    parser.add_argument(
        "--record-duration",
        type=float,
        default=10.0,
        help="녹화 모드에서 녹화할 시간(초). --record-frames 지정 시 무시.",
    )
    parser.add_argument(
        "--record-frames",
        type=int,
        default=None,
        metavar="N",
        help="녹화 모드에서 녹화할 프레임 수. 지정 시 --record-duration 무시.",
    )

    def _font_sizes_arg(s: str) -> Any:
        try:
            return _parse_conversation_font_sizes(s)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e)) from e

    parser.add_argument(
        "--font-sizes",
        type=_font_sizes_arg,
        default=None,
        metavar="A,B,C,D,E,F",
        help=(
            "conversation: 폰트 pt 6개 (쉼표): cn_big,cn,cn_step1_hanzi,cn_step1_pinyin,kr,kr_step1 "
            "예: 36,28,124,66,28,56"
        ),
    )
    args = parser.parse_args()

    csv_path: str | None = (args.csv or "").strip() or None
    if args.studio == "conversation":
        load_base_sentences_from_csv(DEFAULT_BASE_SENTENCES_CSV)
        load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
        load_sub_sentences_from_csv(DEFAULT_SUB_SENTENCES_CSV)
        set_table(get_table_rows())
        content = get_loaded_content() if get_table() else None
        if not content or (not content.video_segments and not content.overlay_items):
            print("콘텐츠가 없습니다. create_all_csv.bat으로 CSV를 생성한 뒤 resource/csv/ 를 확인하세요.", file=sys.stderr)
            sys.exit(1)
    else:
        content = None

    studio = _create_studio(args.studio, csv_path or "", content=content)
    run(
        studio,
        mode=args.mode,
        record_duration=args.record_duration,
        record_frames=args.record_frames,
        conversation_render=_conversation_render_from_cli_args(args),
    )


if __name__ == "__main__":
    main()
