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
    SHORTS_VIDEO_AFTER_ALPHA,
    SHORTS_VIDEO_END_HOLD_SEC,
    SHORTS_SOUND_PLAY_COUNT,
    SHORTS_VIDEO_FADE_OUT_SEC,
)
from studio.conversation.video_players import SimpleVideoPlayer
from studio.shorts.clip_types import CLIP_TYPE_CONVERSATION
from studio.shorts.data_loading import resolve_hook_title
from studio.shorts.layout import ShortsLayoutZones
from studio.shorts.tools.shorts_drawer import ShortsDrawer

logger = logging.getLogger(__name__)

_CHANNEL_HOOK = "shorts_hook"
_CHANNEL_BOTTOM = "shorts_bottom"


class ClipStage(Enum):
    VIDEO_PLAY = auto()
    VIDEO_HOLD = auto()
    VIDEO_FADE_OUT = auto()
    HOOK_IN = auto()
    LEARN_PLAY = auto()
    CTA_HOLD = auto()
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
        hook_fade_sec: float = HOOK_FADE_IN_SEC,
        cta_hold_sec: float = CTA_HOLD_SEC,
    ) -> None:
        self._drawer = drawer
        self._style = style
        self._play_voice = play_voice
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
        self._voice_channel: Optional[pygame.mixer.Channel] = None
        self._on_clip_done: Optional[Callable[[], None]] = None
        self._is_last_clip = True

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
        self._voice_channel = None
        self._video_player.close()
        self._frozen_video_frame = None
        self._video_inner_size = (0, 0)
        self._video_display_alpha = 255
        self._had_video_intro = False

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
            self._video_player.tick(max(0.0, float(dt_sec)))
            end_sec = float(self._video_player.get_effective_end_sec())
            pts = float(self._video_player.get_pts())
            if self._video_player.is_paused() and pts >= end_sec - 1e-3:
                self._freeze_video_frame()
                self._enter_video_hold()
            return

        if self._stage == ClipStage.VIDEO_HOLD:
            if self._timer >= SHORTS_VIDEO_END_HOLD_SEC:
                self._enter_video_fade_out()
            return

        if self._stage == ClipStage.VIDEO_FADE_OUT:
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
            if self._is_voice_finished():
                if self._should_play_sound_again():
                    self._play_sound_once()
                else:
                    self._enter_cta_hold()
            return

        if self._stage == ClipStage.CTA_HOLD:
            if self._timer >= self._cta_hold_sec:
                if self._is_last_clip:
                    self._finish_clip()
                else:
                    self.begin_transition_out()
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
        self._stage = ClipStage.LEARN_PLAY
        self._timer = 0.0
        self._learn_elapsed = 0.0
        self._sound_play_count = 0
        self._sound_once_duration = 0.0
        self._sound_duration = 0.0
        self._drawer.fade.fade_on(_CHANNEL_BOTTOM, 0.25)
        path = str(self._clip.get("sound_path") or "").strip()
        if path:
            self._play_sound_once()
        else:
            self._sound_play_count = max(1, int(SHORTS_SOUND_PLAY_COUNT))

    def _play_sound_once(self) -> None:
        path = str(self._clip.get("sound_path") or "").strip()
        self._learn_elapsed = 0.0
        self._sound_once_duration = self._play_voice(path) if path else 0.0
        if self._sound_once_duration <= 0 and path:
            self._sound_once_duration = 3.0
        self._sound_duration = self._sound_once_duration
        self._sound_play_count += 1

    def _should_play_sound_again(self) -> bool:
        path = str(self._clip.get("sound_path") or "").strip()
        if not path:
            return False
        return self._sound_play_count < max(1, int(SHORTS_SOUND_PLAY_COUNT))

    def _enter_cta_hold(self) -> None:
        self._stage = ClipStage.CTA_HOLD
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

    def set_voice_channel(self, channel: Optional[pygame.mixer.Channel]) -> None:
        self._voice_channel = channel

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
                )
            else:
                self._draw_pinned_video(screen, zones)
            self._drawer.draw_bottom_zone(
                screen,
                zones=zones,
                situation_subtitle=str(self._clip.get("situation_subtitle") or ""),
                cta_text="",
                channel=_CHANNEL_BOTTOM,
                show_cta=False,
            )
            return
        show_cta = self._stage in (ClipStage.CTA_HOLD, ClipStage.TRANSITION_OUT)
        show_karaoke = self._stage in (ClipStage.LEARN_PLAY, ClipStage.CTA_HOLD)
        show_bottom = self._stage in (
            ClipStage.LEARN_PLAY,
            ClipStage.CTA_HOLD,
            ClipStage.TRANSITION_OUT,
        )

        if self._frozen_video_frame is not None:
            self._draw_pinned_video(screen, zones)

        if show_karaoke:
            elapsed = self._learn_elapsed if self._stage == ClipStage.LEARN_PLAY else self._sound_duration
            screen.set_clip(zones.middle)
            try:
                self._drawer.draw_middle(
                    screen,
                    zones=zones,
                    item=self._clip,
                    elapsed_sec=elapsed,
                    syllable_times=list(self._clip.get("syllable_times") or []),
                    sound_duration_sec=float(self._sound_duration or 0.0),
                    style=self._style,
                )
            finally:
                screen.set_clip(None)

        if show_bottom:
            self._drawer.draw_bottom_zone(
                screen,
                zones=zones,
                situation_subtitle=str(self._clip.get("situation_subtitle") or ""),
                cta_text=str(self._clip.get("cta_text") or ""),
                channel=_CHANNEL_BOTTOM,
                show_cta=show_cta,
            )

        screen.set_clip(None)
        self._draw_hook_layers(screen, zones)
