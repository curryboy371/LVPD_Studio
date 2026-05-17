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
)
from studio.shorts.data_loading import resolve_hook_title
from studio.shorts.layout import ShortsLayoutZones
from studio.shorts.tools.shorts_drawer import ShortsDrawer

logger = logging.getLogger(__name__)

_CHANNEL_HOOK = "shorts_hook"
_CHANNEL_BOTTOM = "shorts_bottom"


class ClipStage(Enum):
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
        self._stage = ClipStage.HOOK_IN
        self._timer = 0.0
        self._learn_elapsed = 0.0
        self._sound_duration = 0.0
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

    def start_clip(self, clip: dict[str, Any], *, is_last: bool = True) -> None:
        """새 클립 시작."""
        self._clip = dict(clip)
        self._hook_title = resolve_hook_title(self._clip)
        if self._hook_title:
            self._clip["hook_title"] = self._hook_title
        self._is_last_clip = bool(is_last)
        self._stage = ClipStage.HOOK_IN
        self._timer = 0.0
        self._learn_elapsed = 0.0
        self._sound_duration = 0.0
        self._voice_channel = None
        fade = self._drawer.fade
        fade.fade_off(_CHANNEL_HOOK, 0.0)
        fade.fade_off(_CHANNEL_BOTTOM, 0.0)
        fade.fade_on(_CHANNEL_HOOK, self._hook_fade_sec)
        fade.fade_on(_CHANNEL_BOTTOM, 0.0)

    def _finish_clip(self) -> None:
        self._stage = ClipStage.DONE
        if self._on_clip_done:
            self._on_clip_done()

    def begin_transition_out(self) -> None:
        if self._stage in (ClipStage.DONE, ClipStage.TRANSITION_OUT):
            return
        self._stage = ClipStage.TRANSITION_OUT
        self._timer = 0.0
        self._drawer.fade.fade_off(_CHANNEL_HOOK, CLIP_TRANSITION_FADE_SEC)
        self._drawer.fade.fade_off(_CHANNEL_BOTTOM, CLIP_TRANSITION_FADE_SEC)

    def update(self, dt_sec: float) -> None:
        self._drawer.tick_fade(dt_sec)
        self._timer += max(0.0, float(dt_sec))

        if self._stage == ClipStage.HOOK_IN:
            if self._timer >= self._hook_fade_sec:
                self._enter_learn_play()
            return

        if self._stage == ClipStage.LEARN_PLAY:
            self._learn_elapsed += max(0.0, float(dt_sec))
            if self._is_voice_finished():
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

    def _enter_learn_play(self) -> None:
        self._stage = ClipStage.LEARN_PLAY
        self._timer = 0.0
        self._learn_elapsed = 0.0
        self._drawer.fade.fade_on(_CHANNEL_BOTTOM, 0.25)
        path = str(self._clip.get("sound_path") or "").strip()
        self._sound_duration = self._play_voice(path) if path else 0.0
        if self._sound_duration <= 0 and path:
            self._sound_duration = 3.0

    def _enter_cta_hold(self) -> None:
        self._stage = ClipStage.CTA_HOLD
        self._timer = 0.0
        self._drawer.fade.fade_on(_CHANNEL_BOTTOM, 0.35)

    def _is_voice_finished(self) -> bool:
        ch = self._voice_channel
        if ch is not None and ch.get_busy():
            return False
        dur = max(0.0, float(self._sound_duration))
        if dur <= 1e-6:
            return self._learn_elapsed >= 2.0
        return self._learn_elapsed >= dur + 0.15

    def set_voice_channel(self, channel: Optional[pygame.mixer.Channel]) -> None:
        self._voice_channel = channel

    def draw(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        if not self._clip:
            return

        zones = ShortsLayoutZones.from_surface(screen, ctx)
        show_cta = self._stage in (ClipStage.CTA_HOLD, ClipStage.TRANSITION_OUT)
        show_karaoke = self._stage in (ClipStage.LEARN_PLAY, ClipStage.CTA_HOLD)
        show_bottom = self._stage in (
            ClipStage.LEARN_PLAY,
            ClipStage.CTA_HOLD,
            ClipStage.TRANSITION_OUT,
        )

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
