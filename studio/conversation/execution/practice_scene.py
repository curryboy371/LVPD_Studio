"""연습 장면(Scene): 비디오 + 문장 + 현재 단어(최소)."""

from __future__ import annotations

from dataclasses import replace
from enum import Enum, auto
from pathlib import Path
import logging
import os
import math
import time
from typing import Callable, Literal, Optional

import pygame

from core.paths import get_repo_root
from utils.fonts import load_font_chinese, load_font_korean

from ..core.scene_transition import SceneTransitionMode
from ..core.types import (
    ConversationItemLike,
    FrameContext,
    SentenceStyleConfig,
    build_sentence_render_data_with_tone_icons,
)
from ..core.conversation_step import IConversationStep
from ..follow_audio import PracticeFollowSoundPlayer
from ..tools.mode_icons import blit_mode_icon_bottom_left, load_mode_icon
from ..tools.playback_bar import PlaybackBarRenderer
from utils.pinyin_processor import get_pinyin_processor

logger = logging.getLogger(__name__)

# sub 한 변형당 자동 대기 상한(초). 음성 길이×배율+간격이 과하면 녹화가 수십 분 멈춘 것처럼 보임.
_SUB_VARIANT_WAIT_WARN_SEC = 90.0
_SUB_VARIANT_WAIT_MAX_SEC = 180.0

# sub 변형: 팁·문장 동시 표시 → 팁 아웃 → 듣기/말하기 재생
_SubPlayPhase = Literal["intro_hold", "tip_out", "playing"]


def _sanitize_wait_sec(v: float, *, fallback: float) -> float:
    """NaN/inf면 타이머 비교가 영원히 False가 되어 PRACTICE가 멈출 수 있음."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(x) or x < 0.0:
        return fallback
    return x


def _clamp_sub_variant_wait(wt: float, *, hold: float) -> float:
    w = _sanitize_wait_sec(wt, fallback=hold)
    if w > _SUB_VARIANT_WAIT_MAX_SEC:
        logger.warning(
            "PRACTICE: sub 변형 대기 %.1fs → 상한 %.1fs로 제한(너무 길면 녹화가 멈춘 것처럼 보입니다)",
            w,
            _SUB_VARIANT_WAIT_MAX_SEC,
        )
        return float(_SUB_VARIANT_WAIT_MAX_SEC)
    if w > _SUB_VARIANT_WAIT_WARN_SEC:
        logger.info(
            "PRACTICE: sub 변형 대기 약 %.1fs (%.0fs 넘으면 상한 %ss 적용)",
            w,
            _SUB_VARIANT_WAIT_WARN_SEC,
            _SUB_VARIANT_WAIT_MAX_SEC,
        )
    return w


class PracticeScene(IConversationStep):
    """연습 장면.

    render_only 범위에서는 '단어 리스트를 순회' 로직은 넣지 않고,
    words가 있으면 첫 단어만 화면에 표시하는 수준으로 단순화한다.

    `style`은 `ConversationStudio.init`에서 폰트 로드와 맞춘 RGB로 구성해 넘긴다.
    """

    class Stage(Enum):
        """연습 장면 내부 단계."""

        TITLE = auto()
        INTRO_SENTENCE_IN = auto()
        INTRO_SENTENCE_HOLD = auto()
        SHOW_CONTENT = auto()
        SHOW_SUB_CONTENT = auto()

    _SPEAK_SOUND_LEN_SCALE = 1.3
    _SUB_TIP_HOLD_PER_WORD_SEC = 0.25
    _SUB_TIP_HOLD_MAX_SEC = 3.8
    def __init__(
        self,
        *,
        drawer,
        video_player,
        style: SentenceStyleConfig,
        play_voice: Callable[..., None] | None = None,
        start_listen_clip: Callable[..., float] | None = None,
        on_follow_sound_started: Callable[[str, float], None] | None = None,
        is_recording: Callable[[], bool] | None = None,
        recording_timeline_sec: Callable[[], float] | None = None,
        title_text: str = "듣고 따라해보기",
        title_fade_in_sec: float = 1.0,
        tip_box_intro_fade_in_sec: float = 0.5,
        sentence_intro_fade_in_sec: float = 0.55,
        tip_box_intro_fade_out_sec: float = 1.25,
        tip_intro_hold_sec: float = 1.5,
        sentence_intro_hold_sec: float = 2.0,
        content_hold_sec: float = 3.0,
        base_to_sub_slide_out_sec: float = 0.55,
        base_to_sub_slide_in_sec: float = 0.6,
        base_to_sub_slide_out_px: int = 28,
        base_to_sub_slide_in_offset_px: int = 10,
    ) -> None:
        """연습용 Drawer·비디오·문장 스타일을 연결하고 제목 페이드인을 준비한다."""
        super().__init__()
        self.drawer = drawer
        self.video_player = video_player
        self.play_voice = play_voice
        self.start_listen_clip = start_listen_clip
        self.on_follow_sound_started = on_follow_sound_started
        self.is_recording = is_recording
        self._recording_timeline_sec = recording_timeline_sec
        self.scene_transition_mode: SceneTransitionMode = SceneTransitionMode.CUT
        self.scene_transition_duration_sec: float = 0.4
        self.scene_transition_overlay_peak_alpha: int = 220
        self._style = style
        self.title_text = str(title_text or "듣고 따라해보기")
        self.title_fade_in_sec = float(title_fade_in_sec)
        self._tip_intro_fade_in_sec = max(1e-6, float(tip_box_intro_fade_in_sec))
        self._sentence_intro_fade_in_sec = max(1e-6, float(sentence_intro_fade_in_sec))
        self._tip_intro_fade_out_sec = max(1e-6, float(tip_box_intro_fade_out_sec))
        self._tip_intro_hold_sec = max(0.0, float(tip_intro_hold_sec))
        self._sentence_intro_hold_sec = max(0.0, float(sentence_intro_hold_sec))
        # SHOW_CONTENT 단계에서 sub 문장으로 넘어가기 전 대기 시간(초).
        self.content_hold_sec = float(content_hold_sec)
        self.base_to_sub_slide_out_sec = max(1e-6, float(base_to_sub_slide_out_sec))
        self.base_to_sub_slide_in_sec = max(1e-6, float(base_to_sub_slide_in_sec))
        self.base_to_sub_slide_out_px = int(base_to_sub_slide_out_px)
        self.base_to_sub_slide_in_offset_px = int(base_to_sub_slide_in_offset_px)
        self._base_to_sub_transition: Optional[Literal["out", "in"]] = None
        self._base_to_sub_elapsed: float = 0.0
        self._title_channel = "practice_title"
        self._sentence_channel = "practice_sentence"
        self._tip_intro_channel = "practice_tip_intro"
        self._active_item_key = None
        self._title_wait_remaining_sec = 0.0
        self._content_wait_remaining_sec = 0.0
        # SHOW_SUB_CONTENT 단계에서 sub 문장 간 자동 전환 대기 시간(초).
        self._sub_content_hold_sec = 3.0
        # 듣기 게이지 완료 후 말하기 게이지 시작 전 대기(초).
        self._listen_to_speak_gap_sec = 1.0
        # 말하기(주황) 게이지 완료 후 다음 sub/전환 전 대기(초).
        self._speak_complete_hold_sec = 1.5
        self._sub_content_wait_remaining_sec = 0.0
        self._sub_content_wait_total_sec = 0.0
        self._sub_content_sound_sec = 0.0
        self._sub_content_ko_listen_sec = 0.0
        self._sub_speak_sec = 0.0
        self._sub_listen_ko_path = ""
        self._sub_listen_cn_path = ""
        self._sub_listen_ko_played = False
        self._sub_listen_cn_played = False
        self._sub_variants: list[dict] = []
        self._sub_variant_index = 0
        self._content_visible = False
        self._current_sub_variant = None
        self._playback_bar = PlaybackBarRenderer()
        self._tip_box_surface = self._load_tip_box_surface()
        self._tip_font_cn = load_font_chinese(42, (0, 0, 0), weight="bold")
        self._tip_font_kr = load_font_korean(42, (0, 0, 0), weight="bold")
        self._tip_font_fallback = pygame.font.Font(None, 42)
        self._title_image_surface = self._load_title_image_surface("문장_연습하기.png")
        if self._title_image_surface is None:
            raise RuntimeError("타이틀 이미지 파일을 찾을 수 없습니다: 문장_연습하기.png")
        # 문장 이해하기 타이틀의 실제 렌더 크기를 기준으로 연습 타이틀 크기를 맞추기 위해 보관한다.
        self._title_reference_surface = self._load_title_image_surface("문장_이해하기.png")
        self._listen_icon_surface = self._load_mode_icon_surface("listen.png")
        self._speak_icon_surface = self._load_mode_icon_surface("speak.png")
        self._follow_player = PracticeFollowSoundPlayer(
            on_follow_started=on_follow_sound_started,
            is_recording=is_recording,
        )
        # LearningScene과 동일하게 디버그에서 읽을 수 있도록 stage 필드를 유지한다.
        self.stage: "PracticeScene.Stage" = self.Stage.TITLE
        self._practice_stage_log_last: "PracticeScene.Stage | None" = None
        self._intro_wait_remaining_sec = 0.0
        self._sub_play_phase: _SubPlayPhase | None = None
        self._sub_phase_log_last: _SubPlayPhase | None = None
        self._sub_intro_wait_remaining_sec = 0.0
        self._sub_slide_in_elapsed = 0.0
        self._sub_play_started_mono_sec: float = 0.0
        self._sub_play_timeline_anchor_sec: float | None = None
        self._sub_all_variants_finished: bool = False
        self._sub_render_item_cache_key: tuple | None = None
        self._sub_render_item_cached: ConversationItemLike | None = None
        self._clip_duration_cache: dict[str, float] = {}
        self.drawer.hide_now(self._title_channel)
        self.drawer.hide_now(self._sentence_channel)
        self.drawer.hide_now(self._tip_intro_channel)

    def reset(self, *, clear_background: bool = False) -> None:
        """다른 SceneKind로 갔다가 돌아올 때 Stage·타이머 잔상으로 문장/재생바가 깜빡이지 않게 한다."""
        super().reset(clear_background=clear_background)
        if clear_background:
            self._active_item_key = None
            self._set_stage(self.Stage.TITLE)
            self._content_visible = False
            self._title_wait_remaining_sec = 0.0
            self._content_wait_remaining_sec = 0.0
            self._sub_variants = []
            self._sub_variant_index = 0
            self._current_sub_variant = None
            self._sub_content_wait_remaining_sec = 0.0
            self._sub_content_wait_total_sec = 0.0
            self._sub_content_sound_sec = 0.0
            self._sub_content_ko_listen_sec = 0.0
            self._sub_speak_sec = 0.0
            self._reset_sub_listen_playback()
            self._base_to_sub_transition = None
            self._base_to_sub_elapsed = 0.0
            self._stop_follow_sound()
            self.drawer.hide_now(self._title_channel)
            self.drawer.hide_now(self._sentence_channel)
            self.drawer.hide_now(self._tip_intro_channel)
            self._intro_wait_remaining_sec = 0.0
            self._sub_play_phase = None
            self._sub_phase_log_last = None
            self._sub_intro_wait_remaining_sec = 0.0
            self._sub_slide_in_elapsed = 0.0
            self._sub_play_started_mono_sec = 0.0
            self._sub_play_timeline_anchor_sec = None
            self._sub_all_variants_finished = False
            self._practice_stage_log_last = None
            self._invalidate_sub_render_cache()

    def _invalidate_sub_render_cache(self) -> None:
        self._sub_render_item_cache_key = None
        self._sub_render_item_cached = None

    def _is_recording_active(self) -> bool:
        if self.is_recording is None:
            return False
        try:
            return bool(self.is_recording())
        except Exception:
            return False

    def _sub_playing_elapsed_sec(self) -> float:
        """playing 단계 경과(초).

        녹화: runner의 `recording_time_sec`(프레임 인덱스/fps) — mux·게이지·노래방 동기.
        디버그: monotonic — 실시간 재생과 맞춤.
        """
        if (
            self._is_recording_active()
            and self._recording_timeline_sec is not None
            and self._sub_play_timeline_anchor_sec is not None
        ):
            try:
                return max(
                    0.0,
                    float(self._recording_timeline_sec())
                    - float(self._sub_play_timeline_anchor_sec),
                )
            except Exception:
                pass
        if self._sub_play_started_mono_sec <= 0.0:
            return 0.0
        return max(0.0, time.monotonic() - self._sub_play_started_mono_sec)

    def _arm_sub_play_clock(self) -> None:
        """playing 구간 타이머 기준을 잡는다(녹화 타임라인 vs monotonic)."""
        self._sub_play_timeline_anchor_sec = None
        self._sub_play_started_mono_sec = 0.0
        if self._is_recording_active() and self._recording_timeline_sec is not None:
            try:
                self._sub_play_timeline_anchor_sec = float(self._recording_timeline_sec())
            except Exception:
                self._sub_play_timeline_anchor_sec = None
        if self._sub_play_timeline_anchor_sec is None:
            self._sub_play_started_mono_sec = time.monotonic()

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """항목만 바뀌고 슬롯 리셋이 빠진 경우에도 이전 base의 sub가 남지 않게 한다."""
        key = self._playback_item_key(item)
        if self.is_done and self._active_item_key is not None and key != self._active_item_key:
            self.is_done = False
            self.transition_signal = False
            self._sub_all_variants_finished = False
        if self.is_done and not self.transition_signal:
            # 마지막 변형 재생 중 잘못 is_done=True가 되면 타이머가 멈춘 것처럼 보인다.
            if (
                not self._sub_all_variants_finished
                and self.stage == self.Stage.SHOW_SUB_CONTENT
                and self._sub_play_phase == "playing"
                and float(self._sub_content_wait_remaining_sec) > 1e-3
            ):
                self.is_done = False
            else:
                return
        self.on_update(ctx, item=item)

    def _set_stage(self, stage: "PracticeScene.Stage") -> None:
        """연습 장면 내부 Stage를 전환한다."""
        self.stage = stage
        try:
            if self._practice_stage_log_last == stage:
                return
            self._practice_stage_log_last = stage
            print(f"[practice][stage] {stage.name}", flush=True)
        except Exception:
            pass

    def _log_sub_variant_wait(self, wt: float) -> None:
        """SHOW_SUB_CONTENT: 변형별 대기 시작 시 녹화 콘솔용(장시간 무응답처럼 보이지 않게)."""
        total = max(1, len(self._sub_variants))
        cur = min(total, self._sub_variant_index + 1)
        try:
            print(f"[practice][sub] variant {cur}/{total} 대기~{wt:.1f}s", flush=True)
        except Exception:
            pass

    def _sentence_slide_y_offset_px(self) -> int:
        """기본→첫 sub 전환 시 문장 블록 세로 오프셋(위 슬라이드 아웃 / sub 문장 인트로 슬라이드 인)."""
        if self.stage == self.Stage.SHOW_CONTENT and self._base_to_sub_transition == "out":
            t = min(1.0, self._base_to_sub_elapsed / self.base_to_sub_slide_out_sec)
            return int(round(-self.base_to_sub_slide_out_px * t))
        if self.stage == self.Stage.SHOW_SUB_CONTENT and self._sub_play_phase == "sentence_in":
            t = min(1.0, self._sub_slide_in_elapsed / self.base_to_sub_slide_in_sec)
            return int(round(self.base_to_sub_slide_in_offset_px * (1.0 - t)))
        return 0

    @staticmethod
    def _playback_item_key(item: ConversationItemLike) -> tuple:
        """아이템 전환 판별용 키. topic·id·index로 구분한다(동일 id 다른 topic 등)."""
        topic_key = str(item.get("topic") or "").strip().lower()
        raw_id = item.get("id")
        try:
            id_key = int(float(str(raw_id).strip())) if raw_id not in (None, "") else None
        except (TypeError, ValueError):
            id_key = raw_id
        try:
            idx_key = int(item.get("index", -1))
        except (TypeError, ValueError):
            idx_key = -1
        return (topic_key, id_key, idx_key)

    def on_update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """아이템이 바뀌면 제목을 먼저 fade in 하고, 끝난 뒤 문장/단어를 노출한다."""
        # Drawer 내부 알파 애니메이션 타이머를 매 프레임 진행한다.
        dt = float(ctx.dt_sec)
        eff_dt = dt if dt > 1e-6 else (1.0 / 30.0)
        self.drawer.fade_tick(dt)

        key = self._playback_item_key(item)
        if key != self._active_item_key:
            self._active_item_key = key
            self._practice_stage_log_last = None
            # 새 아이템 진입 시에는 본문을 숨기고 제목 페이드부터 진행한다.
            self._content_visible = False
            self._title_wait_remaining_sec = self.title_fade_in_sec
            # 기본 문장 노출 후 sub 문장으로 전환할 타이머를 초기화한다.
            self._content_wait_remaining_sec = self.content_hold_sec * 0.5
            self._sub_variants = self._pick_sub_variants(item)
            self._sub_variant_index = 0
            self._current_sub_variant = self._sub_variants[0] if self._sub_variants else None
            self._sub_content_wait_remaining_sec = self._sub_content_hold_sec
            self._sub_content_wait_total_sec = self._sub_content_hold_sec
            self._sub_content_sound_sec = 0.0
            self._sub_content_ko_listen_sec = 0.0
            self._sub_speak_sec = 0.0
            self._reset_sub_listen_playback()
            self._base_to_sub_transition = None
            self._base_to_sub_elapsed = 0.0
            self._sub_play_phase = None
            self._sub_phase_log_last = None
            self._sub_intro_wait_remaining_sec = 0.0
            self._sub_slide_in_elapsed = 0.0
            self._sub_all_variants_finished = False
            self._invalidate_sub_render_cache()
            self._stop_follow_sound()
            self.drawer.hide_now(self._sentence_channel)
            self.drawer.hide_now(self._tip_intro_channel)
            self.drawer.fade_on(self._title_channel, self.title_fade_in_sec)
            self._set_stage(self.Stage.TITLE)
            return

        # Stage 기반으로 제목 페이드 완료 시점을 관리한다.
        if self.stage == self.Stage.TITLE:
            if self._title_wait_remaining_sec > 0.0:
                self._title_wait_remaining_sec = max(0.0, self._title_wait_remaining_sec - eff_dt)
            if self._title_wait_remaining_sec <= 0.0:
                self.drawer.show_now(self._title_channel)
                if self._current_sub_variant is not None:
                    # sub 변형이 있으면 기본 문장 intro를 생략하고
                    # 바로 tip box -> sub sentence 시퀀스로 진입한다.
                    self._content_visible = True
                    self._set_stage(self.Stage.SHOW_SUB_CONTENT)
                    self._begin_sub_variant_intro()
                else:
                    self._set_stage(self.Stage.INTRO_SENTENCE_IN)
                    self.drawer.hide_now(self._tip_intro_channel)
                    self.drawer.fade_on(self._sentence_channel, self._sentence_intro_fade_in_sec)
                    self._intro_wait_remaining_sec = self._sentence_intro_fade_in_sec
            return

        if self.stage == self.Stage.INTRO_SENTENCE_IN:
            self._intro_wait_remaining_sec = max(0.0, self._intro_wait_remaining_sec - eff_dt)
            if self._intro_wait_remaining_sec <= 0.0:
                self._set_stage(self.Stage.INTRO_SENTENCE_HOLD)
                self._intro_wait_remaining_sec = self._sentence_intro_hold_sec
            return

        if self.stage == self.Stage.INTRO_SENTENCE_HOLD:
            self._intro_wait_remaining_sec = max(0.0, self._intro_wait_remaining_sec - eff_dt)
            if self._intro_wait_remaining_sec <= 0.0:
                self.drawer.hide_now(self._tip_intro_channel)
                self._content_visible = True
                self._content_wait_remaining_sec = self.content_hold_sec * 0.5
                self._set_stage(self.Stage.SHOW_CONTENT)
            return

        # 기본 문장을 잠시 보여준 뒤, sub_sentences.csv 기반 변형이 있으면 다음 Stage로 넘긴다.
        if self.stage == self.Stage.SHOW_CONTENT:
            if self._base_to_sub_transition == "out":
                self._base_to_sub_elapsed += dt
                if self._base_to_sub_elapsed >= self.base_to_sub_slide_out_sec:
                    self._base_to_sub_transition = None
                    self._base_to_sub_elapsed = 0.0
                    self._set_stage(self.Stage.SHOW_SUB_CONTENT)
                    self._begin_sub_variant_intro()
                return
            if self._content_wait_remaining_sec > 0.0:
                self._content_wait_remaining_sec = max(0.0, self._content_wait_remaining_sec - eff_dt)
            if self._content_wait_remaining_sec <= 0.0:
                # sub 변형이 없으면 기본 문장 노출 후 곧바로 Step 완료 처리한다.
                if self._current_sub_variant is None:
                    self.complete()
                    self.allow_transition()
                    return
                if self._base_to_sub_transition is None:
                    self._base_to_sub_transition = "out"
                    self._base_to_sub_elapsed = 0.0
                    self.drawer.fade_off(self._sentence_channel, self.base_to_sub_slide_out_sec)
            return

        # SHOW_SUB_CONTENT: sub별 팁 인 → 문장 인 → 팁 아웃 → 듣기/말하기 타이머
        if self.stage == self.Stage.SHOW_SUB_CONTENT:
            if self._sub_play_phase != self._sub_phase_log_last:
                self._sub_phase_log_last = self._sub_play_phase
                try:
                    phase = str(self._sub_play_phase or "none")
                    print(
                        f"[practice][sub-phase] {phase} | intro_wait={self._sub_intro_wait_remaining_sec:.3f}s "
                        f"play_wait={self._sub_content_wait_remaining_sec:.3f}s",
                        flush=True,
                    )
                except Exception:
                    pass
            if self._sub_play_phase == "intro_hold":
                self._sub_intro_wait_remaining_sec = max(0.0, self._sub_intro_wait_remaining_sec - eff_dt)
                if self._sub_intro_wait_remaining_sec <= 0.0:
                    self._sub_play_phase = "tip_out"
                    self.drawer.fade_off(self._tip_intro_channel, self._tip_intro_fade_out_sec)
                    self._sub_intro_wait_remaining_sec = self._tip_intro_fade_out_sec
                return
            if self._sub_play_phase == "tip_out":
                self._sub_intro_wait_remaining_sec = max(0.0, self._sub_intro_wait_remaining_sec - eff_dt)
                if self._sub_intro_wait_remaining_sec <= 0.0:
                    self.drawer.hide_now(self._tip_intro_channel)
                    self._sub_play_phase = "playing"
                    wait_total = self._start_current_sub_variant_audio_and_get_wait()
                    wt = _clamp_sub_variant_wait(
                        float(wait_total), hold=float(self._sub_content_hold_sec)
                    )
                    self._sub_content_wait_total_sec = wt
                    self._sub_content_wait_remaining_sec = wt
                    self._arm_sub_play_clock()
                    self._log_sub_variant_wait(wt)
                return
            if self._sub_play_phase != "playing":
                return
            total_wait = max(0.0, float(self._sub_content_wait_total_sec))
            elapsed_wait = self._sub_playing_elapsed_sec()
            self._sub_content_wait_remaining_sec = _sanitize_wait_sec(
                total_wait - elapsed_wait,
                fallback=0.0,
            )
            self._tick_sub_listen_audio(elapsed_wait)
            self._sync_follow_sound_for_sub_content()
            hard_limit = max(15.0, total_wait + 5.0)
            if elapsed_wait >= hard_limit and self._sub_content_wait_remaining_sec > 0.0:
                logger.warning(
                    "PRACTICE: sub 변형 재생 타임아웃(%.1fs >= %.1fs)으로 강제 전환",
                    elapsed_wait,
                    hard_limit,
                )
                self._sub_content_wait_remaining_sec = 0.0
            if self._sub_content_wait_remaining_sec <= 0.0:
                self._sub_play_timeline_anchor_sec = None
                self._sub_play_started_mono_sec = 0.0
                if self._sub_all_variants_finished:
                    return
                if len(self._sub_variants) > 1:
                    next_index = self._sub_variant_index + 1
                    if next_index < len(self._sub_variants):
                        self._sub_variant_index = next_index
                        self._current_sub_variant = self._sub_variants[self._sub_variant_index]
                        self._begin_sub_variant_intro()
                        return
                # 마지막 sub 변형까지 모두 끝나면 다음 SceneKind로 전환한다.
                try:
                    print(
                        f"[practice][sub] 변형 {len(self._sub_variants)}개 완료 → 다음 장면 전환",
                        flush=True,
                    )
                except Exception:
                    pass
                self._stop_follow_sound()
                self._sub_all_variants_finished = True
                self.complete()
                self.allow_transition()
        return

    def _sync_follow_sound_for_sub_content(self) -> None:
        """말하기(주황) + 말하기 완료 후 대기 구간까지 follow mp3를 재생한다."""
        if not self._is_follow_active_phase():
            self._stop_follow_sound()
            return
        if self._follow_player.is_playing:
            return
        self._play_random_follow_sound()

    def _sub_listen_total_sec(self) -> float:
        """듣기 구간 전체(한국어 선행 + 중국어) 길이(초)."""
        return max(0.0, float(self._sub_content_ko_listen_sec)) + max(
            0.0, float(self._sub_content_sound_sec)
        )

    def _is_follow_active_phase(self) -> bool:
        tl = self._sub_playback_timeline()
        if tl["listen_total"] <= 1e-6 or tl["speak_sec"] <= 1e-6:
            return False
        return tl["t_speak_start"] <= tl["elapsed"] < tl["t_follow_end"]

    def _follow_active_remaining_sec(self) -> float:
        tl = self._sub_playback_timeline()
        if tl["listen_total"] <= 1e-6 or tl["speak_sec"] <= 1e-6:
            return 0.0
        if tl["elapsed"] < tl["t_speak_start"] or tl["elapsed"] >= tl["t_follow_end"]:
            return 0.0
        return max(0.0, tl["t_follow_end"] - tl["elapsed"])

    def _play_random_follow_sound(self) -> None:
        self._follow_player.play_random(
            duration_hint_sec=self._follow_active_remaining_sec(),
        )

    def _stop_follow_sound(self) -> None:
        self._follow_player.stop()

    def _pick_sub_variants(self, item: ConversationItemLike) -> list[dict]:
        """아이템의 sub_variants(=sub_sentences.csv 변형)에서 유효 항목만 반환한다."""
        variants = item.get("sub_variants") or []
        if not isinstance(variants, list) or not variants:
            return []
        valid: list[dict] = []
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            replaced = str(variant.get("replaced_sentence") or "").strip()
            if not replaced:
                continue
            valid.append(dict(variant))
        return valid

    def _begin_sub_variant_intro(self) -> None:
        """sub 변형: 팁·문장 동시 표시 → 팁 아웃 → 음성/게이지."""
        self.drawer.show_now(self._tip_intro_channel)
        self.drawer.show_now(self._sentence_channel)
        self._sub_play_phase = "intro_hold"
        self._sub_play_started_mono_sec = 0.0
        self._sub_play_timeline_anchor_sec = None
        hold = max(
            float(self._sentence_intro_hold_sec),
            self._compute_sub_tip_hold_sec(),
        )
        self._sub_intro_wait_remaining_sec = hold
        self._sub_slide_in_elapsed = 0.0

    def _sub_variant_render_item(self, item: ConversationItemLike) -> ConversationItemLike:
        """현재 `sub` 변형으로 `draw_item_sentence` / 하이라이트용 렌더 항목을 만든다."""
        if self._current_sub_variant is None or not isinstance(item, dict):
            return item
        cache_key = (
            self._playback_item_key(item),
            self._sub_variant_index,
            str(self._current_sub_variant.get("replaced_sentence") or ""),
        )
        if (
            cache_key == self._sub_render_item_cache_key
            and self._sub_render_item_cached is not None
        ):
            return self._sub_render_item_cached
        base_map = item
        replaced_sentence = str(self._current_sub_variant.get("replaced_sentence") or "").strip()
        pinyin_marks = str(self._current_sub_variant.get("pinyin_marks") or "").strip()
        pinyin_phonetic = str(self._current_sub_variant.get("pinyin_phonetic") or "").strip()
        pinyin_lexical = str(self._current_sub_variant.get("pinyin_lexical") or "").strip()
        if replaced_sentence and not pinyin_marks:
            try:
                pinyin_processor = get_pinyin_processor()
                if pinyin_processor.available:
                    pinyin_marks = pinyin_processor.full_convert(replaced_sentence)
                    pinyin_lexical = " ".join(pinyin_processor.get_lexical_pinyin(replaced_sentence)).strip()
                    pinyin_phonetic = " ".join(pinyin_processor.get_phonetic_pinyin(replaced_sentence)).strip()
            except Exception:
                pass
        rendered: ConversationItemLike = {
            **base_map,
            "sentence": [replaced_sentence],
            "translation": [str(self._current_sub_variant.get("alt_translation") or "").strip()],
            "pinyin": pinyin_marks,
            "pinyin_marks": pinyin_marks,
            "pinyin_phonetic": pinyin_phonetic,
            "pinyin_lexical": pinyin_lexical,
        }
        self._sub_render_item_cache_key = cache_key
        self._sub_render_item_cached = rendered
        return rendered

    @staticmethod
    def _resolve_sub_audio_path(variant: dict, key: str) -> str:
        raw = str(variant.get(key) or "").strip()
        if not raw:
            return ""
        if key == "alt_sound_path":
            from core.paths import resolve_conversation_sub_cn_sound_path

            resolved = resolve_conversation_sub_cn_sound_path(raw)
            return str(resolved) if resolved else ""
        sp = Path(raw.replace("\\", "/"))
        if not sp.is_absolute():
            sp = get_repo_root() / sp
        return str(sp) if sp.is_file() else ""

    def _reset_sub_listen_playback(self) -> None:
        self._sub_listen_ko_path = ""
        self._sub_listen_cn_path = ""
        self._sub_listen_ko_played = False
        self._sub_listen_cn_played = False

    def _clip_duration_sec(self, path: str) -> float:
        if not path:
            return 0.0
        cached = self._clip_duration_cache.get(path)
        if cached is not None:
            return cached
        try:
            if pygame.mixer.get_init() is None:
                from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
            dur = max(0.0, float(pygame.mixer.Sound(path).get_length() or 0.0))
        except Exception:
            dur = 0.0
        self._clip_duration_cache[path] = dur
        return dur

    def _tick_sub_listen_audio(self, elapsed_sec: float) -> None:
        """playing 단계 경과 시간에 맞춰 ko 선행 → cn 재생(초록 게이지는 cn 구간만)."""
        variant = self._current_sub_variant if isinstance(self._current_sub_variant, dict) else {}
        ko_sec = max(0.0, float(self._sub_content_ko_listen_sec))
        if (
            self._sub_listen_ko_path
            and not self._sub_listen_ko_played
            and elapsed_sec < max(0.05, ko_sec + 0.05)
        ):
            self._sub_listen_ko_played = True
            self._play_listen_clip(self._sub_listen_ko_path, variant=variant)
            return
        if (
            self._sub_listen_cn_path
            and not self._sub_listen_cn_played
            and elapsed_sec + 1e-3 >= ko_sec
        ):
            self._sub_listen_cn_played = True
            self._play_listen_clip(self._sub_listen_cn_path, variant=variant)

    def _play_listen_clip(self, path: str, *, variant: dict) -> None:
        if self.start_listen_clip is not None:
            try:
                self.start_listen_clip(path, item=variant)
                return
            except Exception as ex:
                logger.warning("PRACTICE: start_listen_clip 실패(%s): %s", path, ex)
        # 녹화 모드 play_voice는 채널 idle까지 블로킹 → FSM·타이머가 멈춘 것처럼 보임.
        if self.is_recording is not None:
            try:
                if bool(self.is_recording()):
                    return
            except Exception:
                return
        if self.play_voice is not None:
            try:
                self.play_voice(path, item=variant)
            except Exception:
                pass

    def _start_current_sub_variant_audio_and_get_wait(self) -> float:
        """듣기 타이머: ko 선행 → cn(초록 게이지) → gap → 말하기. 재생은 경과에 맞춰 tick."""
        variant = self._current_sub_variant if isinstance(self._current_sub_variant, dict) else {}
        ko_path = self._resolve_sub_audio_path(variant, "alt_ko_sound_path")
        cn_path = self._resolve_sub_audio_path(variant, "alt_sound_path")
        self._reset_sub_listen_playback()
        self._sub_listen_ko_path = ko_path
        self._sub_listen_cn_path = cn_path

        ko_sec = self._clip_duration_sec(ko_path) if ko_path else 0.0
        cn_sec = self._clip_duration_sec(cn_path) if cn_path else 0.0
        ko_sec = _sanitize_wait_sec(ko_sec, fallback=0.0)
        cn_sec = _sanitize_wait_sec(cn_sec, fallback=0.0)

        if ko_sec <= 1e-6 and cn_sec <= 1e-6:
            logger.warning(
                "PRACTICE: sub 듣기 음성 길이 0 — 기본 대기 %.1fs | ko=%s cn=%s",
                self._sub_content_hold_sec,
                ko_path or "(없음)",
                cn_path or "(없음)",
            )
            self._sub_content_ko_listen_sec = 0.0
            self._sub_content_sound_sec = 0.0
            return float(self._sub_content_hold_sec)

        self._sub_content_ko_listen_sec = ko_sec
        self._sub_content_sound_sec = cn_sec
        gap = float(self._listen_to_speak_gap_sec)
        tail = max(0.0, float(self._speak_complete_hold_sec))
        speak_base = cn_sec if cn_sec > 1e-6 else (ko_sec + cn_sec)
        speak_sec = speak_base * float(self._SPEAK_SOUND_LEN_SCALE)
        self._sub_speak_sec = max(0.0, float(speak_sec))
        total = ko_sec + cn_sec + max(0.0, gap) + speak_sec + tail
        return _sanitize_wait_sec(total, fallback=float(self._sub_content_hold_sec))

    def _sub_playback_timeline(self) -> dict[str, float]:
        """sub playing 구간 경계(초). 게이지·노래방·follow가 동일 기준."""
        total_sec = max(0.0, float(self._sub_content_wait_total_sec))
        remaining_sec = max(0.0, float(self._sub_content_wait_remaining_sec))
        elapsed_sec = max(0.0, total_sec - remaining_sec)
        ko_sec = max(0.0, float(self._sub_content_ko_listen_sec))
        cn_sec = max(0.0, float(self._sub_content_sound_sec))
        listen_total_sec = ko_sec + cn_sec
        gap_sec = max(0.0, float(self._listen_to_speak_gap_sec))
        after_speak_sec = max(0.0, float(self._speak_complete_hold_sec))
        speak_sec = max(0.0, float(self._sub_speak_sec))
        if speak_sec <= 1e-6:
            speak_sec = max(0.0, total_sec - listen_total_sec - gap_sec - after_speak_sec)
        t_speak_start = listen_total_sec + gap_sec
        t_speak_end = t_speak_start + speak_sec
        return {
            "elapsed": elapsed_sec,
            "ko_sec": ko_sec,
            "cn_sec": cn_sec,
            "listen_total": listen_total_sec,
            "gap_sec": gap_sec,
            "speak_sec": speak_sec,
            "after_speak_sec": after_speak_sec,
            "t_cn_start": ko_sec,
            "t_cn_end": ko_sec + cn_sec,
            "t_speak_start": t_speak_start,
            "t_speak_end": t_speak_end,
            "t_follow_end": t_speak_end + after_speak_sec,
        }

    def _current_sub_variant_word_count(self) -> int:
        """현재 sub 변형의 tip 출력 단어 수를 추정한다."""
        variant = self._current_sub_variant if isinstance(self._current_sub_variant, dict) else {}
        alt_words = variant.get("alt_words")
        if isinstance(alt_words, list) and alt_words:
            words_clean = [str(w).strip() for w in alt_words if str(w).strip()]
            return len(words_clean)
        alt_word = str(variant.get("alt_word") or "").strip()
        return 1 if alt_word else 0

    def _compute_sub_tip_hold_sec(self) -> float:
        """SHOW_SUB_CONTENT에서 tip 박스 홀드 시간을 단어 수에 따라 늘린다."""
        base = max(0.0, float(self._tip_intro_hold_sec))
        word_count = self._current_sub_variant_word_count()
        extra_words = max(0, int(word_count) - 1)
        hold = base + float(extra_words) * float(self._SUB_TIP_HOLD_PER_WORD_SEC)
        return min(float(self._SUB_TIP_HOLD_MAX_SEC), hold)

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """비디오 위에 LEARNING과 동일 세로 배치(중앙·타이틀 밴드 여유)의 문장과 첫 단어(있으면)를 표시한다."""
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        self._draw_title(screen, ctx=ctx)

        if self.stage in (
            self.Stage.INTRO_SENTENCE_IN,
            self.Stage.INTRO_SENTENCE_HOLD,
        ):
            slide_y = self._sentence_slide_y_offset_px()
            draw_style = replace(
                self._style,
                colors=replace(self._style.colors, hanzi_color=(255, 255, 255)),
            )
            self.drawer.draw_item_sentence(
                screen,
                item,
                ctx=ctx,
                channel=self._sentence_channel,
                style=draw_style,
                title_clearance=(self.title_text, 0.12, 12),
                y_offset_px=slide_y,
            )
            return

        if (
            self.stage == self.Stage.SHOW_SUB_CONTENT
            and self._sub_play_phase
            in ("intro_hold", "tip_out")
            and self._current_sub_variant is not None
        ):
            variant = self._current_sub_variant if isinstance(self._current_sub_variant, dict) else {}
            alt_words = variant.get("alt_words")
            alt_meanings = variant.get("alt_word_meanings")
            if isinstance(alt_words, list) and alt_words:
                words_clean = [str(w).strip() for w in alt_words if str(w).strip()]
                meanings_clean: list[str] = []
                if isinstance(alt_meanings, list) and alt_meanings:
                    meanings_clean = [str(m).strip() for m in alt_meanings if str(m).strip()]
                lines: list[str] = []
                for i, w in enumerate(words_clean):
                    m = meanings_clean[i] if i < len(meanings_clean) else ""
                    lines.append(f"{w}   :   {m}".rstrip())
                tip_text = "\n".join(lines).strip()
            else:
                alt_word_text = str(variant.get("alt_word") or "").strip()
                alt_meaning_text = str(variant.get("alt_word_meaning") or "").strip()
                tip_text = f"{alt_word_text}   :   {alt_meaning_text}".strip()
            tip_text = tip_text or "듣고 따라 말해보세요"
            self._draw_tip_box_above_gauge(
                screen,
                ctx=ctx,
                tip_text=tip_text or "듣고 따라 말해보세요",
                alpha_channel=self._tip_intro_channel,
                scale_y=0.36,
                scale_x=0.55,
            )
            if self._sub_play_phase in ("intro_hold", "tip_out", "playing"):
                slide_y = self._sentence_slide_y_offset_px()
                render_item = self._sub_variant_render_item(item)
                self._draw_sub_sentence_with_highlight(
                    screen,
                    ctx=ctx,
                    base_item=item,
                    render_item=render_item,
                    y_offset_px=slide_y,
                )
            return

        if not self._content_visible:
            return

        slide_y = self._sentence_slide_y_offset_px()
        render_item = item
        if self.stage == self.Stage.SHOW_SUB_CONTENT and self._current_sub_variant is not None:
            render_item = self._sub_variant_render_item(item)

        # SHOW_SUB_CONTENT에서는 기본 한자색을 흰색으로 그리고,
        # 슬롯에 들어간 alt_word 구간만 연습색(AMBER)으로 오버레이한다.
        if self.stage == self.Stage.SHOW_SUB_CONTENT and self._current_sub_variant is not None:
            self._draw_sub_sentence_with_highlight(
                screen,
                ctx=ctx,
                base_item=item,
                render_item=render_item,
                y_offset_px=slide_y,
            )
            if self._sub_play_phase == "playing":
                self._draw_sub_content_playback_bar(screen, ctx=ctx, item=item)
            return

        draw_style = self._style
        # SHOW_CONTENT 단계의 한자 색은 흰색으로 고정한다.
        if self.stage == self.Stage.SHOW_CONTENT:
            draw_style = replace(
                self._style,
                colors=replace(self._style.colors, hanzi_color=(255, 255, 255)),
            )

        self.drawer.draw_item_sentence(
            screen,
            render_item,
            ctx=ctx,
            channel=self._sentence_channel,
            style=draw_style,
            title_clearance=(self.title_text, 0.12, 12),
            y_offset_px=slide_y,
        )

        # 하단 단어(노란 텍스트) 렌더링은 비활성화한다.
        # PRACTICE 화면은 문장/번역 표시에만 집중한다.

    def _sub_ko_translation_karaoke_timing(self) -> tuple[bool, float, float]:
        """한국어 alt_translation TTS 구간 (active, elapsed, duration)."""
        if self.stage != self.Stage.SHOW_SUB_CONTENT or self._sub_play_phase != "playing":
            return False, 0.0, 0.0
        ko_sec = max(0.0, float(self._sub_content_ko_listen_sec))
        if ko_sec <= 1e-6:
            return False, 0.0, 0.0
        variant = self._current_sub_variant if isinstance(self._current_sub_variant, dict) else {}
        if not str(variant.get("alt_translation") or "").strip():
            return False, 0.0, 0.0
        elapsed_sec = self._sub_content_elapsed_sec()
        if elapsed_sec >= ko_sec:
            return False, 0.0, 0.0
        return True, elapsed_sec, ko_sec

    def _sub_content_elapsed_sec(self) -> float:
        total_sec = max(0.0, float(self._sub_content_wait_total_sec))
        remaining_sec = max(0.0, float(self._sub_content_wait_remaining_sec))
        return max(0.0, total_sec - remaining_sec)

    def _alt_hanzi_spans(self, hanzi_text: str, alt_word: str) -> list[tuple[int, int]]:
        """alt_word / alt_hanzi_spans 기준 하이라이트 구간."""
        spans_raw = (
            self._current_sub_variant.get("alt_hanzi_spans")
            if isinstance(self._current_sub_variant, dict)
            else None
        )
        spans: list[tuple[int, int]] = []
        if isinstance(spans_raw, list):
            for s in spans_raw:
                if not isinstance(s, dict):
                    continue
                st = s.get("start")
                ln = s.get("len")
                if not isinstance(st, int) or not isinstance(ln, int):
                    continue
                if st < 0 or st >= len(hanzi_text) or ln <= 0:
                    continue
                spans.append((st, min(ln, len(hanzi_text) - st)))
        if spans:
            return spans
        start_raw = (
            self._current_sub_variant.get("alt_hanzi_start")
            if isinstance(self._current_sub_variant, dict)
            else None
        )
        len_raw = (
            self._current_sub_variant.get("alt_hanzi_len")
            if isinstance(self._current_sub_variant, dict)
            else None
        )
        if isinstance(start_raw, int) and isinstance(len_raw, int) and len_raw > 0:
            idx = start_raw
            span_len = len_raw
        else:
            idx = hanzi_text.find(alt_word)
            if idx < 0:
                return []
            span_len = len(alt_word)
        if idx < 0 or idx >= len(hanzi_text):
            return []
        span_len = min(span_len, len(hanzi_text) - idx)
        if span_len <= 0:
            return []
        return [(idx, span_len)]

    @staticmethod
    def _hanzi_color_segments(
        hanzi_text: str,
        spans: list[tuple[int, int]],
        *,
        white_color: tuple[int, int, int],
        highlight_color: tuple[int, int, int],
    ) -> list[tuple[str, tuple[int, int, int]]]:
        """한자 줄을 흰색·강조(amber) 구간으로 분할."""
        if not hanzi_text:
            return []
        if not spans:
            return [(hanzi_text, white_color)]
        color_flags = [False] * len(hanzi_text)
        for idx, span_len in spans:
            end_i = min(len(hanzi_text), max(idx, 0) + max(span_len, 0))
            for i in range(max(0, idx), end_i):
                color_flags[i] = True
        segments: list[tuple[str, tuple[int, int, int]]] = []
        cur_text = ""
        cur_highlight: bool | None = None
        for i, ch in enumerate(hanzi_text):
            is_hl = color_flags[i]
            if cur_highlight is None:
                cur_highlight = is_hl
                cur_text = ch
                continue
            if is_hl == cur_highlight:
                cur_text += ch
                continue
            segments.append(
                (cur_text, highlight_color if cur_highlight else white_color)
            )
            cur_text = ch
            cur_highlight = is_hl
        if cur_text:
            segments.append(
                (cur_text, highlight_color if cur_highlight else white_color)
            )
        return segments

    def _sub_cn_hanzi_karaoke_timing(self) -> tuple[bool, float, float]:
        """중국어 듣기(cn mp3)·주황 말하기 게이지(speak_sec)와 동기 한자 노래방."""
        if self.stage != self.Stage.SHOW_SUB_CONTENT or self._sub_play_phase != "playing":
            return False, 0.0, 0.0
        tl = self._sub_playback_timeline()
        elapsed = tl["elapsed"]
        cn_sec = tl["cn_sec"]
        if cn_sec > 1e-6 and tl["t_cn_start"] <= elapsed < tl["t_cn_end"]:
            return True, elapsed - tl["t_cn_start"], cn_sec
        speak_sec = tl["speak_sec"]
        if speak_sec > 1e-6 and tl["t_speak_start"] <= elapsed < tl["t_speak_end"]:
            return True, elapsed - tl["t_speak_start"], speak_sec
        if speak_sec > 1e-6 and tl["t_speak_end"] <= elapsed < tl["t_follow_end"]:
            return True, speak_sec, speak_sec
        return False, 0.0, 0.0

    def _draw_sub_sentence_with_highlight(
        self,
        screen: pygame.Surface,
        *,
        ctx: FrameContext,
        base_item: ConversationItemLike,
        render_item: ConversationItemLike,
        y_offset_px: int = 0,
    ) -> None:
        """SHOW_SUB_CONTENT용 한자 하이라이트 렌더.

        기본 한자 줄은 흰색으로 그리고, `target_slot_order`에 넣은 `alt_word` 구간만
        기존 연습 색상(AMBER)으로 덮어쓴다. `alt_hanzi_start`/`alt_hanzi_len`이 있으면
        슬롯 좌표를 쓰고, 없으면 `alt_word`의 첫 부분 문자열 매칭으로 폴백한다.
        """
        white_style = replace(
            self._style,
            colors=replace(self._style.colors, hanzi_color=(255, 255, 255)),
        )
        data = build_sentence_render_data_with_tone_icons(render_item)
        y_base = (
            self.drawer.layout_sentence_y_base(
                ctx,
                data,
                white_style,
                align_v="center",
                center_y_ratio=self.drawer.ITEM_SENTENCE_CENTER_Y_RATIO,
                top_y_ratio=0.12,
                bottom_margin_px=48,
                title_clearance=(self.title_text, 0.12, 12),
            )
            + int(y_offset_px)
        )
        ko_karaoke_active, ko_elapsed, ko_dur = self._sub_ko_translation_karaoke_timing()
        cn_karaoke_active, cn_elapsed, cn_dur = self._sub_cn_hanzi_karaoke_timing()
        trans_line = (data.translation or "").strip()
        line_ys = self.drawer.compute_sentence_line_ys(y_base, data, white_style)
        center_x = int(ctx.width) // 2
        alpha = int(max(0, min(255, self.drawer.fade_alpha(self._sentence_channel))))
        # SHOW_SUB_CONTENT에서는 한자 줄을 별도 수동 렌더링하므로,
        # drawer에는 병음/번역만 그리게 한다(겹침/잔상 방지).
        self.drawer.draw_sentence(
            screen,
            replace(data, sentence=""),
            channel=self._sentence_channel,
            center_x=center_x,
            y_base=y_base,
            style=white_style,
            skip_translation=bool(ko_karaoke_active and trans_line),
        )

        replaced_sentence = str(self._current_sub_variant.get("replaced_sentence") or "").strip()
        alt_word = str(self._current_sub_variant.get("alt_word") or "").strip()
        hanzi_text = (data.sentence or "")[: white_style.text.max_hanzi]
        y_hanzi = int(line_ys.get("hanzi", y_base))

        if cn_karaoke_active and hanzi_text and alpha > 0:
            spans = self._alt_hanzi_spans(hanzi_text, alt_word) if alt_word else []
            segments = self._hanzi_color_segments(
                hanzi_text,
                spans,
                white_color=white_style.colors.hanzi_color,
                highlight_color=self._style.colors.hanzi_color,
            )
            self.drawer.draw_hanzi_karaoke_wipe_segments(
                screen,
                segments,
                center_x=center_x,
                y=y_hanzi,
                elapsed_sec=cn_elapsed,
                duration_sec=cn_dur,
                min_margin_x=white_style.layout.min_margin_x,
                alpha=alpha,
            )
            if ko_karaoke_active and trans_line and "translation" in line_ys:
                self.drawer.draw_translation_karaoke(
                    screen,
                    trans_line,
                    center_x=center_x,
                    y=int(line_ys["translation"]),
                    elapsed_sec=ko_elapsed,
                    duration_sec=ko_dur,
                    min_margin_x=white_style.layout.min_margin_x,
                    alpha=alpha,
                )
            return

        if not replaced_sentence or not alt_word or not hanzi_text:
            if hanzi_text and alpha > 0:
                surf, _ = self.drawer._get_cached_text_pair(
                    self.drawer._cache_hanzi,
                    self.drawer._fonts.hanzi_ft,
                    self.drawer._fonts.hanzi_pg,
                    hanzi_text,
                    white_style.colors.hanzi_color,
                )
                x = max(
                    white_style.layout.min_margin_x,
                    center_x - surf.get_width() // 2,
                )
                if alpha >= 255:
                    screen.blit(surf, (x, y_hanzi))
                else:
                    old_alpha = surf.get_alpha()
                    surf.set_alpha(alpha)
                    try:
                        screen.blit(surf, (x, y_hanzi))
                    finally:
                        if old_alpha is None:
                            surf.set_alpha(None)
                        else:
                            surf.set_alpha(old_alpha)
            if ko_karaoke_active and trans_line and "translation" in line_ys:
                self.drawer.draw_translation_karaoke(
                    screen,
                    trans_line,
                    center_x=center_x,
                    y=int(line_ys["translation"]),
                    elapsed_sec=ko_elapsed,
                    duration_sec=ko_dur,
                    min_margin_x=white_style.layout.min_margin_x,
                    alpha=alpha,
                )
            return

        spans = self._alt_hanzi_spans(hanzi_text, alt_word)
        segments = self._hanzi_color_segments(
            hanzi_text,
            spans,
            white_color=white_style.colors.hanzi_color,
            highlight_color=self._style.colors.hanzi_color,
        )
        if not segments:
            return

        fonts = getattr(self.drawer, "_fonts", None)
        if getattr(fonts, "hanzi_pg", None) is None:
            return

        full_w = sum(
            int(
                self.drawer._get_cached_text_pair(
                    self.drawer._cache_hanzi,
                    self.drawer._fonts.hanzi_ft,
                    self.drawer._fonts.hanzi_pg,
                    seg_text,
                    seg_color,
                )[0].get_width()
            )
            for seg_text, seg_color in segments
        )
        x_line = max(white_style.layout.min_margin_x, center_x - full_w // 2)

        if alpha <= 0:
            return
        cur_x = x_line
        for seg_text, seg_color in segments:
            surf, _ = self.drawer._get_cached_text_pair(
                self.drawer._cache_hanzi,
                self.drawer._fonts.hanzi_ft,
                self.drawer._fonts.hanzi_pg,
                seg_text,
                seg_color,
            )
            if alpha >= 255:
                screen.blit(surf, (cur_x, y_hanzi))
            else:
                old_alpha = surf.get_alpha()
                surf.set_alpha(alpha)
                try:
                    screen.blit(surf, (cur_x, y_hanzi))
                finally:
                    if old_alpha is None:
                        surf.set_alpha(None)
                    else:
                        surf.set_alpha(old_alpha)
            cur_x += int(surf.get_width())

        if ko_karaoke_active and trans_line and "translation" in line_ys:
            alpha = int(max(0, min(255, self.drawer.fade_alpha(self._sentence_channel))))
            self.drawer.draw_translation_karaoke(
                screen,
                trans_line,
                center_x=center_x,
                y=int(line_ys["translation"]),
                elapsed_sec=ko_elapsed,
                duration_sec=ko_dur,
                min_margin_x=white_style.layout.min_margin_x,
                alpha=alpha,
            )

    def _draw_sub_content_playback_bar(
        self,
        screen: pygame.Surface,
        *,
        ctx: FrameContext,
        item: ConversationItemLike,
    ) -> None:
        """SHOW_SUB_CONTENT 단계에서만 재생바와 시간 텍스트를 렌더한다."""
        _ = item
        tl = self._sub_playback_timeline()
        elapsed_sec = tl["elapsed"]
        ko_sec = tl["ko_sec"]
        cn_sec = tl["cn_sec"]
        listen_total_sec = tl["listen_total"]
        gap_sec = tl["gap_sec"]
        after_speak_sec = tl["after_speak_sec"]
        speak_sec = tl["speak_sec"]
        t_cn_start = tl["t_cn_start"]
        t_cn_end = tl["t_cn_end"]
        t_after_listen_gap_end = tl["t_speak_start"]
        t_speak_end = tl["t_speak_end"]

        # 4구간: ko 선행(게이지 0) → cn 채움(초록) → 듣기 만료 대기 → 말하기(주황)
        if cn_sec > 1e-6 and elapsed_sec < t_cn_start:
            is_listen_phase = True
            bar_current_sec = 0.0
            bar_total_sec = cn_sec
        elif cn_sec > 1e-6 and elapsed_sec < t_cn_end:
            is_listen_phase = True
            bar_current_sec = elapsed_sec - t_cn_start
            bar_total_sec = cn_sec
        elif listen_total_sec > 1e-6 and elapsed_sec < t_after_listen_gap_end:
            is_listen_phase = True
            bar_current_sec = cn_sec if cn_sec > 1e-6 else 0.0
            bar_total_sec = cn_sec if cn_sec > 1e-6 else max(0.1, listen_total_sec)
        elif speak_sec > 1e-6 and elapsed_sec < t_speak_end:
            is_listen_phase = False
            bar_current_sec = min(max(0.0, elapsed_sec - t_after_listen_gap_end), speak_sec)
            bar_total_sec = speak_sec
        elif speak_sec > 1e-6 and elapsed_sec < tl["t_follow_end"]:
            is_listen_phase = False
            bar_current_sec = speak_sec
            bar_total_sec = speak_sec
        else:
            total_sec = max(0.0, float(self._sub_content_wait_total_sec))
            bar_total_sec = max(0.1, total_sec if total_sec > 1e-6 else float(self._sub_content_hold_sec))
            bar_current_sec = min(elapsed_sec, bar_total_sec)
            is_listen_phase = listen_total_sec <= 1e-6

        self._playback_bar.draw(
            screen,
            frame_width=ctx.width,
            frame_height=ctx.height,
            current_sec=bar_current_sec,
            total_sec=bar_total_sec,
            show_time_text=False,
            progress_color=self._resolve_playback_bar_color(is_listen_phase=is_listen_phase),
        )
        self._draw_mode_icon(screen, ctx=ctx, is_listen_phase=is_listen_phase)

    def _resolve_playback_bar_color(self, *, is_listen_phase: bool) -> tuple[int, int, int]:
        """현재 재생 모드에 맞는 재생바 색상을 반환한다."""
        color_table = {
            "listen": (46, 204, 113),
            "speak": (255, 159, 67),
        }
        mode = "listen" if is_listen_phase else "speak"
        return color_table[mode]

    def _load_mode_icon_surface(self, filename: str) -> pygame.Surface | None:
        """재생 모드 아이콘을 로드한다(크기·경로는 LEARNING listen 과 공통)."""
        root = Path(__file__).resolve().parents[3]
        return load_mode_icon(root, filename)

    def _load_title_image_surface(self, filename: str) -> pygame.Surface | None:
        root = Path(__file__).resolve().parents[3]
        candidates = (
            root / "resource" / "image" / "title" / filename,
            root / "resource" / "images" / "title" / filename,
            root / "resource" / "image" / "icon" / filename,
            root / "resource" / "images" / "icon" / filename,
            root / "resource" / "image" / filename,
            root / "resource" / "images" / filename,
        )
        for path in candidates:
            if not path.exists():
                continue
            try:
                return pygame.image.load(str(path))
            except Exception:
                continue
        return None

    def _load_tip_box_surface(self) -> pygame.Surface | None:
        root = Path(__file__).resolve().parents[3]
        candidates = (
            root / "resource" / "image" / "icon" / "tip_box.png",
            root / "resource" / "image" / "tip_box.png",
            root / "resource" / "images" / "icon" / "tip_box.png",
        )
        for path in candidates:
            if not path.exists():
                continue
            try:
                return pygame.image.load(str(path))
            except Exception:
                continue
        return None

    def _draw_title(self, screen: pygame.Surface, *, ctx: FrameContext) -> None:
        surf = self._title_image_surface
        if surf is None:
            return
        alpha = int(max(0, min(255, self.drawer.fade_alpha(self._title_channel))))
        if alpha <= 0:
            return
        # 단어 모드 타이틀("단어_공부하기")과 같은 위치/스케일 기준을 사용한다.
        margin_left = 44
        margin_top = 18
        max_w = int(ctx.width * 0.54)
        max_h = 114
        sw, sh = int(surf.get_width()), int(surf.get_height())
        if sw <= 0 or sh <= 0:
            return
        tw, th = self._resolve_learning_title_target_size(
            max_w=max_w,
            max_h=max_h,
            fallback_w=sw,
            fallback_h=sh,
        )
        # 요청: 연습 타이틀은 기준 대비 세로 높이만 소폭 키운다.
        th = max(1, int(round(th * 1.08)))
        draw = pygame.transform.smoothscale(surf, (tw, th)) if (tw != sw or th != sh) else surf.copy()
        if alpha < 255:
            draw.set_alpha(alpha)
        x = max(self._style.layout.min_margin_x, margin_left)
        y = max(0, margin_top)
        screen.blit(draw, (x, y))

    def _resolve_learning_title_target_size(
        self,
        *,
        max_w: int,
        max_h: int,
        fallback_w: int,
        fallback_h: int,
    ) -> tuple[int, int]:
        """문장 이해하기 기준 렌더 크기를 계산한다. 실패 시 현재 타이틀 크기로 폴백한다."""
        ref = self._title_reference_surface
        if ref is None:
            scale = min(float(max_w) / float(fallback_w), float(max_h) / float(fallback_h), 1.0)
            return max(1, int(round(fallback_w * scale))), max(1, int(round(fallback_h * scale)))
        rw, rh = int(ref.get_width()), int(ref.get_height())
        if rw <= 0 or rh <= 0:
            scale = min(float(max_w) / float(fallback_w), float(max_h) / float(fallback_h), 1.0)
            return max(1, int(round(fallback_w * scale))), max(1, int(round(fallback_h * scale)))
        ref_scale = min(float(max_w) / float(rw), float(max_h) / float(rh), 1.0)
        target_w = max(1, int(round(rw * ref_scale)))
        target_h = max(1, int(round(rh * ref_scale)))
        return target_w, target_h

    def _tip_box_pixel_alpha(self, *, alpha_channel: str | None) -> int:
        base = 178
        if not alpha_channel:
            return base
        fa = int(self.drawer.fade_alpha(str(alpha_channel)))
        return max(0, min(255, int(round(float(base) * float(fa) / 255.0))))

    def _draw_tip_box_above_gauge(
        self,
        screen: pygame.Surface,
        *,
        ctx: FrameContext,
        tip_text: str,
        alpha_channel: str | None = None,
        scale: float = 0.3,
        scale_x: float | None = None,
        scale_y: float | None = None,
    ) -> None:
        box = self._tip_box_surface
        if box is None:
            return
        px_alpha = self._tip_box_pixel_alpha(alpha_channel=alpha_channel)
        if px_alpha <= 0:
            return
        bar_rect = self._playback_bar.get_bar_rect(frame_width=ctx.width, frame_height=ctx.height)
        sw, sh = int(box.get_width()), int(box.get_height())
        if sw <= 0 or sh <= 0:
            return
        base_scale = 0.3
        scale = float(scale)
        if scale <= 0:
            scale = base_scale
        scale_x = float(scale_x) if scale_x is not None else scale
        scale_y = float(scale_y) if scale_y is not None else scale
        if scale_x <= 0:
            scale_x = base_scale
        if scale_y <= 0:
            scale_y = base_scale
        tw = max(1, int(round(sw * scale_x)))
        th = max(1, int(round(sh * scale_y)))
        draw = pygame.transform.smoothscale(box, (tw, th)) if (tw != sw or th != sh) else box
        draw = draw.copy()
        draw.set_alpha(px_alpha)
        x = int(bar_rect.centerx - (tw // 2))
        y = int(bar_rect.top - th + 24)
        x = max(0, min(int(ctx.width) - tw, x))
        y = max(0, y)
        screen.blit(draw, (x, y))
        txt = str(tip_text or "").strip()
        if not txt:
            return
        lines = [ln for ln in txt.replace("\\n", "\n").split("\n")]
        rendered = [self._render_tip_line(ln) for ln in lines if ln is not None]
        if not rendered:
            return
        scale_factor = max(0.1, float(scale_y) / float(base_scale))
        line_gap = max(0, int(round(10 * scale_factor)))
        padding_left = max(0, int(round(28 * scale_factor)))
        padding_top = max(0, int(round(16 * scale_factor)))
        cur_y = int(y + padding_top)
        for surf in rendered:
            tx = int(x + padding_left)
            if px_alpha < 255:
                s2 = surf.copy()
                s2.set_alpha(px_alpha)
                screen.blit(s2, (tx, cur_y))
            else:
                screen.blit(surf, (tx, cur_y))
            cur_y += int(surf.get_height()) + line_gap

    @staticmethod
    def _is_hangul_char(ch: str) -> bool:
        code = ord(ch)
        return (0xAC00 <= code <= 0xD7A3) or (0x1100 <= code <= 0x11FF) or (0x3130 <= code <= 0x318F)

    @staticmethod
    def _is_cjk_char(ch: str) -> bool:
        code = ord(ch)
        return (
            (0x4E00 <= code <= 0x9FFF)
            or (0x3400 <= code <= 0x4DBF)
            or (0xF900 <= code <= 0xFAFF)
        )

    def _pick_tip_font_for_char(self, ch: str) -> pygame.font.Font:
        if self._is_hangul_char(ch):
            return self._tip_font_kr or self._tip_font_cn or self._tip_font_fallback
        if self._is_cjk_char(ch):
            return self._tip_font_cn or self._tip_font_kr or self._tip_font_fallback
        return self._tip_font_kr or self._tip_font_cn or self._tip_font_fallback

    def _render_tip_line(self, text: str) -> pygame.Surface:
        line = str(text or "")
        if not line:
            return (self._tip_font_kr or self._tip_font_cn or self._tip_font_fallback).render("", True, (0, 0, 0))
        segments: list[tuple[pygame.font.Font, str]] = []
        cur_font: pygame.font.Font | None = None
        cur_text = ""
        for ch in line:
            picked = self._pick_tip_font_for_char(ch)
            if cur_font is None:
                cur_font = picked
                cur_text = ch
                continue
            if picked == cur_font:
                cur_text += ch
                continue
            segments.append((cur_font, cur_text))
            cur_font = picked
            cur_text = ch
        if cur_font is not None and cur_text:
            segments.append((cur_font, cur_text))
        if not segments:
            return self._tip_font_fallback.render("", True, (0, 0, 0))
        rendered = [ft.render(seg, True, (0, 0, 0)) for ft, seg in segments]
        total_w = sum(s.get_width() for s in rendered)
        max_h = max(s.get_height() for s in rendered)
        line_surf = pygame.Surface((max(1, total_w), max(1, max_h)), pygame.SRCALPHA)
        x = 0
        for surf in rendered:
            y = (max_h - surf.get_height()) // 2
            line_surf.blit(surf, (x, y))
            x += surf.get_width()
        return line_surf


    def _draw_mode_icon(self, screen: pygame.Surface, *, ctx: FrameContext, is_listen_phase: bool) -> None:
        """현재 재생 구간에 맞는 모드 아이콘을 좌하단에 표시한다."""
        icon_surface = self._listen_icon_surface if is_listen_phase else self._speak_icon_surface
        blit_mode_icon_bottom_left(screen, icon_surface, frame_height=ctx.height)
