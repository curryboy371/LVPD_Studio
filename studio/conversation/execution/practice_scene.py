"""연습 장면(Scene): 비디오 + 문장 + 현재 단어(최소)."""

from __future__ import annotations

from dataclasses import replace
from enum import Enum, auto
from pathlib import Path
import logging
import os
import math
import random
from typing import Callable, Literal, Optional

import pygame

from core.paths import get_repo_root
from data.table_manager import get_word
from utils.fonts import load_font_chinese, load_font_korean

from ..core.scene_transition import SceneTransitionMode
from ..core.types import (
    ConversationItemLike,
    FrameContext,
    SentenceStyleConfig,
    build_sentence_render_data_with_tone_icons,
)
from ..core.conversation_step import IConversationStep
from ..tools.mode_icons import blit_mode_icon_bottom_left, load_mode_icon
from ..tools.playback_bar import PlaybackBarRenderer
from utils.pinyin_processor import get_pinyin_processor

logger = logging.getLogger(__name__)

# sub 한 변형당 자동 대기 상한(초). 음성 길이×배율+간격이 과하면 녹화가 수십 분 멈춘 것처럼 보임.
_SUB_VARIANT_WAIT_WARN_SEC = 90.0
_SUB_VARIANT_WAIT_MAX_SEC = 180.0


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
        SHOW_CONTENT = auto()
        SHOW_SUB_CONTENT = auto()

    _SPEAK_SOUND_LEN_SCALE = 1.3
    _BG_SOUND_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}

    def __init__(
        self,
        *,
        drawer,
        video_player,
        style: SentenceStyleConfig,
        play_voice: Callable[..., None] | None = None,
        on_bg_sound_started: Callable[[str, float], None] | None = None,
        title_text: str = "듣고 따라해보기",
        title_fade_in_sec: float = 1.0,
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
        self.on_bg_sound_started = on_bg_sound_started
        self.scene_transition_mode: SceneTransitionMode = SceneTransitionMode.CUT
        self.scene_transition_duration_sec: float = 0.4
        self.scene_transition_overlay_peak_alpha: int = 220
        self._style = style
        self.title_text = str(title_text or "듣고 따라해보기")
        self.title_fade_in_sec = float(title_fade_in_sec)
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
        self._active_item_key = None
        self._title_wait_remaining_sec = 0.0
        self._content_wait_remaining_sec = 0.0
        # SHOW_SUB_CONTENT 단계에서 sub 문장 간 자동 전환 대기 시간(초).
        self._sub_content_hold_sec = 3.0
        # 듣기 게이지 완료 후 말하기 게이지 시작 전 대기(초).
        self._listen_to_speak_gap_sec = 2.0
        # 말하기(주황) 게이지 완료 후 다음 sub/전환 전 대기(초).
        self._speak_complete_hold_sec = 1.5
        self._sub_content_wait_remaining_sec = 0.0
        self._sub_content_wait_total_sec = 0.0
        self._sub_content_sound_sec = 0.0
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
        self._bg_sounds = self._load_background_sounds()
        self._bg_last_sound_index: int | None = None
        self._bg_channel_index = 5
        self._bg_channel: pygame.mixer.Channel | None = None
        self._bg_fade_ms = 1000
        self._bg_volume = 0.2
        self._bg_playing = False
        # LearningScene과 동일하게 디버그에서 읽을 수 있도록 stage 필드를 유지한다.
        self.stage: "PracticeScene.Stage" = self.Stage.TITLE
        self._practice_stage_log_last: "PracticeScene.Stage | None" = None
        self.drawer.hide_now(self._title_channel)
        self.drawer.hide_now(self._sentence_channel)

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
            self._base_to_sub_transition = None
            self._base_to_sub_elapsed = 0.0
            self._stop_background_sound()
            self.drawer.hide_now(self._title_channel)
            self.drawer.hide_now(self._sentence_channel)
            self._practice_stage_log_last = None

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """항목만 바뀌고 슬롯 리셋이 빠진 경우에도 이전 base의 sub가 남지 않게 한다."""
        key = self._playback_item_key(item)
        if self.is_done and self._active_item_key is not None and key != self._active_item_key:
            self.is_done = False
            self.transition_signal = False
        if self.is_done:
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
        """기본→첫 sub 전환 시 문장 블록 세로 오프셋(위 슬라이드 아웃 / 아래에서 슬라이드 인)."""
        if self.stage == self.Stage.SHOW_CONTENT and self._base_to_sub_transition == "out":
            t = min(1.0, self._base_to_sub_elapsed / self.base_to_sub_slide_out_sec)
            return int(round(-self.base_to_sub_slide_out_px * t))
        if self.stage == self.Stage.SHOW_SUB_CONTENT and self._base_to_sub_transition == "in":
            t = min(1.0, self._base_to_sub_elapsed / self.base_to_sub_slide_in_sec)
            return int(round(self.base_to_sub_slide_in_offset_px * (1.0 - t)))
        return 0

    @staticmethod
    def _playback_item_key(item: ConversationItemLike) -> tuple:
        """아이템 전환 판별용 키. topic·id·index·구간으로 구분한다(동일 id 다른 topic 등)."""
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

    def on_update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """아이템이 바뀌면 제목을 먼저 fade in 하고, 끝난 뒤 문장/단어를 노출한다."""
        # Drawer 내부 알파 애니메이션 타이머를 매 프레임 진행한다.
        dt = float(ctx.dt_sec)
        self.drawer.fade_tick(dt)

        key = self._playback_item_key(item)
        if key != self._active_item_key:
            self._active_item_key = key
            self._practice_stage_log_last = None
            # 새 아이템 진입 시에는 본문을 숨기고 제목 페이드부터 진행한다.
            self._content_visible = False
            self._title_wait_remaining_sec = self.title_fade_in_sec
            # 기본 문장 노출 후 sub 문장으로 전환할 타이머를 초기화한다.
            self._content_wait_remaining_sec = self.content_hold_sec
            self._sub_variants = self._pick_sub_variants(item)
            self._sub_variant_index = 0
            self._current_sub_variant = self._sub_variants[0] if self._sub_variants else None
            self._sub_content_wait_remaining_sec = self._sub_content_hold_sec
            self._sub_content_wait_total_sec = self._sub_content_hold_sec
            self._sub_content_sound_sec = 0.0
            self._base_to_sub_transition = None
            self._base_to_sub_elapsed = 0.0
            self.drawer.hide_now(self._sentence_channel)
            self.drawer.fade_on(self._title_channel, self.title_fade_in_sec)
            self._set_stage(self.Stage.TITLE)
            return

        # Stage 기반으로 제목 페이드 완료 시점을 관리한다.
        if self.stage == self.Stage.TITLE:
            self._stop_background_sound()
            if self._title_wait_remaining_sec > 0.0:
                self._title_wait_remaining_sec = max(0.0, self._title_wait_remaining_sec - dt)
            if self._title_wait_remaining_sec <= 0.0:
                self._content_visible = True
                self.drawer.show_now(self._sentence_channel)
                self._set_stage(self.Stage.SHOW_CONTENT)
            return

        # 기본 문장을 잠시 보여준 뒤, sub_sentences.csv 기반 변형이 있으면 다음 Stage로 넘긴다.
        if self.stage == self.Stage.SHOW_CONTENT:
            self._stop_background_sound()
            if self._base_to_sub_transition == "out":
                self._base_to_sub_elapsed += dt
                if self._base_to_sub_elapsed >= self.base_to_sub_slide_out_sec:
                    self._base_to_sub_transition = "in"
                    self._base_to_sub_elapsed = 0.0
                    self._set_stage(self.Stage.SHOW_SUB_CONTENT)
                    self.drawer.fade_on(self._sentence_channel, self.base_to_sub_slide_in_sec)
                return
            if self._content_wait_remaining_sec > 0.0:
                self._content_wait_remaining_sec = max(0.0, self._content_wait_remaining_sec - dt)
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

        # SHOW_SUB_CONTENT 타이머는 sub 개수와 무관하게 항상 흐르게 유지한다.
        if self.stage == self.Stage.SHOW_SUB_CONTENT:
            if self._base_to_sub_transition == "in":
                self._base_to_sub_elapsed += dt
                # 슬라이드·Drawer 페이드 인이 끝난 뒤에만 듣기/게이지 타이머를 시작한다.
                slide_done = self._base_to_sub_elapsed >= self.base_to_sub_slide_in_sec
                alpha = int(self.drawer.fade_alpha(self._sentence_channel))
                # int 보간으로 알파가 249 근처에서 멈추면 fade_alpha>=250이 영원히 False가 될 수 있음 → 완화 + 타임아웃
                fade_done = alpha >= 248
                fade_force = self._base_to_sub_elapsed >= self.base_to_sub_slide_in_sec + 1.0
                if slide_done and (fade_done or fade_force):
                    if fade_force and not fade_done:
                        logger.warning(
                            "PRACTICE SHOW_SUB_CONTENT: Drawer 페이드 인 타임아웃(alpha=%s), 타이머 강제 시작",
                            alpha,
                        )
                    self._base_to_sub_transition = None
                    self._base_to_sub_elapsed = 0.0
                    wait_total = self._start_current_sub_variant_audio_and_get_wait()
                    wt = _clamp_sub_variant_wait(
                        float(wait_total), hold=float(self._sub_content_hold_sec)
                    )
                    self._sub_content_wait_total_sec = wt
                    self._sub_content_wait_remaining_sec = wt
                    self._log_sub_variant_wait(wt)
                return
            self._sync_background_sound_for_sub_content()
            if self._sub_content_wait_remaining_sec > 0.0:
                nr = max(0.0, float(self._sub_content_wait_remaining_sec) - dt)
                self._sub_content_wait_remaining_sec = _sanitize_wait_sec(nr, fallback=0.0)
            if self._sub_content_wait_remaining_sec <= 0.0:
                if len(self._sub_variants) > 1:
                    next_index = self._sub_variant_index + 1
                    if next_index < len(self._sub_variants):
                        self._sub_variant_index = next_index
                        self._current_sub_variant = self._sub_variants[self._sub_variant_index]
                        wait_total = self._start_current_sub_variant_audio_and_get_wait()
                        wt = _clamp_sub_variant_wait(
                            float(wait_total), hold=float(self._sub_content_hold_sec)
                        )
                        self._sub_content_wait_total_sec = wt
                        self._sub_content_wait_remaining_sec = wt
                        self._log_sub_variant_wait(wt)
                        return
                # 마지막 sub 변형까지 모두 끝나면 다음 SceneKind로 전환한다.
                try:
                    print(
                        f"[practice][sub] 변형 {len(self._sub_variants)}개 완료 → 다음 장면 전환",
                        flush=True,
                    )
                except Exception:
                    pass
                self._stop_background_sound()
                self.complete()
                self.allow_transition()
        return

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

    def _start_current_sub_variant_audio_and_get_wait(self) -> float:
        """현재 sub 변형의 alt_sound_path를 재생하고, 듣기·간격·말하기·말하기후간격을 합한 대기 시간(초)을 반환한다."""
        variant = self._current_sub_variant if isinstance(self._current_sub_variant, dict) else {}
        sound_raw = str(variant.get("alt_sound_path") or "").strip()
        if not sound_raw:
            self._sub_content_sound_sec = 0.0
            return self._sub_content_hold_sec

        sp = Path(sound_raw.replace("\\", "/"))
        if not sp.is_absolute():
            sp = get_repo_root() / sp
        sound_path = str(sp)

        if not os.path.isfile(sound_path):
            logger.warning(
                "PRACTICE: sub 사운드 파일 없음 — 기본 대기 %.1fs | %s",
                self._sub_content_hold_sec,
                sound_path,
            )
            self._sub_content_sound_sec = 0.0
            return float(self._sub_content_hold_sec)

        gap = float(self._listen_to_speak_gap_sec)
        if self.play_voice is not None:
            try:
                self.play_voice(sound_path, item=variant)
            except Exception:
                pass

        try:
            if pygame.mixer.get_init() is None:
                from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
            sound_len_sec = float(pygame.mixer.Sound(sound_path).get_length() or 0.0)
            sound_len_sec = _sanitize_wait_sec(sound_len_sec, fallback=0.0)
            if sound_len_sec > 0.0:
                self._sub_content_sound_sec = sound_len_sec
                tail = max(0.0, float(self._speak_complete_hold_sec))
                # 듣기 + 듣기후간격 + 말하기(원음 길이 * 배율) + 말하기 후 간격
                speak_sec = sound_len_sec * float(self._SPEAK_SOUND_LEN_SCALE)
                total = sound_len_sec + max(0.0, gap) + speak_sec + tail
                return _sanitize_wait_sec(total, fallback=float(self._sub_content_hold_sec))
        except Exception:
            pass
        self._sub_content_sound_sec = 0.0
        return self._sub_content_hold_sec

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """비디오 위에 LEARNING과 동일 세로 배치(중앙·타이틀 밴드 여유)의 문장과 첫 단어(있으면)를 표시한다."""
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        self._draw_title(screen, ctx=ctx)

        if not self._content_visible:
            return

        slide_y = self._sentence_slide_y_offset_px()
        render_item = item
        # sub 단계에서는 sub_sentences.csv에서 만들어진 교체 문장/번역을 우선 렌더한다.
        if self.stage == self.Stage.SHOW_SUB_CONTENT and self._current_sub_variant is not None:
            base_map = item if isinstance(item, dict) else {}
            replaced_sentence = str(self._current_sub_variant.get("replaced_sentence") or "").strip()
            pinyin_marks = ""
            pinyin_phonetic = ""
            pinyin_lexical = ""
            # sub 문장은 base 문장과 달라질 수 있어, 매번 현재 문장 기준 병음을 재생성한다.
            if replaced_sentence:
                try:
                    pinyin_processor = get_pinyin_processor()
                    if pinyin_processor.available:
                        pinyin_marks = pinyin_processor.full_convert(replaced_sentence)
                        pinyin_lexical = " ".join(pinyin_processor.get_lexical_pinyin(replaced_sentence)).strip()
                        pinyin_phonetic = " ".join(pinyin_processor.get_phonetic_pinyin(replaced_sentence)).strip()
                except Exception:
                    pass
            render_item = {
                **base_map,
                "sentence": [replaced_sentence],
                "translation": [str(self._current_sub_variant.get("alt_translation") or "").strip()],
                # sub 문장에서도 병음/발음 정보를 채워야 병음 줄과 발음 아이콘이 함께 표시된다.
                "pinyin": pinyin_marks,
                "pinyin_marks": pinyin_marks,
                "pinyin_phonetic": pinyin_phonetic,
                "pinyin_lexical": pinyin_lexical,
            }

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
            if self._base_to_sub_transition != "in":
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
        # SHOW_SUB_CONTENT에서는 한자 줄을 별도 수동 렌더링하므로,
        # drawer에는 병음/번역만 그리게 한다(겹침/잔상 방지).
        self.drawer.draw_sentence(
            screen,
            replace(data, sentence=""),
            channel=self._sentence_channel,
            center_x=int(ctx.width) // 2,
            y_base=y_base,
            style=white_style,
        )

        replaced_sentence = str(self._current_sub_variant.get("replaced_sentence") or "").strip()
        alt_word = str(self._current_sub_variant.get("alt_word") or "").strip()
        if not replaced_sentence or not alt_word:
            return

        hanzi_text = (data.sentence or "")[: white_style.text.max_hanzi]
        if not hanzi_text:
            return

        spans_raw = self._current_sub_variant.get("alt_hanzi_spans")
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
        if not spans:
            # 하위 호환: 기존 단일 span 필드를 우선 사용하고, 없으면 alt_word 문자열 검색으로 폴백한다.
            start_raw = self._current_sub_variant.get("alt_hanzi_start")
            len_raw = self._current_sub_variant.get("alt_hanzi_len")
            if isinstance(start_raw, int) and isinstance(len_raw, int) and len_raw > 0:
                idx = start_raw
                span_len = len_raw
            else:
                idx = hanzi_text.find(alt_word)
                if idx < 0:
                    return
                span_len = len(alt_word)
            if idx < 0 or idx >= len(hanzi_text):
                return
            span_len = min(span_len, len(hanzi_text) - idx)
            if span_len <= 0:
                return
            spans.append((idx, span_len))

        # 별도 폰트를 만들지 않고, _sentence_channel이 쓰는 메인 한자 폰트 체계를 그대로 사용한다.
        fonts = getattr(self.drawer, "_fonts", None)
        hanzi_ft = getattr(fonts, "hanzi_ft", None)
        hanzi_pg = getattr(fonts, "hanzi_pg", None)
        cache_hanzi = getattr(self.drawer, "_cache_hanzi", None)
        if hanzi_pg is None or cache_hanzi is None:
            return

        y_hanzi = y_base + (white_style.layout.line_gap_px if (data.pinyin or "").strip() else 0)
        center_x = int(ctx.width) // 2
        # 오버레이(흰색 전체 + 노란색 덧그리기) 대신,
        # 문장을 색 구간으로 쪼개 "한 번만" 그려서 겹침 테두리를 제거한다.
        color_flags = [False] * len(hanzi_text)
        for idx, span_len in spans:
            end_i = min(len(hanzi_text), max(idx, 0) + max(span_len, 0))
            for i in range(max(0, idx), end_i):
                color_flags[i] = True

        segments: list[tuple[str, tuple[int, int, int]]] = []
        cur_text = ""
        cur_is_yellow: bool | None = None
        for i, ch in enumerate(hanzi_text):
            is_yellow = color_flags[i]
            if cur_is_yellow is None:
                cur_is_yellow = is_yellow
                cur_text = ch
                continue
            if is_yellow == cur_is_yellow:
                cur_text += ch
                continue
            segments.append(
                (
                    cur_text,
                    self._style.colors.hanzi_color if cur_is_yellow else white_style.colors.hanzi_color,
                )
            )
            cur_text = ch
            cur_is_yellow = is_yellow
        if cur_text:
            segments.append(
                (
                    cur_text,
                    self._style.colors.hanzi_color if cur_is_yellow else white_style.colors.hanzi_color,
                )
            )

        if not segments:
            return

        seg_surfs: list[pygame.Surface] = []
        total_w = 0
        for seg_text, seg_color in segments:
            surf, _ = self.drawer._get_cached_text_pair(
                cache_hanzi,
                hanzi_ft,
                hanzi_pg,
                seg_text,
                seg_color,
            )
            seg_surfs.append(surf)
            total_w += int(surf.get_width())

        full_w = int(total_w)
        x_line = max(white_style.layout.min_margin_x, center_x - full_w // 2)

        alpha = int(max(0, min(255, self.drawer.fade_alpha(self._sentence_channel))))
        if alpha <= 0:
            return
        cur_x = x_line
        for surf in seg_surfs:
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

    def _draw_sub_content_playback_bar(
        self,
        screen: pygame.Surface,
        *,
        ctx: FrameContext,
        item: ConversationItemLike,
    ) -> None:
        """SHOW_SUB_CONTENT 단계에서만 재생바와 시간 텍스트를 렌더한다."""
        _ = item
        total_sec = max(0.0, float(self._sub_content_wait_total_sec))
        remaining_sec = max(0.0, float(self._sub_content_wait_remaining_sec))
        elapsed_sec = max(0.0, total_sec - remaining_sec)
        listen_sec = max(0.0, float(self._sub_content_sound_sec))
        gap_sec = float(self._listen_to_speak_gap_sec) if listen_sec > 1e-6 else 0.0
        gap_sec = max(0.0, gap_sec)
        after_speak_sec = float(self._speak_complete_hold_sec) if listen_sec > 1e-6 else 0.0
        after_speak_sec = max(0.0, after_speak_sec)
        speak_sec = max(0.0, total_sec - listen_sec - gap_sec - after_speak_sec)

        t_listen_end = listen_sec
        t_after_listen_gap_end = t_listen_end + gap_sec
        t_speak_end = t_after_listen_gap_end + speak_sec

        # 4구간: 듣기 채움 → 듣기 만 채움 대기 → 말하기 채움 → 주황 만 채움 대기
        if listen_sec > 1e-6 and elapsed_sec < t_listen_end:
            is_listen_phase = True
            bar_current_sec = elapsed_sec
            bar_total_sec = listen_sec
        elif listen_sec > 1e-6 and elapsed_sec < t_after_listen_gap_end:
            is_listen_phase = True
            bar_current_sec = listen_sec
            bar_total_sec = listen_sec
        elif speak_sec > 1e-6 and elapsed_sec < t_speak_end:
            is_listen_phase = False
            bar_current_sec = min(max(0.0, elapsed_sec - t_after_listen_gap_end), speak_sec)
            bar_total_sec = speak_sec
        elif speak_sec > 1e-6 and elapsed_sec < t_speak_end + after_speak_sec:
            is_listen_phase = False
            bar_current_sec = speak_sec
            bar_total_sec = speak_sec
        else:
            bar_total_sec = max(0.1, total_sec if total_sec > 1e-6 else float(self._sub_content_hold_sec))
            bar_current_sec = min(elapsed_sec, bar_total_sec)
            is_listen_phase = listen_sec <= 1e-6

        self._playback_bar.draw(
            screen,
            frame_width=ctx.width,
            frame_height=ctx.height,
            current_sec=bar_current_sec,
            total_sec=bar_total_sec,
            show_time_text=False,
            progress_color=self._resolve_playback_bar_color(is_listen_phase=is_listen_phase),
        )
        self._draw_tip_box_above_gauge(
            screen,
            ctx=ctx,
            tip_text=self._build_current_sub_tip_text(),
        )
        self._draw_mode_icon(screen, ctx=ctx, is_listen_phase=is_listen_phase)

    def _build_current_sub_tip_text(self) -> str:
        """현재 sub 변형의 alt_word_id(들)로 tip box용 '한자 : 뜻' 여러 줄 텍스트를 만든다."""
        variant = self._current_sub_variant if isinstance(self._current_sub_variant, dict) else {}
        alt_word_ids_raw = variant.get("alt_word_ids")
        alt_words_raw = variant.get("alt_words")
        alt_word_ids: list[int] = []
        alt_words: list[str] = []

        if isinstance(alt_word_ids_raw, list) and alt_word_ids_raw:
            for raw in alt_word_ids_raw:
                try:
                    wid = int(raw)
                except (TypeError, ValueError):
                    continue
                if wid > 0:
                    alt_word_ids.append(wid)
        else:
            try:
                single_id = int(variant.get("alt_word_id") or 0)
            except (TypeError, ValueError):
                single_id = 0
            if single_id > 0:
                alt_word_ids.append(single_id)

        if isinstance(alt_words_raw, list) and alt_words_raw:
            alt_words = [str(w or "").strip() for w in alt_words_raw]
        else:
            alt_words = [str(variant.get("alt_word") or "").strip()]

        rows: list[str] = []
        for i, wid in enumerate(alt_word_ids):
            word_obj = get_word(wid)
            hanzi = ""
            if i < len(alt_words):
                hanzi = str(alt_words[i] or "").strip()
            if not hanzi and word_obj is not None:
                hanzi = str(word_obj.word or "").strip()
            meaning = str(word_obj.meaning or "").strip() if word_obj is not None else ""
            if not hanzi and not meaning:
                continue
            if not hanzi:
                rows.append(meaning)
            elif not meaning:
                rows.append(hanzi)
            else:
                rows.append(f"{hanzi} : {meaning}")

        if not rows:
            fallback = str(variant.get("alt_translation") or "").strip()
            return fallback
        return "\n".join(rows)

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

    def _draw_tip_box_above_gauge(self, screen: pygame.Surface, *, ctx: FrameContext, tip_text: str) -> None:
        box = self._tip_box_surface
        if box is None:
            return
        bar_rect = self._playback_bar.get_bar_rect(frame_width=ctx.width, frame_height=ctx.height)
        sw, sh = int(box.get_width()), int(box.get_height())
        if sw <= 0 or sh <= 0:
            return
        scale_x = 0.3
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
        padding_left = 28
        padding_top = 16
        cur_y = int(y + padding_top)
        for surf in rendered:
            tx = int(x + padding_left)
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


    def _load_background_sounds(self) -> list[tuple[str, pygame.mixer.Sound]]:
        """회화 모드용 배경 사운드 묶음(bg)을 미리 로드한다."""
        root = Path(__file__).resolve().parents[3]
        bg_dir = root / "resource" / "sound" / "background"
        if not bg_dir.exists() or not bg_dir.is_dir():
            return []
        sounds: list[tuple[str, pygame.mixer.Sound]] = []
        for path in sorted(bg_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in self._BG_SOUND_EXTS:
                continue
            try:
                if pygame.mixer.get_init() is None:
                    from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                    pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
                sounds.append((str(path), pygame.mixer.Sound(str(path))))
            except Exception:
                continue
        return sounds

    def _sync_background_sound_for_sub_content(self) -> None:
        """말하기(주황) + 말하기 완료 후 대기 구간까지 bg를 유지 재생한다."""
        if not self._is_bg_active_phase():
            self._stop_background_sound()
            return
        if self._bg_playing:
            return
        self._play_random_background_sound()

    def _is_bg_active_phase(self) -> bool:
        total_sec = max(0.0, float(self._sub_content_wait_total_sec))
        if total_sec <= 1e-6:
            return False
        remaining_sec = max(0.0, float(self._sub_content_wait_remaining_sec))
        elapsed_sec = max(0.0, total_sec - remaining_sec)
        listen_sec = max(0.0, float(self._sub_content_sound_sec))
        if listen_sec <= 1e-6:
            return False
        gap_sec = max(0.0, float(self._listen_to_speak_gap_sec))
        after_speak_sec = max(0.0, float(self._speak_complete_hold_sec))
        speak_sec = max(0.0, total_sec - listen_sec - gap_sec - after_speak_sec)
        if speak_sec <= 1e-6:
            return False
        t_speak_start = listen_sec + gap_sec
        t_bg_end = t_speak_start + speak_sec + after_speak_sec
        return t_speak_start <= elapsed_sec < t_bg_end

    def _bg_active_remaining_sec(self) -> float:
        total_sec = max(0.0, float(self._sub_content_wait_total_sec))
        if total_sec <= 1e-6:
            return 0.0
        remaining_sec = max(0.0, float(self._sub_content_wait_remaining_sec))
        elapsed_sec = max(0.0, total_sec - remaining_sec)
        listen_sec = max(0.0, float(self._sub_content_sound_sec))
        if listen_sec <= 1e-6:
            return 0.0
        gap_sec = max(0.0, float(self._listen_to_speak_gap_sec))
        after_speak_sec = max(0.0, float(self._speak_complete_hold_sec))
        speak_sec = max(0.0, total_sec - listen_sec - gap_sec - after_speak_sec)
        if speak_sec <= 1e-6:
            return 0.0
        t_speak_start = listen_sec + gap_sec
        t_bg_end = t_speak_start + speak_sec + after_speak_sec
        if elapsed_sec < t_speak_start or elapsed_sec >= t_bg_end:
            return 0.0
        return max(0.0, t_bg_end - elapsed_sec)

    def _play_random_background_sound(self) -> None:
        if not self._bg_sounds:
            return
        try:
            if pygame.mixer.get_init() is None:
                from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
            if len(self._bg_sounds) == 1:
                picked_index = 0
            else:
                candidates = [i for i in range(len(self._bg_sounds)) if i != self._bg_last_sound_index]
                picked_index = random.choice(candidates) if candidates else 0
            sound_path, sound = self._bg_sounds[picked_index]
            channel = pygame.mixer.Channel(self._bg_channel_index)
            channel.set_volume(float(self._bg_volume))
            channel.play(sound, loops=-1, fade_ms=int(self._bg_fade_ms))
            self._bg_channel = channel
            self._bg_last_sound_index = picked_index
            self._bg_playing = True
            if self.on_bg_sound_started is not None:
                try:
                    self.on_bg_sound_started(sound_path, self._bg_active_remaining_sec())
                except Exception:
                    pass
        except Exception:
            self._bg_channel = None
            self._bg_playing = False

    def _stop_background_sound(self) -> None:
        channel = self._bg_channel
        if channel is None:
            self._bg_playing = False
            return
        try:
            if channel.get_busy():
                channel.fadeout(int(self._bg_fade_ms))
        except Exception:
            pass
        self._bg_playing = False

    def _draw_mode_icon(self, screen: pygame.Surface, *, ctx: FrameContext, is_listen_phase: bool) -> None:
        """현재 재생 구간에 맞는 모드 아이콘을 좌하단에 표시한다."""
        icon_surface = self._listen_icon_surface if is_listen_phase else self._speak_icon_surface
        blit_mode_icon_bottom_left(screen, icon_surface, frame_height=ctx.height)
