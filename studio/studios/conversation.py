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
import time
from pathlib import Path
from typing import Any, Optional

import pygame

from core.paths import STUDIO_HEIGHT, STUDIO_VIDEO_FALLBACK_FPS, STUDIO_WIDTH
from utils.fonts import load_font_chinese, load_font_chinese_freetype, load_font_korean
from utils.pinyin_processor import (
    SANDHI_TYPE_LABELS,
    diff_lexical_phonetic_per_syllable,
    get_pinyin_processor,
    parse_tone_from_syllable,
)
from utils.syllable_timing import parse_syllable_times_ms

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
    audio_tracks = getattr(content, "audio_tracks", []) or []
    n = min(len(segments), len(overlays))
    processor = get_pinyin_processor()
    table_rows = []
    try:
        from data.table_manager import get_table
        table_rows = get_table() or []
    except Exception:
        pass
    out = []
    for i in range(n):
        seg = segments[i]
        ov = overlays[i]
        sen_raw = ov.sentence or ov.text
        if isinstance(sen_raw, list):
            sen_str = str(sen_raw[0]) if sen_raw else ""
        else:
            sen_str = str(sen_raw or "")
        pinyin_sandhi_types = processor.get_sandhi_types(sen_str) if sen_str and processor.available else []
        sound_l1 = audio_tracks[2 * i].sound_path if len(audio_tracks) > 2 * i else ""
        sound_l2 = audio_tracks[2 * i + 1].sound_path if len(audio_tracks) > 2 * i + 1 else ""
        row = table_rows[i] if i < len(table_rows) else {}
        syllable_times_l1 = parse_syllable_times_ms(str(row.get("syllable_times_l1_ms") or "").strip())
        syllable_times_l2 = parse_syllable_times_ms(str(row.get("syllable_times_l2_ms") or "").strip())
        out.append({
            "video_path": seg.file_path or "",
            "start_time": seg.start_time,
            "end_time": seg.end_time,
            "sentence": [ov.sentence or ov.text] if (ov.sentence or ov.text) else [],
            "translation": [ov.translation] if ov.translation else [],
            "pinyin": (ov.pinyin or "").strip(),  # 성조표기병음 (성조 기호)
            "pinyin_phonetic": (ov.pinyin_phonetic or "").strip(),  # 발음 병음
            "pinyin_lexical": (ov.pinyin_lexical or "").strip(),  # 표기 병음
            "pinyin_sandhi_types": pinyin_sandhi_types,  # 음절별 성조변화 타입 (표시용)
            "sound_l1": sound_l1,
            "sound_l2": sound_l2,
            "syllable_times_l1": syllable_times_l1,
            "syllable_times_l2": syllable_times_l2,
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
        self._font_cn_step1_ft: Any = None  # Step 1 중앙 한자용 (큰 글자)
        self._font_cn_step1_pinyin_ft: Any = None  # Step 1 병음용 (더 큰 글자)
        self._font_kr: Optional[pygame.font.Font] = None
        self._font_kr_step1: Optional[pygame.font.Font] = None  # Step 1 해석용 (더 큰 글자)
        self._font: Optional[pygame.font.Font] = None
        self._paused_label: Optional[pygame.Surface] = None
        self._last_sync_pts: float = -10.0
        self._recording_initial_logged: bool = False
        self._shadowing_step: int = 1  # 셰도잉 훈련 단계 (1=원어민 속도로 듣기)
        self._tone_surfaces: dict[str, Any] = {}  # tone 파일명 -> Surface (resource/image/icon)
        self._listen_panda_surface: Any = None  # 듣기 이미지 영역용 (스케일 캐시)
        self._listen_panda_cached_size: tuple[int, int] = (0, 0)
        # Step 1: UI 일괄 on/off. 영상 재생 중엔 off, 멈추면 서서히 어둡게 한 뒤 on
        self._ui_visible: bool = False
        self._fade_alpha: float = 0.0  # 0~75%, 멈춤 시 증가 후 UI on
        self._fade_overlay_surface: Any = None
        self._fade_overlay_size: tuple[int, int] = (0, 0)
        # Step 1 테이블 사운드: 이번 일시정지에서 L1→L2 한 번만 재생
        self._step1_sound_schedule: Optional[str] = None  # None | "playing_l1" | "playing_l2"
        self._step1_l1_channel: Any = None  # L1 재생 채널 (get_busy()로 종료 감지)
        self._step1_l2_channel: Any = None  # L2 재생 채널 (위치·종료 감지)
        self._step1_l1_play_start_time: Optional[float] = None  # L1 재생 시작 시각 (time.time()), pygame.Channel에 get_position 없음
        self._step1_l2_play_start_time: Optional[float] = None  # L2 재생 시작 시각
        self._step1_graph_display_ratio: float = 0.0  # 0~1, 시간 보간된 곡선 진행도 (구간 시간 반영)
        self._step1_graph_item_id: Any = None  # 그래프 리셋용 (문장 바뀌면 0으로)
        self._step1_sounds_played_this_pause: bool = False  # 이번 pause에서 이미 L1/L2 재생했으면 True
        # 녹화 모드: 이전 프레임 상태 (세그먼트·일시정지 전환 시 이벤트 로그용)
        self._last_recording_seg_idx: int = -1
        self._last_recording_paused: bool = False
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

    def set_ui_visible(self, visible: bool) -> None:
        """Step 1 UI(타이틀·병음·한자·해석·듣기 이미지 등)를 한꺼번에 on/off."""
        self._ui_visible = visible
        if not visible:
            self._fade_alpha = 0.0

    def _current_segment_times(self) -> tuple[float, float]:
        """현재 항목의 start_time, end_time. 없으면 (0.0, -1.0)."""
        if not self._data_list or self._current_index >= len(self._data_list):
            return 0.0, -1.0
        item = self._data_list[self._current_index]
        return item.get("start_time", 0.0), item.get("end_time", -1.0)

    def _current_shadowing_step(self) -> int:
        """현재 셰도잉 훈련 단계. Step 2 이상에서 비디오 오버레이 등 분기용."""
        return self._shadowing_step

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
            # 녹화(배치) 모드: recording_time_sec으로 세그먼트·일시정지·fade·UI 동기화 → 디버그 출력과 동일한 프레임 생성
            if config is not None and is_recording(config) and self._data_list:
                self._sync_recording_timeline(config)
            else:
                self._video_player.tick(dt)
                if not self._video_player.is_paused():
                    self._sync_audio_to_video()
            # Step 1: 전용 제어 (fade, UI on/off, 테이블 사운드 L1 → L2). 녹화 모드에선 _sync_recording_timeline에서 이미 반영
            if self._shadowing_step == 1 and not (config and is_recording(config)):
                self._update_step1(config)
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

    def _sync_recording_timeline(self, config: Any) -> None:
        """녹화(배치) 모드: recording_time_sec으로 세그먼트·일시정지·fade·UI를 동기화해 디버그와 동일한 프레임을 만든다."""
        t = getattr(config, "recording_time_sec", 0.0)
        data = self._data_list
        n = len(data)
        if n == 0:
            return
        # 세그먼트별 재생 구간 길이 (녹화 타임라인 상)
        seg_durations: list[float] = []
        for i in range(n):
            st = data[i].get("start_time", 0.0) or 0.0
            et = data[i].get("end_time", -1.0)
            if et is None or et < 0:
                et = st + 10.0
            seg_durations.append(max(0.1, et - st))
        # 현재 시각 t에 해당하는 세그먼트 인덱스와 구간 내 로컬 시간
        cum = 0.0
        seg_idx = 0
        local_t = t
        for i in range(n):
            d = seg_durations[i]
            if t < cum + d:
                seg_idx = i
                local_t = t - cum
                break
            cum += d
        else:
            seg_idx = n - 1
            local_t = t - (cum - seg_durations[-1])
        log_ev = getattr(config, "recording_log_event", None)
        path_cur = self._resolve_video_path(data[self._current_index].get("video_path") or "")

        if seg_idx != self._current_index:
            if log_ev and path_cur:
                recording_log_event(log_ev, VideoSegmentEnd(t))
            self._current_index = seg_idx
            item = data[seg_idx]
            path = self._resolve_video_path(item.get("video_path") or "")
            st = item.get("start_time", 0.0) or 0.0
            et = item.get("end_time", -1.0)
            self._video_player.set_source(path, st, et)
            self._video_audio.set_source(path, st)
            self._last_sync_pts = -10.0
            self._last_recording_seg_idx = seg_idx
            self._last_recording_paused = False
            if log_ev and path:
                recording_log_event(log_ev, VideoSegmentStart(t, path, st))
        item = data[self._current_index]
        seg_start = item.get("start_time", 0.0) or 0.0
        path_cur = self._resolve_video_path(item.get("video_path") or "")
        # 세그먼트 내 "일시정지" 구간: 0.5초~2.5초 (fade 후 UI 표시) → 디버그에서 멈춘 것과 동일한 화면
        pause_start, pause_end = 0.5, 2.5
        in_pause = pause_start <= local_t < pause_end
        if in_pause != self._last_recording_paused:
            if in_pause and log_ev and path_cur:
                recording_log_event(log_ev, VideoSegmentEnd(t))
            elif not in_pause and log_ev and path_cur:
                recording_log_event(log_ev, VideoSegmentStart(t, path_cur, seg_start + local_t))
            self._last_recording_paused = in_pause
        if seg_idx != self._last_recording_seg_idx:
            self._last_recording_seg_idx = seg_idx

        if in_pause:
            self._video_player.seek_to(seg_start + pause_start)
            if not self._video_player.is_paused():
                self._video_player.toggle_pause()
            self._video_audio.pause()
            fade_elapsed = local_t - pause_start
            self._fade_alpha = min(191.25, fade_elapsed * 180.0)  # 180/초 ≈ 6/프레임@30fps
            self._ui_visible = self._fade_alpha >= 191.25
            self._step1_sound_schedule = None
            self._step1_l1_channel = None
            self._step1_l2_channel = None
        else:
            self._video_player.seek_to(seg_start + local_t)
            if self._video_player.is_paused():
                self._video_player.toggle_pause()
            self._video_audio.seek_to(seg_start + local_t)
            self._video_audio.unpause()
            self._fade_alpha = 0.0
            self._ui_visible = False
            self._step1_sound_schedule = None
            self._step1_l1_channel = None
            self._step1_l2_channel = None
            self._step1_sounds_played_this_pause = False  # 다음 멈춤에서 다시 L1→L2 재생 가능

    def _update_step1(self, config: Any) -> None:
        """Step 1 제어: 영상 멈춤 시 fade 후 UI on, 테이블 사운드 레벨1 한 번 재생 → 끝나면 레벨2 재생."""
        if self._video_player.is_paused():
            self._fade_alpha = min(191.25, self._fade_alpha + 6.0)
            if self._fade_alpha >= 191.25:
                self._ui_visible = True
                # UI on 직후 이번 pause에서 아직 안 재생했을 때만 레벨1 한 번 재생
                if not self._step1_sounds_played_this_pause and self._step1_sound_schedule is None and self._data_list:
                    self._step1_sounds_played_this_pause = True
                    item = self._data_list[self._current_index]
                    path = (item.get("sound_l1") or "").strip()
                    if path and os.path.exists(path):
                        try:
                            snd = pygame.mixer.Sound(path)
                            ch = pygame.mixer.find_channel(True)
                            self._step1_sound_schedule = "playing_l1"
                            if ch is not None:
                                ch.play(snd)
                                self._step1_l1_channel = ch
                                self._step1_l1_play_start_time = time.time()
                            else:
                                self._step1_l1_channel = None
                                self._step1_l1_play_start_time = None
                        except Exception:
                            self._step1_l1_channel = None
                            self._step1_l1_play_start_time = None
                            self._step1_sound_schedule = "playing_l1"
                    else:
                        self._step1_sound_schedule = "playing_l1"
                        self._step1_l1_channel = None
                        self._step1_l1_play_start_time = None
            # L1 재생 중 → 채널이 끝나면 레벨2 한 번만 재생 후 스케줄 종료
            if self._step1_sound_schedule == "playing_l1" and self._data_list:
                if self._step1_l1_channel is None or not self._step1_l1_channel.get_busy():
                    self._step1_l1_channel = None
                    self._step1_l1_play_start_time = None
                    self._step1_sound_schedule = None
                    item = self._data_list[self._current_index]
                    path = (item.get("sound_l2") or "").strip()
                    if path and os.path.exists(path):
                        try:
                            snd = pygame.mixer.Sound(path)
                            ch = pygame.mixer.find_channel(True)
                            if ch is not None:
                                ch.play(snd)
                                self._step1_l2_channel = ch
                                self._step1_l2_play_start_time = time.time()
                                self._step1_sound_schedule = "playing_l2"
                        except Exception:
                            pass
            # L2 재생 중 → 채널이 끝나면 스케줄만 정리
            if self._step1_sound_schedule == "playing_l2":
                if self._step1_l2_channel is None or not self._step1_l2_channel.get_busy():
                    self._step1_l2_channel = None
                    self._step1_l2_play_start_time = None
                    self._step1_sound_schedule = None
        else:
            self._fade_alpha = 0.0
            self._ui_visible = False
            self._step1_sound_schedule = None
            self._step1_l1_channel = None
            self._step1_l2_channel = None
            self._step1_l1_play_start_time = None
            self._step1_l2_play_start_time = None

    def init(self, config: Any = None) -> None:
        """pygame.init() 이후 러너가 한 번 호출. 폰트 등 리소스 로드."""
        if self._font_kr is not None:
            return
        from core.paths import DEFAULT_FONT_DIR, FONT_CN_FILENAME
        self._font_cn_big = load_font_chinese(36)
        self._font_cn = load_font_chinese(28)
        self._font_cn_big_ft = load_font_chinese_freetype(36)
        self._font_cn_ft = load_font_chinese_freetype(28)
        self._font_cn_step1_ft = load_font_chinese_freetype(124)  # Step 1 중앙 한자용 (더 크게)
        if self._font_cn_step1_ft is None:
            self._font_cn_step1_ft = self._font_cn_big_ft  # 폴백
        self._font_cn_step1_pinyin_ft = load_font_chinese_freetype(66)  # Step 1 병음용
        if self._font_cn_step1_pinyin_ft is None:
            self._font_cn_step1_pinyin_ft = self._font_cn_ft
        self._font_kr = load_font_korean(28)
        self._font_kr_step1 = load_font_korean(56)  # Step 1 해석용 (더 크게)
        if self._font_kr_step1 is None:
            self._font_kr_step1 = self._font_kr
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
        except Exception as e:
            screen.fill((40, 40, 50))
            font = self._font_kr or pygame.font.Font(None, 28)
            err = font.render("그리기 오류", True, (200, 100, 100))
            screen.blit(err, (20, 20))
            try:
                import traceback
                msg = f"{type(e).__name__}: {e}"
                if font.get_height() and len(msg) > 80:
                    msg = msg[:77] + "..."
                line2 = font.render(msg, True, (220, 180, 180))
                screen.blit(line2, (20, 52))
                traceback.print_exc()
            except Exception:
                pass

    def _draw_impl(self, screen: Any, config: Any) -> None:
        w, h = config.width, config.height
        screen.fill(config.bg_color)

        # 셰도잉 Step 1: 백그라운드 영상 → (멈춤 시 서서히 어두운 오버레이) → UI on 시에만 병음/한자/해석
        if self._shadowing_step == 1:
            vid_surf = self._video_player.get_frame(w, h)
            if vid_surf is not None:
                screen.blit(vid_surf, (0, 0))
            if self._fade_alpha > 0:
                if self._fade_overlay_surface is None or self._fade_overlay_size != (w, h):
                    self._fade_overlay_surface = pygame.Surface((w, h))
                    self._fade_overlay_surface.fill((0, 0, 0))
                    self._fade_overlay_size = (w, h)
                self._fade_overlay_surface.set_alpha(int(min(192, self._fade_alpha)))  # 최대 75%
                screen.blit(self._fade_overlay_surface, (0, 0))
            if self._ui_visible:
                self._draw_step1(screen, config)
            self._draw_paused_and_debug(screen, config)
            return

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
            # 병음 (성조 기호) — 붉은색
            if pinyin_text:
                if self._font_cn_ft is not None:
                    try:
                        pinyin_surf, _ = self._font_cn_ft.render(pinyin_text[:120], (220, 70, 70))
                        screen.blit(pinyin_surf, (20, y_pos + 36))
                    except Exception:
                        pinyin_surf = font_cn.render(pinyin_text[:120], True, (220, 70, 70))
                        screen.blit(pinyin_surf, (20, y_pos + 36))
                else:
                    pinyin_surf = font_cn.render(pinyin_text[:120], True, (220, 70, 70))
                    screen.blit(pinyin_surf, (20, y_pos + 36))
            # 번역 (한국어) — 한국어 폰트
            if trans_text:
                trans_surf = font_kr.render(trans_text[:80], True, (200, 200, 200))
                screen.blit(trans_surf, (20, y_pos + (72 if pinyin_text else 36)))
        else:
            font_kr = self._font_kr or pygame.font.Font(None, 28)
            msg = font_kr.render("데이터 없음 (CSV 로드 실패 또는 비어 있음)", True, (180, 180, 180))
            screen.blit(msg, (20, h // 2 - 14))

        self._draw_paused_and_debug(screen, config)

    def _draw_step1(self, screen: Any, config: Any) -> None:
        """셰도잉 Step 1: 좌측 듣기 이미지(플레이스홀더), 중앙 병음/한자/해석, 하단 안내 문구."""
        w, h = config.width, config.height
        font_kr = self._font_kr or pygame.font.Font(None, 28)
        font_cn = self._font_cn or pygame.font.Font(None, 28)
        font_cn_big = self._font_cn_big or pygame.font.Font(None, 36)
        font_kr_step1 = self._font_kr_step1 or font_kr

        if not self._data_list:
            msg = font_kr.render("데이터 없음 (CSV 로드 실패 또는 비어 있음)", True, (180, 180, 180))
            r = msg.get_rect(center=(w // 2, h // 2))
            screen.blit(msg, r)
            return

        item = self._data_list[self._current_index]
        sentences = item.get("sentence") or []
        translations = item.get("translation") or []
        pinyin_text = (item.get("pinyin") or "").strip()
        pinyin_lexical = (item.get("pinyin_lexical") or "").strip()
        pinyin_phonetic = (item.get("pinyin_phonetic") or "").strip()
        sen_text = " ".join(str(x) for x in sentences) if sentences else "(문장 없음)"
        trans_text = " ".join(str(x) for x in translations) if translations else ""

        # 상단 타이틀: 쉐도잉 훈련 Step 1: (흰색) + 원어민 속도 듣기 (주황) — bold/extrabold, 크게
        title_font = getattr(self, "_font_step1_title", None) or load_font_korean(52, weight="bold") or load_font_korean(52, weight="extrabold") or load_font_korean(52)
        self._font_step1_title = title_font
        if title_font is not None:
            cx = w // 2
            title_y = int(h * 0.06)
            part1 = title_font.render("쉐도잉 훈련 Step 1:", True, (255, 255, 255))
            part2 = title_font.render(" 원어민 속도 듣기", True, (255, 140, 0))
            r1, r2 = part1.get_rect(), part2.get_rect()
            total_w = r1.width + r2.width
            x1 = cx - total_w // 2
            screen.blit(part1, (x1, title_y))
            screen.blit(part2, (x1 + r1.width, title_y))

        # 좌측: 듣기 이미지 — resource/image/icon/listen_panda.png (영역/테두리 없이 이미지만)
        left_x, left_y = config.get_pos(0.02, 0.20)
        left_w, left_h = config.get_size(0.20, 0.36)
        icon_dir = _REPO_ROOT / "resource" / "image" / "icon"
        listen_path = icon_dir / "listen_panda.png"
        if (self._listen_panda_cached_size != (left_w, left_h) or self._listen_panda_surface is None) and listen_path.exists():
            try:
                surf = pygame.image.load(str(listen_path))
                if surf.get_alpha() is None:
                    surf = surf.convert()
                else:
                    surf = surf.convert_alpha()
                self._listen_panda_surface = pygame.transform.smoothscale(surf, (left_w, left_h))
                self._listen_panda_cached_size = (left_w, left_h)
            except Exception:
                self._listen_panda_surface = None
                self._listen_panda_cached_size = (0, 0)
        if self._listen_panda_surface is not None:
            screen.blit(self._listen_panda_surface, (left_x, left_y))
        else:
            placeholder = font_kr.render("듣기 이미지 (추가 예정)", True, (140, 140, 150))
            pr = placeholder.get_rect(center=(left_x + left_w // 2, left_y + left_h // 2))
            screen.blit(placeholder, pr)

        # 병음·한자·해석 모두 화면 가운데 정렬
        cx = w // 2
        center_top = int(h * 0.38)
        line_gap = 96

        pinyin_ft = self._font_cn_step1_pinyin_ft or self._font_cn_ft
        # 발음 병음도 같은 폰트(pinyin_ft)로 그려야 표기 병음과 위아래 정렬이 맞음 (폰트 차이로 틀어짐 방지)
        diff_ft = pinyin_ft
        _tone_contour_enabled = True   # 병음 위 성조선 표시
        _phonetic_diff_enabled = True  # 발음 병음(주황 텍스트) 표시
        _punct_set = frozenset("?.,，．？!！、。；;：:")

        def _is_punct_only(s: str) -> bool:
            t = s.strip()
            return len(t) <= 2 and all(c in _punct_set for c in t)

        def _align_pinyin_with_hanzi(sen_chars: str, syllables: list[str]) -> tuple[str, list[str], bool]:
            """한자 문장(구두점 포함)과 병음 음절을 1:1로 맞춰, 병음 줄에 구두점을 끼워 넣은 문자열과 음절별 prefix 반환.
            반환: (display_pinyin, prefix_before_syllable, aligned). aligned=False면 prefix는 사용하지 않고 호출처에서 기존 방식으로 계산.
            """
            parts: list[str] = []
            syl_idx = 0
            for c in sen_chars:
                if c in _punct_set or c.isspace():
                    parts.append(c)
                else:
                    if syl_idx < len(syllables):
                        parts.append(syllables[syl_idx])
                        syl_idx += 1
            if syl_idx != len(syllables):
                return (" ".join(syllables), [], False)

            # 음절 사이에만 공백, 구두점은 붙여서
            display = ""
            prefix_before_syllable: list[str] = []
            for i, p in enumerate(parts):
                if p not in _punct_set and not p.isspace():
                    prefix_before_syllable.append(display)
                display += p
                if i + 1 < len(parts) and p not in _punct_set and not p.isspace() and parts[i + 1] not in _punct_set and not parts[i + 1].isspace():
                    display += " "
            prefix_before_syllable.append(display)
            return (display, prefix_before_syllable, True)

        if pinyin_text:
            syllables = pinyin_text.strip().split()
            diff_per = diff_lexical_phonetic_per_syllable(pinyin_lexical, pinyin_phonetic)
            while len(diff_per) < len(syllables):
                diff_per.append(None)
            diff_per = diff_per[: len(syllables)]
            def _render_syllable(font_ft: Any, font_pg: Any, text: str, color: tuple) -> tuple[Any, Any]:
                if font_ft is not None:
                    try:
                        surf, rect = font_ft.render(text, color)
                        return surf, rect
                    except Exception:
                        pass
                surf = font_pg.render(text, True, color)
                return surf, surf.get_rect()

            # 한자와 칸 맞춤: 병음 줄에 구두점(! , ? 등)을 같은 위치에 끼워 넣기
            sen_chars = "".join(str(x) for x in sentences)
            display_pinyin, prefix_before_syllable, pinyin_aligned = _align_pinyin_with_hanzi(sen_chars, syllables)
            display_syllables: list[tuple[str, Optional[str]]] = [
                (syllables[i], diff_per[i] if i < len(diff_per) else None)
                for i in range(len(syllables))
                if not _is_punct_only(syllables[i])
            ]
            # 본래 성조: diff에 성조가 없을 때 pinyin_lexical 음절 참고
            lexical_syllables = (pinyin_lexical or "").strip().split()
            while len(lexical_syllables) < len(syllables):
                lexical_syllables.append("")
            lexical_syllables = lexical_syllables[: len(syllables)]
            lexical_for_display: list[str] = [
                lexical_syllables[i]
                for i in range(len(syllables))
                if not _is_punct_only(syllables[i])
            ]

            space_surf, space_rect = _render_syllable(pinyin_ft, font_cn, " ", (220, 70, 70))
            space_w = space_rect.width if space_rect else 8
            y_red_top = center_top
            pinyin_hanzi_gap = 180  # 병음 아래 ~ 한자 위 여유
            contour_gap = 4
            contour_height = 16
            line_color = (255, 180, 80)
            line_thickness = 5  # 성조선 진하게

            # 표기 병음: 한 줄 렌더 (구두점 포함) → 한자와 칸 맞춤
            line_surf, line_rect = _render_syllable(pinyin_ft, font_cn, display_pinyin, (220, 70, 70))
            x_start = cx - line_rect.width // 2
            screen.blit(line_surf, (x_start, y_red_top))
            # 칸 위치: 실제로 그리는 display_pinyin의 앞부분을 잘라서 측정 → 뒷부분 커닝/위치 일치
            n_syl = len(display_syllables)
            prefix_w: list[float] = []
            if pinyin_aligned and len(prefix_before_syllable) >= n_syl + 1:
                for i in range(n_syl + 1):
                    # prefix_before_syllable[i]와 같은 길이의 display_pinyin 앞부분으로 측정 (한 번에 그린 줄과 동일 커닝)
                    prefix_len = len(prefix_before_syllable[i])
                    chunk = display_pinyin[:prefix_len] if prefix_len <= len(display_pinyin) else prefix_before_syllable[i]
                    _, r = _render_syllable(pinyin_ft, font_cn, chunk, (220, 70, 70))
                    prefix_w.append(r.width)
            else:
                # 정렬 실패 시에도 실제 그린 줄에서 음절 시작 위치를 찾아 동그라미 위치 맞춤
                fallback_pinyin = " ".join(syllables)
                pos = 0
                syllable_starts: list[int] = []
                for syl, _ in display_syllables:
                    idx = fallback_pinyin.find(syl, pos)
                    if idx >= 0:
                        syllable_starts.append(idx)
                        pos = idx + len(syl)
                    else:
                        syllable_starts.append(pos)
                for i in range(n_syl + 1):
                    if i == 0:
                        prefix_w.append(0.0)
                    elif i < len(syllable_starts):
                        chunk = fallback_pinyin[: syllable_starts[i]]
                        _, r = _render_syllable(pinyin_ft, font_cn, chunk, (220, 70, 70))
                        prefix_w.append(r.width)
                    else:
                        prefix_w.append(line_rect.width)

            # 성조 표기 규칙: 표기 병음에서 성조가 붙는 모음(āéǐ 등) 위치 = 병음이 표기되는 정확한 위치
            _TONED_VOWELS = frozenset("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ")

            def _tonic_vowel_index(s: str) -> Optional[int]:
                """표기 병음 문자열에서 성조가 붙은 모음의 인덱스. 없으면 None(경성 등)."""
                for i, c in enumerate(s):
                    if c in _TONED_VOWELS:
                        return i
                return None

            def _tonic_center_x(slot_left: int, syl: str) -> int:
                """붉은 표기 병음에서 성조가 붙는 모음(병음표시 위치) 바로 위에 동그라미 → 해당 모음 중심 x."""
                idx = _tonic_vowel_index(syl)
                if idx is None:
                    _, r = _render_syllable(pinyin_ft, font_cn, syl, (220, 70, 70))
                    return slot_left + r.width // 2
                _, r_prefix = _render_syllable(pinyin_ft, font_cn, syl[:idx], (220, 70, 70))
                _, r_char = _render_syllable(pinyin_ft, font_cn, syl[idx], (220, 70, 70))
                return slot_left + r_prefix.width + r_char.width // 2

            def _draw_tone_contour(surf: Any, left: int, bottom: int, width: int, tone: float) -> None:
                """성조 시각화: 1=고평, 2=상승, 3=V자, 3.5=반3성 내려가서 끊김, 4=하강, 5/0=중평."""
                top = bottom - contour_height
                mid_y = (top + bottom) // 2
                right = left + width
                mid_x = (left + right) // 2
                left, right, top, bottom = int(left), int(right), int(top), int(bottom)
                mid_x, mid_y = int(mid_x), int(mid_y)
                is_half_third = 3.4 <= tone <= 3.6
                if tone <= 0.5 or tone >= 4.5:
                    pygame.draw.line(surf, line_color, (left, mid_y), (right, mid_y), line_thickness)
                elif 1 <= tone < 1.5:
                    pygame.draw.line(surf, line_color, (left, top), (right, top), line_thickness)
                elif 2 <= tone < 2.5:
                    pygame.draw.line(surf, line_color, (left, bottom), (right, top), line_thickness)
                elif is_half_third:
                    pygame.draw.line(surf, line_color, (left, mid_y), (mid_x, bottom), line_thickness)
                elif 2.9 <= tone <= 3.1:
                    pygame.draw.line(surf, line_color, (left, mid_y), (mid_x, bottom), line_thickness)
                    pygame.draw.line(surf, line_color, (mid_x, bottom), (right, mid_y), line_thickness)
                elif 4 <= tone < 4.5:
                    pygame.draw.line(surf, line_color, (left, top), (right, bottom), line_thickness)
                else:
                    pygame.draw.line(surf, line_color, (left, mid_y), (right, mid_y), line_thickness)

            def _tone_contour_point(left: float, bottom: float, width: float, height: float, tone: float, t: float) -> tuple[float, float]:
                """성조 곡선 위 파라미터 t(0~1)에 해당하는 (x, y) 반환. _draw_tone_contour와 동일 좌표계."""
                top = bottom - height
                right = left + width
                mid_x = left + width / 2
                mid_y = (top + bottom) / 2
                t = max(0.0, min(1.0, t))
                is_half_third = 3.4 <= tone <= 3.6
                if tone <= 0.5 or tone >= 4.5:
                    return (left + t * width, mid_y)
                if 1 <= tone < 1.5:
                    return (left + t * width, top)
                if 2 <= tone < 2.5:
                    return (left + t * width, bottom + t * (top - bottom))
                if is_half_third:
                    return (left + t * (mid_x - left), mid_y + t * (bottom - mid_y))
                if 2.9 <= tone <= 3.1:
                    if t <= 0.5:
                        u = t * 2
                        return (left + u * (mid_x - left), mid_y + u * (bottom - mid_y))
                    u = (t - 0.5) * 2
                    return (mid_x + u * (right - mid_x), bottom + u * (mid_y - bottom))
                if 4 <= tone < 4.5:
                    return (left + t * width, top + t * (bottom - top))
                return (left + t * width, mid_y)

            # 발음 라인 위치: 성조 표기 규칙으로 정확한 위치 추정 → 그 위치에 성조 이미지 표시
            ref_phonetic_height = 28
            y_phonetic_top = y_red_top - 8 - ref_phonetic_height
            contour_bottom_y = y_phonetic_top - contour_gap
            contour_center_y = contour_bottom_y - contour_height // 2
            circle_radius = 6  # 성조 이미지 없을 때 폴백용
            icon_dir = _REPO_ROOT / "resource" / "image" / "icon"

            def _tone_to_filename(t: float) -> str:
                """성조 값 → 아이콘 파일명 (tone1~5, tone3_5)."""
                if t <= 0.5 or t >= 4.5:
                    return "경성.png"   # 경성
                if 1 <= t < 1.5:
                    return "1성.png"
                if 2 <= t < 2.5:
                    return "2성.png"
                if 3.4 <= t <= 3.6:
                    return "3_5성.png"
                if 2.9 <= t <= 3.1:
                    return "3성.png"
                if 4 <= t < 4.5:
                    return "4성.png"
                return "경성.png"

            tone_icon_max_h = 96  # 성조 아이콘 표시 높이 (비율 유지, 작은 이미지는 확대)

            def _get_tone_surface(filename: str) -> Optional[Any]:
                """성조 아이콘 Surface 캐시 로드. 높이를 tone_icon_max_h로 맞춤."""
                if filename in self._tone_surfaces:
                    return self._tone_surfaces[filename]
                path = icon_dir / filename
                if path.exists():
                    try:
                        surf = pygame.image.load(str(path))
                        if surf.get_alpha() is None:
                            surf = surf.convert()
                        else:
                            surf = surf.convert_alpha()
                        h = surf.get_height()
                        if h != tone_icon_max_h:
                            scale = tone_icon_max_h / h
                            w = max(1, int(surf.get_width() * scale))
                            surf = pygame.transform.smoothscale(surf, (w, tone_icon_max_h))
                        self._tone_surfaces[filename] = surf
                        return surf
                    except Exception:
                        pass
                return None

            for i, (syl, diff_val) in enumerate(display_syllables):
                slot_left = x_start + int(prefix_w[i])
                if pinyin_aligned:
                    slot_width = int(prefix_w[i + 1] - prefix_w[i])
                else:
                    slot_width = int(prefix_w[i + 1] - prefix_w[i] - (space_w if i < n_syl - 1 else 0))
                if slot_width < 1:
                    slot_width = 1
                slot_rect = (slot_left, y_phonetic_top, slot_width, ref_phonetic_height)
                if _tone_contour_enabled:
                    tone = parse_tone_from_syllable(diff_val) if (diff_val and parse_tone_from_syllable(diff_val) is not None) else (parse_tone_from_syllable(lexical_for_display[i]) if i < len(lexical_for_display) else parse_tone_from_syllable(syl))
                    if tone is not None:
                        circle_x = _tonic_center_x(slot_left, syl)
                        tone_fname = _tone_to_filename(tone)
                        tone_surf = _get_tone_surface(tone_fname)
                        if tone_surf is not None:
                            tw, th = tone_surf.get_size()
                            screen.blit(tone_surf, (circle_x - tw // 2, contour_center_y - th // 2))
                        else:
                            pygame.draw.circle(screen, line_color, (circle_x, contour_center_y), circle_radius, 2)
                if diff_val and _phonetic_diff_enabled:
                    pass  # 주황 발음 텍스트 비표시


            # 가운데 네모 박스: syllable_times_l1 / l2에 따라 재생 시 움직이는 성조 그래프
            syllable_times_l1 = item.get("syllable_times_l1") or []
            syllable_times_l2 = item.get("syllable_times_l2") or []
            has_l1 = len(syllable_times_l1) == n_syl + 1  # 경계 시각 n_syl+1개 (시작~끝)
            has_l2 = len(syllable_times_l2) == n_syl + 1
            # 재생 중인 채널에 맞는 타이밍 선택, 아니면 있는 쪽 사용
            if n_syl > 0 and (has_l1 or has_l2):
                if self._step1_l1_channel is not None and self._step1_l1_channel.get_busy() and has_l1:
                    t_list = syllable_times_l1
                    if self._step1_l1_play_start_time is not None:
                        current_sec = time.time() - self._step1_l1_play_start_time
                    else:
                        current_sec = None
                elif self._step1_l2_channel is not None and self._step1_l2_channel.get_busy() and has_l2:
                    t_list = syllable_times_l2
                    if self._step1_l2_play_start_time is not None:
                        current_sec = time.time() - self._step1_l2_play_start_time
                    else:
                        current_sec = None
                else:
                    t_list = syllable_times_l2 if has_l2 else syllable_times_l1
                    current_sec = None
                t0, t1 = t_list[0], t_list[-1]
                total_dur = t1 - t0
                if total_dur <= 0:
                    total_dur = 1.0
                if current_sec is not None:
                    current_sec = max(t0, min(current_sec, t1))
                else:
                    current_sec = t1
                box_w, box_h = 500, 120
                box_x = cx - box_w // 2
                # 제목 바로 아래: title_y(0.06*h) + 제목 높이(~56) + 간격
                box_y = int(h * 0.06) + 56 + 30
                box_rect = pygame.Rect(box_x, box_y, box_w, box_h)
                pygame.draw.rect(screen, (60, 60, 70), box_rect)
                pygame.draw.rect(screen, (0, 0, 0), box_rect, 2)
                # 성조: diff에 성조가 있으면 발음, 없으면 pinyin_lexical(본래) 성조
                # 구간 시간 비율로 샘플 수 결정 → 부드러운 곡선
                points: list[tuple[float, float]] = []
                seg_end_idx: list[int] = []
                for i in range(n_syl):
                    syl, diff_val = display_syllables[i]
                    lex_syl = lexical_for_display[i] if i < len(lexical_for_display) else syl
                    tone = parse_tone_from_syllable(diff_val) if (diff_val and parse_tone_from_syllable(diff_val) is not None) else parse_tone_from_syllable(lex_syl)
                    if tone is None:
                        tone = 0.0
                    t_start, t_end = t_list[i], t_list[i + 1]
                    seg_dur = t_end - t_start
                    if seg_dur <= 0:
                        seg_dur = 1e-6
                    seg_left = box_x + (t_start - t0) / total_dur * box_w
                    seg_width = seg_dur / total_dur * box_w
                    bottom = box_y + box_h
                    # 구간 길이에 비례해 샘플 수 (짧으면 10, 길면 최대 24)
                    n_samples = max(10, min(24, int(seg_dur * 60)))
                    for j in range(n_samples):
                        t = j / (n_samples - 1) if n_samples > 1 else 1.0
                        x_pt, y_pt = _tone_contour_point(
                            seg_left, float(bottom), seg_width, float(box_h), tone, t
                        )
                        points.append((x_pt, y_pt))
                    seg_end_idx.append(len(points))
                # 구간 경계에서 보간해 뾰족한 꺾임 완화
                if len(points) > 2 and n_syl > 1:
                    smoothed: list[tuple[float, float]] = []
                    for b in range(n_syl):
                        start = 0 if b == 0 else seg_end_idx[b - 1]
                        end = seg_end_idx[b]
                        if b > 0 and start > 0 and start < len(points):
                            pa, pb = points[start - 1], points[start]
                            smoothed.append((0.67 * pa[0] + 0.33 * pb[0], 0.67 * pa[1] + 0.33 * pb[1]))
                            smoothed.append((0.33 * pa[0] + 0.67 * pb[0], 0.33 * pa[1] + 0.67 * pb[1]))
                        for j in range(start, end):
                            smoothed.append(points[j])
                    points = smoothed
                if points:
                    # 현재=가운데 + 짧은 히스토리(잔상): 과거는 최근만, 길어지면 밀려남
                    history_dur = 0.9  # 초 단위, 이만큼만 과거 표시
                    target_ratio = (current_sec - t0) / total_dur if current_sec is not None else 1.0
                    target_ratio = max(0.0, min(1.0, target_ratio))
                    item_id = (id(item), tuple(t_list) if t_list else ())
                    if self._step1_graph_item_id != item_id:
                        self._step1_graph_item_id = item_id
                        self._step1_graph_display_ratio = 0.0 if current_sec is not None else 1.0
                    if current_sec is not None:
                        cur_i = 0
                        for k in range(n_syl):
                            if t_list[k] <= current_sec < t_list[k + 1]:
                                cur_i = k
                                break
                            if current_sec >= t_list[-1]:
                                cur_i = n_syl - 1
                        seg_dur = t_list[cur_i + 1] - t_list[cur_i] if cur_i < n_syl else total_dur
                        if seg_dur <= 0:
                            seg_dur = total_dur / max(1, n_syl)
                        blend = 0.12 + 0.38 * min(1.0, 0.04 / seg_dur)
                        if target_ratio < 0.03:
                            self._step1_graph_display_ratio = target_ratio
                        else:
                            self._step1_graph_display_ratio += (target_ratio - self._step1_graph_display_ratio) * blend
                    else:
                        self._step1_graph_display_ratio = 1.0
                    # 창: [window_start, window_end] → 박스 왼쪽 절반에 매핑, 끝(현재)이 가운데
                    window_end_sec = t0 + self._step1_graph_display_ratio * total_dur
                    window_start_sec = max(t0, window_end_sec - history_dur)
                    window_dur = window_end_sec - window_start_sec
                    if window_dur <= 0:
                        window_dur = 1e-6
                    color_future = (100, 100, 105)
                    color_past = (45, 100, 55)
                    color_now = (100, 255, 120)
                    # 문장이 길면 스트리밍: 재생 위치를 가운데로 두고 고정 길이 창만 표시
                    streaming_threshold = 2.8  # 초 이상이면 스트리밍
                    visible_half_dur = 1.25    # 가운데 기준 앞뒤로 보여줄 길이(초)
                    use_streaming = total_dur > streaming_threshold
                    if use_streaming:
                        view_center = window_end_sec
                        view_start = max(t0, view_center - visible_half_dur)
                        view_end = min(t1, view_center + visible_half_dur)
                        view_dur = view_end - view_start
                        if view_dur <= 0:
                            view_dur = 1e-6
                        # [view_start, view_end] 구간만 박스 전체에 매핑 → 재생 위치 = 박스 가운데
                        streamed: list[tuple[float, float]] = []
                        for k in range(len(points)):
                            x_pt, y_pt = points[k]
                            t_pt = t0 + (x_pt - box_x) / box_w * total_dur
                            if t_pt < view_start - 1e-6:
                                continue
                            if t_pt > view_end + 1e-6:
                                if k > 0:
                                    x_prev, y_prev = points[k - 1]
                                    t_prev = t0 + (x_prev - box_x) / box_w * total_dur
                                    if t_prev < view_end:
                                        r = (view_end - t_prev) / (t_pt - t_prev) if t_pt != t_prev else 1.0
                                        y_end = y_prev + r * (y_pt - y_prev)
                                        streamed.append((box_x + box_w, y_end))
                                break
                            if not streamed and t_pt > view_start + 1e-6 and k > 0:
                                x_prev, y_prev = points[k - 1]
                                t_prev = t0 + (x_prev - box_x) / box_w * total_dur
                                r = (view_start - t_prev) / (t_pt - t_prev) if (t_pt != t_prev) else 0.0
                                y_start = y_prev + r * (y_pt - y_prev)
                                streamed.append((box_x, y_start))
                            x_new = box_x + (t_pt - view_start) / view_dur * box_w
                            streamed.append((x_new, y_pt))
                        draw_pts = streamed
                        center_x = box_x + (view_center - view_start) / view_dur * box_w
                        past_end_x = center_x
                        past_start_x = center_x - (view_center - view_start) / view_dur * box_w
                    else:
                        draw_pts = [(p[0], p[1]) for p in points]
                        center_x = box_x + (window_end_sec - t0) / total_dur * box_w
                        past_end_x = center_x
                        past_start_x = box_x + (window_start_sec - t0) / total_dur * box_w
                    # 선분별 색: 과거(연함)→현재(밝은 녹색)→미래(회색)
                    for k in range(len(draw_pts) - 1):
                        x0, y0 = draw_pts[k]
                        x1, y1 = draw_pts[k + 1]
                        mid_x = (x0 + x1) * 0.5
                        if mid_x > past_end_x:
                            color = color_future
                        else:
                            if mid_x < past_start_x:
                                color = color_past
                            else:
                                span = past_end_x - past_start_x
                                ratio = (mid_x - past_start_x) / span if span > 0 else 1.0
                                ratio = max(0.0, min(1.0, ratio))
                                r = int(color_past[0] + (color_now[0] - color_past[0]) * ratio)
                                g = int(color_past[1] + (color_now[1] - color_past[1]) * ratio)
                                b = int(color_past[2] + (color_now[2] - color_past[2]) * ratio)
                                color = (r, g, b)
                        pygame.draw.line(
                            screen, color,
                            (int(x0), int(y0)), (int(x1), int(y1)), 3
                        )
                    pygame.draw.line(
                        screen, (100, 240, 120),
                        (int(center_x), box_y), (int(center_x), box_y + box_h), 1
                    )

            # 한자 위치: 실제 병음 줄 높이만큼 띄워서 겹침 방지 (ref_height 고정값 대신 line_rect.height 사용)
            center_top = y_red_top + line_rect.height + pinyin_hanzi_gap

        # 한자 (큰 글자): 렌더 rect 기준으로 화면 가운데 정확히 배치
        hanzi_font_ft = self._font_cn_step1_ft or self._font_cn_big_ft
        if hanzi_font_ft is not None:
            try:
                sen_surf, sen_rect = hanzi_font_ft.render(sen_text[:80], (255, 255, 255))
                # 실제 글자 영역(rect) 중심이 (cx, center_top)에 오도록 blit
                blit_x = cx - sen_rect.width // 2 - sen_rect.x
                blit_y = center_top - sen_rect.height // 2 - sen_rect.y
                screen.blit(sen_surf, (blit_x, blit_y))
            except Exception:
                sen_surf = font_cn_big.render(sen_text[:80], True, (255, 255, 255))
                sr = sen_surf.get_rect(center=(cx, center_top))
                screen.blit(sen_surf, sr)
        else:
            sen_surf = font_cn_big.render(sen_text[:80], True, (255, 255, 255))
            sr = sen_surf.get_rect(center=(cx, center_top))
            screen.blit(sen_surf, sr)
        center_top += line_gap + 56  # 한자–뜻(해석) 간격 넓게

        # 해석 (한국어): 화면 가운데 정확히 배치
        if trans_text:
            trans_surf = font_kr_step1.render(trans_text[:80], True, (200, 200, 200))
            tr = trans_surf.get_rect(center=(cx, center_top))
            screen.blit(trans_surf, tr)

        # 좌측 하단: 발음상 성조 변화 (이 문장에서 쓰인 타입만, 반3성 제외)
        sandhi_types_raw = item.get("pinyin_sandhi_types") or []
        _sandhi_skip = {"tone3_half", "bu_to_4", "neutral_char"}  # 반3성, 不(표기동일→4성), 일반경성 제외
        unique_sandhi = list(dict.fromkeys(t for t in sandhi_types_raw if t and t not in _sandhi_skip))
        if unique_sandhi:
            left_margin = 20
            line_height = 28  # 줄 간격 (겹침 방지)
            box_y = h - 40 - (len(unique_sandhi) + 1) * line_height
            title_surf = font_kr.render("발음상 성조 변화", True, (200, 200, 180))
            screen.blit(title_surf, (left_margin, box_y))
            for j, st in enumerate(unique_sandhi):
                label = SANDHI_TYPE_LABELS.get(st, st)
                line_surf = font_kr.render(label, True, (255, 220, 100))
                screen.blit(line_surf, (left_margin, box_y + line_height + j * line_height))

        # 맨 아래: 안내 문구
        hint = "눈으로 보면서 원어민 리듬을 익히세요"
        hint_surf = font_kr.render(hint, True, (180, 190, 200))
        hint_r = hint_surf.get_rect(center=(w // 2, h - 40))
        screen.blit(hint_surf, hint_r)

    def _draw_paused_and_debug(self, screen: Any, config: Any) -> None:
        """일시정지 라벨 및 디버그(FPS/PTS/오디오) 오버레이."""
        if self._video_player.is_paused():
            if self._paused_label is None:
                font_kr = self._font_kr or pygame.font.Font(None, 36)
                self._paused_label = font_kr.render("일시정지", True, (255, 255, 0))
            if self._paused_label is not None:
                px, py = config.get_pos(0.08, 0.05)
                screen.blit(self._paused_label, (px, py))

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
