"""회화 스튜디오 메인 클래스."""
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import pygame

from utils.fonts import load_font_chinese, load_font_chinese_freetype, load_font_korean
from studio.recording_events import (
    VideoSegmentStart,
    VideoSegmentEnd,
    InsertSound,
    recording_log_event,
    is_recording,
)

from .constants import (
    _REPO_ROOT,
    ShadowingStep,
    Step1SoundState,
)
from .data_loading import build_data_list
from .overlay_draw import draw_paused_and_debug
from .video_players import SimpleVideoPlayer, VideoAudioPlayer
from .steps import ConversationStepContext, build_shadowing_steps

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
        self._step_ctx = ConversationStepContext(self)
        self._step_impls = build_shadowing_steps(self._step_ctx)
        self._step_impls[self._shadowing_step].enter()

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
        self._shadowing_step: ShadowingStep = ShadowingStep.LISTEN  # 기본: 듣기(멈춤 시 UI)
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
        """현재 셰도잉 훈련 단계 (VIDEO / LISTEN / UTIL)."""
        return self._shadowing_step

    def _set_shadowing_step(self, step: ShadowingStep) -> None:
        """단계 전환: exit → enter (VIDEO·UTIL enter 시 페이드/UI 잔상 제거는 각 Step.enter에서)."""
        if step == self._shadowing_step:
            return
        self._step_impls[self._shadowing_step].exit()
        self._shadowing_step = step
        self._step_impls[self._shadowing_step].enter()

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
                continue
            if e.key in (pygame.K_1, pygame.K_KP1):
                self._set_shadowing_step(ShadowingStep.VIDEO)
                continue
            if e.key in (pygame.K_2, pygame.K_KP2):
                self._set_shadowing_step(ShadowingStep.LISTEN)
                continue
            if e.key in (pygame.K_3, pygame.K_KP3):
                self._set_shadowing_step(ShadowingStep.UTIL)
                continue
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
            self._step_impls[self._shadowing_step].update(config)
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
        """메인 그리기: 현재 ShadowingStep에 대응하는 Step의 draw + 공통 오버레이."""
        screen.fill(config.bg_color)
        self._step_impls[self._shadowing_step].draw(screen, config)
        draw_paused_and_debug(self, screen, config)

    def get_recording_prefix(self) -> Optional[str]:
        if not self._data_list:
            return None
        item = self._data_list[self._current_index]
        vid = item.get("id", 0)
        return f"REC_{vid}"