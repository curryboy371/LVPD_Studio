"""Learning step: video + central sentence block."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, auto
from typing import Any

import pygame

from ..core.step_transition import StepTransitionMode
from ..core.types import ConversationItemLike, FrameContext, SentenceStyleConfig
from .base import IStep


class LearningStep(IStep):
    """학습(중앙 문장 표시) Step.

    상태 전환은 `update`의 if/elif와 `_set_stage`에만 둔다(엔진/자동 바인딩 없음).
    `style`은 `ConversationStudio.init`에서 폰트 로드와 같은 RGB 상수로 구성해 넘긴다.
    """

    class Stage(Enum):
        TITLE = auto()
        PLAY_L1 = auto()
        WAIT_AFTER_L1 = auto()
        PLAY_L2 = auto()
        WAIT_AFTER_L2 = auto()
        DONE = auto()

    @classmethod
    def channels_from_layers(
        cls,
        layers: tuple[str, ...] | list[str],
        *,
        prefix: str,
    ) -> dict[str, str]:
        p = str(prefix).strip()
        if not p.endswith("_"):
            p = f"{p}_"
        return {layer: f"{p}{layer}" for layer in layers}

    def __init__(
        self,
        *,
        drawer,
        video_player,
        style: SentenceStyleConfig,
        hold_sec: float = 2.0,
        play_voice: Callable[..., None] | None = None,
        title_text: str = "학습",
        title_fade_in_sec: float = 1.0,
        layer_channel_map: dict[str, str] | None = None,
        layer_channel_prefix: str = "learning",
        stage_audio_keys: dict["LearningStep.Stage", str] | None = None,
        wait_for_sound_end: bool = False,
    ) -> None:
        super().__init__()
        self.drawer = drawer
        self.video_player = video_player
        self.step_transition_mode: StepTransitionMode = StepTransitionMode.CUT
        self.step_transition_duration_sec: float = 0.4
        self.step_transition_overlay_peak_alpha: int = 220
        self._active_item_key: Any | None = None

        layers_default = ("title", "sentence")
        if layer_channel_map is not None:
            lmap = dict(layer_channel_map)
        else:
            lmap = self.channels_from_layers(layers_default, prefix=layer_channel_prefix)
        for required in layers_default:
            if required not in lmap:
                raise ValueError(
                    f"layer_channel_map must include {required!r} keys (got {sorted(lmap)})"
                )
        self._style = style
        self._hold_sec = max(0.0, float(hold_sec))
        self._play_voice = play_voice
        self._title_text = str(title_text)
        self._title_fade_in_sec = max(0.0, float(title_fade_in_sec))
        self._title_channel = lmap["title"]
        self._sentence_channel = lmap["sentence"]
        self._wait_for_sound_end = bool(wait_for_sound_end)
        self._stage_audio_keys: dict[LearningStep.Stage, str] = {
            self.Stage.PLAY_L1: "sound_l1",
            self.Stage.PLAY_L2: "sound_l2",
            **(stage_audio_keys or {}),
        }
        self._current_item: ConversationItemLike = {}
        self._timer: float = 0.0
        self.stage: LearningStep.Stage = LearningStep.Stage.TITLE
        self._set_stage(LearningStep.Stage.TITLE)

    def _all_channels(self) -> list[str]:
        return list(dict.fromkeys([self._title_channel, self._sentence_channel]))

    def _item_identity_key(self, item: ConversationItemLike) -> Any:
        try:
            return (
                str(item.get("id") or ""),
                float(item.get("start_time", 0.0) or 0.0),
                float(item.get("end_time", -1.0) or -1.0),
            )
        except Exception:
            return None

    def _reset_step_on_item_change(self, item: ConversationItemLike) -> None:
        _ = item
        self.drawer.fade_all_off(self._all_channels(), 0.0)
        self.transition_bg_frame = None
        self.transition_signal = False
        self._set_stage(LearningStep.Stage.TITLE)

    def sync_item_identity(self, item: ConversationItemLike) -> bool:
        key = self._item_identity_key(item)
        if key == self._active_item_key:
            return False
        self._active_item_key = key
        self._reset_step_on_item_change(item)
        return True

    def _fade_on_title_and_sentence(self) -> None:
        self.drawer.fade_on(self._title_channel, 0.0)
        self.drawer.fade_on(self._sentence_channel, 0.0)

    def _play_item_sound(self, key: str) -> float:
        path = str(self._current_item.get(key) or "").strip()
        if not path:
            return 0.0
        if self._play_voice is not None:
            try:
                self._play_voice(path, item=self._current_item)
            except Exception:
                pass
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
        except Exception:
            pass
        try:
            snd = pygame.mixer.Sound(path)
            return float(snd.get_length())
        except Exception:
            return 0.0

    def _apply_done_transition(self) -> None:
        if self.transition_bg_frame is None and self.bg_frame is not None:
            try:
                self.transition_bg_frame = self.bg_frame.copy()
            except Exception:
                self.transition_bg_frame = self.bg_frame
        self.transition_signal = True

    def _set_stage(self, stage: LearningStep.Stage) -> None:
        self.stage = stage

        if stage == LearningStep.Stage.TITLE:
            self.drawer.fade_off(self._sentence_channel, 0.0)
            self.drawer.fade_on(self._title_channel, self._title_fade_in_sec)
            self._timer = self._title_fade_in_sec

        elif stage == LearningStep.Stage.PLAY_L1:
            self._fade_on_title_and_sentence()
            dur = self._play_item_sound(self._stage_audio_keys[LearningStep.Stage.PLAY_L1])
            self._timer = dur if self._wait_for_sound_end else 0.0

        elif stage == LearningStep.Stage.WAIT_AFTER_L1:
            self._fade_on_title_and_sentence()
            self._timer = self._hold_sec

        elif stage == LearningStep.Stage.PLAY_L2:
            self._fade_on_title_and_sentence()
            dur = self._play_item_sound(self._stage_audio_keys[LearningStep.Stage.PLAY_L2])
            self._timer = dur if self._wait_for_sound_end else 0.0

        elif stage == LearningStep.Stage.WAIT_AFTER_L2:
            self._fade_on_title_and_sentence()
            self._timer = self._hold_sec

        elif stage == LearningStep.Stage.DONE:
            self._timer = float("inf")
            self._apply_done_transition()

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        self._current_item = item

        if self.sync_item_identity(item):
            self.drawer.fade_tick(float(ctx.dt_sec))
            return

        dt = float(ctx.dt_sec)
        self.drawer.fade_tick(dt)

        if self.stage == LearningStep.Stage.DONE:
            return

        self._timer -= dt
        if self._timer > 0:
            return

        if self.stage == LearningStep.Stage.TITLE:
            self._set_stage(LearningStep.Stage.PLAY_L1)
        elif self.stage == LearningStep.Stage.PLAY_L1:
            self._set_stage(LearningStep.Stage.WAIT_AFTER_L1)
        elif self.stage == LearningStep.Stage.WAIT_AFTER_L1:
            self._set_stage(LearningStep.Stage.PLAY_L2)
        elif self.stage == LearningStep.Stage.PLAY_L2:
            self._set_stage(LearningStep.Stage.WAIT_AFTER_L2)
        elif self.stage == LearningStep.Stage.WAIT_AFTER_L2:
            self._set_stage(LearningStep.Stage.DONE)

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        self.drawer.draw_item_sentence(
            screen,
            item,
            ctx=ctx,
            channel=self._sentence_channel,
            style=self._style,
        )
        self.drawer.draw_item_title(
            screen,
            self._title_text,
            ctx=ctx,
            channel=self._title_channel,
            style=self._style,
        )
