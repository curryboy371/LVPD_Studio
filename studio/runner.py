"""
공통 스튜디오 러너: pygame 초기화, 창/Config/녹화/Clock 관리, IStudio 구현체 실행.
- debug: 화면 출력만, 녹화 없음 (상태/타이밍/UI/인터랙션 확인).
- record: 오프스크린 버퍼만 렌더링 후 프레임 인코딩 (품질·결정론·프레임 정확성).
"""
from __future__ import annotations

import argparse
import logging
import os
import queue
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)
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
    DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV,
    DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV,
    DEFAULT_SUB_SENTENCES_CSV,
    DEFAULT_VOCABULARY_WORD_ROWS_CSV,
    DEFAULT_WORDS_TABLE_CSV,
    SHORTS_HEIGHT,
    SHORTS_WIDTH,
    STUDIO_FPS,
    STUDIO_HEIGHT,
    STUDIO_WIDTH,
)
from data.table_manager import (
    get_base_sentences,
    get_loaded_content,
    get_table,
    set_table,
    load_base_sentences_from_csv,
    load_sub_sentences_from_csv,
    load_vocabulary_word_rows_from_csv,
    load_words_table_from_csv,
    get_table_rows,
    select_all_vocabulary_word_rows,
    select_vocabulary_word_rows_for_session_topics,
)


# ----- 공통 인프라 -----


def _ensure_mixer_ready(pygame, *, context: str = "스튜디오") -> None:
    """display 준비 후 mixer·채널을 점검한다."""
    from core.paths import STUDIO_AUDIO_SAMPLE_RATE

    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
        pygame.mixer.set_num_channels(8)
    except Exception as e:
        raise RuntimeError(
            f"{context} 오디오 초기화 실패: pygame.mixer를 사용할 수 없습니다. "
            "오디오 장치/드라이버 설정을 확인하세요."
        ) from e
    if pygame.mixer.get_init() is None:
        raise RuntimeError(f"{context} 오디오 초기화 실패: mixer가 비활성 상태입니다.")


def _ensure_record_audio_ready(pygame) -> None:
    """record 시작 전에 mixer를 강제 점검하고, 실패 시 즉시 예외를 올린다."""
    _ensure_mixer_ready(pygame, context="녹화 모드")


def _ensure_debug_audio_ready(pygame) -> None:
    """debug 창 표시 직후 mixer를 다시 점검한다(set_mode 이후 재생용)."""
    _ensure_mixer_ready(pygame, context="디버그 모드")


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
        # False면 ConversationStudio 등에서 FPS/PTS 등 화면 디버그 오버레이를 그리지 않음(녹화 모드용).
        self.show_debug_overlay: bool = True

    def get_pos(self, rx: float, ry: float) -> tuple[int, int]:
        """0.0~1.0 비율 좌표를 절대 좌표로."""
        return (int(self.width * rx), int(self.height * ry))

    def get_size(self, rw: float, rh: float) -> tuple[int, int]:
        """비율 크기를 절대 크기로."""
        return (int(self.width * rw), int(self.height * rh))


class SimpleRecordingManager:
    """녹화: 프레임을 OpenCV VideoWriter에 즉시 저장한다."""
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
        self._cv2: Any = None
        self._writer: Any = None
        # 디스크/코덱 지연으로 메인 루프가 막히지 않게 비동기 프레임 큐를 사용한다.
        self._queue_maxsize = 240
        self._submitted_frames = 0
        self._encoded_frames = 0
        self._dropped_frames = 0

    def start(self, filename_prefix: str = "rec", fps: float = STUDIO_FPS, size: tuple[int, int] = (STUDIO_WIDTH, STUDIO_HEIGHT)) -> None:
        """VideoWriter를 열고 녹화 상태로 전환한다."""
        if self.is_recording:
            return
        try:
            import cv2
        except ImportError:
            print("[!] opencv-python 없음. 녹화 비디오 저장을 건너뜁니다.")
            return
        from datetime import datetime

        self._fps = fps
        self._size = size
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"{filename_prefix}_{stamp}.mp4"
        w, h = self._size[0], self._size[1]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(path), fourcc, self._fps, (w, h))
        if not writer.isOpened():
            print("[!] OpenCV VideoWriter 열기 실패:", path)
            return
        self._cv2 = cv2
        self._writer = writer
        self._last_video_path = path
        self._submitted_frames = 0
        self._encoded_frames = 0
        self._dropped_frames = 0
        self._frame_queue = queue.Queue(maxsize=max(8, int(self._queue_maxsize)))
        self.is_recording = True
        self._thread = threading.Thread(target=self._record_loop, args=(filename_prefix,), daemon=True)
        self._thread.start()

    def submit_frame(self, frame_rgb) -> None:
        """RGB 프레임을 비동기 큐에 넣고, 저장은 별도 스레드에서 처리한다."""
        if not self.is_recording or self._writer is None or self._cv2 is None or np is None or self._frame_queue is None:
            return
        self._submitted_frames += 1
        frame = np.asarray(frame_rgb, dtype=np.uint8).copy()
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            # 실시간 진행을 우선한다: 큐가 꽉 차면 가장 오래된 프레임을 버리고 최신 프레임을 넣는다.
            try:
                _ = self._frame_queue.get_nowait()
                self._dropped_frames += 1
            except queue.Empty:
                pass
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                self._dropped_frames += 1

    def stop(self) -> None:
        """VideoWriter를 닫고 마지막 녹화 경로를 출력한다."""
        self.is_recording = False
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=30.0)
        writer = self._writer
        self._writer = None
        self._frame_queue = None
        if writer is not None:
            writer.release()
            if self._last_video_path is not None:
                print("[rec] 녹화 저장:", self._last_video_path)
                submitted = int(self._submitted_frames)
                encoded = int(self._encoded_frames)
                dropped = int(self._dropped_frames)
                drop_rate = (float(dropped) / float(submitted) * 100.0) if submitted > 0 else 0.0
                print(
                    f"[rec][stats] frame 제출={submitted} 저장={encoded} 드롭={dropped} "
                    f"(drop={drop_rate:.2f}%)"
                )
                if dropped > 0:
                    print(f"[rec][warn] 인코딩 지연으로 프레임 {dropped}개 드롭됨")

    def _record_loop(self, filename_prefix: str) -> None:
        """스레드 진입점: 큐 프레임을 인코딩해 비디오로 저장한다."""
        _ = filename_prefix
        try:
            self._record_video_from_queue()
        except Exception as e:
            print("[!] 녹화 저장 중 오류:", e)

    def _record_video_from_queue(self) -> None:
        """큐를 비우며 VideoWriter에 기록한다(메인 루프 비차단)."""
        if self._writer is None or self._cv2 is None:
            return
        w, h = self._size[0], self._size[1]
        while self.is_recording or (self._frame_queue is not None and not self._frame_queue.empty()):
            if self._frame_queue is None:
                break
            try:
                frame = self._frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if frame.shape[0] != h or frame.shape[1] != w:
                frame = self._cv2.resize(frame, (w, h))
            self._writer.write(self._cv2.cvtColor(frame, self._cv2.COLOR_RGB2BGR))
            self._encoded_frames += 1

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
    record_until_content_done: bool = False,
    record_max_sec: float = 3600.0,
    viewport: Optional[tuple[int, int]] = None,
    debug_preview_scale: Optional[float] = None,
) -> None:
    """IStudio 실행. debug=화면만(녹화 없음), record=오프스크린 버퍼→인코딩만.

    conversation 스튜디오: `conversation_render`(`ConversationRenderSettings`)를
    `config.conversation_render`로 넘기면 폰트 크기가 적용된다. 색은 스튜디오 `load_font_*` 인자로만 지정한다.

    record_until_content_done: True면 `studio.should_stop_recording()`이 True가 될 때까지 프레임을 찍되,
    최대 `record_max_sec` 초(×fps)에서 강제 종료한다.
    """
    if mode == "record":
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    elif mode == "debug":
        os.environ["SDL_VIDEO_CENTERED"] = "1"
    from core.paths import STUDIO_AUDIO_SAMPLE_RATE

    import pygame

    pygame.mixer.pre_init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
    pygame.init()
    vw, vh = viewport if viewport else (STUDIO_WIDTH, STUDIO_HEIGHT)
    config = StudioConfig(int(vw), int(vh), STUDIO_FPS)
    if conversation_render is not None:
        config.conversation_render = conversation_render
    clock = pygame.time.Clock()
    studio.init(config)

    if mode == "debug":
        scale = float(debug_preview_scale) if debug_preview_scale is not None else 1.0
        if debug_preview_scale is None and viewport == (SHORTS_WIDTH, SHORTS_HEIGHT):
            scale = 0.7
        _run_debug(studio, config, clock, pygame, preview_scale=scale)
    else:
        _run_record(
            studio,
            config,
            clock,
            pygame,
            record_duration,
            record_frames,
            record_until_content_done=record_until_content_done,
            record_max_sec=record_max_sec,
        )
    pygame.quit()


def _is_shorts_studio(studio: IStudio) -> bool:
    """isinstance 대신 title로 판별 (debugpy 이중 로드 시에도 동작)."""
    try:
        return "숏츠" in (studio.get_title() or "")
    except Exception:
        return False


def _warm_shorts_brand_icon(studio: IStudio, pygame) -> None:
    if not _is_shorts_studio(studio):
        return
    from studio.shorts.brand_icon import invalidate_brand_icon_cache, warm_brand_icon

    invalidate_brand_icon_cache()
    warm_brand_icon()
    drawer = getattr(studio, "_drawer", None)
    if drawer is not None and getattr(drawer, "_bg_surface", None) is not None:
        drawer._bg_surface = None


def _run_debug(
    studio: IStudio,
    config: StudioConfig,
    clock,
    pygame,
    *,
    preview_scale: float = 1.0,
) -> None:
    """디버그 모드: 창에만 출력, 녹화 없음. FPS 등 디버그 정보는 config에 설정됨."""
    fw, fh = int(config.width), int(config.height)
    scale = max(0.25, min(1.0, float(preview_scale)))
    if scale < 1.0:
        dw = max(1, int(round(fw * scale)))
        dh = max(1, int(round(fh * scale)))
        screen = pygame.display.set_mode((dw, dh))
        buffer = pygame.Surface((fw, fh))
    else:
        screen = pygame.display.set_mode((fw, fh))
        buffer = screen

    title = studio.get_title()
    if scale < 1.0:
        pct = int(round(scale * 100))
        title = f"{title} (미리보기 {pct}%, {dw}×{dh})"
    pygame.display.set_caption(title)
    _warm_shorts_brand_icon(studio, pygame)

    _ensure_debug_audio_ready(pygame)
    _start = getattr(studio, "start_playback", None)
    if callable(_start):
        try:
            _start()
        except Exception as ex:
            logger.warning("start_playback 실패: %s", ex)

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
        if buffer is screen:
            studio.draw(screen, config)
        else:
            buffer.fill(config.bg_color)
            studio.draw(buffer, config)
            pygame.transform.smoothscale(buffer, screen.get_size(), screen)
        pygame.display.flip()
        clock.tick(config.fps)


def _run_record(
    studio: IStudio,
    config: StudioConfig,
    clock,
    pygame,
    record_duration: float,
    record_frames: Optional[int],
    *,
    record_until_content_done: bool = False,
    record_max_sec: float = 3600.0,
) -> None:
    """녹화 모드: 오프스크린 버퍼만 렌더링 후 인코딩, 창 없음. 타임라인 기준 오디오 이벤트 수집 후 사후 mux.

    debug 루프와 동일하게 매 프레임 `event.get`·QUIT/ESC·`handle_events`를 처리한다.
    장면 진행은 녹화 타임라인과 맞추기 위해 update에는 고정 dt(1/fps)를 쓴다.
    """
    pygame.display.set_mode((1, 1))  # 최소 디스플레이 (폰트 등 동작용)
    pygame.display.set_caption(studio.get_title())
    _ensure_record_audio_ready(pygame)
    buffer = pygame.Surface((config.width, config.height))
    _warm_shorts_brand_icon(studio, pygame)
    recorder = SimpleRecordingManager()
    prefix = studio.get_recording_prefix() or "rec"
    recorder.start(prefix, float(config.fps), (config.width, config.height))
    shorts_thumb_png: Optional[Path] = None
    if _is_shorts_studio(studio):
        vp = recorder.get_last_video_path()
        if vp is not None:
            from studio.shorts.thumbnail_postprocess import shorts_thumbnail_png_path

            shorts_thumb_png = shorts_thumbnail_png_path(vp)
            _set_thumb = getattr(studio, "set_session_thumbnail_png_path", None)
            if callable(_set_thumb):
                _set_thumb(str(shorts_thumb_png))

    # 녹화 타임라인: 0 기준, 매 프레임 현재 시간 전달. 오디오 이벤트 로그 수집.
    recording_events: list = []
    config.recording_time_sec = 0.0
    config.recording_log_event = lambda ev: recording_events.append(ev)
    config.record_max_sec = float(record_max_sec)
    config.show_debug_overlay = False

    _begin_rec = getattr(studio, "begin_recording_session", None)
    if callable(_begin_rec):
        try:
            _begin_rec(config)
        except Exception as ex:
            logger.warning("begin_recording_session 실패: %s", ex)

    target_frames = (
        record_frames
        if record_frames is not None
        else int(record_duration * config.fps)
    )
    if record_until_content_done:
        loop_limit = max(1, int(float(record_max_sec) * config.fps))
    else:
        loop_limit = max(1, target_frames)

    frames_written = 0
    stopped_by_content = False
    progress_fn = getattr(studio, "recording_progress_line", None)
    last_progress_sec = -999.0
    try:
        for frame_index in range(loop_limit):
            config.actual_fps = clock.get_fps()
            events = list(pygame.event.get())
            stop = False
            for e in events:
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    stop = True
                    break
            if stop:
                break
            if not studio.handle_events(events, config):
                break

            config.recording_time_sec = frame_index / config.fps
            config.dt_sec = 1.0 / config.fps
            studio.update(config)
            studio.draw(buffer, config)
            if _is_shorts_studio(studio):
                _cap = getattr(studio, "capture_session_thumbnail_if_armed", None)
                if callable(_cap):
                    try:
                        _cap(buffer)
                    except Exception as ex:
                        logger.debug("capture_session_thumbnail_if_armed 실패: %s", ex)
            if np is not None:
                buf = pygame.surfarray.array3d(buffer)
                frame = np.transpose(buf, (1, 0, 2))
                recorder.submit_frame(frame)
                frames_written += 1
            pygame.display.flip()
            clock.tick(config.fps)
            t_sec = (frame_index + 1) / max(1e-9, float(config.fps))
            if t_sec - last_progress_sec >= 2.0:
                extra = ""
                if callable(progress_fn):
                    try:
                        extra = f" | {progress_fn()}"
                    except Exception:
                        pass
                print(
                    f"[rec] 녹화 중… {frames_written}프레임 {t_sec:.1f}s{extra}",
                    flush=True,
                )
                last_progress_sec = t_sec
            if record_until_content_done and studio.should_stop_recording():
                stopped_by_content = True
                try:
                    extra = ""
                    if callable(progress_fn):
                        try:
                            extra = f" | {progress_fn()}"
                        except Exception:
                            pass
                    print(
                        "[rec][step] should_stop_recording=True → 루프 종료 | "
                        f"frame={frame_index} t={frame_index / max(1e-9, float(config.fps)):.3f}s"
                        f"{extra}",
                        flush=True,
                    )
                except Exception:
                    pass
                break
        else:
            if record_until_content_done and not stopped_by_content:
                print(
                    "[!] record_max_sec 상한에 도달했습니다. 콘텐츠가 끝나기 전에 끊겼다면 --record-max-sec 을 늘리세요.",
                )
                _fn_partial = getattr(studio, "recording_stop_summary", None)
                if callable(_fn_partial):
                    try:
                        line = _fn_partial()
                        if line:
                            print("[!] 상한 도달 시점:", line)
                    except Exception:
                        pass
    finally:
        try:
            end_tl = (frames_written / float(config.fps)) if frames_written > 0 else 0.0
            fin = getattr(studio, "finalize_recording_audio_segments", None)
            if callable(fin):
                fin(timeline_end_sec=end_tl)
        except Exception:
            pass
        recorder.stop()
        config.recording_log_event = None
        config.recording_time_sec = 0.0
        config.show_debug_overlay = True

    print("[rec] 녹화 완료:", frames_written, "프레임")
    if record_until_content_done and stopped_by_content:
        print("[rec] 콘텐츠 종료 조건(마지막 아이템·마지막 장면까지)으로 루프를 마쳤습니다.")
        _fn = getattr(studio, "recording_stop_summary", None)
        if callable(_fn):
            try:
                line = _fn()
                if line:
                    print("[rec]", line)
            except Exception:
                pass
    video_path = recorder.get_last_video_path()
    duration_sec = frames_written / config.fps if frames_written > 0 else 0.0
    if video_path is not None and recording_events and duration_sec > 0:
        print("[audio] 녹화 오디오 분리: 이벤트", len(recording_events), "개 -> WAV 생성 후 mux")
        _mux_recorded_audio(
            video_path, recording_events, config.fps, duration_sec, studio=studio
        )
    elif video_path is not None and not recording_events:
        print("[!] 녹화 오디오 mux 건너뜀: 오디오 이벤트 없음 (스튜디오에서 이벤트 로그 필요)")
    if video_path is not None and _is_shorts_studio(studio):
        from studio.shorts.thumbnail_postprocess import apply_shorts_thumbnail_if_present

        apply_shorts_thumbnail_if_present(video_path)


def _mux_recorded_audio(
    video_path: Path,
    recording_events: list,
    fps: int,
    duration_sec: float,
    *,
    studio: Any = None,
) -> None:
    """녹화 이벤트 로그로 오디오 WAV 생성 후 비디오와 mux. 실패 시 경고만 출력."""
    try:
        from core.paths import (
            STUDIO_SHORTS_BG_AUDIO_LINEAR_GAIN,
            STUDIO_WORD_MEMORIZE_BG_AUDIO_LINEAR_GAIN,
        )
        from studio.recorded_audio_mux import build_audio_and_mux

        shorts_bg_gain = STUDIO_SHORTS_BG_AUDIO_LINEAR_GAIN
        if studio is not None:
            fn = getattr(studio, "recording_shorts_bg_linear_gain", None)
            if callable(fn):
                try:
                    override = fn()
                    if override is not None:
                        shorts_bg_gain = float(override)
                except Exception:
                    pass
        build_audio_and_mux(
            video_path,
            recording_events,
            float(fps),
            duration_sec,
            shorts_bg_linear_gain=shorts_bg_gain,
        )
    except Exception as e:
        print("[!] 녹화 오디오 mux 건너뜀:", e)


def _parse_session_topics_arg(raw: str) -> Optional[list[str]]:
    """CLI `--topic` 값: 쉼표 또는 세로줄로 구분된 topic 목록. 비어 있으면 None."""
    s = (raw or "").strip()
    if not s:
        return None
    parts = [p.strip() for p in s.replace("|", ",").split(",") if p.strip()]
    return parts or None


def _parse_shorts_clip_types_arg(raw: str) -> Optional[list[str]]:
    """CLI `--shorts-type` 값: conversation | vocabulary (쉼표로 복수 가능). 비우면 전체."""
    s = (raw or "").strip()
    if not s:
        return None
    parts = [p.strip() for p in s.replace("|", ",").split(",") if p.strip()]
    return parts or None


def _create_studio(
    name: str,
    csv_path: str | None,
    content: Optional[Any] = None,
    **kwargs,
) -> IStudio:
    """이름에 맞는 IStudio 인스턴스를 만든다(conversation / vocabulary / conversation_then_words)."""
    kw = dict(kwargs)
    session_topics: Optional[list[str]] = kw.pop("session_topics", None)

    if name == "conversation":
        from studio.conversation import ConversationStudio
        return ConversationStudio(
            csv_path=csv_path or "",
            content=content,
            session_topics=session_topics,
        )
    if name == "conversation_then_words":
        from studio.studios.conversation_then_words import ConversationThenWordsStudio
        return ConversationThenWordsStudio(
            csv_path=csv_path or "",
            content=content,
            session_topics=session_topics,
            **kw,
        )
    if name == "vocabulary":
        from studio.studios.vocabulary import VocabularyStudio
        kw.pop("vocabulary_topics", None)
        if "word_rows" not in kw:
            if session_topics:
                kw["word_rows"] = select_vocabulary_word_rows_for_session_topics(list(session_topics))
            else:
                kw["word_rows"] = select_all_vocabulary_word_rows()
        return VocabularyStudio(**kw)
    if name == "shorts":
        from studio.shorts import ShortsStudio

        shorts_mode: str = kw.pop("shorts_mode", "conversation")
        clips_csv_path: str = str(kw.pop("clips_csv_path", "") or "")
        return ShortsStudio(
            shorts_mode=shorts_mode,
            session_topics=session_topics,
            clips_csv_path=clips_csv_path,
            **kw,
        )
    if name == "word_memorize":
        from studio.studios.word_memorize import WordMemorizeStudio

        layout_path = str(kw.pop("layout_path", "") or "").strip()
        if not layout_path:
            raise ValueError("word_memorize 스튜디오에는 layout_path가 필요합니다.")
        meaning_lang = str(kw.pop("meaning_lang", "ko") or "ko").strip().lower()
        if meaning_lang not in ("ko", "en", "zh"):
            meaning_lang = "ko"
        kw.pop("show_images", None)
        kw.pop("word_images", None)
        return WordMemorizeStudio(
            layout_path=layout_path,
            meaning_lang=meaning_lang,  # type: ignore[arg-type]
        )
    raise ValueError(f"알 수 없는 스튜디오: {name}")


def main() -> None:
    """CLI 인자 파싱 후 콘텐츠 로드·스튜디오 생성·run() 호출."""
    parser = argparse.ArgumentParser(description="LVPD 스튜디오 러너 (IStudio 구현체 실행)")
    parser.add_argument(
        "--studio",
        type=str,
        default="conversation",
        choices=(
            "conversation",
            "conversation_then_words",
            "vocabulary",
            "shorts",
            "word_memorize",
        ),
        help=(
            "실행할 스튜디오 (기본: conversation). "
            "conversation_then_words=회화 후 집계 단어, shorts=9:16 숏츠, "
            "word_memorize=단어 외우기 배치 JSON"
        ),
    )
    parser.add_argument(
        "--layout",
        type=str,
        default="",
        metavar="PATH",
        help="word_memorize: resource/table/word_memorize_layouts/*.json 경로",
    )
    parser.add_argument(
        "--meaning-lang",
        type=str,
        default="ko",
        choices=("ko", "en", "zh"),
        help="word_memorize: 카드 뜻·TTS 순서 (ko=한→중, en=영→중, zh=중→한·BG/ch MP4). 기본 ko.",
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
        "--debug-preview-scale",
        type=float,
        default=None,
        metavar="RATIO",
        help=(
            "debug 창 미리보기 배율(0.25~1.0, 비율 유지). "
            "숏츠 미지정 시 기본 0.7. 1.0=원본 1080×1920 창."
        ),
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
    parser.add_argument(
        "--record-until-content-done",
        action="store_true",
        help=(
            "녹화: studio.should_stop_recording()이 True가 될 때까지 진행(회화=마지막 아이템·마지막 장면 끝). "
            "최대 길이는 --record-max-sec."
        ),
    )
    parser.add_argument(
        "--record-max-sec",
        type=float,
        default=3600.0,
        help="--record-until-content-done 일 때 녹화 루프 상한(초). 기본 3600.",
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
    parser.add_argument(
        "--topic",
        type=str,
        default="",
        metavar="TOPIC",
        help=(
            "회화·회화+단어·단어장·숏츠: base_sentences / vocabulary_word_rows / shorts_*_clips의 topic과 일치. "
            "여러 개는 쉼표 또는 | 로 구분. 비우면 회화는 전체, 단어장(vocabulary)은 테이블 전체."
        ),
    )
    parser.add_argument(
        "--shorts-type",
        type=str,
        default="",
        metavar="TYPE",
        help=(
            "숏츠 전용(필수 권장): conversation → shorts_conversation_clips.csv, "
            "vocabulary → shorts_vocabulary_clips.csv. 비우면 conversation."
        ),
    )
    args = parser.parse_args()

    csv_path: str | None = (args.csv or "").strip() or None
    if args.studio in ("conversation", "conversation_then_words"):
        load_base_sentences_from_csv(DEFAULT_BASE_SENTENCES_CSV)
        load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
        load_sub_sentences_from_csv(DEFAULT_SUB_SENTENCES_CSV)
        load_vocabulary_word_rows_from_csv(DEFAULT_VOCABULARY_WORD_ROWS_CSV)
        set_table(get_table_rows())
        content = get_loaded_content() if get_table() else None
        if not content or (not content.video_segments and not content.overlay_items):
            print("콘텐츠가 없습니다. create_all_csv.bat으로 CSV를 생성한 뒤 resource/csv/ 를 확인하세요.", file=sys.stderr)
            sys.exit(1)
    elif args.studio == "vocabulary":
        load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
        load_vocabulary_word_rows_from_csv(DEFAULT_VOCABULARY_WORD_ROWS_CSV)
        content = None
    elif args.studio == "shorts":
        load_base_sentences_from_csv(DEFAULT_BASE_SENTENCES_CSV)
        load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
        load_vocabulary_word_rows_from_csv(DEFAULT_VOCABULARY_WORD_ROWS_CSV)
        content = None
        if not get_base_sentences():
            print(
                "base_sentences.csv가 없거나 비어 있습니다. create_all_csv.bat 실행 후 "
                f"{DEFAULT_BASE_SENTENCES_CSV} 를 확인하세요.",
                file=sys.stderr,
            )
            sys.exit(1)
    elif args.studio == "word_memorize":
        load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
        content = None
    else:
        content = None

    session_topics = _parse_session_topics_arg(getattr(args, "topic", "") or "")
    shorts_type_list = _parse_shorts_clip_types_arg(getattr(args, "shorts_type", "") or "")
    studio_kw: dict[str, Any] = {}
    if session_topics:
        studio_kw["session_topics"] = session_topics

    if args.studio == "word_memorize":
        layout_raw = (getattr(args, "layout", "") or "").strip()
        if not layout_raw:
            print(
                "word_memorize 스튜디오에는 --layout 이 필요합니다.",
                file=sys.stderr,
            )
            sys.exit(1)
        layout_file = Path(layout_raw)
        if not layout_file.is_file():
            print(f"배치 JSON을 찾을 수 없습니다: {layout_file}", file=sys.stderr)
            sys.exit(1)
        studio_kw["layout_path"] = str(layout_file.resolve())
        studio_kw["meaning_lang"] = str(getattr(args, "meaning_lang", "ko") or "ko")

    if args.studio == "shorts":
        from studio.shorts.clip_types import CLIP_TYPE_VOCABULARY, normalize_clip_type

        if shorts_type_list and len(shorts_type_list) > 1:
            print(
                "숏츠 CSV가 회화/단어로 분리되어 있습니다. "
                "--shorts-type 은 conversation 또는 vocabulary 중 하나만 지정하세요.",
                file=sys.stderr,
            )
            sys.exit(1)
        shorts_mode = normalize_clip_type(
            shorts_type_list[0] if shorts_type_list else "conversation"
        )
        clips_csv = (
            DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV
            if shorts_mode == CLIP_TYPE_VOCABULARY
            else DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV
        )
        if not clips_csv.exists():
            print(f"숏츠 CSV가 없습니다: {clips_csv}", file=sys.stderr)
            sys.exit(1)
        studio_kw["shorts_mode"] = shorts_mode
        studio_kw["clips_csv_path"] = str(clips_csv)
    studio = _create_studio(
        args.studio,
        csv_path or "",
        content=content,
        **studio_kw,
    )
    viewport = (
        (SHORTS_WIDTH, SHORTS_HEIGHT)
        if args.studio in ("shorts", "word_memorize")
        else None
    )
    run(
        studio,
        mode=args.mode,
        record_duration=args.record_duration,
        record_frames=args.record_frames,
        conversation_render=_conversation_render_from_cli_args(args),
        record_until_content_done=bool(getattr(args, "record_until_content_done", False)),
        record_max_sec=float(getattr(args, "record_max_sec", 3600.0)),
        viewport=viewport,
        debug_preview_scale=args.debug_preview_scale,
    )


if __name__ == "__main__":
    main()
