"""숏츠 클립 1개 재생 FSM."""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Any, Callable, Optional

import pygame

from studio.conversation.core.types import FrameContext, SentenceStyleConfig
from studio.shorts.constants import (
    CLIP_TRANSITION_FADE_SEC,
    CTA_HOLD_SEC,
    HOOK_FADE_IN_SEC,
    SHORTS_BG_KARAOKE_SLOW_EXTRA_SEC,
    SHORTS_BG_PRACTICE_MIN_SEC,
    SHORTS_FOLLOW_ALONG_LABEL,
    SHORTS_VIDEO_AFTER_ALPHA,
    SHORTS_VIDEO_END_HOLD_SEC,
    SHORTS_SOUND_PLAY_COUNT,
    SHORTS_RECORD_END_HOLD_SEC,
    SHORTS_VIDEO_FADE_OUT_SEC,
)
from studio.conversation.video_players import SimpleVideoPlayer
from studio.shorts.clip_types import CLIP_TYPE_CONVERSATION
from studio.shorts.data_loading import resolve_hook_title
from studio.shorts.layout import ShortsLayoutZones
from studio.shorts.tools.karaoke_renderer import compute_karaoke_progress
from studio.shorts.tools.shorts_drawer import ShortsDrawer

logger = logging.getLogger(__name__)

try:
    from audio.ko_narration import (
        KoNarrationPlan,
        build_ko_narration_plan,
        try_load_cached_ko_plan,
    )
except ImportError:
    KoNarrationPlan = None  # type: ignore[misc, assignment]
    build_ko_narration_plan = None  # type: ignore[assignment]
    try_load_cached_ko_plan = None  # type: ignore[assignment]

_CHANNEL_HOOK = "shorts_hook"
_CHANNEL_BOTTOM = "shorts_bottom"


class ClipStage(Enum):
    VIDEO_PLAY = auto()
    VIDEO_HOLD = auto()
    VIDEO_FADE_OUT = auto()
    HOOK_IN = auto()
    LEARN_PLAY = auto()
    KO_NARRATION = auto()
    CTA_HOLD = auto()
    END_HOLD = auto()
    DONE = auto()
    TRANSITION_OUT = auto()


class ClipScene:
    """단일 클립 Hook → Learn → CTA FSM."""

    def __init__(
        self,
        *,
        drawer: ShortsDrawer,
        style: SentenceStyleConfig,
        play_voice: Callable[[str], float],
        start_learn_background: Optional[Callable[[float], None]] = None,
        stop_learn_background: Optional[Callable[[], None]] = None,
        follow_along_mp3: Optional[Callable[[], str]] = None,
        hook_fade_sec: float = HOOK_FADE_IN_SEC,
        cta_hold_sec: float = CTA_HOLD_SEC,
    ) -> None:
        self._drawer = drawer
        self._style = style
        self._play_voice = play_voice
        self._start_learn_background = start_learn_background
        self._stop_learn_background = stop_learn_background
        self._follow_along_mp3 = follow_along_mp3
        self._hook_fade_sec = max(0.01, float(hook_fade_sec))
        self._cta_hold_sec = max(0.0, float(cta_hold_sec))
        self._clip: dict[str, Any] = {}
        self._hook_title: str = ""
        self._video_player = SimpleVideoPlayer()
        self._frozen_video_frame: Optional[pygame.Surface] = None
        self._video_inner_size: tuple[int, int] = (0, 0)
        self._video_display_alpha: int = 255
        self._video_fade_from_alpha: int = 255
        self._had_video_intro = False
        self._stage = ClipStage.HOOK_IN
        self._timer = 0.0
        self._learn_elapsed = 0.0
        self._sound_duration = 0.0
        self._sound_once_duration = 0.0
        self._sound_play_count = 0
        self._learn_round = 0
        self._sentence_sound_duration = 0.0
        self._bg_practice_duration = 0.0
        self._voice_channel: Optional[pygame.mixer.Channel] = None
        self._on_clip_done: Optional[Callable[[], None]] = None
        self._is_last_clip = True
        self._ko_plan: Optional[Any] = None
        self._ko_cue_index = 0
        self._ko_current_text = ""
        self._ko_cue_elapsed = 0.0
        self._ko_cue_duration = 0.0
        self._ko_finished = False
        self._ko_started = False
        self._record_end_hold_sec = 0.0
        self._end_hold_after_learn = False

    def set_record_end_hold(self, seconds: float) -> None:
        """녹화 모드 tail hold(초). 0이면 비활성(debug)."""
        self._record_end_hold_sec = max(0.0, float(seconds))

    @property
    def stage(self) -> ClipStage:
        return self._stage

    @property
    def is_done(self) -> bool:
        return self._stage == ClipStage.DONE

    @property
    def hook_title(self) -> str:
        return self._hook_title

    def set_on_clip_done(self, callback: Optional[Callable[[], None]]) -> None:
        self._on_clip_done = callback

    def _try_start_deferred_ko_narration(self) -> None:
        """비디오 구간 KO TTS는 첫 update에서 시작(녹화 로거 준비 후 InsertSound 기록)."""
        if self._ko_started or self._ko_plan is None or not self._had_video_intro:
            return
        if self._stage not in (
            ClipStage.VIDEO_PLAY,
            ClipStage.VIDEO_HOLD,
            ClipStage.VIDEO_FADE_OUT,
        ):
            return
        self._start_ko_narration_sequence(during_video=True)

    def _enter_hook_in(self) -> None:
        self._stage = ClipStage.HOOK_IN
        self._timer = 0.0
        fade = self._drawer.fade
        fade.fade_off(_CHANNEL_HOOK, 0.0)
        fade.fade_off(_CHANNEL_BOTTOM, 0.0)
        fade.fade_on(_CHANNEL_HOOK, self._hook_fade_sec)
        fade.fade_on(_CHANNEL_BOTTOM, 0.0)

    def start_clip(self, clip: dict[str, Any], *, is_last: bool = True) -> None:
        """새 클립 시작."""
        self._clip = dict(clip)
        self._hook_title = resolve_hook_title(self._clip)
        if self._hook_title:
            self._clip["hook_title"] = self._hook_title
        self._is_last_clip = bool(is_last)
        self._timer = 0.0
        self._learn_elapsed = 0.0
        self._sound_duration = 0.0
        self._sound_once_duration = 0.0
        self._sound_play_count = 0
        self._learn_round = 0
        self._sentence_sound_duration = 0.0
        self._bg_practice_duration = 0.0
        self._stop_learn_audio()
        self._video_player.close()
        self._frozen_video_frame = None
        self._video_inner_size = (0, 0)
        self._video_display_alpha = 255
        self._had_video_intro = False
        self._ko_plan = None
        self._ko_cue_index = 0
        self._ko_current_text = ""
        self._ko_cue_elapsed = 0.0
        self._ko_cue_duration = 0.0
        self._ko_finished = False
        self._ko_started = False
        self._ensure_ko_plan()

        clip_type = str(self._clip.get("clip_type") or "").strip()
        video_path = str(self._clip.get("video_path") or "").strip()
        if clip_type == CLIP_TYPE_CONVERSATION and video_path:
            self._video_player.set_source(video_path, 0.0, -1.0)
            if self._video_player.has_source():
                self._had_video_intro = True
                self._video_display_alpha = 255
                self._stage = ClipStage.VIDEO_PLAY
                fade = self._drawer.fade
                fade.fade_on(_CHANNEL_HOOK, 0.0)
                fade.fade_on(_CHANNEL_BOTTOM, 0.0)
                return
            self._video_player.close()

        self._enter_hook_in()

    def _ensure_ko_plan(self) -> None:
        """ko_narration_id → 캐시 mp3 우선, 없으면 재생 시점 TTS 생성."""
        if try_load_cached_ko_plan is None:
            return
        set_id = int(self._clip.get("ko_narration_id") or 0)
        if set_id < 1:
            return
        plan = try_load_cached_ko_plan(self._clip)
        if plan is None and build_ko_narration_plan is not None:
            logger.info(
                "ko TTS 재생 시점 생성 clip_id=%s set_id=%s",
                self._clip.get("clip_id"),
                set_id,
            )
            try:
                plan = build_ko_narration_plan(self._clip)
            except Exception as ex:
                logger.warning("ko TTS 생성 실패 set_id=%s: %s", set_id, ex)
        if plan is None:
            logger.warning(
                "ko 내레이션 없음 clip_id=%s set_id=%s — "
                "ko_narration_lines·sets 확인 또는 batch-shorts-ko",
                self._clip.get("clip_id"),
                set_id,
            )
        self._ko_plan = plan
        if plan is not None:
            self._clip["_ko_plan"] = plan

    def _finish_clip(self) -> None:
        self._stage = ClipStage.DONE
        if self._on_clip_done:
            self._on_clip_done()

    def begin_transition_out(self) -> None:
        if self._stage in (ClipStage.DONE, ClipStage.TRANSITION_OUT):
            return
        if self._stage in (ClipStage.VIDEO_PLAY, ClipStage.VIDEO_HOLD, ClipStage.VIDEO_FADE_OUT):
            self._video_player.close()
            self._enter_learn_play()
            return
        if self._stage == ClipStage.LEARN_PLAY:
            self._stop_learn_audio()
        self._stage = ClipStage.TRANSITION_OUT
        self._timer = 0.0
        self._drawer.fade.fade_off(_CHANNEL_HOOK, CLIP_TRANSITION_FADE_SEC)
        self._drawer.fade.fade_off(_CHANNEL_BOTTOM, CLIP_TRANSITION_FADE_SEC)
        if self._frozen_video_frame is not None:
            dur = max(1e-6, float(CLIP_TRANSITION_FADE_SEC))
            t = max(0.0, min(1.0, self._timer / dur))
            self._video_display_alpha = int(self._video_display_alpha * (1.0 - t))

    def update(self, dt_sec: float) -> None:
        self._drawer.tick_fade(dt_sec)
        self._timer += max(0.0, float(dt_sec))

        if self._stage == ClipStage.VIDEO_PLAY:
            self._try_start_deferred_ko_narration()
            self._tick_ko_narration(dt_sec)
            self._video_player.tick(max(0.0, float(dt_sec)))
            end_sec = float(self._video_player.get_effective_end_sec())
            pts = float(self._video_player.get_pts())
            if self._video_player.is_paused() and pts >= end_sec - 1e-3:
                self._freeze_video_frame()
                self._enter_video_hold()
            return

        if self._stage == ClipStage.VIDEO_HOLD:
            self._tick_ko_narration(dt_sec)
            if self._timer >= SHORTS_VIDEO_END_HOLD_SEC:
                self._enter_video_fade_out()
            return

        if self._stage == ClipStage.VIDEO_FADE_OUT:
            self._tick_ko_narration(dt_sec)
            dur = max(1e-6, float(SHORTS_VIDEO_FADE_OUT_SEC))
            t = max(0.0, min(1.0, self._timer / dur))
            target = max(0, min(255, int(SHORTS_VIDEO_AFTER_ALPHA)))
            self._video_display_alpha = int(
                self._video_fade_from_alpha + (target - self._video_fade_from_alpha) * t
            )
            if t >= 1.0:
                self._video_display_alpha = target
                self._enter_learn_play()
            return

        if self._stage == ClipStage.HOOK_IN:
            if self._timer >= self._hook_fade_sec:
                self._enter_learn_play()
            return

        if self._stage == ClipStage.LEARN_PLAY:
            self._learn_elapsed += max(0.0, float(dt_sec))
            if self._learn_round == 4:
                if self._learn_elapsed >= self._bg_practice_duration:
                    self._stop_learn_background_only()
                    if self._should_post_follow_along_hold():
                        self._enter_post_follow_along_hold()
                    else:
                        self._finish_learn_sequence()
                return
            if self._is_voice_finished():
                self._advance_learn_voice_step()
            return

        if self._stage == ClipStage.KO_NARRATION:
            self._tick_ko_narration(dt_sec)
            return

        if self._stage == ClipStage.CTA_HOLD:
            if self._timer >= self._cta_hold_sec:
                if self._is_last_clip:
                    self._finish_clip()
                else:
                    self.begin_transition_out()
            return

        if self._stage == ClipStage.END_HOLD:
            if self._timer >= self._record_end_hold_sec:
                if self._end_hold_after_learn:
                    self._end_hold_after_learn = False
                    self._finish_learn_sequence()
                else:
                    self._finish_clip()
            return

        if self._stage == ClipStage.TRANSITION_OUT:
            if self._timer >= CLIP_TRANSITION_FADE_SEC:
                self._finish_clip()

    def _freeze_video_frame(self) -> None:
        w, h = self._video_inner_size
        if w > 0 and h > 0:
            self._frozen_video_frame = self._video_player.get_frame(w, h, contain=True)
        self._video_player.close()

    def _enter_video_hold(self) -> None:
        self._stage = ClipStage.VIDEO_HOLD
        self._timer = 0.0

    def _enter_video_fade_out(self) -> None:
        self._stage = ClipStage.VIDEO_FADE_OUT
        self._timer = 0.0
        self._video_fade_from_alpha = self._video_display_alpha

    def _enter_learn_play(self) -> None:
        self._stop_learn_audio()
        self._stage = ClipStage.LEARN_PLAY
        self._timer = 0.0
        self._learn_elapsed = 0.0
        self._sound_play_count = 0
        self._learn_round = 0
        self._sound_once_duration = 0.0
        self._sound_duration = 0.0
        self._sentence_sound_duration = 0.0
        self._bg_practice_duration = 0.0
        self._drawer.fade.fade_on(_CHANNEL_BOTTOM, 0.25)
        path = str(self._clip.get("sound_path") or "").strip()
        if path:
            self._start_sentence_play(play_index=1)
        else:
            self._start_follow_along_voice()

    def _start_sentence_play(self, *, play_index: int) -> None:
        """sound_path 1·2회차. 병음·한자 노래방 동기."""
        path = str(self._clip.get("sound_path") or "").strip()
        self._learn_round = int(play_index)
        self._learn_elapsed = 0.0
        self._sound_play_count = self._learn_round
        dur = self._play_voice(path) if path else 0.0
        if dur <= 0 and path:
            dur = 3.0
        self._sound_once_duration = dur
        if self._learn_round == 1:
            self._sentence_sound_duration = dur
            self._sound_duration = dur
        elif self._sentence_sound_duration <= 1e-6:
            self._sentence_sound_duration = dur
            self._sound_duration = dur

    def _start_follow_along_voice(self) -> None:
        """따라해보세요 TTS (sound 2회 다음)."""
        self._learn_round = 3
        self._learn_elapsed = 0.0
        fa_path = ""
        if self._follow_along_mp3 is not None:
            try:
                fa_path = str(self._follow_along_mp3() or "").strip()
            except Exception as ex:
                logger.warning("따라해보세요 mp3 경로 실패: %s", ex)
        dur = self._play_voice(fa_path) if fa_path else 0.0
        if dur <= 0 and fa_path:
            dur = 2.5
        self._sound_once_duration = dur

    def _start_bg_practice(self) -> None:
        """따라해보세요 다음: bg + 병음·한자(sound_path보다 1.5초 느린 노래방)."""
        self._learn_round = 4
        self._learn_elapsed = 0.0
        base = max(0.0, float(self._sentence_sound_duration))
        slow_karaoke = base + float(SHORTS_BG_KARAOKE_SLOW_EXTRA_SEC)
        self._bg_practice_duration = max(float(SHORTS_BG_PRACTICE_MIN_SEC), slow_karaoke)
        if self._start_learn_background is not None:
            try:
                self._start_learn_background(self._bg_practice_duration + 2.0)
            except Exception as ex:
                logger.debug("bg 시작 실패: %s", ex)

    def _advance_learn_voice_step(self) -> None:
        if self._learn_round == 1 and self._sound_play_count < max(
            1, int(SHORTS_SOUND_PLAY_COUNT)
        ):
            self._start_sentence_play(play_index=2)
        elif self._learn_round == 2:
            self._start_follow_along_voice()
        elif self._learn_round == 3:
            self._start_bg_practice()
        else:
            self._finish_learn_sequence()

    def _finish_learn_sequence(self) -> None:
        if self._ko_plan is not None and not self._ko_finished:
            self._enter_ko_narration()
        else:
            self._enter_cta_hold()

    def _stop_learn_background_only(self) -> None:
        if self._stop_learn_background is not None:
            try:
                self._stop_learn_background()
            except Exception as ex:
                logger.debug("bg 중지 실패: %s", ex)

    def _stop_learn_audio(self) -> None:
        self._stop_voice()
        self._stop_learn_background_only()

    def _stop_voice(self) -> None:
        ch = self._voice_channel
        if ch is not None:
            try:
                ch.stop()
            except Exception:
                pass
        self._voice_channel = None

    def _start_ko_narration_sequence(self, *, during_video: bool = False) -> None:
        """문장별 TTS·자막 순차 재생 시작."""
        plan = self._ko_plan
        if plan is None or not getattr(plan, "cues", None):
            self._ko_finished = True
            return
        if self._ko_started and not self._ko_finished:
            return
        self._ko_started = True
        self._ko_finished = False
        self._ko_cue_index = 0
        self._ko_current_text = ""
        self._ko_cue_elapsed = 0.0
        self._ko_cue_duration = 0.0
        self._voice_channel = None
        if during_video:
            self._drawer.fade.fade_on(_CHANNEL_BOTTOM, 0.25)
        self._play_ko_cue_at(0)

    def _tick_ko_narration(self, dt_sec: float) -> None:
        if not self._ko_started or self._ko_finished:
            return
        self._ko_cue_elapsed += max(0.0, float(dt_sec))
        if self._is_ko_cue_voice_finished():
            self._advance_ko_cue()

    def _enter_ko_narration(self) -> None:
        """비디오 없는 클립: 학습 후 한국어 내레이션."""
        self._stop_learn_audio()
        self._stage = ClipStage.KO_NARRATION
        self._timer = 0.0
        self._drawer.fade.fade_on(_CHANNEL_BOTTOM, 0.25)
        plan = self._ko_plan
        if plan is None or not getattr(plan, "cues", None):
            self._enter_cta_hold()
            return
        if self._ko_finished:
            self._enter_cta_hold()
            return
        self._start_ko_narration_sequence(during_video=False)

    def _play_ko_cue_at(self, index: int) -> None:
        plan = self._ko_plan
        if plan is None:
            self._ko_finished = True
            if self._stage == ClipStage.KO_NARRATION:
                self._enter_cta_hold()
            return
        cues = list(getattr(plan, "cues", None) or [])
        if index >= len(cues):
            self._ko_finished = True
            self._ko_current_text = ""
            if self._stage == ClipStage.KO_NARRATION:
                self._enter_cta_hold()
            return
        cue = cues[index]
        self._ko_cue_index = index
        self._ko_current_text = str(getattr(cue, "text", "") or "")
        self._ko_cue_elapsed = 0.0
        path = str(getattr(cue, "audio_path", "") or "").strip()
        self._ko_cue_duration = self._play_voice(path) if path else 0.0
        if self._ko_cue_duration <= 0 and path:
            self._ko_cue_duration = 3.0
        elif self._ko_cue_duration <= 0:
            self._ko_cue_duration = 2.0

    def _advance_ko_cue(self) -> None:
        self._play_ko_cue_at(self._ko_cue_index + 1)

    def _is_ko_cue_voice_finished(self) -> bool:
        if self._ko_cue_elapsed < 0.04:
            return False
        ch = self._voice_channel
        if ch is not None and ch.get_busy():
            return False
        dur = max(0.0, float(self._ko_cue_duration))
        if dur <= 1e-6:
            return self._ko_cue_elapsed >= 0.5
        return self._ko_cue_elapsed >= dur + 0.1

    def _active_ko_subtitle(self) -> str:
        if self._ko_finished or not self._ko_started:
            return ""
        return (self._ko_current_text or "").strip()

    def _follow_along_overlay_subtitle(self) -> str:
        """학습 3·4단계: 따라해보세요 TTS·BG 구간 비디오 하단 자막."""
        if self._stage == ClipStage.LEARN_PLAY and self._learn_round in (3, 4):
            return SHORTS_FOLLOW_ALONG_LABEL
        return ""

    def _overlay_subtitle_text(self) -> str:
        ko = self._active_ko_subtitle()
        if ko:
            return ko
        return self._follow_along_overlay_subtitle()

    def _ko_subtitle_progress(self) -> Optional[float]:
        text = self._active_ko_subtitle()
        if not text:
            return None
        return compute_karaoke_progress(self._ko_cue_elapsed, self._ko_cue_duration)

    def _overlay_subtitle_progress(self) -> Optional[float]:
        if self._active_ko_subtitle():
            return self._ko_subtitle_progress()
        if self._stage == ClipStage.LEARN_PLAY and self._learn_round == 3:
            dur = max(0.0, float(self._sound_once_duration))
            if dur > 1e-6:
                return compute_karaoke_progress(self._learn_elapsed, dur)
        return None

    def _enter_cta_hold(self) -> None:
        self._stop_learn_audio()
        self._stage = ClipStage.CTA_HOLD
        self._timer = 0.0
        self._drawer.fade.fade_on(_CHANNEL_BOTTOM, 0.35)

    def _should_post_follow_along_hold(self) -> bool:
        if self._record_end_hold_sec <= 1e-6:
            return False
        return str(self._clip.get("clip_type") or "").strip() == CLIP_TYPE_CONVERSATION

    def _enter_post_follow_along_hold(self) -> None:
        """녹화·회화: 따라해보세요(BG) 직후 tail hold."""
        self._end_hold_after_learn = True
        self._stage = ClipStage.END_HOLD
        self._timer = 0.0
        self._drawer.fade.fade_on(_CHANNEL_BOTTOM, 0.35)

    def _is_voice_finished(self) -> bool:
        ch = self._voice_channel
        if ch is not None and ch.get_busy():
            return False
        dur = max(0.0, float(self._sound_once_duration))
        if dur <= 1e-6:
            return self._learn_elapsed >= 2.0
        return self._learn_elapsed >= dur + 0.15

    def _sentence_karaoke_duration(self) -> float:
        base = max(0.0, float(self._sentence_sound_duration or self._sound_duration))
        if base > 1e-6:
            return base
        return max(0.0, float(self._sound_once_duration))

    def _learn_karaoke_timing(self) -> tuple[float, float]:
        """노래방 (elapsed, duration). progress = elapsed/duration."""
        base = self._sentence_karaoke_duration()
        if self._stage != ClipStage.LEARN_PLAY:
            if base > 1e-6:
                return base, base
            return max(0.0, float(self._learn_elapsed)), 1.0

        if self._learn_round in (1, 2) and not self._is_voice_finished():
            dur = base if base > 1e-6 else 3.0
            return max(0.0, float(self._learn_elapsed)), dur

        if self._learn_round == 3:
            if base > 1e-6:
                return base, base
            return max(0.0, float(self._learn_elapsed)), 1.0

        if self._learn_round == 4:
            slow = base + float(SHORTS_BG_KARAOKE_SLOW_EXTRA_SEC) if base > 1e-6 else 4.5
            return max(0.0, float(self._learn_elapsed)), slow

        if base > 1e-6:
            return base, base
        return max(0.0, float(self._learn_elapsed)), 1.0

    def _karaoke_elapsed_sec(self) -> float:
        return self._learn_karaoke_timing()[0]

    def _situation_subtitle_for_bottom(self) -> str:
        """하단 situation 문구 — 따라해보세요(3·4단계) 포함 학습이 끝난 뒤에만."""
        if self._stage == ClipStage.LEARN_PLAY:
            return ""
        if self._stage in (
            ClipStage.VIDEO_PLAY,
            ClipStage.VIDEO_HOLD,
            ClipStage.VIDEO_FADE_OUT,
            ClipStage.HOOK_IN,
        ):
            return ""
        return str(self._clip.get("situation_subtitle") or "").strip()

    def _should_show_learn_karaoke(self) -> bool:
        return self._stage in (
            ClipStage.LEARN_PLAY,
            ClipStage.KO_NARRATION,
            ClipStage.CTA_HOLD,
            ClipStage.END_HOLD,
            ClipStage.TRANSITION_OUT,
        )

    def set_voice_channel(self, channel: Optional[pygame.mixer.Channel]) -> None:
        self._voice_channel = channel

    def _video_frame_inner_size(self) -> Optional[tuple[int, int]]:
        w, h = self._video_inner_size
        if w > 0 and h > 0:
            return (w, h)
        return None

    def _ko_subtitle_anchor_rect(self, zones: ShortsLayoutZones) -> pygame.Rect:
        inner = self._video_frame_inner_size()
        player = self._video_player if self._stage == ClipStage.VIDEO_PLAY else None
        frame_rect = self._drawer.compute_center_video_frame_rect(
            zones.middle,
            player=player,
            frozen_frame=self._frozen_video_frame,
            frame_inner_size=inner,
        )
        if frame_rect is not None:
            return frame_rect
        fallback = zones.middle.inflate(-32, -32)
        return fallback if fallback.width > 0 and fallback.height > 0 else zones.middle

    def _draw_ko_subtitle_if_any(self, screen: pygame.Surface, zones: ShortsLayoutZones) -> None:
        sub = self._overlay_subtitle_text()
        if not sub:
            return
        self._drawer.draw_ko_subtitle_overlay(
            screen,
            anchor_rect=self._ko_subtitle_anchor_rect(zones),
            text=sub,
            fade_alpha=self._drawer.fade_alpha(_CHANNEL_BOTTOM),
            subtitle_progress=self._overlay_subtitle_progress(),
        )

    def _draw_pinned_video(self, screen: pygame.Surface, zones: ShortsLayoutZones) -> None:
        """고정된 마지막 프레임(문장 단계에서도 유지)."""
        if self._frozen_video_frame is None:
            return
        self._drawer.draw_center_video(
            screen,
            None,
            zones.middle,
            frozen_frame=self._frozen_video_frame,
            alpha=self._video_display_alpha,
            frame_inner_size=self._video_frame_inner_size(),
        )

    def _draw_hook_layers(self, screen: pygame.Surface, zones: ShortsLayoutZones) -> None:
        image_y = self._drawer.draw_hook_title(
            screen,
            zones=zones,
            hook_title=self._hook_title,
        )
        self._drawer.draw_top_zone(
            screen,
            zones=zones,
            hook_image_path=str(self._clip.get("hook_image_path") or ""),
            channel=_CHANNEL_HOOK,
            image_y=image_y,
        )

    def draw(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        if not self._clip:
            return

        zones = ShortsLayoutZones.from_surface(screen, ctx)

        if self._stage in (ClipStage.VIDEO_PLAY, ClipStage.VIDEO_HOLD, ClipStage.VIDEO_FADE_OUT):
            inner = zones.middle.inflate(-32, -32)
            if inner.width > 0 and inner.height > 0:
                self._video_inner_size = (inner.width, inner.height)
            self._draw_hook_layers(screen, zones)
            if self._stage == ClipStage.VIDEO_PLAY:
                self._drawer.draw_center_video(
                    screen,
                    self._video_player,
                    zones.middle,
                    alpha=self._video_display_alpha,
                    frame_inner_size=self._video_frame_inner_size(),
                )
            else:
                self._draw_pinned_video(screen, zones)
            self._draw_ko_subtitle_if_any(screen, zones)
            situation = self._situation_subtitle_for_bottom()
            if not self._overlay_subtitle_text():
                self._drawer.draw_bottom_zone(
                    screen,
                    zones=zones,
                    situation_subtitle=situation,
                    channel=_CHANNEL_BOTTOM,
                )
            return
        show_karaoke = self._should_show_learn_karaoke()
        show_bottom = self._stage in (
            ClipStage.LEARN_PLAY,
            ClipStage.KO_NARRATION,
            ClipStage.CTA_HOLD,
            ClipStage.END_HOLD,
            ClipStage.TRANSITION_OUT,
        )
        overlay_sub = self._overlay_subtitle_text()

        if self._frozen_video_frame is not None:
            self._draw_pinned_video(screen, zones)

        if show_karaoke:
            k_elapsed, k_dur = self._learn_karaoke_timing()
            screen.set_clip(zones.middle)
            try:
                self._drawer.draw_middle(
                    screen,
                    zones=zones,
                    item=self._clip,
                    elapsed_sec=k_elapsed,
                    syllable_times=list(self._clip.get("syllable_times") or []),
                    sound_duration_sec=k_dur,
                    style=self._style,
                )
            finally:
                screen.set_clip(None)

        if overlay_sub:
            self._draw_ko_subtitle_if_any(screen, zones)
        if show_bottom:
            situation = self._situation_subtitle_for_bottom()
            self._drawer.draw_bottom_zone(
                screen,
                zones=zones,
                situation_subtitle=situation,
                channel=_CHANNEL_BOTTOM,
            )

        screen.set_clip(None)
        self._draw_hook_layers(screen, zones)
