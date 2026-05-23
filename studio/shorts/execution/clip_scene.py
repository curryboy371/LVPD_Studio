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
    SHORTS_NATIVE_LISTEN_LABEL,
    SHORTS_VIDEO_AFTER_ALPHA,
    SHORTS_VIDEO_END_HOLD_SEC,
    SHORTS_SOUND_PLAY_COUNT,
    SHORTS_RECORD_END_HOLD_SEC,
    SHORTS_VIDEO_FADE_OUT_SEC,
    SHORTS_HEIGHT,
    SHORTS_WIDTH,
    ZONE_MIDDLE_RATIO,
)
from studio.conversation.video_players import SimpleVideoPlayer
from studio.shorts.clip_types import CLIP_TYPE_CONVERSATION, CLIP_TYPE_VOCABULARY
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
    VOCAB_MEANING_KO = auto()
    LEARN_PLAY = auto()
    KO_NARRATION = auto()
    CTA_HOLD = auto()
    VOCAB_GAP = auto()
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
        self._default_cta_hold_sec = max(0.0, float(cta_hold_sec))
        self._cta_hold_sec = self._default_cta_hold_sec
        self._clip: dict[str, Any] = {}
        self._hook_title: str = ""
        self._video_player = SimpleVideoPlayer()
        self._word_video_player = SimpleVideoPlayer()
        self._frozen_video_frame: Optional[pygame.Surface] = None
        self._word_video_frozen_frame: Optional[pygame.Surface] = None
        self._word_video_last_live_frame: Optional[pygame.Surface] = None
        self._word_video_inner_size: tuple[int, int] = (0, 0)
        self._word_video_started: bool = False
        self._word_video_clock: float = 0.0
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
        self._on_topic_intro_done: Optional[Callable[[], None]] = None
        self._topic_intro_mode = False
        self._is_last_clip = True
        self._ko_plan: Optional[Any] = None
        self._ko_cue_index = 0
        self._ko_current_text = ""
        self._ko_cue_elapsed = 0.0
        self._ko_cue_duration = 0.0
        self._ko_finished = False
        self._ko_started = False
        self._vocab_meaning_plan: Optional[Any] = None
        self._vocab_meaning_subtitle_hold = ""
        self._vocab_meaning_entered = False
        self._record_end_hold_sec = 0.0
        self._end_hold_after_learn = False
        self._last_live_video_frame: Optional[pygame.Surface] = None
        self._vocab_gap_sec = 0.0

    def set_record_end_hold(self, seconds: float) -> None:
        """녹화 모드 tail hold(초). 0이면 비활성(debug)."""
        self._record_end_hold_sec = max(0.0, float(seconds))

    def reset_playback_state(self) -> None:
        """녹화 시작 직전: init()에서 쌓인 FSM·오디오 상태 초기화."""
        self._stop_learn_audio()
        self._video_player.close()
        self._reset_word_video()
        self._frozen_video_frame = None
        self._last_live_video_frame = None
        self._video_inner_size = (0, 0)
        self._video_display_alpha = 255
        self._had_video_intro = False
        self._topic_intro_mode = False
        self._stage = ClipStage.HOOK_IN
        self._timer = 0.0
        self._ko_plan = None
        self._ko_cue_index = 0
        self._ko_current_text = ""
        self._ko_cue_elapsed = 0.0
        self._ko_cue_duration = 0.0
        self._ko_finished = False
        self._ko_started = False
        self._vocab_meaning_plan = None
        self._vocab_meaning_subtitle_hold = ""
        self._vocab_meaning_entered = False

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

    def set_on_topic_intro_done(self, callback: Optional[Callable[[], None]]) -> None:
        self._on_topic_intro_done = callback

    def start_topic_intro(self, intro: dict[str, Any]) -> None:
        """단어 숏츠: topic당 1회 — 비디오 + ko_narration_id TTS 후 단어 클립 시작."""
        self._topic_intro_mode = True
        self._clip = {
            "clip_type": CLIP_TYPE_VOCABULARY,
            "clip_id": int(intro.get("clip_id") or 0),
            "topic": str(intro.get("topic") or "").strip(),
            "hook_title": str(intro.get("hook_title") or "").strip(),
            "ko_narration_id": int(intro.get("ko_narration_id") or 0),
            "video_path": str(intro.get("video_path") or "").strip(),
            "sentence": [],
            "translation": [],
        }
        self._hook_title = resolve_hook_title(self._clip)
        self._is_last_clip = False
        self._timer = 0.0
        self._stop_learn_audio()
        self._video_player.close()
        self._reset_word_video()
        self._frozen_video_frame = None
        self._video_inner_size = (0, 0)
        self._video_display_alpha = 255
        self._had_video_intro = False
        self._last_live_video_frame = None
        self._ko_plan = None
        self._ko_finished = False
        self._ko_started = False
        self._vocab_meaning_plan = None
        self._ensure_ko_plan()

        video_path = str(self._clip.get("video_path") or "").strip()
        if video_path:
            self._video_player.set_source(video_path, 0.0, -1.0)
            if self._video_player.has_source():
                self._had_video_intro = True
                self._stage = ClipStage.VIDEO_PLAY
                fade = self._drawer.fade
                fade.fade_on(_CHANNEL_HOOK, 0.0)
                fade.fade_on(_CHANNEL_BOTTOM, 0.0)
                return
            self._video_player.close()

        if self._ko_plan is not None:
            self._stage = ClipStage.VIDEO_PLAY
            self._had_video_intro = bool(video_path)
            self._drawer.fade.fade_on(_CHANNEL_BOTTOM, 0.25)
            self._start_ko_narration_sequence(during_video=bool(video_path))
            if not video_path:
                return

        self._finish_topic_intro()

    def _finish_topic_intro(self) -> None:
        if not self._topic_intro_mode:
            return
        self._topic_intro_mode = False
        self._stop_learn_audio()
        self._video_player.close()
        self._frozen_video_frame = None
        self._last_live_video_frame = None
        self._video_display_alpha = 255
        cb = self._on_topic_intro_done
        if cb:
            cb()

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

    def _is_video_ko_narration_pending(self) -> bool:
        """인트로 비디오 구간 KO 자막·TTS가 아직 끝나지 않았으면 True."""
        if not self._had_video_intro or not self._ko_started or self._ko_finished:
            return False
        if self._stage not in (
            ClipStage.VIDEO_PLAY,
            ClipStage.VIDEO_HOLD,
            ClipStage.VIDEO_FADE_OUT,
        ):
            return False
        return True

    def _vocab_show_ui_immediately(self) -> None:
        """단어 숏츠: 훅·하단 페이드 없이 즉시 표시."""
        fade = self._drawer.fade
        fade.fade_on(_CHANNEL_HOOK, 0.0)
        fade.fade_on(_CHANNEL_BOTTOM, 0.0)

    def _vocab_skip_to_content(self) -> None:
        """단어 숏츠: HOOK_IN 대기 없이 뜻 TTS 또는 발음 단계로."""
        self._vocab_show_ui_immediately()
        if self._vocab_meaning_plan is None:
            self._ensure_vocab_meaning_plan()
        if self._vocab_meaning_plan is not None:
            self._enter_vocab_meaning_ko()
        else:
            self._enter_learn_play()

    def _enter_hook_in(self) -> None:
        if self._is_vocabulary_clip():
            self._stage = ClipStage.HOOK_IN
            self._timer = 0.0
            self._vocab_skip_to_content()
            return
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
        self._reset_word_video()
        self._frozen_video_frame = None
        self._video_inner_size = (0, 0)
        self._video_display_alpha = 255
        self._had_video_intro = False
        self._last_live_video_frame = None
        self._ko_plan = None
        self._ko_cue_index = 0
        self._ko_current_text = ""
        self._ko_cue_elapsed = 0.0
        self._ko_cue_duration = 0.0
        self._ko_finished = False
        self._ko_started = False
        self._vocab_meaning_plan = None
        self._vocab_meaning_subtitle_hold = ""
        self._vocab_meaning_entered = False
        self._ensure_ko_plan()
        self._ensure_vocab_meaning_plan()

        video_path = str(self._clip.get("video_path") or "").strip()
        if video_path and self._clip_has_video_intro():
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

    def _clip_has_video_intro(self) -> bool:
        """단어 숏츠는 topic 인트로에서만 비디오. 회화만 클립별 비디오."""
        return str(self._clip.get("clip_type") or "").strip() == CLIP_TYPE_CONVERSATION

    def _word_video_path(self) -> str:
        return str(self._clip.get("word_video_path") or "").strip()

    def _has_word_video(self) -> bool:
        return bool(self._word_video_path())

    def _reset_word_video(self) -> None:
        self._word_video_player.close()
        self._word_video_frozen_frame = None
        self._word_video_last_live_frame = None
        self._word_video_inner_size = (0, 0)
        self._word_video_started = False
        self._word_video_clock = 0.0

    def _load_word_video_source(self) -> bool:
        """비디오 파일을 연다(클립당 1회)."""
        path = self._word_video_path()
        if not path:
            return False
        self._word_video_player.set_source(path, 0.0, -1.0)
        if not self._word_video_player.has_source():
            logger.warning(
                "단어 비디오 열기 실패 word_id=%s: %s",
                self._clip.get("word_id"),
                path,
            )
            return False
        self._word_video_player.seek_to(0.0)
        return True

    def _begin_word_video_once(self) -> None:
        """video_path 있으면 단어 클립 전체에서 비디오 1회만 시작(뜻 TTS·발음 구간 연속)."""
        if not self._has_word_video():
            return
        if self._word_video_started:
            return
        self._word_video_frozen_frame = None
        self._word_video_last_live_frame = None
        self._word_video_clock = 0.0
        if not self._load_word_video_source():
            self._reset_word_video()
            return
        self._word_video_started = True

    def _should_draw_word_video(self) -> bool:
        if not self._has_word_video() or not self._word_video_started:
            return False
        return self._stage in (
            ClipStage.VOCAB_MEANING_KO,
            ClipStage.LEARN_PLAY,
            ClipStage.VOCAB_GAP,
            ClipStage.CTA_HOLD,
            ClipStage.END_HOLD,
            ClipStage.TRANSITION_OUT,
        )

    def _freeze_word_video_frame(self) -> None:
        if self._word_video_frozen_frame is not None:
            if self._word_video_player.has_source():
                self._word_video_player.close()
            return
        iw, ih = self._word_video_inner_size
        if iw <= 0 or ih <= 0:
            iw, ih = self._vocab_word_media_inner_size()
        frame = None
        if self._word_video_player.has_source():
            frame = self._word_video_player.get_frame(iw, ih, contain=True)
        if frame is None and self._word_video_last_live_frame is not None:
            frame = self._word_video_last_live_frame
        if frame is not None:
            self._word_video_frozen_frame = frame.copy()
        if self._word_video_player.has_source():
            self._word_video_player.close()

    def _sync_word_video_timeline(self, dt_sec: float) -> None:
        """단어 클립 단일 타임라인 — 뜻 TTS·발음 구간에 걸쳐 1회만 재생."""
        if not self._word_video_started or self._word_video_frozen_frame is not None:
            return
        if not self._word_video_player.has_source():
            return
        self._word_video_clock += max(0.0, float(dt_sec))
        end_sec = float(self._word_video_player.get_effective_end_sec())
        t = min(self._word_video_clock, end_sec)
        self._word_video_player.seek_to(t)
        if t >= end_sec - 1e-3:
            self._freeze_word_video_frame()

    def _vocab_word_media_inner_size(self) -> tuple[int, int]:
        from studio.shorts.constants import shorts_vocab_word_img_inner_size

        w = max(1, int(SHORTS_WIDTH))
        h = max(1, int(SHORTS_HEIGHT * ZONE_MIDDLE_RATIO))
        return shorts_vocab_word_img_inner_size(w, h, SHORTS_HEIGHT)

    def _vocab_word_media_slot(
        self, zones: Optional[ShortsLayoutZones]
    ) -> tuple[pygame.Rect, tuple[int, int]]:
        from studio.shorts.constants import (
            shorts_vocab_image_y_offset,
            shorts_vocab_layout_metrics,
            shorts_vocab_word_img_inner_size,
        )

        if zones is None:
            mid_top = int(SHORTS_HEIGHT * (1.0 - ZONE_MIDDLE_RATIO - 0.30))
            mid_h = int(SHORTS_HEIGHT * ZONE_MIDDLE_RATIO)
            mid_bottom = mid_top + mid_h
            mid_left = 0
            mid_width = SHORTS_WIDTH
            fh = SHORTS_HEIGHT
        else:
            mid_top = zones.middle.top
            mid_h = zones.middle.height
            mid_bottom = zones.middle.bottom
            mid_left = zones.middle.left
            mid_width = zones.middle.width
            fh = max(1, int(zones.middle.height))
        hook_bottom = self._drawer.measure_hook_title_bottom_y(
            self._hook_title, frame_height=fh
        )
        layout_top, img_band_h = shorts_vocab_layout_metrics(
            mid_top,
            mid_h,
            mid_bottom,
            fh,
            hook_title_bottom_y=hook_bottom,
        )
        max_w, max_h = shorts_vocab_word_img_inner_size(mid_width, mid_h, fh)
        iy = int(layout_top) + shorts_vocab_image_y_offset(fh)
        slot = pygame.Rect(mid_left, max(0, iy), mid_width, max(48, int(img_band_h)))
        inner = (
            max(1, min(max_w, slot.width)),
            max(1, min(max(max_h, int(img_band_h)), slot.height)),
        )
        return slot, inner

    def _use_vocab_media_slot_for_video(self) -> bool:
        """단어 숏츠 topic 인트로 — middle 중앙이 아닌 연상 이미지·단어 비디오 슬롯."""
        return bool(self._topic_intro_mode and self._is_vocabulary_clip())

    def _draw_video_in_vocab_media_slot(
        self,
        screen: pygame.Surface,
        zones: ShortsLayoutZones,
        *,
        player: Any,
        frozen_frame: Optional[pygame.Surface],
        alpha: int = 255,
        track_inner: str = "main",
    ) -> None:
        """단어 연상 이미지·word_video와 동일 Y·밴드에 contain 비디오."""
        slot, inner = self._vocab_word_media_slot(zones)
        if track_inner == "main":
            self._video_inner_size = inner
        elif track_inner == "word":
            self._word_video_inner_size = inner
        self._drawer.draw_center_video(
            screen,
            player,
            slot,
            pad=0,
            frozen_frame=frozen_frame,
            alpha=alpha,
            frame_inner_size=inner,
        )

    def _draw_word_video_in_slot(self, screen: pygame.Surface, zones: ShortsLayoutZones) -> None:
        if not self._has_word_video():
            return
        frozen = self._word_video_frozen_frame
        player = None if frozen is not None else self._word_video_player
        if frozen is None and not (player and player.has_source()):
            return
        self._draw_video_in_vocab_media_slot(
            screen,
            zones,
            player=player,
            frozen_frame=frozen,
            track_inner="word",
        )
        inner = self._word_video_inner_size
        if frozen is not None:
            self._word_video_last_live_frame = frozen
        elif player is not None and player.has_source():
            live = player.get_frame(inner[0], inner[1], contain=True)
            if live is not None:
                self._word_video_last_live_frame = live.copy()

    def _enter_post_video_intro(self) -> None:
        """인트로 비디오·KO 내레이션 후 — 단어: 뜻 TTS, 회화: 학습."""
        if self._is_vocabulary_clip() and self._vocab_meaning_plan is not None:
            self._enter_vocab_meaning_ko()
        else:
            self._enter_learn_play()

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
        self._reset_word_video()
        self._stage = ClipStage.DONE
        if self._on_clip_done:
            self._on_clip_done()

    def begin_transition_out(self) -> None:
        if self._stage in (ClipStage.DONE, ClipStage.TRANSITION_OUT):
            return
        if self._stage in (ClipStage.VIDEO_PLAY, ClipStage.VIDEO_HOLD, ClipStage.VIDEO_FADE_OUT):
            self._video_player.close()
            if self._topic_intro_mode:
                self._finish_topic_intro()
            else:
                self._enter_post_video_intro()
            return
        if self._stage == ClipStage.LEARN_PLAY:
            self._stop_learn_audio()
        if (
            self._is_vocabulary_clip()
            and not self._is_last_clip
            and not self._topic_intro_mode
        ):
            self._finish_clip()
            return
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
            # tick 중 topic→단어 handoff(start_clip) 시 stage가 바뀌면 아래 VIDEO_HOLD 등 재진입 금지
            if self._stage != ClipStage.VIDEO_PLAY:
                pass
            elif self._topic_intro_mode and not self._video_player.has_source():
                if self._ko_finished or not self._is_video_ko_narration_pending():
                    self._finish_topic_intro()
            elif self._frozen_video_frame is not None:
                if not self._is_video_ko_narration_pending():
                    self._enter_video_hold()
            else:
                iw, ih = self._video_inner_size
                if iw <= 0 or ih <= 0:
                    iw, ih = self._default_video_inner_size()
                self._video_player.tick(max(0.0, float(dt_sec)))
                if self._video_player.has_source():
                    live = self._video_player.get_frame(iw, ih, contain=True)
                    if live is not None:
                        self._last_live_video_frame = live.copy()
                end_sec = float(self._video_player.get_effective_end_sec())
                pts = float(self._video_player.get_pts())
                if self._video_player.is_paused() and pts >= end_sec - 1e-3:
                    self._freeze_video_frame()
                    if (
                        self._stage == ClipStage.VIDEO_PLAY
                        and not self._is_video_ko_narration_pending()
                    ):
                        self._enter_video_hold()
            if self._stage == ClipStage.VIDEO_PLAY:
                return
            return

        if self._stage == ClipStage.VIDEO_HOLD:
            self._tick_ko_narration(dt_sec)
            if self._stage != ClipStage.VIDEO_HOLD:
                return
            if self._is_video_ko_narration_pending():
                self._timer = 0.0
                return
            if self._timer >= SHORTS_VIDEO_END_HOLD_SEC:
                self._enter_video_fade_out()
            return

        if self._stage == ClipStage.VIDEO_FADE_OUT:
            self._tick_ko_narration(dt_sec)
            if self._stage != ClipStage.VIDEO_FADE_OUT:
                return
            if self._is_video_ko_narration_pending():
                self._timer = 0.0
                return
            dur = max(1e-6, float(SHORTS_VIDEO_FADE_OUT_SEC))
            t = max(0.0, min(1.0, self._timer / dur))
            target = max(0, min(255, int(SHORTS_VIDEO_AFTER_ALPHA)))
            self._video_display_alpha = int(
                self._video_fade_from_alpha + (target - self._video_fade_from_alpha) * t
            )
            if t >= 1.0:
                self._video_display_alpha = target
                if self._topic_intro_mode:
                    self._finish_topic_intro()
                else:
                    self._enter_post_video_intro()
            return

        if self._stage == ClipStage.HOOK_IN:
            if self._is_vocabulary_clip():
                return
            if self._timer >= self._hook_fade_sec:
                if self._vocab_meaning_plan is not None:
                    self._enter_vocab_meaning_ko()
                else:
                    self._enter_learn_play()
            return

        if self._stage == ClipStage.VOCAB_MEANING_KO:
            self._tick_ko_narration(dt_sec)
            if self._is_vocabulary_clip():
                self._sync_word_video_timeline(dt_sec)
            return

        if self._stage == ClipStage.LEARN_PLAY:
            self._learn_elapsed += max(0.0, float(dt_sec))
            if self._is_vocabulary_clip():
                self._sync_word_video_timeline(dt_sec)
            if self._learn_round == 4:
                if self._learn_elapsed >= self._bg_practice_duration:
                    self._stop_learn_background_only()
                    if self._is_vocabulary_clip() and self._try_vocab_extra_cn_follow_cycle():
                        return
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

        if self._stage == ClipStage.VOCAB_GAP:
            if self._timer >= self._vocab_gap_sec:
                self._finish_clip()
            return

        if self._stage == ClipStage.CTA_HOLD:
            if self._timer >= self._cta_hold_sec:
                if self._is_last_clip:
                    self._finish_clip()
                elif self._is_vocabulary_clip():
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

    def _default_video_inner_size(self) -> tuple[int, int]:
        pad = 32
        w = max(1, int(SHORTS_WIDTH) - pad * 2)
        h = max(1, int(SHORTS_HEIGHT * ZONE_MIDDLE_RATIO) - pad * 2)
        return w, h

    def _freeze_video_frame(self) -> None:
        if self._frozen_video_frame is not None:
            if self._video_player.has_source():
                self._video_player.close()
            return
        w, h = self._video_inner_size
        if w <= 0 or h <= 0:
            w, h = self._default_video_inner_size()
        frame = None
        if self._video_player.has_source():
            frame = self._video_player.get_frame(w, h, contain=True)
        if frame is None and self._last_live_video_frame is not None:
            frame = self._last_live_video_frame
        if frame is not None:
            self._frozen_video_frame = frame.copy()
        if self._video_player.has_source():
            self._video_player.close()

    def _enter_video_hold(self) -> None:
        if self._topic_intro_mode and not self._is_video_ko_narration_pending():
            self._finish_topic_intro()
            return
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
        if self._is_vocabulary_clip():
            self._begin_word_video_once()
        path = str(self._clip.get("sound_path") or "").strip()
        if path:
            self._start_sentence_play(play_index=1)
        else:
            if self._is_vocabulary_clip():
                self._finish_learn_sequence()
            else:
                self._start_follow_along_voice()

    def _is_vocabulary_clip(self) -> bool:
        return str(self._clip.get("clip_type") or "").strip() == CLIP_TYPE_VOCABULARY

    def _should_read_meaning_ko(self) -> bool:
        """shorts_vocabulary_clips.read_meaning_ko — false면 뜻 TTS 없이 중국어 mp3만."""
        v = self._clip.get("read_meaning_ko")
        if v is None:
            return True
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ("", "1", "true", "yes", "y", "on", "t"):
            return True
        if s in ("0", "false", "no", "n", "off", "f"):
            return False
        return True

    def _ensure_vocab_meaning_plan(self) -> None:
        if not self._is_vocabulary_clip():
            return
        if not self._should_read_meaning_ko():
            self._vocab_meaning_plan = None
            return
        try:
            from audio.vocab_meaning_ko import ensure_vocab_meaning_plan_for_clip

            plan = ensure_vocab_meaning_plan_for_clip(self._clip, build_if_missing=True)
            if plan is not None:
                self._vocab_meaning_plan = plan
                self._clip["_vocab_meaning_plan"] = plan
            else:
                wid = self._clip.get("word_id")
                logger.warning(
                    "단어 뜻 TTS 없음 word_id=%s — "
                    "lvpd.bat → 2 TTS (숏츠 단어) 로 생성 후 재생",
                    wid,
                )
        except Exception as ex:
            logger.warning("단어 뜻 TTS 로드 실패 word_id=%s: %s", self._clip.get("word_id"), ex)

    def _active_ko_plan(self) -> Optional[Any]:
        if self._stage == ClipStage.VOCAB_MEANING_KO:
            return self._vocab_meaning_plan
        return self._ko_plan

    def _enter_vocab_meaning_ko(self) -> None:
        """단어 모드: 한국어 뜻 TTS·자막 후 중국어 발음."""
        if self._vocab_meaning_entered:
            return
        if (
            self._stage == ClipStage.VOCAB_MEANING_KO
            and self._ko_started
            and not self._ko_finished
        ):
            return
        plan = self._vocab_meaning_plan
        if plan is None or not getattr(plan, "cues", None):
            logger.info(
                "단어 뜻 TTS 스킵 → 중국어 발음(word sound_path) word_id=%s",
                self._clip.get("word_id"),
            )
            self._enter_learn_play()
            return
        self._stop_learn_audio()
        self._stage = ClipStage.VOCAB_MEANING_KO
        self._timer = 0.0
        self._ko_started = False
        self._ko_finished = False
        self._vocab_meaning_entered = True
        self._vocab_show_ui_immediately()
        self._begin_word_video_once()
        self._start_ko_narration_sequence(during_video=False)

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

    def _vocab_sound_repeat_target(self) -> int:
        try:
            return max(1, int(self._clip.get("sound_repeat_count") or 1))
        except (TypeError, ValueError):
            return 1

    def _vocab_after_sound_delay_sec(self) -> float:
        try:
            return max(0.0, float(self._clip.get("after_sound_delay_sec") or 0))
        except (TypeError, ValueError):
            return 0.0

    def _word_video_remaining_sec(self) -> float:
        """단어 mp4 타임라인 잔여(초). 동결·미시작이면 0."""
        if not self._word_video_started or self._word_video_frozen_frame is not None:
            return 0.0
        if not self._word_video_player.has_source():
            return 0.0
        end_sec = max(0.0, float(self._word_video_player.get_effective_end_sec()))
        return max(0.0, end_sec - float(self._word_video_clock))

    def _vocab_cn_follow_cycle_sec(self) -> float:
        """중국어 N회 + 따라해보세요 + BG 따라발음 1사이클 추정 길이."""
        cn = max(0.1, float(self._sentence_sound_duration or self._sound_once_duration))
        target = max(1, int(self._vocab_sound_repeat_target()))
        follow = max(2.5, float(self._sound_once_duration) if self._learn_round == 3 else 2.5)
        bg = max(
            float(SHORTS_BG_PRACTICE_MIN_SEC),
            cn + float(SHORTS_BG_KARAOKE_SLOW_EXTRA_SEC),
        )
        return target * cn + follow + bg + 1.0

    def _try_vocab_extra_cn_follow_cycle(self) -> bool:
        """word_video 잔여 시간이 있으면 뜻 TTS 없이 중국어→따라발음만 반복."""
        remain = self._word_video_remaining_sec()
        need = self._vocab_cn_follow_cycle_sec()
        if remain < need * 0.85:
            return False
        self._learn_round = 0
        self._learn_elapsed = 0.0
        self._sound_play_count = 0
        self._start_sentence_play(play_index=1)
        return True

    def _enter_vocab_gap(self) -> None:
        self._stop_learn_audio()
        self._stage = ClipStage.VOCAB_GAP
        self._timer = 0.0
        self._vocab_gap_sec = self._vocab_after_sound_delay_sec()

    def _advance_learn_voice_step(self) -> None:
        if self._is_vocabulary_clip():
            target = self._vocab_sound_repeat_target()
            if self._sound_play_count < target:
                self._start_sentence_play(play_index=self._sound_play_count + 1)
            elif self._learn_round < 3:
                self._start_follow_along_voice()
            elif self._learn_round == 3:
                self._start_bg_practice()
            else:
                self._finish_learn_sequence()
            return
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
        if self._is_vocabulary_clip():
            if self._is_last_clip:
                self._enter_cta_hold()
            elif self._vocab_after_sound_delay_sec() > 1e-6:
                self._enter_vocab_gap()
            else:
                self._finish_clip()
            return
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
        plan = self._active_ko_plan()
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
        plan = self._active_ko_plan()
        if plan is None:
            self._ko_finished = True
            if self._stage == ClipStage.VOCAB_MEANING_KO:
                self._enter_learn_play()
            elif self._stage == ClipStage.KO_NARRATION:
                self._enter_cta_hold()
            return
        cues = list(getattr(plan, "cues", None) or [])
        if index >= len(cues):
            self._ko_finished = True
            if self._stage == ClipStage.VOCAB_MEANING_KO and self._is_vocabulary_clip():
                hold = (self._ko_current_text or "").strip()
                if hold:
                    self._vocab_meaning_subtitle_hold = hold
            self._ko_current_text = ""
            if self._topic_intro_mode:
                if self._had_video_intro:
                    self._enter_video_hold()
                else:
                    self._finish_topic_intro()
            elif self._stage == ClipStage.VOCAB_MEANING_KO:
                logger.debug(
                    "단어 뜻 TTS 완료 → 중국어 발음 word_id=%s",
                    self._clip.get("word_id"),
                )
                self._enter_learn_play()
            elif self._stage == ClipStage.KO_NARRATION:
                self._enter_cta_hold()
            return
        cue = cues[index]
        self._ko_cue_index = index
        self._ko_current_text = str(getattr(cue, "text", "") or "")
        if self._stage == ClipStage.VOCAB_MEANING_KO and self._is_vocabulary_clip():
            t = (self._ko_current_text or "").strip()
            if t:
                self._vocab_meaning_subtitle_hold = t
        self._ko_cue_elapsed = 0.0
        path = str(getattr(cue, "audio_path", "") or "").strip()
        if path:
            try:
                from audio.ko_narration import resolve_ko_cue_audio_path

                path = resolve_ko_cue_audio_path(path)
            except Exception:
                pass
        if (
            self._stage == ClipStage.VOCAB_MEANING_KO
            and self._is_vocabulary_clip()
            and path
        ):
            logger.info(
                "단어 뜻 TTS 재생 word_id=%s: %s",
                self._clip.get("word_id"),
                path,
            )
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
        if self._ko_started and not self._ko_finished:
            text = (self._ko_current_text or "").strip()
            if not text:
                return ""
            if self._is_vocabulary_clip():
                if self._stage in (
                    ClipStage.VIDEO_PLAY,
                    ClipStage.VIDEO_HOLD,
                    ClipStage.VIDEO_FADE_OUT,
                    ClipStage.VOCAB_MEANING_KO,
                    ClipStage.KO_NARRATION,
                ):
                    return text
                return ""
            return text
        return ""

    def _learn_overlay_subtitle(self) -> str:
        """학습 구간 비디오 하단 안내 자막( KO 내레이션 cue 와 별도 )."""
        if self._stage != ClipStage.LEARN_PLAY:
            return ""
        if self._learn_round in (1, 2):
            return SHORTS_NATIVE_LISTEN_LABEL
        if self._learn_round in (3, 4):
            return SHORTS_FOLLOW_ALONG_LABEL
        return ""

    def _overlay_subtitle_text(self) -> str:
        ko = self._active_ko_subtitle()
        if ko:
            return ko
        return self._learn_overlay_subtitle()

    def _ko_subtitle_progress(self) -> Optional[float]:
        text = self._active_ko_subtitle()
        if not text:
            return None
        return compute_karaoke_progress(self._ko_cue_elapsed, self._ko_cue_duration)

    def _overlay_subtitle_progress(self) -> Optional[float]:
        if self._is_vocabulary_clip() and self._stage == ClipStage.VOCAB_MEANING_KO:
            if self._active_ko_subtitle():
                return 1.0
        if self._active_ko_subtitle() and self._ko_started and not self._ko_finished:
            return self._ko_subtitle_progress()
        if self._stage == ClipStage.LEARN_PLAY and self._learn_round == 3:
            dur = max(0.0, float(self._sound_once_duration))
            if dur > 1e-6:
                return compute_karaoke_progress(self._learn_elapsed, dur)
        return None

    def _last_hold_sec_for_clip(self) -> float:
        """shorts_*_clips.last_hold_sec — 비우면 CTA_HOLD_SEC(2.5)."""
        raw = self._clip.get("last_hold_sec")
        if raw is None:
            return self._default_cta_hold_sec
        if isinstance(raw, (int, float)):
            return max(0.0, float(raw))
        s = str(raw).strip()
        if not s:
            return self._default_cta_hold_sec
        try:
            return max(0.0, float(s))
        except (TypeError, ValueError):
            return self._default_cta_hold_sec

    def _enter_cta_hold(self) -> None:
        self._stop_learn_audio()
        self._stage = ClipStage.CTA_HOLD
        self._timer = 0.0
        self._cta_hold_sec = self._last_hold_sec_for_clip()
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
        """하단 situation 문구 — 학습(1~4단계) 중에는 숨기고, 학습 끝난 뒤에만."""
        if self._is_vocabulary_clip():
            return ""
        if self._stage in (ClipStage.LEARN_PLAY, ClipStage.VOCAB_MEANING_KO):
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
        stages = (
            ClipStage.VOCAB_MEANING_KO,
            ClipStage.LEARN_PLAY,
            ClipStage.KO_NARRATION,
            ClipStage.VOCAB_GAP,
            ClipStage.CTA_HOLD,
            ClipStage.END_HOLD,
            ClipStage.TRANSITION_OUT,
        )
        if self._is_vocabulary_clip() and self._stage == ClipStage.HOOK_IN:
            return True
        return self._stage in stages

    def set_voice_channel(self, channel: Optional[pygame.mixer.Channel]) -> None:
        self._voice_channel = channel

    def _video_frame_inner_size(self) -> Optional[tuple[int, int]]:
        w, h = self._video_inner_size
        if w > 0 and h > 0:
            return (w, h)
        return None

    def _vocab_ko_subtitle_anchor_rect(
        self, zones: ShortsLayoutZones, *, frame_height: int = 0
    ) -> pygame.Rect:
        """단어 숏츠 TTS 자막 — drawer 뜻(meaning_y)과 동일 앵커."""
        fh = max(int(frame_height), zones.middle.height, 1)
        fw = max(1, zones.middle.width)
        _, _, overlay = self._vocab_overlay_layout(zones, frame_height=fh, frame_width=fw)
        w = max(80, fw - 64)
        return pygame.Rect(
            zones.middle.centerx - w // 2,
            overlay.meaning_anchor_bottom - 1,
            w,
            1,
        )

    def _ko_subtitle_anchor_rect(
        self, zones: ShortsLayoutZones, *, frame_height: int = 0
    ) -> pygame.Rect:
        if self._is_vocabulary_clip():
            return self._vocab_ko_subtitle_anchor_rect(zones, frame_height=frame_height)
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
        fh = max(1, int(screen.get_height()))
        gap_fn = None
        if self._is_vocabulary_clip():
            from studio.shorts.constants import shorts_vocab_meaning_subtitle_gap

            gap_fn = shorts_vocab_meaning_subtitle_gap
        self._drawer.draw_ko_subtitle_overlay(
            screen,
            anchor_rect=self._ko_subtitle_anchor_rect(zones, frame_height=fh),
            text=sub,
            fade_alpha=self._drawer.fade_alpha(_CHANNEL_BOTTOM),
            subtitle_progress=self._overlay_subtitle_progress(),
            below_gap_fn=gap_fn,
        )

    def _vocab_overlay_layout(
        self,
        zones: ShortsLayoutZones,
        *,
        frame_height: int,
        frame_width: int = 0,
    ):
        from studio.shorts.constants import (
            shorts_ko_subtitle_font_size,
            shorts_vocab_layout_metrics,
            shorts_vocab_overlay_layout,
        )

        fh = max(int(frame_height), zones.middle.height, 1)
        fw = max(1, int(frame_width) if frame_width > 0 else zones.middle.width)
        hook_bottom = self._drawer.measure_hook_title_bottom_y(
            self._hook_title, frame_height=fh
        )
        layout_top, img_band_h = shorts_vocab_layout_metrics(
            zones.middle.top,
            zones.middle.height,
            zones.middle.bottom,
            fh,
            hook_title_bottom_y=hook_bottom,
        )
        pos_label = str(self._clip.get("word_pos") or "").strip()
        tip_label = str(self._clip.get("word_tip") or "").strip()
        ko_pt = shorts_ko_subtitle_font_size(fh)
        overlay = shorts_vocab_overlay_layout(
            layout_top,
            img_band_h,
            fh,
            frame_width=fw,
            has_pos=bool(pos_label),
            has_tip=bool(tip_label),
            ko_subtitle_pt=ko_pt,
        )
        return layout_top, img_band_h, overlay

    def _draw_vocab_meaning_if_any(
        self, screen: pygame.Surface, zones: ShortsLayoutZones
    ) -> None:
        if not self._is_vocabulary_clip() or not self._clip:
            return
        if self._stage not in (
            ClipStage.VOCAB_MEANING_KO,
            ClipStage.LEARN_PLAY,
            ClipStage.VOCAB_GAP,
            ClipStage.CTA_HOLD,
            ClipStage.END_HOLD,
            ClipStage.TRANSITION_OUT,
            ClipStage.HOOK_IN,
        ):
            return
        self._drawer.draw_vocab_meaning_if_any(
            screen,
            zones=zones,
            item=self._clip,
            hook_title=self._hook_title,
            fade_alpha=self._drawer.fade_alpha(_CHANNEL_BOTTOM),
        )

    def _draw_vocab_tip_if_any(self, screen: pygame.Surface, zones: ShortsLayoutZones) -> None:
        if not self._is_vocabulary_clip():
            return
        tip = str(self._clip.get("word_tip") or "").strip()
        if not tip:
            return
        if self._stage not in (
            ClipStage.VOCAB_MEANING_KO,
            ClipStage.LEARN_PLAY,
            ClipStage.VOCAB_GAP,
            ClipStage.CTA_HOLD,
            ClipStage.END_HOLD,
            ClipStage.TRANSITION_OUT,
        ):
            return
        fh = max(1, int(screen.get_height()))
        fw = max(1, int(screen.get_width()))
        _, _, overlay = self._vocab_overlay_layout(
            zones, frame_height=fh, frame_width=fw
        )
        if overlay.tip_y <= 0:
            return
        self._drawer.draw_vocab_tip(
            screen,
            center_x=zones.middle.centerx,
            y=overlay.tip_y,
            text=tip,
            fade_alpha=self._drawer.fade_alpha(_CHANNEL_BOTTOM),
            frame_height=fh,
        )

    def _last_hold_text(self) -> str:
        return str(self._clip.get("last_hold_text") or "").strip()

    def _last_hold_anchor_y(
        self, zones: ShortsLayoutZones, *, frame_height: int, frame_width: int
    ) -> int:
        """last_hold_text 시작 Y — tip 블록 아래 우선."""
        from studio.shorts.constants import (
            measure_vocab_tip_block_height,
            shorts_ko_subtitle_font_size,
            shorts_ko_subtitle_below_video_gap,
            shorts_last_hold_below_tip_gap,
            shorts_vocab_ko_subtitle_line_height,
        )

        fh = max(1, int(frame_height))
        gap = shorts_last_hold_below_tip_gap(fh)

        if self._is_vocabulary_clip():
            _, _, overlay = self._vocab_overlay_layout(
                zones, frame_height=fh, frame_width=frame_width
            )
            tip = str(self._clip.get("word_tip") or "").strip()
            ko_pt = shorts_ko_subtitle_font_size(fh)
            if tip and overlay.tip_y > 0:
                return (
                    int(overlay.tip_y)
                    + measure_vocab_tip_block_height(tip, fh, ko_subtitle_pt=ko_pt)
                    + gap
                )
            if overlay.meaning_y > 0:
                return (
                    int(overlay.meaning_y)
                    + shorts_vocab_ko_subtitle_line_height(fh, ko_subtitle_pt=ko_pt)
                    + gap
                )
            if overlay.tip_y > 0:
                return int(overlay.tip_y) + gap
            return int(zones.middle.centery)

        anchor = self._ko_subtitle_anchor_rect(zones, frame_height=fh)
        below = shorts_ko_subtitle_below_video_gap(fh)
        if anchor.height > 0:
            return int(anchor.bottom) + below + gap
        return int(zones.middle.centery) + gap

    def _draw_last_hold_if_any(self, screen: pygame.Surface, zones: ShortsLayoutZones) -> None:
        if self._stage != ClipStage.CTA_HOLD:
            return
        text = self._last_hold_text()
        if not text:
            return
        fh = max(1, int(screen.get_height()))
        fw = max(1, int(screen.get_width()))
        y = self._last_hold_anchor_y(zones, frame_height=fh, frame_width=fw)
        if y <= 0:
            return
        self._drawer.draw_last_hold_text(
            screen,
            center_x=zones.middle.centerx,
            y=y,
            text=text,
            fade_alpha=self._drawer.fade_alpha(_CHANNEL_BOTTOM),
            frame_height=fh,
        )

    def _draw_pinned_video(self, screen: pygame.Surface, zones: ShortsLayoutZones) -> None:
        """고정된 마지막 프레임(문장 단계에서도 유지)."""
        if self._frozen_video_frame is None:
            return
        if self._use_vocab_media_slot_for_video():
            self._draw_video_in_vocab_media_slot(
                screen,
                zones,
                player=None,
                frozen_frame=self._frozen_video_frame,
                alpha=self._video_display_alpha,
                track_inner="main",
            )
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
            if not self._use_vocab_media_slot_for_video():
                inner = zones.middle.inflate(-32, -32)
                if inner.width > 0 and inner.height > 0:
                    self._video_inner_size = (inner.width, inner.height)
            self._draw_hook_layers(screen, zones)
            if self._frozen_video_frame is not None:
                self._draw_pinned_video(screen, zones)
            elif self._stage == ClipStage.VIDEO_PLAY and self._video_player.has_source():
                if self._use_vocab_media_slot_for_video():
                    self._draw_video_in_vocab_media_slot(
                        screen,
                        zones,
                        player=self._video_player,
                        frozen_frame=None,
                        alpha=self._video_display_alpha,
                        track_inner="main",
                    )
                else:
                    self._drawer.draw_center_video(
                        screen,
                        self._video_player,
                        zones.middle,
                        alpha=self._video_display_alpha,
                        frame_inner_size=self._video_frame_inner_size(),
                    )
            elif self._stage in (ClipStage.VIDEO_HOLD, ClipStage.VIDEO_FADE_OUT):
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
        show_bottom_stages = (
            ClipStage.VOCAB_MEANING_KO,
            ClipStage.LEARN_PLAY,
            ClipStage.KO_NARRATION,
            ClipStage.VOCAB_GAP,
            ClipStage.CTA_HOLD,
            ClipStage.END_HOLD,
            ClipStage.TRANSITION_OUT,
        )
        show_bottom = self._stage in show_bottom_stages or (
            self._is_vocabulary_clip() and self._stage == ClipStage.HOOK_IN
        )
        overlay_sub = self._overlay_subtitle_text()

        if (
            self._frozen_video_frame is not None
            and self._stage
            not in (ClipStage.VOCAB_MEANING_KO, ClipStage.LEARN_PLAY, ClipStage.HOOK_IN)
        ):
            self._draw_pinned_video(screen, zones)

        meaning_karaoke: Optional[tuple[float, float]] = None
        if show_karaoke:
            k_elapsed, k_dur = self._learn_karaoke_timing()
            if self._stage == ClipStage.VOCAB_MEANING_KO:
                k_elapsed = float(self._ko_cue_elapsed)
                k_dur = max(1e-6, float(self._ko_cue_duration))
                meaning_karaoke = (k_elapsed, k_dur)
            clip_rect = (
                zones.vocab_middle_draw_clip()
                if self._is_vocabulary_clip()
                else zones.middle
            )
            screen.set_clip(clip_rect)
            try:
                if self._should_draw_word_video():
                    self._draw_word_video_in_slot(screen, zones)
                self._drawer.draw_middle(
                    screen,
                    zones=zones,
                    item=self._clip,
                    elapsed_sec=k_elapsed,
                    syllable_times=list(self._clip.get("syllable_times") or []),
                    sound_duration_sec=k_dur,
                    style=self._style,
                    hook_title=self._hook_title,
                    vocab_meaning_karaoke=meaning_karaoke,
                )
            finally:
                screen.set_clip(None)

        if show_karaoke or (
            self._is_vocabulary_clip()
            and self._stage
            in (
                ClipStage.VOCAB_MEANING_KO,
                ClipStage.LEARN_PLAY,
                ClipStage.VOCAB_GAP,
                ClipStage.CTA_HOLD,
                ClipStage.END_HOLD,
                ClipStage.TRANSITION_OUT,
                ClipStage.HOOK_IN,
            )
        ):
            self._draw_vocab_meaning_if_any(screen, zones)
        if overlay_sub:
            self._draw_ko_subtitle_if_any(screen, zones)
        self._draw_vocab_tip_if_any(screen, zones)
        self._draw_last_hold_if_any(screen, zones)
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
