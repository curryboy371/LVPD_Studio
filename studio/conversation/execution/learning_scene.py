"""학습 장면(Scene): 비디오 + 중앙 문장 블록."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import Enum, auto
from pathlib import Path
from typing import Any

import pygame

from ..core.scene_transition import SceneTransitionMode
from ..core.types import ConversationItemLike, FrameContext, SentenceStyleConfig
from ..core.conversation_step_fsm import FSMConversationStep, StageConfig
from ..tools.playback_bar import PlaybackBarRenderer

LISTEN_BAR_COLOR = (46, 204, 113)


class LearningScene(FSMConversationStep):
    """학습 장면(중앙 문장). 내부 진행은 `Stage` FSM."""

    class Stage(Enum):
        TITLE = auto()
        PLAY_L1 = auto()
        WAIT_AFTER_L1 = auto()
        PLAY_L2 = auto()
        WAIT_AFTER_L2 = auto()
        DONE = auto()

    # ------------------------
    # Channel Helper
    # ------------------------
    @classmethod
    def channels_from_layers(
        cls,
        layers: Iterable[str],
        *,
        prefix: str,
    ) -> dict[str, str]:
        p = f"{str(prefix).strip().rstrip('_')}_"
        return {layer: f"{p}{layer}" for layer in layers}

    # ------------------------
    # Init
    # ------------------------
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
        layer_channel_prefix: str = "learning",
        stage_audio_keys: dict["LearningScene.Stage", str] | None = None,
        wait_for_sound_end: bool = False,
    ) -> None:
        super().__init__()

        # 컴포넌트
        self.drawer = drawer
        self.video_player = video_player
        self.play_voice = play_voice
        self.wait_for_sound_end = bool(wait_for_sound_end)

        # UI
        self.style = style
        self.hold_sec = float(hold_sec)
        self.title_text = title_text
        self.title_fade_in_sec = float(title_fade_in_sec)
        self._playback_bar = PlaybackBarRenderer()
        self._listen_icon_surface = self._load_listen_icon_surface()
        self._current_play_total_sec = 0.0

        # SceneKind 간 전환 연출(내부 Stage FSM 전환과 무관)
        self.scene_transition_mode = SceneTransitionMode.CUT
        self.scene_transition_duration_sec = 0.4
        self.scene_transition_overlay_peak_alpha = 220

        # 채널
        ch = self.channels_from_layers(["title", "sentence"], prefix=layer_channel_prefix)
        self.title_channel = ch["title"]
        self.sentence_channel = ch["sentence"]

        # 오디오
        self.stage_audio_keys = {
            self.Stage.PLAY_L1: "sound_l1",
            self.Stage.PLAY_L2: "sound_l2",
            **(stage_audio_keys or {}),
        }

        # 상태
        self.current_item: ConversationItemLike = {}
        self.active_item_key: Any | None = None

        S = self.Stage

        # ------------------------
        # FSM 정의
        # ------------------------
        self.stage_table = {
            S.TITLE: StageConfig(
                on_enter=self._enter_title,
                next_stage=S.PLAY_L1,
            ),
            S.PLAY_L1: StageConfig(
                on_enter=lambda s=S.PLAY_L1: self._enter_play(s),
                next_stage=S.WAIT_AFTER_L1,
            ),
            S.WAIT_AFTER_L1: StageConfig(
                on_enter=self._enter_wait,
                next_stage=S.PLAY_L2,
            ),
            S.PLAY_L2: StageConfig(
                on_enter=lambda s=S.PLAY_L2: self._enter_play(s),
                next_stage=S.WAIT_AFTER_L2,
            ),
            S.WAIT_AFTER_L2: StageConfig(
                on_enter=self._enter_wait,
                next_stage=S.DONE,
            ),
            S.DONE: StageConfig(
                on_enter=self._enter_done,
            ),
        }

        self.set_stage(S.TITLE)

    def reset(self, *, clear_background: bool = False) -> None:
        """장면 슬롯 재진입(숫자 키 전환 등) 시 내부 FSM이 DONE 등에 남아 UI가 깜빡이지 않도록 동기 키를 비운다.

        `sync_item`이 호출하는 `reset()`은 clear_background=False이므로 active_item_key는 유지된다.
        """
        super().reset(clear_background=clear_background)
        if clear_background:
            self.active_item_key = None

    # ------------------------
    # Condition
    # ------------------------
    def _audio_done_condition(self) -> bool:
        """오디오 종료 조건."""
        # PLAY_L1/PLAY_L2는 설정과 무관하게 오디오 길이(timer)만큼 항상 대기한다.
        return self.timer <= 0

    # ------------------------
    # Enter Logic
    # ------------------------
    def _enter_title(self) -> float:
        self.drawer.hide_now(self.sentence_channel)
        self.drawer.fade_on(self.title_channel, self.title_fade_in_sec)
        return self.title_fade_in_sec

    def _enter_play(self, stage: "LearningScene.Stage") -> float:
        self.drawer.show_now(self.title_channel)
        self.drawer.show_now(self.sentence_channel)

        path = str(self.current_item.get(self.stage_audio_keys[stage]) or "")
        if path and self.play_voice:
            try:
                self.play_voice(path, item=self.current_item)
            except Exception:
                pass

        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            sound_len = float(pygame.mixer.Sound(path).get_length())
            self._current_play_total_sec = max(0.0, sound_len)
            return sound_len
        except Exception:
            self._current_play_total_sec = 0.0
            return 0.0

    def _enter_wait(self) -> float:
        return self.hold_sec

    def _enter_done(self) -> float:
        self.complete()
        self.allow_transition()
        return float("inf")

    # ------------------------
    # Item Sync
    # ------------------------
    def _item_key(self, item: ConversationItemLike):
        """PracticeScene._playback_item_key와 동일 규칙으로 topic·id·index·구간을 맞춘다."""
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
        st = float(item.get("start_time", 0.0) or 0.0)
        et = float(item.get("end_time", -1.0) or -1.0)
        return (topic_key, id_key, idx_key, st, et)

    def sync_item(self, item):
        key = self._item_key(item)
        if key == self.active_item_key:
            return False
        self.active_item_key = key
        self.reset()
        self.set_stage(self.Stage.TITLE)
        return True

    # ------------------------
    # Update
    # ------------------------
    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        self.current_item = item

        dt = float(ctx.dt_sec)
        self.drawer.fade_tick(dt)

        if self.sync_item(item):
            return

        if self.is_done:
            return

        super().on_update(ctx, item=item)

    # ------------------------
    # Render
    # ------------------------
    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame:
            screen.blit(frame, (0, 0))

        self.drawer.draw_item_sentence(
            screen,
            item,
            ctx=ctx,
            channel=self.sentence_channel,
            style=self.style,
            title_clearance=(self.title_text, 0.12, 12),
        )

        self.drawer.draw_item_title(
            screen,
            self.title_text,
            ctx=ctx,
            channel=self.title_channel,
            style=self.style,
        )
        self._draw_play_listen_overlay(screen, ctx=ctx)

    def _load_listen_icon_surface(self) -> pygame.Surface | None:
        """학습 듣기 단계에서 사용할 listen 아이콘을 로드한다."""
        root = Path(__file__).resolve().parents[3]
        candidates = (
            root / "resource" / "image" / "icon" / "listen.png",
            root / "resource" / "images" / "icon" / "listen.png",
        )
        for path in candidates:
            if not path.exists():
                continue
            try:
                surface = pygame.image.load(str(path))
                return pygame.transform.smoothscale(surface, (318, 318))
            except Exception:
                continue
        return None

    def _draw_play_listen_overlay(self, screen: pygame.Surface, *, ctx: FrameContext) -> None:
        """PLAY_L1/PLAY_L2 단계에서 재생바와 listen 아이콘을 출력한다."""
        if self.stage not in (self.Stage.PLAY_L1, self.Stage.PLAY_L2):
            return
        total_sec = max(0.0, float(self._current_play_total_sec))
        if total_sec <= 1e-6:
            return
        remaining_sec = max(0.0, float(self.timer))
        current_sec = min(total_sec, max(0.0, total_sec - remaining_sec))
        self._playback_bar.draw(
            screen,
            frame_width=ctx.width,
            frame_height=ctx.height,
            current_sec=current_sec,
            total_sec=total_sec,
            show_time_text=False,
            progress_color=LISTEN_BAR_COLOR,
        )
        if self._listen_icon_surface is None:
            return
        margin_left = 24
        margin_bottom = 20
        x = margin_left
        y = int(ctx.height) - int(self._listen_icon_surface.get_height()) - margin_bottom
        screen.blit(self._listen_icon_surface, (x, y))
