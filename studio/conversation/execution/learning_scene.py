"""학습 장면(Scene): 비디오 + 중앙 문장 블록."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import Enum, auto
from pathlib import Path
from typing import Any

import pygame

from utils.fonts import load_font_chinese, load_font_korean

from ..core.scene_transition import SceneTransitionMode
from ..core.types import ConversationItemLike, FrameContext, SentenceStyleConfig
from ..core.conversation_step_fsm import FSMConversationStep, StageConfig
from ..tools.mode_icons import blit_mode_icon_bottom_left, load_mode_icon
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
        title_text: str = "문장 이해하기",
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
        self._tip_box_surface = self._load_tip_box_surface()
        self._tip_font_cn = load_font_chinese(42, (0, 0, 0), weight="bold")
        self._tip_font_kr = load_font_korean(42, (0, 0, 0), weight="bold")
        self._tip_font_fallback = pygame.font.Font(None, 42)
        self._title_image_surface = self._load_title_image_surface("문장_이해하기.png")
        if self._title_image_surface is None:
            raise RuntimeError("타이틀 이미지 파일을 찾을 수 없습니다: 문장_이해하기.png")
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
            self.Stage.PLAY_L1: "sound_lv",
            self.Stage.PLAY_L2: "sound_lv",
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

    def set_stage(self, stage: Any) -> None:
        """내부 FSM 단계 전환 시 stdout 로그(녹화 시 장면 전환 로그만 있으면 ‘멈춤’으로 오인되기 쉬움)."""
        super().set_stage(stage)
        try:
            sn = getattr(stage, "name", str(stage))
            t = float(self.timer)
            ts = "inf" if t > 1e100 else f"{t:.3f}"
            print(f"[learning][stage] {sn} | timer={ts}s", flush=True)
        except Exception:
            pass

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
                from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
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

        self._draw_title(screen, ctx=ctx)
        self._draw_play_listen_overlay(screen, ctx=ctx, item=item)

    def _load_listen_icon_surface(self) -> pygame.Surface | None:
        """학습 듣기 단계에서 사용할 listen 아이콘을 로드한다."""
        root = Path(__file__).resolve().parents[3]
        return load_mode_icon(root, "listen.png")

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
        alpha = int(max(0, min(255, self.drawer.fade_alpha(self.title_channel))))
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
        scale = min(float(max_w) / float(sw), float(max_h) / float(sh), 1.0)
        tw = max(1, int(round(sw * scale)))
        th = max(1, int(round(sh * scale)))
        draw = pygame.transform.smoothscale(surf, (tw, th)) if (tw != sw or th != sh) else surf.copy()
        if alpha < 255:
            draw.set_alpha(alpha)
        x = max(self.style.layout.min_margin_x, margin_left)
        y = max(0, margin_top)
        screen.blit(draw, (x, y))

    def _draw_play_listen_overlay(
        self,
        screen: pygame.Surface,
        *,
        ctx: FrameContext,
        item: ConversationItemLike,
    ) -> None:
        """PLAY_L1/PLAY_L2 및 직후 대기(WAIT_AFTER_*)에서 재생바·listen 아이콘을 동일하게 유지한다."""
        play = (self.Stage.PLAY_L1, self.Stage.PLAY_L2)
        wait_after = (self.Stage.WAIT_AFTER_L1, self.Stage.WAIT_AFTER_L2)
        if self.stage not in play + wait_after:
            return
        total_sec = max(0.0, float(self._current_play_total_sec))
        if total_sec <= 1e-6:
            return
        if self.stage in play:
            remaining_sec = max(0.0, float(self.timer))
            current_sec = min(total_sec, max(0.0, total_sec - remaining_sec))
        else:
            current_sec = total_sec
        self._playback_bar.draw(
            screen,
            frame_width=ctx.width,
            frame_height=ctx.height,
            current_sec=current_sec,
            total_sec=total_sec,
            show_time_text=False,
            progress_color=LISTEN_BAR_COLOR,
        )
        tip_text = str(item.get("tip") or "").strip() if isinstance(item, dict) else ""
        self._draw_tip_box_above_gauge(
            screen,
            ctx=ctx,
            tip_text=tip_text or "문장을 듣고 이해해보세요",
        )
        blit_mode_icon_bottom_left(screen, self._listen_icon_surface, frame_height=ctx.height)

    def _draw_tip_box_above_gauge(self, screen: pygame.Surface, *, ctx: FrameContext, tip_text: str) -> None:
        box = self._tip_box_surface
        if box is None:
            return
        bar_rect = self._playback_bar.get_bar_rect(frame_width=ctx.width, frame_height=ctx.height)
        sw, sh = int(box.get_width()), int(box.get_height())
        if sw <= 0 or sh <= 0:
            return
        scale_x = 0.55
        scale_y = 0.3
        tw = max(1, int(round(sw * scale_x)))
        th = max(1, int(round(sh * scale_y)))
        draw = pygame.transform.smoothscale(box, (tw, th)) if (tw != sw or th != sh) else box
        draw = draw.copy()
        draw.set_alpha(178)
        x = int(bar_rect.centerx - (tw // 2))
        y = int(bar_rect.top - th - 12)
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
        line_gap = 6
        total_h = sum(s.get_height() for s in rendered) + line_gap * (len(rendered) - 1)
        cur_y = int(y + (th - total_h) * 0.5)
        for surf in rendered:
            tx = int(x + (tw - surf.get_width()) * 0.5)
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
