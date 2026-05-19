"""숏츠 스튜디오: 9:16 세로 레이아웃 + 노래방 학습 구역."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import pygame

from core.interfaces import IStudio
from studio.conversation.core.types import FrameContext, SentenceStyleConfig
from studio.conversation.core.types import ColorStyle, LayoutStyle, TextStyle
from studio.shorts.clip_types import CLIP_TYPE_VOCABULARY
from studio.shorts.data_loading import (
    build_shorts_clip_list,
    extract_vocab_topic_intro,
    topic_intro_configured,
)
from studio.shorts.execution.clip_scene import ClipScene
from studio.shorts.tools.fonts import (
    DEFAULT_SHORTS_RENDER_SETTINGS,
    resolve_shorts_render_settings,
)
from studio.shorts.bg_audio import ShortsBackgroundPlayer
from studio.shorts.constants import SHORTS_RECORD_END_HOLD_SEC
from studio.shorts.follow_along_tts import ensure_follow_along_mp3
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
        self._topic_intro_done = False
        self._bg_player: Optional[ShortsBackgroundPlayer] = None
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
        self._bg_player = ShortsBackgroundPlayer(
            on_bg_started=self._on_learn_bg_started,
            is_recording=self._is_recording_mode,
        )
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
            start_learn_background=self._start_learn_background,
            stop_learn_background=self._stop_learn_background,
            follow_along_mp3=self._follow_along_mp3_path,
        )
        self._scene.set_on_clip_done(self._on_clip_done)
        self._scene.set_on_topic_intro_done(self._on_topic_intro_done)
        self._scene.set_record_end_hold(0.0)
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
        try:
            if not self._clips or self._scene is None:
                self._draw_empty(screen, ctx)
            else:
                self._scene.draw(screen, ctx)
        finally:
            from studio.shorts.brand_icon import draw_brand_icon

            draw_brand_icon(screen)

    def get_recording_prefix(self) -> Optional[str]:
        return "SHORTS_REC"

    def should_stop_recording(self) -> bool:
        return bool(self._recording_done)

    def begin_recording_session(self, config: Any) -> None:
        """녹화 루프 직전: init 시점에 쌓인 재생 상태를 버리고 클립 0부터 다시 시작."""
        self._last_config = config
        self._recording_done = False
        self._topic_intro_done = False
        self._stop_learn_audio()
        if self._scene is not None:
            self._scene.set_record_end_hold(SHORTS_RECORD_END_HOLD_SEC)
        if self._scene is not None and self._clips:
            self._clip_index = 0
            self._start_current_clip()

    def _dt_sec(self, config: Any) -> float:
        dt = 1.0 / 30.0
        if config is not None and getattr(config, "dt_sec", None) is not None:
            dt = float(config.dt_sec)
        if dt <= 1e-12:
            fps = float(getattr(config, "fps", 30) or 30) if config is not None else 30.0
            dt = 1.0 / max(1.0, fps)
        return dt

    def _is_recording_mode(self) -> bool:
        cfg = self._last_config
        return getattr(cfg, "recording_log_event", None) is not None

    def _on_learn_bg_started(self, path: str, duration_sec: float) -> None:
        self._record_insert_sound(path, duration_sec=max(1.0, float(duration_sec)))

    def _start_learn_background(self, duration_hint_sec: float) -> None:
        if self._bg_player is not None:
            self._bg_player.start_loop(duration_hint_sec=float(duration_hint_sec))

    def _stop_learn_background(self) -> None:
        if self._bg_player is not None:
            self._bg_player.stop()

    def _follow_along_mp3_path(self) -> str:
        return str(ensure_follow_along_mp3())

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

    def _record_insert_sound(
        self,
        path: str,
        *,
        snd: Any = None,
        duration_sec: float = 0.0,
    ) -> None:
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
        if self._should_play_vocab_topic_intro():
            self._topic_intro_done = True
            intro = extract_vocab_topic_intro(self._clips)
            if intro is not None:
                self._scene.start_topic_intro(intro)
                return
        idx = min(self._clip_index, len(self._clips) - 1)
        is_last = idx >= len(self._clips) - 1
        self._scene.start_clip(self._clips[idx], is_last=is_last)

    def _should_play_vocab_topic_intro(self) -> bool:
        if self._shorts_mode != CLIP_TYPE_VOCABULARY or self._topic_intro_done:
            return False
        return topic_intro_configured(extract_vocab_topic_intro(self._clips))

    def _on_topic_intro_done(self) -> None:
        self._start_current_clip()

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
