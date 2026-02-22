"""
회화 스튜디오: IStudio 구현.
LoadedContent 또는 CSV 로드·비디오 재생·문장/병음/번역 표시.
"""
import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

import pygame

from core.paths import STUDIO_HEIGHT, STUDIO_VIDEO_FALLBACK_FPS, STUDIO_WIDTH
from utils.fonts import load_font_chinese, load_font_chinese_freetype, load_font_korean

from studio.recording_events import (
    VideoSegmentStart,
    VideoSegmentEnd,
    InsertSound,
    recording_log_event,
    is_recording,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _data_list_from_loaded_content(content: Any) -> list[dict]:
    """LoadedContent에서 재생용 _data_list 생성. segment/overlay 쌍당 한 항목."""
    try:
        from data.models import LoadedContent
        content = content if isinstance(content, LoadedContent) else LoadedContent.model_validate(content)
    except Exception:
        return []
    segments = content.video_segments
    overlays = content.overlay_items
    n = min(len(segments), len(overlays))
    out = []
    for i in range(n):
        seg = segments[i]
        ov = overlays[i]
        # seg.file_path는 이미 get_loaded_content()에서 resource/... 를 repo 기준으로 해석한 경로
        out.append({
            "video_path": seg.file_path or "",
            "start_time": seg.start_time,
            "end_time": seg.end_time,
            "sentence": [ov.sentence or ov.text] if (ov.sentence or ov.text) else [],
            "translation": [ov.translation] if ov.translation else [],
            "pinyin": (ov.pinyin or "").strip(),
            "id": str(i),
            "topic": "",
            "index": i,
        })
    return out


def _parse_time_sec(val: Any, default: float = 0.0) -> float:
    """숫자 또는 문자열을 초 단위로 변환. 1000 초과면 ms로 간주."""
    try:
        x = float(val)
    except (TypeError, ValueError):
        return default
    if x > 1000:
        x = x / 1000.0
    return max(-1.0, x)


def _load_conversation_csv(csv_path: str) -> list[dict]:
    """CSV에서 회화 항목 리스트 로드. video_path는 resource/... 형태면 repo 기준으로 해석."""
    path = Path(csv_path)
    if not path.exists():
        return []
    repo = _REPO_ROOT

    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                topic = (row.get("topic") or "").strip()
                vid = (row.get("id") or "0").strip()
                video_path = (row.get("video_path") or "").strip()
                if not video_path and topic:
                    video_path = str(repo / "resource" / "video" / topic / f"{vid}.mp4")
                elif video_path and not os.path.isabs(video_path):
                    video_path = str(repo / video_path.replace("\\", "/"))
                if not os.path.exists(video_path):
                    video_path = ""
                sen = row.get("sentence", "[]")
                trans = row.get("translation", "[]")
                if isinstance(sen, str) and sen.startswith("["):
                    try:
                        sen = json.loads(sen)
                    except json.JSONDecodeError:
                        sen = [sen]
                if isinstance(trans, str) and trans.startswith("["):
                    try:
                        trans = json.loads(trans)
                    except json.JSONDecodeError:
                        trans = [trans]
                if not isinstance(sen, list):
                    sen = [str(sen)]
                if not isinstance(trans, list):
                    trans = [str(trans)]
                start_sec = _parse_time_sec(row.get("start_time") or row.get("start_ms", 0))
                end_raw = row.get("end_time") or row.get("end_ms") or row.get("split_ms")
                end_sec = _parse_time_sec(end_raw, default=-1.0) if end_raw not in (None, "") else -1.0
                if end_sec > 1000:
                    end_sec = end_sec / 1000.0
                rows.append({
                    "id": vid,
                    "topic": topic,
                    "video_path": video_path,
                    "start_time": start_sec,
                    "end_time": end_sec,
                    "sentence": sen,
                    "translation": trans,
                    "index": len(rows),
                })
            except Exception:
                continue
    return rows


class SimpleVideoPlayer:
    """단일 비디오 파일의 화면만 재생 (OpenCV로 비디오 스트림만 읽음, 오디오 미사용). start_time~end_time 구간만 재생, end_time=-1이면 끝까지."""
    def __init__(self) -> None:
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
        return self._end_time if self._end_time >= 0 else self._duration_sec

    def set_source(self, path: str, start_time: float = 0.0, end_time: float = -1.0) -> None:
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
        if self._paused or self._cap is None:
            return
        self._current_pts += dt_sec
        end_sec = self._effective_end_sec()
        if self._current_pts >= end_sec:
            self._current_pts = end_sec
            self._paused = True

    def seek(self, delta_sec: float) -> None:
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
        self._paused = not self._paused

    def is_paused(self) -> bool:
        return self._paused

    def get_frame(self, width: int, height: int) -> Optional[pygame.Surface]:
        if self._cap is None:
            return self._cached_surf
        try:
            return self._get_frame_impl(width, height)
        except Exception:
            return self._cached_surf

    def _get_frame_impl(self, width: int, height: int) -> Optional[pygame.Surface]:
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

        # 첫 프레임: seek 후 한 번만 읽고 캐시
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
        """BGR 프레임을 pygame Surface로. surfarray/scale 대신 OpenCV resize + frombuffer로 속도 확보."""
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
        return self._current_pts

    def get_fps(self) -> float:
        return self._fps


class VideoAudioPlayer:
    """비디오와 동일 경로·동일 이름의 추출된 MP3를 재생. 비디오 내장 음원은 사용하지 않음."""

    def __init__(self) -> None:
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
        if path == self._path and self._start_time == start_time:
            return
        self.stop()
        self._path = path
        self._start_time = start_time
        # 비디오 경로 → 동일 디렉터리·동일 이름의 .mp3 사용 (추출된 오디오만 재생)
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
        """메인 스레드에서 호출: 추출 완료된 오디오가 있으면 로드 후 재생."""
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
        with self._lock:
            return self._pending_wav is not None

    def seek_to(self, time_sec: float) -> None:
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
        self._paused = True
        try:
            pygame.mixer.music.pause()
        except Exception:
            pass

    def unpause(self) -> None:
        self._paused = False
        try:
            pygame.mixer.music.unpause()
        except Exception:
            pass

    def stop(self) -> None:
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
        """디버그용: 오디오 상태 문자열 (재생 중 / 일시정지 / 로딩 중 / 없음)."""
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
        """디버그/싱크용: 현재 오디오 재생 위치(초). 로드 안 됐으면 None."""
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


def _play_sound(path: str, config: Any = None) -> None:
    """별도 사운드 한 번 재생 (효과음·나레이션). 비디오 오디오와 별도 채널. config 있으면 녹화 시 InsertSound 로그."""
    if not path or not os.path.exists(path):
        return
    try:
        snd = pygame.mixer.Sound(path)
        ch = pygame.mixer.find_channel(True)
        if ch is not None:
            ch.play(snd)
        if config is not None:
            log_ev = getattr(config, "recording_log_event", None)
            timeline_sec = getattr(config, "recording_time_sec", 0.0)
            if log_ev is not None:
                duration_sec = snd.get_length()
                recording_log_event(log_ev, InsertSound(timeline_sec, path, duration_sec))
    except Exception:
        pass


class ConversationStudio:
    """회화 스튜디오: LoadedContent 또는 CSV 기반 비디오+문장/병음/번역 표시."""

    def __init__(
        self,
        csv_path: str = "",
        content: Any = None,
        **kwargs: Any,
    ) -> None:
        self._csv_path = csv_path
        if content is not None:
            self._data_list = _data_list_from_loaded_content(content)
        else:
            self._data_list = _load_conversation_csv(csv_path)
        self._current_index = 0
        self._video_player = SimpleVideoPlayer()
        self._video_audio = VideoAudioPlayer()
        # 폰트는 init()에서 로드 (러너가 pygame.init() 후 호출). 중국어는 freetype으로 로드 시 네모 방지
        self._font_cn_big: Optional[pygame.font.Font] = None
        self._font_cn: Optional[pygame.font.Font] = None
        self._font_cn_big_ft: Any = None  # pygame.freetype.Font (중국어 문장용)
        self._font_cn_ft: Any = None      # pygame.freetype.Font (병음용)
        self._font_kr: Optional[pygame.font.Font] = None
        self._font: Optional[pygame.font.Font] = None
        self._paused_label: Optional[pygame.Surface] = None
        self._last_sync_pts: float = -10.0
        self._recording_initial_logged: bool = False
        if self._data_list:
            item = self._data_list[0]
            path = self._resolve_video_path(item.get("video_path") or "")
            st = item.get("start_time", 0.0)
            et = item.get("end_time", -1.0)
            self._video_player.set_source(path, st, et)
            self._video_audio.set_source(path, st)

    def _resolve_video_path(self, path: str) -> str:
        """데이터 비디오 경로 해석. 테이블에 resource/... 형태로 들어 오므로 repo 루트 기준으로만 해석."""
        path = (path or "").strip()
        if not path:
            return ""
        if os.path.isabs(path):
            return path
        resolved = _REPO_ROOT / path.replace("\\", "/")
        return str(resolved)

    def _current_segment_times(self) -> tuple[float, float]:
        """현재 항목의 start_time, end_time. 없으면 (0.0, -1.0)."""
        if not self._data_list or self._current_index >= len(self._data_list):
            return 0.0, -1.0
        item = self._data_list[self._current_index]
        return item.get("start_time", 0.0), item.get("end_time", -1.0)

    def get_title(self) -> str:
        return "LVPD Studio - 회화"

    def handle_events(self, events: list, config: Any = None) -> bool:
        total = len(self._data_list)
        timeline_sec = getattr(config, "recording_time_sec", 0.0) if config else 0.0
        log_ev = getattr(config, "recording_log_event", None) if config else None
        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_SPACE:
                if total and self._current_index < total - 1:
                    if log_ev and self._data_list:
                        path = self._resolve_video_path(
                            self._data_list[self._current_index].get("video_path") or ""
                        )
                        if path:
                            recording_log_event(log_ev, VideoSegmentEnd(timeline_sec))
                    self._current_index += 1
                    item = self._data_list[self._current_index]
                    path = self._resolve_video_path(item.get("video_path") or "")
                    st = item.get("start_time", 0.0)
                    et = item.get("end_time", -1.0)
                    self._video_player.set_source(path, st, et)
                    self._video_audio.set_source(path, st)
                    self._last_sync_pts = -10.0
                    if self._video_player.is_paused():
                        self._video_player.toggle_pause()
                        self._video_audio.unpause()
                    if log_ev and path:
                        recording_log_event(
                            log_ev,
                            VideoSegmentStart(timeline_sec, path, st),
                        )
                continue
            if e.key == pygame.K_p:
                if log_ev and self._data_list:
                    path = self._resolve_video_path(
                        self._data_list[self._current_index].get("video_path") or ""
                    )
                    if path:
                        if self._video_player.is_paused():
                            recording_log_event(log_ev, VideoSegmentStart(
                                timeline_sec, path, self._video_player.get_pts()
                            ))
                        else:
                            recording_log_event(log_ev, VideoSegmentEnd(timeline_sec))
                self._video_player.toggle_pause()
                if self._video_player.is_paused():
                    self._video_audio.pause()
                else:
                    self._video_audio.unpause()
                continue
            if e.key in (pygame.K_HOME, pygame.K_r):
                start_sec, _ = self._current_segment_times()
                if log_ev and self._data_list:
                    path = self._resolve_video_path(
                        self._data_list[self._current_index].get("video_path") or ""
                    )
                    if path:
                        recording_log_event(log_ev, VideoSegmentEnd(timeline_sec))
                self._video_player.seek_to(start_sec)
                self._video_audio.seek_to(start_sec)
                if self._video_player.is_paused():
                    self._video_player.toggle_pause()
                    self._video_audio.unpause()
                if log_ev and self._data_list:
                    path = self._resolve_video_path(
                        self._data_list[self._current_index].get("video_path") or ""
                    )
                    if path:
                        recording_log_event(log_ev, VideoSegmentStart(timeline_sec, path, start_sec))
                continue
            if e.key in (pygame.K_LEFT, pygame.K_j):
                if log_ev and self._data_list:
                    path = self._resolve_video_path(
                        self._data_list[self._current_index].get("video_path") or ""
                    )
                    if path:
                        recording_log_event(log_ev, VideoSegmentEnd(timeline_sec))
                self._video_player.seek(-5.0)
                self._video_audio.seek_to(self._video_player.get_pts())
                if self._video_player.is_paused():
                    self._video_audio.pause()
                if log_ev and self._data_list:
                    path = self._resolve_video_path(
                        self._data_list[self._current_index].get("video_path") or ""
                    )
                    if path:
                        recording_log_event(log_ev, VideoSegmentStart(
                            timeline_sec, path, self._video_player.get_pts()
                        ))
                continue
            if e.key in (pygame.K_RIGHT, pygame.K_l):
                if log_ev and self._data_list:
                    path = self._resolve_video_path(
                        self._data_list[self._current_index].get("video_path") or ""
                    )
                    if path:
                        recording_log_event(log_ev, VideoSegmentEnd(timeline_sec))
                self._video_player.seek(5.0)
                self._video_audio.seek_to(self._video_player.get_pts())
                if self._video_player.is_paused():
                    self._video_audio.pause()
                if log_ev and self._data_list:
                    path = self._resolve_video_path(
                        self._data_list[self._current_index].get("video_path") or ""
                    )
                    if path:
                        recording_log_event(log_ev, VideoSegmentStart(
                            timeline_sec, path, self._video_player.get_pts()
                        ))
                continue
            if e.key == pygame.K_b or (e.key == pygame.K_LEFT and self._current_index > 0):
                if self._current_index > 0:
                    if log_ev and self._data_list:
                        path = self._resolve_video_path(
                            self._data_list[self._current_index].get("video_path") or ""
                        )
                        if path:
                            recording_log_event(log_ev, VideoSegmentEnd(timeline_sec))
                    self._current_index -= 1
                    item = self._data_list[self._current_index]
                    path = self._resolve_video_path(item.get("video_path") or "")
                    st = item.get("start_time", 0.0)
                    et = item.get("end_time", -1.0)
                    self._video_player.set_source(path, st, et)
                    self._video_audio.set_source(path, st)
                    self._last_sync_pts = -10.0
                    if log_ev and path:
                        recording_log_event(
                            log_ev,
                            VideoSegmentStart(timeline_sec, path, st),
                        )
        return True

    def update(self, config: Any = None) -> None:
        try:
            if self._video_audio.has_pending():
                self._video_audio._apply_pending()
            dt = 1.0 / 30.0
            if config is not None and getattr(config, "dt_sec", None):
                dt = config.dt_sec
            self._video_player.tick(dt)
            if not self._video_player.is_paused():
                self._sync_audio_to_video()
            # 세그먼트 end_time 도달 시 오디오도 일시정지 (비디오는 tick()에서 이미 정지됨)
            _, end_sec = self._current_segment_times()
            if end_sec >= 0 and self._video_player.get_pts() >= end_sec:
                self._video_audio.pause()
            # 녹화 타임라인: 첫 프레임에 현재 비디오 재생 구간 시작 로그
            if config is not None and is_recording(config) and self._data_list:
                if not self._recording_initial_logged:
                    path = self._resolve_video_path(
                        self._data_list[self._current_index].get("video_path") or ""
                    )
                    if path:
                        recording_log_event(
                            getattr(config, "recording_log_event", None),
                            VideoSegmentStart(
                                getattr(config, "recording_time_sec", 0.0),
                                path,
                                self._video_player.get_pts(),
                            ),
                        )
                    self._recording_initial_logged = True
        except Exception:
            pass

    def _sync_audio_to_video(self) -> None:
        """클립당 한 번만 오디오를 비디오 PTS에 맞춤 (로딩 지연 보정). 반복 seek로 인한 끊김 방지."""
        if self._last_sync_pts >= 0:
            return
        video_pts = self._video_player.get_pts()
        audio_pos = self._video_audio.get_position_sec()
        if audio_pos is None:
            return
        drift = video_pts - audio_pos
        if abs(drift) > 0.15:
            self._video_audio.seek_to(video_pts)
        self._last_sync_pts = video_pts

    def init(self, config: Any = None) -> None:
        """pygame.init() 이후 러너가 한 번 호출. 폰트 등 리소스 로드."""
        if self._font_kr is not None:
            return
        from core.paths import DEFAULT_FONT_DIR, FONT_CN_FILENAME
        self._font_cn_big = load_font_chinese(36)
        self._font_cn = load_font_chinese(28)
        self._font_cn_big_ft = load_font_chinese_freetype(36)
        self._font_cn_ft = load_font_chinese_freetype(28)
        self._font_kr = load_font_korean(28)
        if self._font_cn_big is None:
            self._font_cn_big = pygame.font.Font(None, 36)
            import logging
            logging.getLogger(__name__).warning(
                "중국어 폰트 미로드 → 기본 폰트 사용(중국어 네모 가능). 다음 경로에 %s 넣기: %s",
                FONT_CN_FILENAME, DEFAULT_FONT_DIR.resolve(),
            )
        if self._font_cn is None:
            self._font_cn = pygame.font.Font(None, 28)
        if self._font_kr is None:
            self._font_kr = pygame.font.Font(None, 28)
        self._font = self._font_kr

    def draw(self, screen: Any, config: Any) -> None:
        try:
            self._draw_impl(screen, config)
        except Exception:
            screen.fill((40, 40, 50))
            font = self._font_kr or pygame.font.Font(None, 28)
            err = font.render("그리기 오류", True, (200, 100, 100))
            screen.blit(err, (20, 20))

    def _draw_impl(self, screen: Any, config: Any) -> None:
        w, h = config.width, config.height
        screen.fill(config.bg_color)

        if self._data_list:
            item = self._data_list[self._current_index]
            # 비디오 출력 위치: (0, 0) 전체 화면. 데이터의 video_path는 _resolve_video_path로 repo 기준 재생
            vid_surf = self._video_player.get_frame(w, h)
            if vid_surf is not None:
                screen.blit(vid_surf, (0, 0))
            else:
                pygame.draw.rect(screen, (40, 40, 50), (0, 0, w, h))
                font_kr = self._font_kr or pygame.font.Font(None, 28)
                no_vid = font_kr.render("(비디오 없음)", True, (180, 180, 180))
                screen.blit(no_vid, (w // 2 - 50, h // 2 - 14))

            font_cn_big = self._font_cn_big or pygame.font.Font(None, 36)
            font_cn = self._font_cn or pygame.font.Font(None, 28)
            font_kr = self._font_kr or pygame.font.Font(None, 28)
            sentences = item.get("sentence") or []
            translations = item.get("translation") or []
            pinyin_text = item.get("pinyin") or ""
            sen_text = " ".join(str(x) for x in sentences[:3]) if sentences else "(문장 없음)"
            trans_text = " ".join(str(x) for x in translations[:3]) if translations else ""
            y_pos = int(h * 0.75)
            # 문장 (중국어) — freetype 사용 시 CJK 네모 방지
            if self._font_cn_big_ft is not None:
                try:
                    sen_surf, _ = self._font_cn_big_ft.render(sen_text[:80], (255, 255, 255))
                    screen.blit(sen_surf, (20, y_pos))
                except Exception:
                    sen_surf = font_cn_big.render(sen_text[:80], True, (255, 255, 255))
                    screen.blit(sen_surf, (20, y_pos))
            else:
                sen_surf = font_cn_big.render(sen_text[:80], True, (255, 255, 255))
                screen.blit(sen_surf, (20, y_pos))
            # 병음 (성조 기호) — freetype 사용 시 CJK 네모 방지
            if pinyin_text:
                if self._font_cn_ft is not None:
                    try:
                        pinyin_surf, _ = self._font_cn_ft.render(pinyin_text[:120], (220, 220, 180))
                        screen.blit(pinyin_surf, (20, y_pos + 36))
                    except Exception:
                        pinyin_surf = font_cn.render(pinyin_text[:120], True, (220, 220, 180))
                        screen.blit(pinyin_surf, (20, y_pos + 36))
                else:
                    pinyin_surf = font_cn.render(pinyin_text[:120], True, (220, 220, 180))
                    screen.blit(pinyin_surf, (20, y_pos + 36))
            # 번역 (한국어) — 한국어 폰트
            if trans_text:
                trans_surf = font_kr.render(trans_text[:80], True, (200, 200, 200))
                screen.blit(trans_surf, (20, y_pos + (72 if pinyin_text else 36)))
        else:
            font_kr = self._font_kr or pygame.font.Font(None, 28)
            msg = font_kr.render("데이터 없음 (CSV 로드 실패 또는 비어 있음)", True, (180, 180, 180))
            screen.blit(msg, (20, h // 2 - 14))

        if self._video_player.is_paused():
            if self._paused_label is None:
                font_kr = self._font_kr or pygame.font.Font(None, 36)
                self._paused_label = font_kr.render("일시정지", True, (255, 255, 0))
            if self._paused_label is not None:
                px, py = config.get_pos(0.08, 0.05)
                screen.blit(self._paused_label, (px, py))

        # 디버그 렌더: FPS, 비디오 FPS, PTS, 오디오(현재 미재생) — 한국어 폰트
        actual_fps = getattr(config, "actual_fps", 0.0)
        if actual_fps >= 0:
            font_kr = self._font_kr or pygame.font.Font(None, 28)
            vid_fps = self._video_player.get_fps()
            pts = self._video_player.get_pts()
            audio_status = self._video_audio.get_status()
            audio_pos = self._video_audio.get_position_sec()
            if audio_pos is not None:
                sync_drift = pts - audio_pos
                lines = [
                    f"FPS: {actual_fps:.1f}",
                    f"Video FPS: {vid_fps:.1f}",
                    f"PTS: {pts:.2f}s",
                    f"Audio: {audio_status} | {audio_pos:.2f}s",
                    f"Sync: {'+' if sync_drift >= 0 else ''}{sync_drift:.3f}s (vid−aud)",
                ]
            else:
                lines = [
                    f"FPS: {actual_fps:.1f}",
                    f"Video FPS: {vid_fps:.1f}",
                    f"PTS: {pts:.2f}s",
                    f"Audio: {audio_status}",
                ]
            y_debug = 8
            for line in lines:
                surf = font_kr.render(line, True, (0, 255, 128))
                screen.blit(surf, (8, y_debug))
                y_debug += 22

    def get_recording_prefix(self) -> Optional[str]:
        if not self._data_list:
            return None
        item = self._data_list[self._current_index]
        vid = item.get("id", 0)
        return f"REC_{vid}"
