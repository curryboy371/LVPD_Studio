"""회화 스튜디오 비디오·오디오 재생기."""
import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Optional

import pygame

from core.paths import (
    STUDIO_HEIGHT,
    STUDIO_VIDEO_FALLBACK_FPS,
    STUDIO_WIDTH,
)

logger = logging.getLogger(__name__)

# OpenCV CAP_PROP_FPS가 1·1000 등 비정상인 mp4에서 연속 read()가 구간을 건너뛰며 빨리 재생되는 것 방지
_MIN_TRUSTED_FPS = 8.0
_MAX_TRUSTED_FPS = 120.0


class SimpleVideoPlayer:
    """단일 비디오 파일의 화면만 재생 (OpenCV로 비디오 스트림만 읽음, 오디오 미사용). start_time~end_time 구간만 재생, end_time=-1이면 끝까지."""
    def __init__(self) -> None:
        """캡처·PTS·캐시 필드를 초기 상태로 둔다."""
        self._path: str = ""
        self._cap: Any = None
        self._fps: float = STUDIO_VIDEO_FALLBACK_FPS
        self._duration_sec: float = 0.0
        self._start_time: float = 0.0
        self._end_time: float = -1.0
        self._paused: bool = False
        self._current_pts: float = 0.0
        self._cached_surf: Optional[pygame.Surface] = None
        self._cached_pts: float = -1.0
        self._cached_size: tuple[int, int, bool] = (0, 0, False)

    def _effective_end_sec(self) -> float:
        """end_time이 음수면 파일 길이까지를 유효 종료 시각으로 본다."""
        return self._end_time if self._end_time >= 0 else self._duration_sec

    @staticmethod
    def _probe_duration_sec(cap: Any, frame_count: float, fps: float) -> float:
        """컨테이너 길이(초). frame_count 메타가 없으면 재생 위치로 추정."""
        if frame_count > 0 and fps > 0:
            return frame_count / fps
        try:
            import cv2

            cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 1.0)
            ms = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
            cap.set(cv2.CAP_PROP_POS_MSEC, 0)
            if ms > 100.0:
                return ms / 1000.0
        except Exception:
            pass
        return 3600.0

    @staticmethod
    def _normalize_capture_fps(cap: Any, frame_count: float) -> float:
        """컨테이너 FPS 메타가 비정상일 때 길이·프레임 수로 보정."""
        fallback = float(STUDIO_VIDEO_FALLBACK_FPS)
        try:
            import cv2

            raw = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        except Exception:
            raw = 0.0
        if _MIN_TRUSTED_FPS <= raw <= _MAX_TRUSTED_FPS:
            return raw
        if frame_count > 1:
            try:
                import cv2

                cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 1.0)
                ms = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
                cap.set(cv2.CAP_PROP_POS_MSEC, 0)
                if ms > 100.0:
                    est = frame_count * 1000.0 / ms
                    if _MIN_TRUSTED_FPS <= est <= _MAX_TRUSTED_FPS:
                        logger.debug(
                            "비디오 FPS 보정(재생 길이 기준): meta=%.3f → %.3f",
                            raw,
                            est,
                        )
                        return est
            except Exception:
                pass
        if raw > 1e-6:
            logger.debug(
                "비디오 FPS 메타 비정상(%.3f) — 폴백 %.1f 사용",
                raw,
                fallback,
            )
        return fallback

    def _seek_display_to_current_pts(
        self,
        width: int,
        height: int,
        *,
        contain: bool = False,
    ) -> bool:
        """current_pts 시점 프레임을 시크로 표시(연속 read 누적 오차·가속 방지)."""
        if self._cap is None:
            return False
        try:
            import cv2

            self._cap.set(cv2.CAP_PROP_POS_MSEC, self._current_pts * 1000.0)
            ok, frame = self._cap.read()
            if not ok or frame is None:
                return False
            out = self._bgr_to_surface(frame, width, height, contain=contain)
            if out is None:
                return False
            self._cached_surf = out
            self._cached_pts = self._current_pts
            self._cached_size = (width, height, contain)
            return True
        except Exception:
            return False

    def set_source(self, path: str, start_time: float = 0.0, end_time: float = -1.0) -> None:
        """OpenCV로 비디오를 열고 구간·FPS·길이를 설정한 뒤 start_time 위치로 시크한다."""
        try:
            import cv2
        except ImportError:
            try:
                logger.warning("OpenCV(cv2) 없음 — 비디오 프레임을 읽을 수 없습니다.")
            except Exception:
                pass
            self._path = ""
            self._cap = None
            return
        if path == self._path and self._cap is not None and self._start_time == start_time and self._end_time == end_time:
            # 같은 소스를 연속 재생할 때도 항상 지정 시점부터 다시 시작한다.
            # (이전 아이템 끝에서 paused된 상태가 남아 VIDEO 장면이 즉시 종료되는 현상 방지)
            self._current_pts = start_time
            self._paused = False
            self._cached_pts = -1.0
            try:
                self._cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000.0)
            except Exception:
                pass
            return
        self.close()
        self._path = path
        self._start_time = start_time
        self._end_time = end_time
        self._current_pts = start_time
        if not path or not os.path.exists(path):
            try:
                logger.warning("비디오 파일 없음: %s", path)
            except Exception:
                pass
            self._cap = None
            return
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            try:
                logger.warning("OpenCV: 비디오 열기 실패: %s", path)
            except Exception:
                pass
            cap.release()
            self._cap = None
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, STUDIO_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STUDIO_HEIGHT)
        self._cap = cap
        fc = max(0.0, float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
        self._fps = self._normalize_capture_fps(cap, fc)
        self._duration_sec = self._probe_duration_sec(cap, fc, self._fps)
        try:
            cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000.0)
        except Exception:
            pass
        self._cached_pts = -1.0
        # 구간 끝에서 True가 된 pause는 다음 소스/세그먼트로 바뀔 때 해제하지 않으면 영원히 멈춤.
        self._paused = False

    def close(self) -> None:
        """캡처 핸들과 캐시를 해제한다."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self._path = ""
        self._duration_sec = 0.0
        self._cached_surf = None
        self._cached_pts = -1.0

    def tick(self, dt_sec: float) -> None:
        """일시정지가 아니면 PTS를 진행하고 구간 끝에서 멈춘다."""
        if self._paused or self._cap is None:
            return
        self._current_pts += dt_sec
        end_sec = self._effective_end_sec()
        if self._current_pts >= end_sec:
            self._current_pts = end_sec
            self._paused = True

    def seek(self, delta_sec: float) -> None:
        """현재 PTS에 delta를 더해 유효 구간 안으로 클램프하고 OpenCV 위치를 맞춘다."""
        if self._cap is None:
            return
        try:
            import cv2
            end_sec = self._effective_end_sec()
            self._current_pts = max(self._start_time, min(end_sec, self._current_pts + delta_sec))
            self._cap.set(cv2.CAP_PROP_POS_MSEC, self._current_pts * 1000.0)
            self._cached_pts = -1.0
        except Exception:
            pass

    def seek_to(self, time_sec: float) -> None:
        """절대 시점으로 이동. 세그먼트 [start_time, end_time] 구간으로 클램프."""
        if self._cap is None:
            return
        try:
            import cv2

            end_sec = self._effective_end_sec()
            clamped = max(self._start_time, min(end_sec, float(time_sec)))
            self._current_pts = clamped
            self._paused = clamped >= end_sec - 1e-3
            self._cap.set(cv2.CAP_PROP_POS_MSEC, clamped * 1000.0)
            self._cached_pts = -1.0
        except Exception:
            pass

    def toggle_pause(self) -> None:
        """재생/일시정지 플래그를 뒤집는다."""
        self._paused = not self._paused

    def is_paused(self) -> bool:
        """현재 일시정지 여부."""
        return self._paused

    def has_source(self) -> bool:
        """현재 아이템의 비디오 소스를 정상적으로 연 상태인지."""
        return self._cap is not None

    def get_frame(self, width: int, height: int, *, contain: bool = False) -> Optional[pygame.Surface]:
        """현재 PTS 프레임. contain=True면 max(width,height) 안에 비율 유지."""
        if self._cap is None:
            return self._cached_surf
        try:
            return self._get_frame_impl(width, height, contain=contain)
        except Exception:
            return self._cached_surf

    def _get_frame_impl(self, width: int, height: int, *, contain: bool = False) -> Optional[pygame.Surface]:
        """OpenCV read·시크·캐시 정책으로 단일 프레임을 준비한다."""
        import cv2
        frame_interval = 1.0 / self._fps
        if (
            self._cached_surf is not None
            and             self._cached_size == (width, height, contain)
            and self._cached_pts >= 0
            and abs(self._current_pts - self._cached_pts) < frame_interval * 0.6
        ):
            return self._cached_surf

        if self._cached_pts >= 0 and self._current_pts < self._cached_pts - frame_interval * 0.5:
            self._cap.set(cv2.CAP_PROP_POS_MSEC, self._current_pts * 1000.0)
            ok, frame = self._cap.read()
            if not ok:
                self._cap.set(cv2.CAP_PROP_POS_MSEC, 0)
                ok, frame = self._cap.read()
            if ok and frame is not None:
                out = self._bgr_to_surface(frame, width, height, contain=contain)
                if out is not None:
                    self._cached_surf = out
                    self._cached_pts = self._current_pts
                    self._cached_size = (width, height, contain)
            return self._cached_surf

        if self._cached_pts < 0:
            self._cap.set(cv2.CAP_PROP_POS_MSEC, self._current_pts * 1000.0)
            ok, frame = self._cap.read()
            if not ok:
                self._cap.set(cv2.CAP_PROP_POS_MSEC, 0)
                ok, frame = self._cap.read()
            if ok and frame is not None:
                out = self._bgr_to_surface(frame, width, height, contain=contain)
                if out is not None:
                    self._cached_surf = out
                    self._cached_pts = self._current_pts
                    self._cached_size = (width, height, contain)
            return self._cached_surf

        duration = max(0.0, self._duration_sec)
        gap = self._current_pts - self._cached_pts
        # FPS 메타 오류·해상도 변경 시 연속 read()가 타임라인을 크게 점프 → 시크로 동기화
        if gap > frame_interval * 2.0:
            if self._seek_display_to_current_pts(width, height, contain=contain):
                return self._cached_surf
        # LEARNING/PRACTICE는 bg_frame만 쓰는 프레임이 있어 get_frame이 오래 없을 수 있음.
        # 그 사이 tick만 진행되면 cached_pts 대비 current_pts가 크게 벌어져 한 호출에 수천 번 read()가 될 수 있다.
        max_seek_reads = 64
        n_read = 0
        while (
            self._cached_pts < self._current_pts - frame_interval * 0.5 and n_read < max_seek_reads
        ):
            n_read += 1
            ok, frame = self._cap.read()
            if not ok:
                self._current_pts = min(self._current_pts, duration) if duration else self._cached_pts
                break
            if frame is None:
                break
            self._cached_pts += frame_interval
            if duration > 0 and self._cached_pts >= duration:
                self._current_pts = min(self._current_pts, duration)
                out = self._bgr_to_surface(frame, width, height, contain=contain)
                if out is not None:
                    self._cached_surf = out
                    self._cached_size = (width, height, contain)
                break
            out = self._bgr_to_surface(frame, width, height, contain=contain)
            if out is not None:
                self._cached_surf = out
                self._cached_size = (width, height, contain)
        if n_read >= max_seek_reads:
            try:
                self._cap.set(cv2.CAP_PROP_POS_MSEC, self._current_pts * 1000.0)
            except Exception:
                pass
            self._cached_pts = -1.0
            self._cached_surf = None
            logger.warning(
                "OpenCV: get_frame 연속 read 상한(%s) 도달 — 시크로 재동기화했습니다. 경로=%s",
                max_seek_reads,
                self._path,
            )

        if self._cached_surf is not None and self._cached_size == (width, height, contain):
            return self._cached_surf
        ok, frame = self._cap.read()
        if ok and frame is not None:
            out = self._bgr_to_surface(frame, width, height, contain=contain)
            if out is not None:
                self._cached_surf = out
                self._cached_pts = self._current_pts
                self._cached_size = (width, height, contain)
        return self._cached_surf

    def _bgr_to_surface(
        self,
        frame: Any,
        width: int,
        height: int,
        *,
        contain: bool = False,
    ) -> Optional[pygame.Surface]:
        """BGR → RGB Surface. contain이면 width×height 안에 비율 유지."""
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            sw = int(rgb.shape[1])
            sh = int(rgb.shape[0])
            if sw <= 0 or sh <= 0:
                return None
            if contain:
                scale = min(float(width) / sw, float(height) / sh)
                tw = max(1, int(round(sw * scale)))
                th = max(1, int(round(sh * scale)))
            else:
                tw, th = max(1, int(width)), max(1, int(height))
            if tw != sw or th != sh:
                rgb = cv2.resize(rgb, (tw, th), interpolation=cv2.INTER_LINEAR)
            buf = rgb.tobytes()
            surf = pygame.image.frombuffer(buf, (tw, th), "RGB")
            return surf.convert()
        except Exception:
            return None

    def get_pts(self) -> float:
        """논리 재생 시각(초)."""
        return self._current_pts

    def get_effective_end_sec(self) -> float:
        """구간 종료 시각(초); end_time 미지정 시 파일 끝."""
        return self._effective_end_sec()

    def get_fps(self) -> float:
        """소스에서 읽은 FPS(실패 시 폴백)."""
        return self._fps

    def width(self) -> int:
        """스냅샷·FrameContext용 폭(마지막 디코드 크기가 있으면 그것을 쓴다)."""
        w, _, _ = self._cached_size
        return int(w) if w > 0 else int(STUDIO_WIDTH)

    def height(self) -> int:
        """스냅샷·FrameContext용 높이."""
        _, h, _ = self._cached_size
        return int(h) if h > 0 else int(STUDIO_HEIGHT)


class VideoAudioPlayer:
    """비디오와 동일 경로·동일 이름의 추출된 MP3를 재생. 비디오 내장 음원은 사용하지 않음."""

    def __init__(self, is_recording: Optional[Callable[[], bool]] = None) -> None:
        """경로·추출 스레드·pending 잠금을 초기화한다."""
        self._is_recording = is_recording
        self._path: str = ""
        self._start_time: float = 0.0
        self._temp_wav: Optional[str] = None
        self._paused: bool = False
        self._play_start_sec: float = 0.0
        self._lock = threading.Lock()
        self._pending_wav: Optional[str] = None
        self._pending_path: Optional[str] = None
        self._extract_thread: Optional[threading.Thread] = None

    def set_is_recording(self, is_recording: Optional[Callable[[], bool]]) -> None:
        self._is_recording = is_recording

    def _recording_mode(self) -> bool:
        if self._is_recording is None:
            return False
        try:
            return bool(self._is_recording())
        except Exception:
            return False

    def set_source(self, path: str, start_time: float = 0.0) -> None:
        """동일 이름 mp3를 ffmpeg로 WAV 추출한 뒤 백그라운드에서 pending으로 둔다."""
        if path == self._path and self._start_time == start_time:
            return
        self.stop()
        self._path = path
        self._start_time = start_time
        audio_path = str(Path(path).with_suffix(".mp3")) if path else ""
        if not audio_path or not os.path.exists(audio_path):
            return
        if self._recording_mode():
            return
        try:
            from core.paths import FFMPEG_CMD
        except ImportError:
            return

        def _extract() -> None:
            from core.paths import STUDIO_AUDIO_SAMPLE_RATE

            fd, wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            sr = str(int(STUDIO_AUDIO_SAMPLE_RATE))
            base = [FFMPEG_CMD, "-y", "-i", audio_path, "-vn"]
            hq = base + [
                "-af", "aresample=resampler=soxr",
                "-acodec", "pcm_s16le", "-ar", sr, "-ac", "2",
                wav,
            ]
            fb = base + ["-acodec", "pcm_s16le", "-ar", sr, "-ac", "2", wav]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            r = None
            try:
                for cmd in (hq, fb):
                    r = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=creationflags)
                    if r.returncode == 0 and os.path.exists(wav) and os.path.getsize(wav) > 0:
                        break
            except Exception:
                try:
                    os.remove(wav)
                except OSError:
                    pass
                return
            if r is None or r.returncode != 0 or not os.path.exists(wav):
                try:
                    os.remove(wav)
                except OSError:
                    pass
                return
            with self._lock:
                self._pending_wav = wav
                self._pending_path = path

        self._extract_thread = threading.Thread(target=_extract, daemon=True)
        self._extract_thread.start()

    def _apply_pending(self) -> None:
        """추출이 끝난 WAV를 mixer.music에 로드하고 start_time부터 재생한다."""
        with self._lock:
            wav = self._pending_wav
            path = self._pending_path
            self._pending_wav = None
            self._pending_path = None
        if wav is None or path is None or path != self._path:
            if wav and os.path.exists(wav):
                try:
                    os.remove(wav)
                except OSError:
                    pass
            return
        if self._recording_mode():
            try:
                os.remove(wav)
            except OSError:
                pass
            self._temp_wav = None
            self._paused = False
            return
        self._temp_wav = wav
        try:
            pygame.mixer.music.load(wav)
            pygame.mixer.music.play(start=self._start_time)
            self._play_start_sec = self._start_time
            # 새 클립 재생이 일시정지 프레임으로 막이지 않도록
            self._paused = False
        except Exception:
            pass

    def has_pending(self) -> bool:
        """백그라운드 추출 결과가 아직 적용 전이면 True."""
        with self._lock:
            return self._pending_wav is not None

    def seek_to(self, time_sec: float) -> None:
        """mixer.music을 지정 시각부터 다시 재생(일시정지면 재생 후 pause)."""
        if self._recording_mode():
            self._play_start_sec = time_sec
            return
        try:
            self._play_start_sec = time_sec
            if self._paused:
                pygame.mixer.music.play(start=time_sec)
                pygame.mixer.music.pause()
            else:
                pygame.mixer.music.play(start=time_sec)
        except Exception:
            pass

    def pause(self) -> None:
        """배경 음악 일시정지."""
        self._paused = True
        try:
            pygame.mixer.music.pause()
        except Exception:
            pass

    def unpause(self) -> None:
        """배경 음악 재개."""
        self._paused = False
        if self._recording_mode():
            return
        try:
            pygame.mixer.music.unpause()
        except Exception:
            pass

    def stop(self) -> None:
        """재생 중지·pending 취소·임시 WAV 파일 삭제."""
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        with self._lock:
            self._pending_wav = None
            self._pending_path = None
        if self._temp_wav and os.path.exists(self._temp_wav):
            try:
                os.remove(self._temp_wav)
            except OSError:
                pass
        self._temp_wav = None
        self._paused = False
        self._path = ""

    def get_status(self) -> str:
        """디버그용 문자열: 로딩/없음/일시정지/재생 등."""
        if self.has_pending():
            return "로딩 중"
        if not self._path:
            return "없음"
        try:
            if self._paused:
                return "일시정지"
            if pygame.mixer.music.get_busy():
                return "재생 중"
            return "대기"
        except Exception:
            return "?"

    def get_position_sec(self) -> Optional[float]:
        """mixer.music 기준 대략 재생 위치(초); 미초기화면 None."""
        if not self._path or self._temp_wav is None:
            return None
        try:
            pos = pygame.mixer.music.get_pos()
            if pos < 0:
                return None
            # pygame.mixer.music.get_pos()는 밀리초를 반환한다.
            pos_sec = float(pos) / 1000.0
            return self._play_start_sec + pos_sec
        except Exception:
            return None
