"""회화 스튜디오 비디오·오디오 재생기."""
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

import pygame

from core.paths import (
    STUDIO_HEIGHT,
    STUDIO_VIDEO_FALLBACK_FPS,
    STUDIO_WIDTH,
)


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
        self._cached_size: tuple[int, int] = (0, 0)

    def _effective_end_sec(self) -> float:
        """end_time이 음수면 파일 길이까지를 유효 종료 시각으로 본다."""
        return self._end_time if self._end_time >= 0 else self._duration_sec

    def set_source(self, path: str, start_time: float = 0.0, end_time: float = -1.0) -> None:
        """OpenCV로 비디오를 열고 구간·FPS·길이를 설정한 뒤 start_time 위치로 시크한다."""
        try:
            import cv2
        except ImportError:
            self._path = ""
            self._cap = None
            return
        if path == self._path and self._cap is not None and self._start_time == start_time and self._end_time == end_time:
            return
        self.close()
        self._path = path
        self._start_time = start_time
        self._end_time = end_time
        self._current_pts = start_time
        if not path or not os.path.exists(path):
            self._cap = None
            return
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            cap.release()
            self._cap = None
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, STUDIO_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, STUDIO_HEIGHT)
        self._cap = cap
        self._fps = max(1.0, cap.get(cv2.CAP_PROP_FPS) or STUDIO_VIDEO_FALLBACK_FPS)
        fc = max(0, cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self._duration_sec = fc / self._fps if fc else 3600.0
        try:
            cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000.0)
        except Exception:
            pass
        self._cached_pts = -1.0

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
        end_sec = self._effective_end_sec()
        clamped = max(self._start_time, min(end_sec, time_sec))
        self.seek(clamped - self._current_pts)

    def toggle_pause(self) -> None:
        """재생/일시정지 플래그를 뒤집는다."""
        self._paused = not self._paused

    def is_paused(self) -> bool:
        """현재 일시정지 여부."""
        return self._paused

    def get_frame(self, width: int, height: int) -> Optional[pygame.Surface]:
        """현재 PTS에 맞는 프레임을 pygame Surface로 반환(캐시·리사이즈 포함)."""
        if self._cap is None:
            return self._cached_surf
        try:
            return self._get_frame_impl(width, height)
        except Exception:
            return self._cached_surf

    def _get_frame_impl(self, width: int, height: int) -> Optional[pygame.Surface]:
        """OpenCV read·시크·캐시 정책으로 단일 프레임을 준비한다."""
        import cv2
        frame_interval = 1.0 / self._fps
        if (
            self._cached_surf is not None
            and self._cached_size == (width, height)
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
                out = self._bgr_to_surface(frame, width, height)
                if out is not None:
                    self._cached_surf = out
                    self._cached_pts = self._current_pts
                    self._cached_size = (width, height)
            return self._cached_surf

        if self._cached_pts < 0:
            self._cap.set(cv2.CAP_PROP_POS_MSEC, self._current_pts * 1000.0)
            ok, frame = self._cap.read()
            if not ok:
                self._cap.set(cv2.CAP_PROP_POS_MSEC, 0)
                ok, frame = self._cap.read()
            if ok and frame is not None:
                out = self._bgr_to_surface(frame, width, height)
                if out is not None:
                    self._cached_surf = out
                    self._cached_pts = self._current_pts
                    self._cached_size = (width, height)
            return self._cached_surf

        duration = max(0.0, self._duration_sec)
        while self._cached_pts < self._current_pts - frame_interval * 0.5:
            ok, frame = self._cap.read()
            if not ok:
                self._current_pts = min(self._current_pts, duration) if duration else self._cached_pts
                break
            if frame is None:
                break
            self._cached_pts += frame_interval
            if duration > 0 and self._cached_pts >= duration:
                self._current_pts = min(self._current_pts, duration)
                out = self._bgr_to_surface(frame, width, height)
                if out is not None:
                    self._cached_surf = out
                    self._cached_size = (width, height)
                break
            out = self._bgr_to_surface(frame, width, height)
            if out is not None:
                self._cached_surf = out
                self._cached_size = (width, height)

        if self._cached_surf is not None and self._cached_size == (width, height):
            return self._cached_surf
        ok, frame = self._cap.read()
        if ok and frame is not None:
            out = self._bgr_to_surface(frame, width, height)
            if out is not None:
                self._cached_surf = out
                self._cached_pts = self._current_pts
                self._cached_size = (width, height)
        return self._cached_surf

    def _bgr_to_surface(self, frame: Any, width: int, height: int) -> Optional[pygame.Surface]:
        """BGR numpy 배열을 RGB pygame Surface로 변환하고 목표 해상도에 맞춘다."""
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if rgb.shape[1] != width or rgb.shape[0] != height:
                rgb = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_LINEAR)
            buf = rgb.tobytes()
            surf = pygame.image.frombuffer(buf, (width, height), "RGB")
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


class VideoAudioPlayer:
    """비디오와 동일 경로·동일 이름의 추출된 MP3를 재생. 비디오 내장 음원은 사용하지 않음."""

    def __init__(self) -> None:
        """경로·추출 스레드·pending 잠금을 초기화한다."""
        self._path: str = ""
        self._start_time: float = 0.0
        self._temp_wav: Optional[str] = None
        self._paused: bool = False
        self._play_start_sec: float = 0.0
        self._lock = threading.Lock()
        self._pending_wav: Optional[str] = None
        self._pending_path: Optional[str] = None
        self._extract_thread: Optional[threading.Thread] = None

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
        try:
            from core.paths import FFMPEG_CMD
        except ImportError:
            return

        def _extract() -> None:
            fd, wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            cmd = [
                FFMPEG_CMD, "-y", "-i", audio_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                wav,
            ]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=creationflags)
            except Exception:
                try:
                    os.remove(wav)
                except OSError:
                    pass
                return
            if r.returncode != 0 or not os.path.exists(wav):
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
        self._temp_wav = wav
        try:
            pygame.mixer.music.load(wav)
            pygame.mixer.music.play(start=self._start_time)
            self._play_start_sec = self._start_time
        except Exception:
            pass

    def has_pending(self) -> bool:
        """백그라운드 추출 결과가 아직 적용 전이면 True."""
        with self._lock:
            return self._pending_wav is not None

    def seek_to(self, time_sec: float) -> None:
        """mixer.music을 지정 시각부터 다시 재생(일시정지면 재생 후 pause)."""
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
            if pos > 10000:
                pos = pos / 1000.0
            return self._play_start_sec + pos
        except Exception:
            return None
