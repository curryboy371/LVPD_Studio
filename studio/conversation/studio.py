"""회화 스튜디오 메인 클래스."""
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import pygame

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

from .constants import (
    _REPO_ROOT,
    _POS_COLORS,
    _DEFAULT_CARD_BG,
    _DEFAULT_CARD_FG,
    ShadowingStep,
    Step1SoundState,
)
from .draw_helpers import (
    draw_dotted_line as _draw_dotted_line,
    smooth_curve_pts as _smooth_curve_pts,
    draw_sparkline_symbol as _draw_sparkline_symbol,
    parse_util_segments as _parse_util_segments,
)
from .data_loading import build_data_list
from .video_players import SimpleVideoPlayer, VideoAudioPlayer

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
        self._data_list = build_data_list(csv_path, content)
        self._current_index = 0
        self._video_player = SimpleVideoPlayer()
        self._video_audio = VideoAudioPlayer()
        self._init_font_attrs()
        self._init_step1_attrs()
        self._init_recording_attrs()
        self._apply_first_segment()

    def _init_font_attrs(self) -> None:
        """폰트·UI 캐시 속성 초기화. 실제 로드는 init()에서."""
        self._font_cn_big: Optional[pygame.font.Font] = None
        self._font_cn: Optional[pygame.font.Font] = None
        self._font_cn_big_ft: Any = None
        self._font_cn_ft: Any = None
        self._font_cn_step1_ft: Any = None
        self._font_cn_step1_pinyin_ft: Any = None
        self._font_kr: Optional[pygame.font.Font] = None
        self._font_kr_step1: Optional[pygame.font.Font] = None
        self._font: Optional[pygame.font.Font] = None
        self._paused_label: Optional[pygame.Surface] = None
        self._last_sync_pts: float = -10.0
        self._recording_initial_logged: bool = False

    def _init_step1_attrs(self) -> None:
        """Step 1(쉐도잉) 관련 상태 초기화."""
        self._shadowing_step: ShadowingStep = ShadowingStep.LISTEN
        self._tone_surfaces: dict[str, Any] = {}
        self._listen_panda_surface: Any = None
        self._listen_panda_cached_size: tuple[int, int] = (0, 0)
        self._ui_visible: bool = False
        self._fade_alpha: float = 0.0
        self._fade_overlay_surface: Any = None
        self._fade_overlay_size: tuple[int, int] = (0, 0)
        self._step1_sound_state: Step1SoundState = Step1SoundState.Idle
        self._step1_l1_channel: Any = None
        self._step1_l2_channel: Any = None
        self._step1_l1_play_start_time: Optional[float] = None
        self._step1_l2_play_start_time: Optional[float] = None
        self._step1_graph_display_ratio: float = 0.0
        self._step1_graph_item_id: Any = None
        self._step1_tone_smooth_pos: float = 0.0
        self._step1_tone_last_item_id: Any = None
        self._step1_sounds_played_this_pause: bool = False
        self._step1_util_slot_offset: dict[tuple[Any, int], float] = {}
        self._step1_util_last_item_id: Any = None

    def _init_recording_attrs(self) -> None:
        """녹화 모드용 상태 초기화."""
        self._last_recording_seg_idx: int = -1
        self._last_recording_paused: bool = False

    def _apply_first_segment(self) -> None:
        """첫 번째 항목으로 비디오·오디오 소스 설정 (로딩 직후 한 번 호출)."""
        if not self._data_list:
            return
        item = self._data_list[0]
        path = self._resolve_video_path(item.get("video_path") or "")
        st = item.get("start_time", 0.0)
        et = item.get("end_time", -1.0)
        self._video_player.set_source(path, st, et)
        self._video_audio.set_source(path, st)
        if item.get("type") == "util":
            if not self._video_player.is_paused():
                self._video_player.toggle_pause()
            self._video_audio.pause()

    def _switch_to_segment(self, index: int, config: Any = None) -> None:
        """지정 인덱스로 세그먼트 전환: 비디오/오디오 소스 설정, util이면 일시정지. config 있으면 녹화 이벤트 로그."""
        if not self._data_list or index < 0 or index >= len(self._data_list):
            return
        log_ev = getattr(config, "recording_log_event", None) if config else None
        timeline_sec = getattr(config, "recording_time_sec", 0.0) if config else 0.0
        if log_ev and self._current_index < len(self._data_list):
            path_cur = self._resolve_video_path(
                self._data_list[self._current_index].get("video_path") or ""
            )
            if path_cur:
                recording_log_event(log_ev, VideoSegmentEnd(timeline_sec))
        self._current_index = index
        item = self._data_list[index]
        path = self._resolve_video_path(item.get("video_path") or "")
        st = item.get("start_time", 0.0)
        et = item.get("end_time", -1.0)
        self._video_player.set_source(path, st, et)
        self._video_audio.set_source(path, st)
        self._last_sync_pts = -10.0
        if item.get("type") == "util":
            if not self._video_player.is_paused():
                self._video_player.toggle_pause()
            self._video_audio.pause()
        else:
            if self._video_player.is_paused():
                self._video_player.toggle_pause()
            self._video_audio.unpause()
        if log_ev and path:
            recording_log_event(log_ev, VideoSegmentStart(timeline_sec, path, st))

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

    def _current_shadowing_step(self) -> ShadowingStep:
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
                    self._switch_to_segment(self._current_index + 1, config)
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
                    self._switch_to_segment(self._current_index - 1, config)
        return True

    def _update_apply_pending_audio(self) -> None:
        """pending 오디오가 있으면 적용."""
        if self._video_audio.has_pending():
            self._video_audio._apply_pending()

    def _update_timeline(self, config: Any) -> None:
        """녹화 모드면 타임라인 동기화, 아니면 비디오 tick + 오디오 싱크."""
        dt = 1.0 / 30.0
        if config is not None and getattr(config, "dt_sec", None) is not None:
            dt = config.dt_sec
        if config is not None and is_recording(config) and self._data_list:
            self._sync_recording_timeline(config)
        else:
            self._video_player.tick(dt)
            if not self._video_player.is_paused():
                self._sync_audio_to_video()

    def _update_step1_if_listen(self, config: Any) -> None:
        """Step 1(LISTEN)이고 녹화 중이 아닐 때만 step1 제어."""
        if self._shadowing_step == ShadowingStep.LISTEN and not (config and is_recording(config)):
            self._update_step1(config)

    def _update_segment_end(self, config: Any) -> None:
        """세그먼트 end_time 도달 시 오디오 일시정지, 다음 항목 있으면 전환."""
        _, end_sec = self._current_segment_times()
        if end_sec < 0:
            end_sec = self._video_player.get_effective_end_sec()
        if end_sec < 0 or self._video_player.get_pts() < end_sec - 0.05:
            return
        self._video_audio.pause()
        total = len(self._data_list)
        if total and self._current_index < total - 1:
            item_cur = self._data_list[self._current_index]
            if item_cur.get("type") != "base":
                self._switch_to_segment(self._current_index + 1, config)

    def _update_recording_initial_log(self, config: Any) -> None:
        """녹화 모드일 때 첫 프레임에만 현재 비디오 구간 시작 로그."""
        if config is None or not is_recording(config) or not self._data_list or self._recording_initial_logged:
            return
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

    def update(self, config: Any = None) -> None:
        try:
            self._update_apply_pending_audio()
            self._update_timeline(config)
            self._update_step1_if_listen(config)
            self._update_segment_end(config)
            self._update_recording_initial_log(config)
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
            self._step1_sound_state = Step1SoundState.Idle
            self._step1_l1_channel = None
            self._step1_l2_channel = None
            self._step1_sounds_played_this_pause = False  # 다음 멈춤에서 다시 L1→L2 재생 가능

    def _step1_clear_channel_timestamps(self) -> None:
        """채널이 None이면 play_start_time 정리 (draw에서 한 프레임 더 진행 위치 표시 가능하도록)."""
        if self._step1_l1_channel is None:
            self._step1_l1_play_start_time = None
        if self._step1_l2_channel is None:
            self._step1_l2_play_start_time = None

    def _step1_when_paused(self, config: Any) -> None:
        """일시정지일 때 fade 증가, UI on, 이번 pause에서 아직 안 재생했으면 L1 한 번 시작."""
        self._fade_alpha = min(191.25, self._fade_alpha + 6.0)
        if self._fade_alpha < 191.25:
            return
        self._ui_visible = True
        if self._step1_sounds_played_this_pause or self._step1_sound_state != Step1SoundState.Idle or not self._data_list:
            return
        self._step1_sounds_played_this_pause = True
        item = self._data_list[self._current_index]
        path = (item.get("sound_l1") or "").strip()
        self._step1_sound_state = Step1SoundState.PlayingL1
        self._step1_l1_channel = None
        self._step1_l1_play_start_time = None
        if path and os.path.exists(path):
            try:
                snd = pygame.mixer.Sound(path)
                ch = pygame.mixer.find_channel(True)
                if ch is not None:
                    ch.play(snd)
                    self._step1_l1_channel = ch
                    self._step1_l1_play_start_time = time.time()
            except Exception:
                pass

    def _step1_when_playing(self) -> None:
        """재생 중이면 fade/UI/사운드 상태 전부 리셋."""
        self._fade_alpha = 0.0
        self._ui_visible = False
        self._step1_sound_state = Step1SoundState.Idle
        self._step1_l1_channel = None
        self._step1_l2_channel = None
        self._step1_l1_play_start_time = None
        self._step1_l2_play_start_time = None

    def _step1_tick_sound_state(self) -> None:
        """L1 재생 끝이면 L2 시작, L2 재생 끝이면 Idle로."""
        if self._step1_sound_state == Step1SoundState.PlayingL1 and self._data_list:
            if self._step1_l1_channel is None or not self._step1_l1_channel.get_busy():
                self._step1_l1_channel = None
                item = self._data_list[self._current_index]
                path = (item.get("sound_l2") or "").strip()
                self._step1_sound_state = Step1SoundState.Idle
                if path and os.path.exists(path):
                    try:
                        snd = pygame.mixer.Sound(path)
                        ch = pygame.mixer.find_channel(True)
                        if ch is not None:
                            ch.play(snd)
                            self._step1_l2_channel = ch
                            self._step1_l2_play_start_time = time.time()
                            self._step1_l1_play_start_time = None
                            self._step1_sound_state = Step1SoundState.PlayingL2
                    except Exception:
                        pass
            return
        if self._step1_sound_state == Step1SoundState.PlayingL2:
            if self._step1_l2_channel is None or not self._step1_l2_channel.get_busy():
                self._step1_l2_channel = None
                self._step1_sound_state = Step1SoundState.Idle

    def _update_step1(self, config: Any) -> None:
        """Step 1 제어: 영상 멈춤 시 fade 후 UI on, 테이블 사운드 레벨1 한 번 재생 → 끝나면 레벨2 재생."""
        self._step1_clear_channel_timestamps()
        if self._video_player.is_paused():
            self._step1_when_paused(config)
            self._step1_tick_sound_state()
        else:
            self._step1_when_playing()

    def init(self, config: Any = None) -> None:
        """pygame.init() 이후 러너가 한 번 호출. 폰트 등 리소스 로드."""
        if self._font_kr is not None:
            return
        self._load_fonts()
        self._apply_font_fallbacks()

    def _load_fonts(self) -> None:
        """폰트 로드 (pygame.freetype으로 중국어 네모 방지)."""
        self._font_cn_big = load_font_chinese(36)
        self._font_cn = load_font_chinese(28)
        self._font_cn_big_ft = load_font_chinese_freetype(36)
        self._font_cn_ft = load_font_chinese_freetype(28)
        self._font_cn_step1_ft = load_font_chinese_freetype(124)
        if self._font_cn_step1_ft is None:
            self._font_cn_step1_ft = self._font_cn_big_ft
        self._font_cn_step1_pinyin_ft = load_font_chinese_freetype(66)
        if self._font_cn_step1_pinyin_ft is None:
            self._font_cn_step1_pinyin_ft = self._font_cn_ft
        self._font_kr = load_font_korean(28)
        self._font_kr_step1 = load_font_korean(56)
        if self._font_kr_step1 is None:
            self._font_kr_step1 = self._font_kr

    def _apply_font_fallbacks(self) -> None:
        """폰트 미로드 시 기본 폰트로 폴백 및 _font 기본값 설정."""
        from core.paths import DEFAULT_FONT_DIR, FONT_CN_FILENAME
        if self._font_cn_big is None:
            self._font_cn_big = pygame.font.Font(None, 36)
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
        """메인 그리기: Step1(듣기) / Step2(자막+단어카드) / 데이터 없음 분기."""
        w, h = config.width, config.height
        screen.fill(config.bg_color)

        # Step 1: 영상 + 페이드 오버레이 + 병음/한자/해석 UI (멈춤 시에만)
        if self._shadowing_step == ShadowingStep.LISTEN:
            self._draw_impl_step1(screen, config)
            self._draw_paused_and_debug(screen, config)
            return

        # Step 2: 비디오 위에 자막(문장/병음/번역) + 단어 카드 — 현재 문장만, Step 1과 동일 위치/크기
        if self._data_list:
            curr_item = self._data_list[self._current_index]
            self._draw_step2_video(screen, w, h)
            card_y = self._draw_step2_subtitles(screen, curr_item, w, h)
            self._draw_step2_word_cards(screen, curr_item, card_y)
        else:
            font_kr = self._font_kr or pygame.font.Font(None, 28)
            msg = font_kr.render("데이터 없음 (CSV 로드 실패 또는 비어 있음)", True, (180, 180, 180))
            screen.blit(msg, (20, h // 2 - 14))

        self._draw_paused_and_debug(screen, config)

    def _draw_step1_video(self, screen: Any, config: Any) -> None:
        """Step 1: 비디오 프레임 그리기."""
        w, h = config.width, config.height
        vid_surf = self._video_player.get_frame(w, h)
        if vid_surf is not None:
            screen.blit(vid_surf, (0, 0))

    def _draw_step1_fade_overlay(self, screen: Any, config: Any) -> None:
        """Step 1: 페이드 오버레이 (멈춤 시 어둡게)."""
        if self._fade_alpha <= 0:
            return
        w, h = config.width, config.height
        if self._fade_overlay_surface is None or self._fade_overlay_size != (w, h):
            self._fade_overlay_surface = pygame.Surface((w, h))
            self._fade_overlay_surface.fill((0, 0, 0))
            self._fade_overlay_size = (w, h)
        self._fade_overlay_surface.set_alpha(int(min(192, self._fade_alpha)))
        screen.blit(self._fade_overlay_surface, (0, 0))

    def _draw_step1_ui(self, screen: Any, config: Any) -> None:
        """Step 1: UI(병음/한자/해석) — _ui_visible일 때만."""
        if self._ui_visible:
            self._draw_step1(screen, config)

    def _draw_impl_step1(self, screen: Any, config: Any) -> None:
        """Step 1: 영상 → 페이드 오버레이 → UI(병음/한자/해석)."""
        self._draw_step1_video(screen, config)
        self._draw_step1_fade_overlay(screen, config)
        self._draw_step1_ui(screen, config)

    def _draw_step2_video(self, screen: Any, w: int, h: int) -> None:
        """Step 2: 비디오 프레임 또는 '(비디오 없음)' 플레이스홀더."""
        vid_surf = self._video_player.get_frame(w, h)
        if vid_surf is not None:
            screen.blit(vid_surf, (0, 0))
        else:
            pygame.draw.rect(screen, (40, 40, 50), (0, 0, w, h))
            font_kr = self._font_kr or pygame.font.Font(None, 28)
            no_vid = font_kr.render("(비디오 없음)", True, (180, 180, 180))
            screen.blit(no_vid, (w // 2 - 50, h // 2 - 14))

    def _draw_step2_sentence_block(
        self,
        screen: Any,
        item: dict,
        w: int,
        y_base: int,
        line_gap: int = 130,
    ) -> None:
        """한 문장 블록(한자+병음+번역)을 y_base에 그리기. Step 1과 동일한 큰 폰트·가운데 정렬."""
        font_cn_big = self._font_cn_big or pygame.font.Font(None, 36)
        font_cn = self._font_cn or pygame.font.Font(None, 28)
        font_kr = self._font_kr or pygame.font.Font(None, 28)
        # Step 1과 동일한 큰 폰트 사용 (한자 124, 병음 66, 번역 56)
        hanzi_ft = self._font_cn_step1_ft or self._font_cn_big_ft
        hanzi_pg = font_cn_big
        pinyin_ft = self._font_cn_step1_pinyin_ft or self._font_cn_ft
        pinyin_pg = font_cn
        trans_font = self._font_kr_step1 or font_kr
        sentences = item.get("sentence") or []
        translations = item.get("translation") or []
        pinyin_text = item.get("pinyin") or ""
        sen_text = " ".join(str(x) for x in sentences[:3]) if sentences else "(문장 없음)"
        trans_text = " ".join(str(x) for x in translations[:3]) if translations else ""
        y_pos = y_base

        def _blit_centered(surf: Any, y: int) -> None:
            if surf is not None:
                x = (w - surf.get_width()) // 2
                screen.blit(surf, (max(20, x), y))

        # 한자
        sen_surf = None
        if hanzi_ft is not None:
            try:
                sen_surf, _ = hanzi_ft.render(sen_text[:80], (255, 255, 255))
            except Exception:
                pass
        if sen_surf is None:
            sen_surf = hanzi_pg.render(sen_text[:80], True, (255, 255, 255))
        _blit_centered(sen_surf, y_pos)
        y_pos += line_gap

        # 병음
        if pinyin_text:
            pinyin_surf = None
            if pinyin_ft is not None:
                try:
                    pinyin_surf, _ = pinyin_ft.render(pinyin_text[:120], (220, 70, 70))
                except Exception:
                    pass
            if pinyin_surf is None:
                pinyin_surf = pinyin_pg.render(pinyin_text[:120], True, (220, 70, 70))
            _blit_centered(pinyin_surf, y_pos)
            y_pos += line_gap
        if trans_text:
            trans_surf = trans_font.render(trans_text[:80], True, (200, 200, 200))
            _blit_centered(trans_surf, y_pos)

    def _draw_step2_subtitles(self, screen: Any, curr_item: dict, w: int, h: int) -> int:
        """Step 2: 현재 문장만 그리기. Step 1과 동일 위치(h*0.38), 동일 큰 폰트·줄간격(130). 단어 카드 시작 y 반환."""
        line_gap = 130
        y_base = int(h * 0.38)
        self._draw_step2_sentence_block(screen, curr_item, w, y_base, line_gap)
        trans_font = self._font_kr_step1 or self._font_kr or pygame.font.Font(None, 28)
        card_y = y_base + line_gap * 2 + trans_font.get_height() + 8
        return card_y

    def _draw_step2_word_cards(self, screen: Any, item: dict, card_y: int) -> None:
        """Step 2: 단어(품사별 색상) 카드 한 줄."""
        words_list = item.get("words") or []
        if not words_list:
            return
        try:
            from data.table_manager import get_word_info_for_display
            font_wk = self._font_kr or pygame.font.Font(None, 22)
            card_gap, card_pad_x, card_pad_y = 10, 12, 8
            card_infos: list[tuple[list[Any], tuple, tuple, int, int]] = []
            for hanzi in words_list:
                info = get_word_info_for_display(hanzi)
                if not info:
                    continue
                pos_strs = info["pos"]
                meaning_strs = info["meaning"]
                n = max(len(pos_strs), len(meaning_strs))
                for k in range(n):
                    pos = pos_strs[k] if k < len(pos_strs) else ""
                    meaning = meaning_strs[k] if k < len(meaning_strs) else ""
                    bg, fg = _POS_COLORS.get(pos, (_DEFAULT_CARD_BG, _DEFAULT_CARD_FG))
                    pos_surf = font_wk.render(pos, True, fg) if pos else None
                    meaning_surf = font_wk.render(meaning[:40], True, (255, 255, 255)) if meaning else None
                    line_surfs: list[Any] = []
                    if pos_surf:
                        line_surfs.append(pos_surf)
                    if meaning_surf:
                        line_surfs.append(meaning_surf)
                    if not line_surfs:
                        continue
                    content_w = max(s.get_width() for s in line_surfs)
                    line_h = font_wk.get_height()
                    content_h = line_h * len(line_surfs) + 4 * (len(line_surfs) - 1)
                    c_w = max(70, content_w + card_pad_x * 2)
                    c_h = content_h + card_pad_y * 2
                    card_infos.append((line_surfs, bg, fg, c_w, c_h))
            card_x = 20
            line_h = font_wk.get_height()
            for (line_surfs, bg, fg, c_w, c_h) in card_infos:
                card_rect = pygame.Rect(card_x, card_y, c_w, c_h)
                pygame.draw.rect(screen, bg, card_rect, border_radius=6)
                pygame.draw.rect(screen, fg, card_rect, 2, border_radius=6)
                y_text = card_y + card_pad_y
                for s in line_surfs:
                    screen.blit(s, (card_x + (c_w - s.get_width()) // 2, y_text))
                    y_text += line_h + 4
                card_x += c_w + card_gap
        except Exception as e:
            logging.getLogger(__name__).debug("단어 카드 오류(일반): %s", e)

    def _draw_step1(self, screen: Any, config: Any) -> None:
        """셰도잉 Step 1: slot_index 0(base)면 _draw_step1_base, 확장문장(util)이면 _draw_step1_util."""
        w, h = config.width, config.height
        font_kr = self._font_kr or pygame.font.Font(None, 28)

        if not self._data_list:
            msg = font_kr.render("데이터 없음 (CSV 로드 실패 또는 비어 있음)", True, (180, 180, 180))
            r = msg.get_rect(center=(w // 2, h // 2))
            screen.blit(msg, r)
            return

        item = self._data_list[self._current_index]
        if item.get("type") == "util":
            self._draw_step1_util(screen, config)
            return

        self._draw_step1_base(screen, config)

    def _draw_step1_base_title(self, screen: Any, config: Any) -> None:
        """Step 1 base: 상단 타이틀 '쉐도잉 훈련 Step 1: 원어민 속도 듣기'."""
        w, h = config.width, config.height
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

    def _draw_step1_base_listen_icon(self, screen: Any, config: Any) -> None:
        """Step 1 base: 좌측 듣기 이미지(판다)."""
        font_kr = self._font_kr or pygame.font.Font(None, 28)
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

    def _draw_step1_base(self, screen: Any, config: Any) -> None:
        """slot_index 0(base) 문장용 UI: 타이틀 → 듣기 아이콘 → 문장(병음/한자/해석·성조) → 단어 카드 → 성조 변화 → 안내."""
        item = self._data_list[self._current_index]
        self._draw_step1_base_title(screen, config)
        self._draw_step1_base_listen_icon(screen, config)
        ctx = self._draw_step1_base_sentence(screen, config, item)
        self._draw_step1_base_word_cards(screen, item, ctx)
        self._draw_step1_base_sandhi(screen, config, item)
        self._draw_step1_base_hint(screen, config)

    def _draw_step1_base_sentence(self, screen: Any, config: Any, item: dict) -> dict:
        """Step 1 base: 병음·한자·해석 및 성조 곡선(L1/L2 진행). 반환 ctx는 word_cards용."""
        w, h = config.width, config.height
        font_kr = self._font_kr or pygame.font.Font(None, 28)
        font_cn = self._font_cn or pygame.font.Font(None, 28)
        font_cn_big = self._font_cn_big or pygame.font.Font(None, 36)
        font_kr_step1 = self._font_kr_step1 or font_kr

        sentences = item.get("sentence") or []
        if isinstance(sentences, str):
            sentences = [sentences.strip()] if sentences.strip() else []
        translations = item.get("translation") or []
        pinyin_text = (item.get("pinyin") or "").strip()
        pinyin_lexical = (item.get("pinyin_lexical") or "").strip()
        pinyin_phonetic = (item.get("pinyin_phonetic") or "").strip()
        sen_text = " ".join(str(x) for x in sentences) if sentences else "(문장 없음)"
        trans_text = " ".join(str(x) for x in translations) if translations else ""

        if not pinyin_text and sen_text and sen_text != "(문장 없음)":
            processor = get_pinyin_processor()
            if processor.available:
                pinyin_text = processor.full_convert(sen_text)
                lex_list = processor.get_lexical_pinyin(sen_text)
                ph_list = processor.get_phonetic_pinyin(sen_text)
                pinyin_lexical = " ".join(lex_list) if lex_list else ""
                pinyin_phonetic = " ".join(ph_list) if ph_list else ""

        cx = w // 2
        center_top = int(h * 0.38)
        line_gap = 96
        hanzi_drawn = False
        slot_left_list: list[float] = []
        slot_width_list: list[float] = []
        use_speed = False

        pinyin_ft = self._font_cn_step1_pinyin_ft or self._font_cn_ft
        # 발음 병음도 같은 폰트(pinyin_ft)로 그려야 표기 병음과 위아래 정렬이 맞음 (폰트 차이로 틀어짐 방지)
        diff_ft = pinyin_ft
        _tone_contour_enabled = True   # 병음 위 성조 이미지 표시
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
            self._step1_sparkline_data = None
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

            # 표기 병음: 한 줄 렌더 (구두점 포함) → 칸 위치 계산용; 실제 그리기는 slot_left_list 반영 후 아래에서
            line_surf, line_rect = _render_syllable(pinyin_ft, font_cn, display_pinyin, (220, 70, 70))
            x_start = cx - line_rect.width // 2
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

            # 속도 시각화: syllable_times가 있으면 구간 길이에 비례해 자간 배분
            syllable_times_l1 = item.get("syllable_times_l1") or []
            syllable_times_l2 = item.get("syllable_times_l2") or []
            has_l1 = len(syllable_times_l1) == n_syl + 1
            has_l2 = len(syllable_times_l2) == n_syl + 1
            use_speed = n_syl > 0 and (has_l1 or has_l2)
            base_x = cx - line_rect.width // 2
            total_width_f = float(line_rect.width)
            if use_speed:
                t_list = syllable_times_l2 if has_l2 else syllable_times_l1
                durations = [t_list[i + 1] - t_list[i] for i in range(n_syl)]
                total_d = sum(durations)
                if total_d < 1e-9:
                    total_d = 1.0
                slot_left_list = [base_x + total_width_f * sum(durations[:i]) / total_d for i in range(n_syl)]
                slot_width_list = [total_width_f * d / total_d for d in durations]
            else:
                slot_left_list = [base_x + prefix_w[i] for i in range(n_syl)]
                slot_width_list = []
                for i in range(n_syl):
                    w = prefix_w[i + 1] - prefix_w[i]
                    if not pinyin_aligned and i < n_syl - 1:
                        w -= space_w
                    slot_width_list.append(max(1, int(w)))

            # 표기 병음: 속도 기반이면 음절별로 그리기, 아니면 한 줄로
            if use_speed:
                _syl_surfs = []
                for i in range(n_syl):
                    syl = display_syllables[i][0]
                    syl_surf, syl_rect = _render_syllable(pinyin_ft, font_cn, syl, (220, 70, 70))
                    _syl_surfs.append((syl_surf, syl_rect))
                # 슬롯 폭이 음절 텍스트보다 좁으면 겹침 발생 → 최소 여백(min_pad) 확보 후 재배치
                min_pad = 8
                adjusted_lefts = list(slot_left_list)
                for i in range(n_syl):
                    sw = slot_width_list[i]
                    tw = _syl_surfs[i][1].width
                    if tw + min_pad > sw:
                        # 슬롯 중심 기준으로 텍스트 배치, 다음 음절과 겹치면 밀어냄
                        center = slot_left_list[i] + sw / 2
                        adjusted_lefts[i] = center - tw / 2
                for i in range(1, n_syl):
                    prev_right = adjusted_lefts[i - 1] + _syl_surfs[i - 1][1].width + min_pad
                    if adjusted_lefts[i] < prev_right:
                        adjusted_lefts[i] = prev_right
                for i in range(n_syl):
                    syl_surf, syl_rect = _syl_surfs[i]
                    sw = slot_width_list[i]
                    sx = int(adjusted_lefts[i])
                    screen.blit(syl_surf, (sx, y_red_top))
            else:
                screen.blit(line_surf, (x_start, y_red_top))

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
                """성조 시각화: 1=고평, 2=상승, 3=V자, 3.5=반3성, 4=하강, 5/0=경성(점선)."""
                top = bottom - contour_height
                mid_y = (top + bottom) // 2
                right = left + width
                mid_x = (left + right) // 2
                left, right, top, bottom = int(left), int(right), int(top), int(bottom)
                mid_x, mid_y = int(mid_x), int(mid_y)
                is_neutral = tone <= 0.5 or tone >= 4.5
                is_half_third = 3.4 <= tone <= 3.6

                def _line(a: tuple, b: tuple) -> None:
                    if is_neutral:
                        _draw_dotted_line(surf, line_color, a, b, line_thickness, dash_length=5)
                    else:
                        pygame.draw.line(surf, line_color, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), line_thickness)

                if is_neutral:
                    _line((left, mid_y), (right, mid_y))
                elif 1 <= tone < 1.5:
                    _line((left, top), (right, top))
                elif 2 <= tone < 2.5:
                    _line((left, bottom), (right, top))
                elif is_half_third:
                    _line((left, mid_y), (mid_x, bottom))
                elif 2.9 <= tone <= 3.1:
                    _line((left, mid_y), (mid_x, bottom))
                    _line((mid_x, bottom), (right, mid_y))
                elif 4 <= tone < 4.5:
                    _line((left, top), (right, bottom))
                else:
                    _line((left, mid_y), (right, mid_y))

            def _tone_contour_point(left: float, bottom: float, width: float, height: float, tone: float, t: float) -> tuple[float, float]:
                """성조 곡선: 1~5도 척도. 1도=bottom(낮음), 5도=top(높음). y = bottom - (level-1)*(height/4)."""
                top = bottom - height
                t = max(0.0, min(1.0, t))
                x = left + t * width

                def level_to_y(level: float) -> float:
                    return bottom - (level - 1.0) * (height / 4.0)

                is_half_third = 3.4 <= tone <= 3.6
                if tone <= 0.5 or tone >= 4.5:
                    return (x, level_to_y(3.0))
                if 1 <= tone < 1.5:
                    return (x, level_to_y(5.0))
                if 2 <= tone < 2.5:
                    return (x, level_to_y(3.0 + 2.0 * t))
                if is_half_third:
                    return (x, level_to_y(2.0 - t))
                if 2.9 <= tone <= 3.1:
                    if t <= 0.5:
                        level = 2.0 - 2.0 * t
                    else:
                        level = 1.0 + 6.0 * (t - 0.5)
                    return (x, level_to_y(level))
                if 4 <= tone < 4.5:
                    return (x, level_to_y(5.0 - 4.0 * t))
                return (x, level_to_y(3.0))

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
                slot_left = int(slot_left_list[i])
                slot_width = max(1, int(round(slot_width_list[i])))
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
                            pygame.draw.circle(screen, (220, 220, 220), (circle_x, contour_center_y), circle_radius, 2)
                if diff_val and _phonetic_diff_enabled:
                    pass  # 주황 발음 텍스트 비표시


            # 작은 사각형: 전체 성조 곡선 항상 표시. 녹색 따라움직임은 L1 재생 시에만 (L2는 syllable 없음 → 진행선 없음)
            if n_syl > 0:
                l1_playing = (
                    self._step1_l1_channel is not None and self._step1_l1_channel.get_busy()
                ) or self._step1_l1_play_start_time is not None
                # 진행 위치: L1 재생 중이고 L1 syllable_times 있을 때만
                if l1_playing and has_l1:
                    t_list = syllable_times_l1
                    play_start = self._step1_l1_play_start_time
                else:
                    t_list = []
                    play_start = None
                current_sec = (time.time() - play_start) if play_start is not None else None
                cur_i = 0
                blend = 0.0
                if current_sec is not None and t_list and len(t_list) >= n_syl + 1:
                    t0, t1 = t_list[0], t_list[-1]
                    current_sec = max(t0, min(current_sec, t1 + 0.01))
                    for k in range(n_syl):
                        if t_list[k] <= current_sec < t_list[k + 1]:
                            cur_i = k
                            seg_dur = t_list[k + 1] - t_list[k]
                            blend = (current_sec - t_list[k]) / seg_dur if seg_dur > 1e-6 else 0.0
                            blend = max(0.0, min(1.0, blend))
                            break
                        if current_sec >= t_list[-1]:
                            cur_i = n_syl - 1
                            blend = 1.0
                            break
                target_pos = cur_i + blend
                item_id = (id(item), tuple(t_list) if t_list else ())
                if getattr(self, "_step1_tone_last_item_id", None) != item_id:
                    self._step1_tone_last_item_id = item_id
                    self._step1_tone_smooth_pos = target_pos
                self._step1_tone_smooth_pos += (target_pos - self._step1_tone_smooth_pos) * 0.25
                smooth_pos = max(0.0, min(n_syl - 0.001, self._step1_tone_smooth_pos))
                cur_i = int(smooth_pos)
                blend = smooth_pos - cur_i
                box_w, box_h = 640, 160
                box_x = cx - box_w // 2
                box_y = int(h * 0.06) + 56 + 30
                box_rect = pygame.Rect(box_x, box_y, box_w, box_h)
                contour_left = float(box_x)
                contour_bottom = float(box_y + box_h)
                contour_top = float(box_y)
                contour_width = float(box_w)
                contour_height = float(box_h)
                grid_color = (80, 80, 90)
                pygame.draw.rect(screen, (60, 60, 70), box_rect)
                for lev in range(5):
                    y_lev = contour_top + (contour_bottom - contour_top) * lev / 4
                    pygame.draw.line(screen, grid_color, (int(contour_left), int(y_lev)), (int(contour_left + contour_width), int(y_lev)), 1)
                pygame.draw.rect(screen, (0, 0, 0), box_rect, 2)
                font_small = self._font_kr or pygame.font.Font(None, 20)
                for lev in range(5):
                    y_lev = contour_top + (contour_bottom - contour_top) * lev / 4
                    lbl = font_small.render(str(lev + 1), True, (120, 120, 130))
                    screen.blit(lbl, (int(contour_left) - 14, int(y_lev) - 8))

                def _get_tone_for_syl(i: int) -> float:
                    if i < 0 or i >= n_syl:
                        return 0.0
                    syl, diff_val = display_syllables[i]
                    lex_syl = lexical_for_display[i] if i < len(lexical_for_display) else syl
                    t = parse_tone_from_syllable(diff_val) if (diff_val and parse_tone_from_syllable(diff_val) is not None) else parse_tone_from_syllable(lex_syl)
                    return t if t is not None else 0.0

                def _pt(l: float, b: float, w: float, h: float, tone_val: float, t: float) -> tuple[float, float]:
                    return _tone_contour_point(l, b, w, h, tone_val, t)

                n_seg = 16
                seg_w_full = contour_width / max(1, n_syl)
                full_pts: list[tuple[float, float]] = []
                for i in range(n_syl):
                    tone_i = _get_tone_for_syl(i)
                    left_i = contour_left + i * seg_w_full
                    for k in range(n_seg + 1):
                        t = k / n_seg
                        full_pts.append(_pt(left_i, contour_bottom, seg_w_full, contour_height, tone_i, t))

                white_color = (255, 255, 255)
                pron_start_color = (160, 160, 165)
                fade_tail_color = (100, 100, 105)
                green_color = (100, 255, 120)
                green_start_color = (70, 180, 95)
                thick_bold = 12
                thick_start = 2
                pts_per_syl = n_seg + 1
                actual_ratio = 0.8   # 0~80% 구간에서 점점 진해짐
                fade_tail_ratio = 0.2  # 80%부터 끝까지 얇아짐
                cap_radius = max(2, thick_bold // 2)  # 녹색 진행 끝 둥글게
                # 흰색 라인 끝은 물방울 모양: 선과 같은 색의 작은 원으로 끝나게
                droplet_cap_radius = max(4, thick_bold // 2)

                progress_count = cur_i * (n_seg + 1) + min(n_seg, int(round(blend * n_seg)))
                progress_count = min(progress_count + 1, len(full_pts))
                show_green = play_start is not None  # L1 재생 시에만 녹색 진행선

                for i in range(n_syl):
                    start_pt = i * pts_per_syl
                    end_actual_pt = i * pts_per_syl + int(actual_ratio * pts_per_syl)
                    actual_len = max(1, min(end_actual_pt, len(full_pts) - 1) - start_pt)
                    tail_len = max(1, int(fade_tail_ratio * pts_per_syl))
                    end_tail_pt = min(end_actual_pt + tail_len, (i + 1) * pts_per_syl - 1, len(full_pts) - 1)

                    # 본체 구간 (0~80%): L1 재생 시에만 녹색이 지난 부분 녹색, 나머지 흰색
                    for idx in range(start_pt, min(end_actual_pt, len(full_pts) - 1)):
                        progress = (idx - start_pt) / actual_len
                        thick = max(thick_start, int(thick_start + (thick_bold - thick_start) * progress))
                        if show_green and idx < progress_count - 1:
                            seg_r = int(green_start_color[0] + (green_color[0] - green_start_color[0]) * progress)
                            seg_g = int(green_start_color[1] + (green_color[1] - green_start_color[1]) * progress)
                            seg_b = int(green_start_color[2] + (green_color[2] - green_start_color[2]) * progress)
                        else:
                            seg_r = int(pron_start_color[0] + (white_color[0] - pron_start_color[0]) * progress)
                            seg_g = int(pron_start_color[1] + (white_color[1] - pron_start_color[1]) * progress)
                            seg_b = int(pron_start_color[2] + (white_color[2] - pron_start_color[2]) * progress)
                        seg_color = (min(255, max(0, seg_r)), min(255, max(0, seg_g)), min(255, max(0, seg_b)))
                        a = (full_pts[idx][0], full_pts[idx][1])
                        b_pt = (full_pts[idx + 1][0], full_pts[idx + 1][1])
                        pygame.draw.line(screen, seg_color, (int(a[0]), int(a[1])), (int(b_pt[0]), int(b_pt[1])), thick)

                    # 꼬리 구간 (80%~끝): L1 재생 시에만 녹색
                    for idx in range(end_actual_pt, end_tail_pt):
                        if idx + 1 >= len(full_pts):
                            break
                        color = (green_color if (show_green and idx < progress_count - 1) else white_color)
                        a = (full_pts[idx][0], full_pts[idx][1])
                        b_pt = (full_pts[idx + 1][0], full_pts[idx + 1][1])
                        pygame.draw.line(screen, color, (int(a[0]), int(a[1])), (int(b_pt[0]), int(b_pt[1])), thick_bold)

                # 녹색 진행 곡선 끝 둥글게 (L1 재생 시에만)
                if show_green and progress_count > 0 and full_pts:
                    end_idx = min(progress_count, len(full_pts) - 1)
                    prog_pt = full_pts[end_idx]
                    pygame.draw.circle(screen, green_color, (int(prog_pt[0]), int(prog_pt[1])), cap_radius)

            # 한자 위치: 실제 병음 줄 높이만큼 띄워서 겹침 방지 (ref_height 고정값 대신 line_rect.height 사용)
            center_top = y_red_top + line_rect.height + pinyin_hanzi_gap

            # 속도 기반일 때 한자 음절별로 그리기 (자간 반영)
            hanzi_bottom_y = center_top + 62  # 폴백: 중심 + 폰트 절반
            if use_speed and n_syl > 0:
                hanzi_font_ft_inner = self._font_cn_step1_ft or self._font_cn_big_ft
                hanzi_chars = [c for c in sen_chars if c not in _punct_set and not c.isspace()]
                if len(hanzi_chars) == n_syl and hanzi_font_ft_inner is not None:
                    _max_bottom = center_top
                    for i in range(n_syl):
                        char = hanzi_chars[i]
                        try:
                            c_surf, c_rect = hanzi_font_ft_inner.render(char, (255, 255, 255))
                        except Exception:
                            c_surf = font_cn_big.render(char, True, (255, 255, 255))
                            c_rect = c_surf.get_rect()
                        cx_char = slot_left_list[i] + slot_width_list[i] / 2
                        blit_x = int(cx_char - c_rect.width / 2 - getattr(c_rect, "x", 0))
                        blit_y = int(center_top - c_rect.height / 2 - getattr(c_rect, "y", 0))
                        screen.blit(c_surf, (blit_x, blit_y))
                        _max_bottom = max(_max_bottom, blit_y + c_rect.height)
                    hanzi_bottom_y = _max_bottom
                    hanzi_drawn = True
            # 스파크라인 그리기용 데이터 (한자 위 미니맵)
            self._step1_sparkline_data = (slot_left_list, slot_width_list, n_syl, display_syllables, lexical_for_display, center_top)
        else:
            self._step1_sparkline_data = None

        # 한자 (큰 글자): 렌더 rect 기준으로 화면 가운데 정확히 배치 (속도 기반이 아닐 때)
        if not hanzi_drawn:
            hanzi_font_ft = self._font_cn_step1_ft or self._font_cn_big_ft
            if hanzi_font_ft is not None:
                try:
                    sen_surf, sen_rect = hanzi_font_ft.render(sen_text[:80], (255, 255, 255))
                    blit_x = cx - sen_rect.width // 2 - sen_rect.x
                    blit_y = center_top - sen_rect.height // 2 - sen_rect.y
                    screen.blit(sen_surf, (blit_x, blit_y))
                    hanzi_bottom_y = blit_y + sen_rect.height
                except Exception:
                    sen_surf = font_cn_big.render(sen_text[:80], True, (255, 255, 255))
                    sr = sen_surf.get_rect(center=(cx, center_top))
                    screen.blit(sen_surf, sr)
                    hanzi_bottom_y = sr.bottom
            else:
                sen_surf = font_cn_big.render(sen_text[:80], True, (255, 255, 255))
                sr = sen_surf.get_rect(center=(cx, center_top))
                screen.blit(sen_surf, sr)
                hanzi_bottom_y = sr.bottom
        center_top += line_gap + 56  # 한자–뜻(해석) 간격 넓게

        # 해석 (한국어): 화면 가운데 정확히 배치
        if trans_text:
            trans_surf = font_kr_step1.render(trans_text[:80], True, (200, 200, 200))
            tr = trans_surf.get_rect(center=(cx, center_top))
            screen.blit(trans_surf, tr)

        return {
            "hanzi_bottom_y": hanzi_bottom_y,
            "slot_left_list": slot_left_list,
            "slot_width_list": slot_width_list,
            "use_speed": use_speed,
            "sentences": sentences,
            "cx": cx,
            "_punct_set": _punct_set,
        }

    def _draw_step1_base_word_cards(self, screen: Any, item: dict, ctx: dict) -> None:
        """Step 1 base: 단어 카드(품사별 색상). ctx에는 hanzi_bottom_y, slot_left_list, slot_width_list, use_speed, sentences, cx, _punct_set."""
        words_list = item.get("words") or []
        if not words_list:
            return
        try:
            from data.table_manager import get_word_info_for_display
            _DEFAULT_BG = (45, 50, 65)
            _DEFAULT_FG = (200, 200, 200)
            font_word_kr = self._font_kr or pygame.font.Font(None, 24)
            card_gap = 12
            card_pad_x, card_pad_y = 16, 10
            card_min_w = 80
            hanzi_bottom_y = ctx["hanzi_bottom_y"]
            slot_left_list = ctx.get("slot_left_list", [])
            slot_width_list = ctx.get("slot_width_list", [])
            use_speed = ctx.get("use_speed", False)
            sentences = ctx["sentences"]
            cx = ctx["cx"]
            _punct_set = ctx["_punct_set"]

            _sen_chars_plain = [c for c in "".join(str(x) for x in sentences) if c not in _punct_set and not c.isspace()]

            def _word_slot_cx(word: str) -> int:
                if not (use_speed and slot_left_list and slot_width_list):
                    return cx
                word_chars = [c for c in word if c not in _punct_set and not c.isspace()]
                if not word_chars:
                    return cx
                n_wc = len(word_chars)
                start_idx = -1
                for si in range(len(_sen_chars_plain) - n_wc + 1):
                    if _sen_chars_plain[si : si + n_wc] == word_chars:
                        start_idx = si
                        break
                if start_idx < 0:
                    return cx
                end_idx = start_idx + n_wc - 1
                if end_idx >= len(slot_left_list):
                    return cx
                x_left = slot_left_list[start_idx]
                x_right = slot_left_list[end_idx] + slot_width_list[end_idx]
                return int((x_left + x_right) / 2)

            card_infos: list[tuple[list[Any], tuple, tuple, int, int, int]] = []
            for word in words_list:
                info = get_word_info_for_display(word)
                if not info:
                    continue
                pos_strs = info["pos"]
                meaning_strs = info["meaning"]
                anchor_cx = _word_slot_cx(word)
                n = max(len(pos_strs), len(meaning_strs))
                word_cards: list[tuple[list[Any], tuple, tuple, int, int]] = []
                for k in range(n):
                    pos = pos_strs[k] if k < len(pos_strs) else ""
                    meaning = meaning_strs[k] if k < len(meaning_strs) else ""
                    bg, fg = _POS_COLORS.get(pos, (_DEFAULT_BG, _DEFAULT_FG))
                    meaning_surf = font_word_kr.render(meaning[:40], True, (255, 255, 255)) if meaning else None
                    line_surfs: list[Any] = []
                    if meaning_surf:
                        line_surfs.append(meaning_surf)
                    if not line_surfs:
                        continue
                    content_w = max(s.get_width() for s in line_surfs)
                    line_h = font_word_kr.get_height()
                    content_h = line_h * len(line_surfs) + 4 * (len(line_surfs) - 1)
                    c_w = max(card_min_w, content_w + card_pad_x * 2)
                    c_h = content_h + card_pad_y * 2
                    word_cards.append((line_surfs, bg, fg, c_w, c_h))
                for wc in word_cards:
                    card_infos.append((*wc, anchor_cx))

            if not card_infos:
                return
            card_y_top = hanzi_bottom_y - 10
            line_h = font_word_kr.get_height()
            from collections import defaultdict as _dd
            anchor_groups: dict[int, list[int]] = _dd(list)
            for idx, ci in enumerate(card_infos):
                anchor_groups[ci[5]].append(idx)
            for anchor_cx_key, idxs in anchor_groups.items():
                group_w = sum(card_infos[i][3] for i in idxs) + card_gap * (len(idxs) - 1)
                gx = anchor_cx_key - group_w // 2
                for i in idxs:
                    line_surfs, bg, fg, c_w, c_h, _ = card_infos[i]
                    card_rect = pygame.Rect(gx, card_y_top, c_w, c_h)
                    pygame.draw.rect(screen, bg, card_rect, border_radius=8)
                    pygame.draw.rect(screen, fg, card_rect, 2, border_radius=8)
                    y_text = card_y_top + card_pad_y
                    for s in line_surfs:
                        screen.blit(s, (gx + (c_w - s.get_width()) // 2, y_text))
                        y_text += line_h + 4
                    gx += c_w + card_gap
        except Exception as _e:
            logging.getLogger(__name__).debug("단어 카드 오류(step1): %s", _e)

    def _draw_step1_base_sandhi(self, screen: Any, config: Any, item: dict) -> None:
        """Step 1 base: 좌측 하단 발음상 성조 변화 (이 문장에서 쓰인 타입만)."""
        sandhi_types_raw = item.get("pinyin_sandhi_types") or []
        _sandhi_skip = {"tone3_half", "bu_to_4", "neutral_char"}
        unique_sandhi = list(dict.fromkeys(t for t in sandhi_types_raw if t and t not in _sandhi_skip))
        if not unique_sandhi:
            return
        h = config.height
        font_kr = self._font_kr or pygame.font.Font(None, 28)
        left_margin = 20
        line_height = 28
        box_y = h - 40 - (len(unique_sandhi) + 1) * line_height
        title_surf = font_kr.render("발음상 성조 변화", True, (200, 200, 180))
        screen.blit(title_surf, (left_margin, box_y))
        for j, st in enumerate(unique_sandhi):
            label = SANDHI_TYPE_LABELS.get(st, st)
            line_surf = font_kr.render(label, True, (255, 220, 100))
            screen.blit(line_surf, (left_margin, box_y + line_height + j * line_height))

    def _draw_step1_base_hint(self, screen: Any, config: Any) -> None:
        """Step 1 base: 맨 아래 안내 문구."""
        w, h = config.width, config.height
        font_kr = self._font_kr or pygame.font.Font(None, 28)
        hint = "눈으로 보면서 원어민 리듬을 익히세요"
        hint_surf = font_kr.render(hint, True, (180, 190, 200))
        hint_r = hint_surf.get_rect(center=(w // 2, h - 40))
        screen.blit(hint_surf, hint_r)

    def _draw_step1_util(self, screen: Any, config: Any) -> None:
        """활용 페이지: 현재(util) 문장만 Step 1과 동일 위치·크기로 가운데에 표시."""
        w, h = config.width, config.height
        cx = w // 2
        item = self._data_list[self._current_index]

        # 타이틀: 쉐도잉 훈련 Step 2: 문장의 활용
        title_font = getattr(self, "_font_step1_title", None) or load_font_korean(52, weight="bold") or load_font_korean(52)
        if title_font:
            y_top = int(h * 0.06)
            part1 = title_font.render("쉐도잉 훈련 Step 2:", True, (255, 255, 255))
            part2 = title_font.render(" 문장의 활용", True, (255, 140, 0))
            r1, r2 = part1.get_rect(), part2.get_rect()
            total_w = r1.width + r2.width
            x1 = cx - total_w // 2
            screen.blit(part1, (x1, y_top))
            screen.blit(part2, (x1 + r1.width, y_top))

        # 현재 문장만 Step 1과 동일 위치(h*0.38), 동일 큰 폰트·가운데 정렬
        y_base = int(h * 0.38)
        self._draw_step2_sentence_block(screen, item, w, y_base, line_gap=130)

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