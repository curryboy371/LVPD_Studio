"""연습 장면(Scene): 비디오 + 문장 + 현재 단어(최소)."""

from __future__ import annotations

from dataclasses import replace
from enum import Enum, auto
from pathlib import Path
from typing import Callable

import pygame

from ..core.scene_transition import SceneTransitionMode
from ..core.types import (
    ConversationItemLike,
    FrameContext,
    SentenceStyleConfig,
    build_sentence_render_data_with_tone_icons,
)
from ..core.conversation_step import IConversationStep
from ..tools.playback_bar import PlaybackBarRenderer
from utils.pinyin_processor import get_pinyin_processor


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

    def __init__(
        self,
        *,
        drawer,
        video_player,
        style: SentenceStyleConfig,
        play_voice: Callable[..., None] | None = None,
        title_text: str = "연습",
        title_fade_in_sec: float = 1.0,
        content_hold_sec: float = 3.0,
    ) -> None:
        """연습용 Drawer·비디오·문장 스타일을 연결하고 제목 페이드인을 준비한다."""
        super().__init__()
        self.drawer = drawer
        self.video_player = video_player
        self.play_voice = play_voice
        self.scene_transition_mode: SceneTransitionMode = SceneTransitionMode.CUT
        self.scene_transition_duration_sec: float = 0.4
        self.scene_transition_overlay_peak_alpha: int = 220
        self._style = style
        self.title_text = str(title_text or "연습")
        self.title_fade_in_sec = float(title_fade_in_sec)
        # SHOW_CONTENT 단계에서 sub 문장으로 넘어가기 전 대기 시간(초).
        self.content_hold_sec = float(content_hold_sec)
        self._title_channel = "practice_title"
        self._sentence_channel = "practice_sentence"
        self._active_item_key = None
        self._title_wait_remaining_sec = 0.0
        self._content_wait_remaining_sec = 0.0
        # SHOW_SUB_CONTENT 단계에서 sub 문장 간 자동 전환 대기 시간(초).
        self._sub_content_hold_sec = 3.0
        self._sub_content_wait_remaining_sec = 0.0
        self._sub_content_wait_total_sec = 0.0
        self._sub_content_sound_sec = 0.0
        self._sub_variants: list[dict] = []
        self._sub_variant_index = 0
        self._content_visible = False
        self._current_sub_variant = None
        self._playback_bar = PlaybackBarRenderer()
        self._listen_icon_surface = self._load_mode_icon_surface("listen.png")
        self._speak_icon_surface = self._load_mode_icon_surface("speak.png")
        # LearningScene과 동일하게 디버그에서 읽을 수 있도록 stage 필드를 유지한다.
        self.stage: "PracticeScene.Stage" = self.Stage.TITLE
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
            self.drawer.hide_now(self._title_channel)
            self.drawer.hide_now(self._sentence_channel)

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
            self.drawer.hide_now(self._sentence_channel)
            self.drawer.fade_on(self._title_channel, self.title_fade_in_sec)
            self._set_stage(self.Stage.TITLE)
            return

        # Stage 기반으로 제목 페이드 완료 시점을 관리한다.
        if self.stage == self.Stage.TITLE:
            if self._title_wait_remaining_sec > 0.0:
                self._title_wait_remaining_sec = max(0.0, self._title_wait_remaining_sec - dt)
            if self._title_wait_remaining_sec <= 0.0:
                self._content_visible = True
                self.drawer.show_now(self._sentence_channel)
                self._set_stage(self.Stage.SHOW_CONTENT)
            return

        # 기본 문장을 잠시 보여준 뒤, sub_sentences.csv 기반 변형이 있으면 다음 Stage로 넘긴다.
        if self.stage == self.Stage.SHOW_CONTENT:
            if self._content_wait_remaining_sec > 0.0:
                self._content_wait_remaining_sec = max(0.0, self._content_wait_remaining_sec - dt)
            if self._content_wait_remaining_sec <= 0.0:
                # sub 변형이 없으면 기본 문장 노출 후 곧바로 Step 완료 처리한다.
                if self._current_sub_variant is None:
                    self.complete()
                    self.allow_transition()
                    return
                self._set_stage(self.Stage.SHOW_SUB_CONTENT)
                wait_total = self._start_current_sub_variant_audio_and_get_wait()
                self._sub_content_wait_total_sec = max(0.0, float(wait_total))
                self._sub_content_wait_remaining_sec = self._sub_content_wait_total_sec
            return

        # SHOW_SUB_CONTENT 타이머는 sub 개수와 무관하게 항상 흐르게 유지한다.
        if self.stage == self.Stage.SHOW_SUB_CONTENT:
            if self._sub_content_wait_remaining_sec > 0.0:
                self._sub_content_wait_remaining_sec = max(0.0, self._sub_content_wait_remaining_sec - dt)
            if self._sub_content_wait_remaining_sec <= 0.0:
                if len(self._sub_variants) > 1:
                    next_index = self._sub_variant_index + 1
                    if next_index < len(self._sub_variants):
                        self._sub_variant_index = next_index
                        self._current_sub_variant = self._sub_variants[self._sub_variant_index]
                        wait_total = self._start_current_sub_variant_audio_and_get_wait()
                        self._sub_content_wait_total_sec = max(0.0, float(wait_total))
                        self._sub_content_wait_remaining_sec = self._sub_content_wait_total_sec
                        return
                # 마지막 sub 변형까지 모두 끝나면 다음 SceneKind로 전환한다.
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
        """현재 sub 변형의 alt_sound_path를 재생하고, 길이의 2배 대기 시간을 반환한다."""
        variant = self._current_sub_variant if isinstance(self._current_sub_variant, dict) else {}
        sound_path = str(variant.get("alt_sound_path") or "").strip()
        if not sound_path:
            self._sub_content_sound_sec = 0.0
            return self._sub_content_hold_sec

        if self.play_voice is not None:
            try:
                self.play_voice(sound_path, item=variant)
            except Exception:
                pass

        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            sound_len_sec = float(pygame.mixer.Sound(sound_path).get_length() or 0.0)
            if sound_len_sec > 0.0:
                self._sub_content_sound_sec = sound_len_sec
                return sound_len_sec * 2.0
        except Exception:
            pass
        self._sub_content_sound_sec = 0.0
        return self._sub_content_hold_sec

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """비디오 위에 LEARNING과 동일 세로 배치(중앙·타이틀 밴드 여유)의 문장과 첫 단어(있으면)를 표시한다."""
        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        self.drawer.draw_item_title(
            screen,
            self.title_text,
            ctx=ctx,
            channel=self._title_channel,
            style=self._style,
        )

        if not self._content_visible:
            return

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
        # 변경된 단어(alt_word)만 노란색으로 오버레이한다.
        if self.stage == self.Stage.SHOW_SUB_CONTENT and self._current_sub_variant is not None:
            self._draw_sub_sentence_with_highlight(
                screen,
                ctx=ctx,
                base_item=item,
                render_item=render_item,
            )
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
    ) -> None:
        """SHOW_SUB_CONTENT용 한자 하이라이트 렌더.

        기본 한자 줄은 흰색으로 그리고, 교체된 단어(alt_word)만 기존 연습 색상(노란색)으로 덮어쓴다.
        """
        white_style = replace(
            self._style,
            colors=replace(self._style.colors, hanzi_color=(255, 255, 255)),
        )
        self.drawer.draw_item_sentence(
            screen,
            render_item,
            ctx=ctx,
            channel=self._sentence_channel,
            style=white_style,
            title_clearance=(self.title_text, 0.12, 12),
        )

        replaced_sentence = str(self._current_sub_variant.get("replaced_sentence") or "").strip()
        alt_word = str(self._current_sub_variant.get("alt_word") or "").strip()
        base_sentence = ""
        base_sentences = base_item.get("sentence") or []
        if base_sentences:
            base_sentence = str(base_sentences[0]).strip()
        if not replaced_sentence or not alt_word or replaced_sentence == base_sentence:
            return

        data = build_sentence_render_data_with_tone_icons(render_item)
        y_base = self.drawer.layout_sentence_y_base(
            ctx,
            data,
            white_style,
            align_v="center",
            center_y_ratio=self.drawer.ITEM_SENTENCE_CENTER_Y_RATIO,
            top_y_ratio=0.12,
            bottom_margin_px=48,
            title_clearance=(self.title_text, 0.12, 12),
        )
        hanzi_text = (data.sentence or "")[: white_style.text.max_hanzi]
        if not hanzi_text:
            return
        idx = hanzi_text.find(alt_word)
        if idx < 0:
            return

        # 별도 폰트를 만들지 않고, _sentence_channel이 쓰는 메인 한자 폰트 체계를 그대로 사용한다.
        fonts = getattr(self.drawer, "_fonts", None)
        hanzi_ft = getattr(fonts, "hanzi_ft", None)
        hanzi_pg = getattr(fonts, "hanzi_pg", None)
        cache_hanzi = getattr(self.drawer, "_cache_hanzi", None)
        if hanzi_pg is None or cache_hanzi is None:
            return

        y_hanzi = y_base + (white_style.layout.line_gap_px if (data.pinyin or "").strip() else 0)
        center_x = int(ctx.width) // 2
        full_surf, _ = self.drawer._get_cached_text_pair(
            cache_hanzi,
            hanzi_ft,
            hanzi_pg,
            hanzi_text,
            white_style.colors.hanzi_color,
        )
        full_w = int(full_surf.get_width())
        x_line = max(white_style.layout.min_margin_x, center_x - full_w // 2)

        prefix = hanzi_text[:idx]
        target = hanzi_text[idx : idx + len(alt_word)]
        if not target:
            return
        if prefix:
            prefix_surf, _ = self.drawer._get_cached_text_pair(
                cache_hanzi,
                hanzi_ft,
                hanzi_pg,
                prefix,
                white_style.colors.hanzi_color,
            )
            prefix_w = int(prefix_surf.get_width())
        else:
            prefix_w = 0
        target_surf, _ = self.drawer._get_cached_text_pair(
            cache_hanzi,
            hanzi_ft,
            hanzi_pg,
            target,
            self._style.colors.hanzi_color,
        )
        alpha = int(max(0, min(255, self.drawer.fade_alpha(self._sentence_channel))))
        if alpha <= 0:
            return
        if alpha < 255:
            target_surf.set_alpha(alpha)
        screen.blit(target_surf, (x_line + prefix_w, y_hanzi))

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
        practice_sec = max(0.0, total_sec - listen_sec)

        # 2구간 재생:
        # 1) 듣기 바: 0 -> sound_len
        # 2) 말하기 바: 0 -> (total - sound_len)
        is_listen_phase = listen_sec > 1e-6 and elapsed_sec < listen_sec
        if is_listen_phase:
            bar_current_sec = elapsed_sec
            bar_total_sec = listen_sec
        elif practice_sec > 1e-6:
            bar_current_sec = min(max(0.0, elapsed_sec - listen_sec), practice_sec)
            bar_total_sec = practice_sec
        else:
            bar_total_sec = max(0.1, total_sec if total_sec > 1e-6 else float(self._sub_content_hold_sec))
            bar_current_sec = min(elapsed_sec, bar_total_sec)

        self._playback_bar.draw(
            screen,
            frame_width=ctx.width,
            frame_height=ctx.height,
            current_sec=bar_current_sec,
            total_sec=bar_total_sec,
            show_time_text=False,
            progress_color=self._resolve_playback_bar_color(is_listen_phase=is_listen_phase),
        )
        self._draw_mode_icon(screen, ctx=ctx, is_listen_phase=is_listen_phase)

    def _resolve_playback_bar_color(self, *, is_listen_phase: bool) -> tuple[int, int, int]:
        """현재 재생 모드에 맞는 재생바 색상을 반환한다."""
        color_table = {
            "listen": (46, 204, 113),
            "speak": (255, 159, 67),
        }
        mode = "listen" if is_listen_phase else "speak"
        return color_table[mode]

    def _load_mode_icon_surface(self, filename: str) -> pygame.Surface | None:
        """재생 모드 아이콘을 로드하고 공통 크기로 축소한다."""
        root = Path(__file__).resolve().parents[3]
        candidates = (
            root / "resource" / "image" / "icon" / filename,
            root / "resource" / "images" / "icon" / filename,
        )
        for path in candidates:
            if not path.exists():
                continue
            try:
                # convert_alpha()는 display 초기화 타이밍에 따라 실패할 수 있어 생략한다.
                surface = pygame.image.load(str(path))
                target_size = 318
                return pygame.transform.smoothscale(surface, (target_size, target_size))
            except Exception:
                continue
        return None

    def _draw_mode_icon(self, screen: pygame.Surface, *, ctx: FrameContext, is_listen_phase: bool) -> None:
        """현재 재생 구간에 맞는 모드 아이콘을 좌하단에 표시한다."""
        icon_surface = self._listen_icon_surface if is_listen_phase else self._speak_icon_surface
        if icon_surface is None:
            return
        margin_left = 24
        margin_bottom = 20
        x = margin_left
        y = int(ctx.height) - int(icon_surface.get_height()) - margin_bottom
        screen.blit(icon_surface, (x, y))
