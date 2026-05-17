"""숏츠 스튜디오: 9:16 세로 레이아웃 + 노래방 학습 구역."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import pygame

from core.interfaces import IStudio
from studio.conversation.core.types import FrameContext, SentenceStyleConfig
from studio.conversation.core.types import ColorStyle, LayoutStyle, TextStyle
from studio.shorts.data_loading import build_shorts_clip_list
from studio.shorts.execution.clip_scene import ClipScene
from studio.shorts.tools.fonts import (
    DEFAULT_SHORTS_RENDER_SETTINGS,
    resolve_shorts_render_settings,
)
from studio.shorts.tools.shorts_drawer import ShortsDrawer

logger = logging.getLogger(__name__)

_VOICE_CHANNEL_INDEX = 2


class ShortsStudio(IStudio):
    """숏츠 클립 순차 재생."""

    def __init__(
        self,
        *,
        shorts_mode: str = "conversation",
        session_topics: Optional[list[str]] = None,
        clips_csv_path: str = "",
        **_: Any,
    ) -> None:
        from studio.shorts.clip_types import CLIP_TYPE_VOCABULARY, normalize_clip_type

        self._shorts_mode = normalize_clip_type(shorts_mode)
        self._session_topics = session_topics
        self._clips_csv_path = clips_csv_path or ""
        self._clips: list[dict[str, Any]] = []
        self._clip_index = 0
        self._drawer: Optional[ShortsDrawer] = None
        self._scene: Optional[ClipScene] = None
        self._last_config: Any = None
        self._recording_done = False
        csv_name = (
            "shorts_vocabulary_clips.csv"
            if self._shorts_mode == CLIP_TYPE_VOCABULARY
            else "shorts_conversation_clips.csv"
        )
        self._empty_message = f"{csv_name}에 유효한 클립이 없습니다."

    def init(self, config: Any = None) -> None:
        if self._drawer is not None:
            return
        self._last_config = config
        self._clips = build_shorts_clip_list(
            shorts_mode=self._shorts_mode,
            csv_path=self._clips_csv_path or None,
            session_topics=self._session_topics,
        )
        if not self._clips:
            logger.warning("%s", self._empty_message)

        settings = resolve_shorts_render_settings(config)
        if config is not None:
            config.shorts_render = settings

        self._drawer = ShortsDrawer(font_sizes=settings.font_sizes)
        style = SentenceStyleConfig(
            colors=ColorStyle(
                hanzi_color=(255, 255, 255),
                pinyin_color=(200, 205, 215),
                translation_color=(180, 190, 210),
            ),
            layout=LayoutStyle(line_gap_px=72, translation_extra_gap_px=12, min_margin_x=24),
            text=TextStyle(max_hanzi=40, max_pinyin=120, max_translation=80),
        )
        self._scene = ClipScene(
            drawer=self._drawer,
            style=style,
            play_voice=self._make_play_voice(),
        )
        self._scene.set_on_clip_done(self._on_clip_done)
        if self._clips:
            self._start_current_clip()

    def get_title(self) -> str:
        return "LVPD Studio - 숏츠"

    def handle_events(self, events: list, config: Any = None) -> bool:
        self._last_config = config
        for e in events:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE and self._clips:
                self._advance_clip()
        return True

    def update(self, config: Any = None) -> None:
        self._last_config = config
        if not self._scene or not self._clips:
            return
        self._scene.update(self._dt_sec(config))

    def draw(self, screen: Any, config: Any) -> None:
        self._last_config = config
        if self._drawer is None:
            return
        ctx = FrameContext(
            width=int(getattr(config, "width", 1080) or 1080),
            height=int(getattr(config, "height", 1920) or 1920),
            dt_sec=self._dt_sec(config),
        )
        self._drawer.draw_background(screen, ctx)
        if not self._clips or self._scene is None:
            self._draw_empty(screen, ctx)
            return
        self._scene.draw(screen, ctx)

    def get_recording_prefix(self) -> Optional[str]:
        return "SHORTS_REC"

    def should_stop_recording(self) -> bool:
        return bool(self._recording_done)

    def _dt_sec(self, config: Any) -> float:
        dt = 1.0 / 30.0
        if config is not None and getattr(config, "dt_sec", None) is not None:
            dt = float(config.dt_sec)
        if dt <= 1e-12:
            fps = float(getattr(config, "fps", 30) or 30) if config is not None else 30.0
            dt = 1.0 / max(1.0, fps)
        return dt

    def _make_play_voice(self) -> Callable[[str], float]:
        def _play(path: str) -> float:
            if not path:
                return 0.0
            try:
                if pygame.mixer.get_init() is None:
                    from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                    pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
            except Exception:
                return 0.0
            try:
                snd = pygame.mixer.Sound(path)
            except Exception as ex:
                logger.debug("숏츠 음성 로드 실패: %s (%s)", path, ex)
                return 0.0
            dur = float(snd.get_length() or 0.0)
            try:
                ch = pygame.mixer.Channel(_VOICE_CHANNEL_INDEX)
                ch.play(snd)
                if self._scene:
                    self._scene.set_voice_channel(ch)
            except Exception:
                try:
                    snd.play()
                except Exception:
                    return 0.0
            self._record_insert_sound(path, snd=snd, duration_sec=dur)
            return dur

        return _play

    def _record_insert_sound(self, path: str, *, snd: Any, duration_sec: float) -> None:
        cfg = self._last_config
        log = getattr(cfg, "recording_log_event", None) if cfg is not None else None
        if log is None:
            return
        try:
            from studio.recording_events import InsertSound, recording_log_event

            timeline_sec = float(getattr(cfg, "recording_time_sec", 0.0) or 0.0)
            recording_log_event(
                log,
                InsertSound(timeline_sec=timeline_sec, path=path, duration_sec=float(duration_sec)),
            )
        except Exception:
            pass

    def _start_current_clip(self) -> None:
        if not self._scene or not self._clips:
            return
        idx = min(self._clip_index, len(self._clips) - 1)
        is_last = idx >= len(self._clips) - 1
        self._scene.start_clip(self._clips[idx], is_last=is_last)

    def _on_clip_done(self) -> None:
        if self._clip_index >= len(self._clips) - 1:
            self._recording_done = True
            return
        self._clip_index += 1
        self._start_current_clip()

    def _advance_clip(self) -> None:
        if self._scene and not self._scene.is_done:
            self._scene.begin_transition_out()

    def _draw_empty(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        from utils.fonts import load_font_korean

        font = load_font_korean(32, (200, 200, 210)) or pygame.font.Font(None, 36)
        surf = font.render(self._empty_message, True, (200, 200, 210))
        screen.blit(surf, (ctx.width // 2 - surf.get_width() // 2, ctx.height // 2 - 18))
