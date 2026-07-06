"""단어 외우기 — 배치 JSON 순차 하이라이트·TTS 재생(ko/en→한자, zh 모드는 한자→한국어)."""
from __future__ import annotations

import logging
import math
import random
import re
import time
from pathlib import Path
from typing import Any, Literal, Optional

import pygame

from core.interfaces import IStudio
from core.paths import (
    DEFAULT_WORDS_TABLE_CSV,
    STUDIO_WORD_MEMORIZE_BG_AUDIO_LINEAR_GAIN,
    get_repo_root,
)
from data.table_manager import get_word, load_words_table_from_csv
from extra.table_editor.services.word_memorize_layout import (
    PICK_REVEAL_SEC,
    TRAP_REGROW_SEC,
    TRAP_REGROW_SMOKE_POLL_SEC,
    WordMemorizeBox,
    box_runtime_key,
    box_uses_mining_regrow,
    box_uses_trap,
    game_tile_display_px,
    is_base_slot_box,
    is_laser_selection_highlight,
    layout_uses_compose,
    layout_uses_pick_mining,
    load_layout,
    normalize_selection_highlight,
)
from studio.studios.word_memorize_box_resolve import (
    active_cta_caption_for_box,
    box_uses_cta_audio,
    resolve_box_word,
    resolve_box_word_id,
)
from studio.studios.word_memorize_trap import (
    collect_trap_fall_land_impacts,
    layout_trap_regrow_duration_sec,
)
from studio.studios.word_memorize_pick import (
    card_mining_row_count,
    card_mining_state,
    card_mining_swing_index,
    pick_reveal_progress,
    pick_random_word_memorize_fall_sound_path,
    pick_random_word_memorize_hamer_sound_path,
    pick_random_word_memorize_spark_sound_path,
    word_memorize_laser_sound_path,
    word_memorize_pick_sound_path,
)
from studio.studios.word_memorize_glass import (
    GLASS_SPARK_SOUND_INTERVAL_MAX_SEC,
    GLASS_SPARK_SOUND_INTERVAL_MIN_SEC,
    glass_dissolve_complete,
    glass_dissolve_t_reverse,
    glass_dissolve_total_sec,
    glass_finale_close_duration_sec,
    layout_uses_laser_glass,
)
from studio.studios.word_memorize_quiz import (
    QUIZ_FADE_OUT_SEC,
    quiz_fade_alpha,
    quiz_fade_y_offset_px,
    quiz_reveal_hold_sec,
    quiz_timer_remaining_ratio,
)
from studio.studios.word_memorize_laser import laser_impact_elapsed_sec
from studio.studios.word_memorize_renderer import (
    WordMemorizeRenderer,
    load_en_meaning_by_id,
    load_ko_meaning_by_id,
    load_word_components_by_id,
    load_word_example_sentences_by_id,
)
from studio.studios.word_memorize_compose import (
    COMPOSE_B_TOTAL_SEC,
    COMPOSE_PREVIEW_HOLD_SEC,
    COMPOSE_REVIEW_HOLD_SEC,
    ComposeSentenceInfo,
    ComposeTiming,
    build_compose_timing,
    compose_brush_sound_path,
    compose_open_sound_path,
    compose_pop_sound_path,
    pick_random_compose_block_sound_path,
)

MeaningLang = Literal["ko", "en", "zh"]

logger = logging.getLogger(__name__)

# 시작 화면(타일·제목) 유지 — 미리보기·녹화 썸네일용
INTRO_HOLD_SEC = 0.4
END_HOLD_SEC = 0.6
TTS_MISSING_HOLD_SEC = 1.2
# 첫 TTS 종료 N초 전에 둘째 TTS 시작 (겹침)
TTS_SECOND_LEAD_BEFORE_FIRST_END_SEC = 0.8
# 조합형 전용 — 부품 뜻(한국어) TTS가 끝난 뒤 중국어 단어 TTS 시작까지 간격(겹치지
# 않고 쉬었다 재생). 뜻 TTS를 COMPOSE_WORD_TTS_CUT_RATIO로 잘라 짧아진 경우가 많아,
# 표준 타입처럼 고정 초 전에 겹치게 하면(TTS_SECOND_LEAD_BEFORE_FIRST_END_SEC) 뜻이
# 끝나기도 전에 단어가 시작돼 버려 텀이 거의 없어 보이는 문제가 있었다.
COMPOSE_TTS_SECOND_GAP_SEC = 0.02
# 부품/결과 단어 뜻(한국어) TTS 끝에서 잘라내는 비율 — quiz reveal의
# QUIZ_TTS_END_EARLY_RATIO(0.25)보다 더 공격적으로 잘라 한국어→중국어 전환을
# 빠르게 한다(quiz reveal과는 무관한 별도 상수라 퀴즈 모드에는 영향 없음).
COMPOSE_WORD_TTS_CUT_RATIO = 0.55
# 부품/결과 단어 발음(중국어) TTS도 끝을 잘라 다음 단계 대기 시간을 더 줄인다.
# 문장 자체 발음이 학습 핵심이라 뜻(한국어)보다는 보수적으로 자른다.
COMPOSE_WORD_ZH_CUT_RATIO = 0.4
# 문장 카드의 중국어 문장 TTS가 끝난 뒤 B 구간을 넘어가기 전 최소 여유(읽을 시간).
COMPOSE_SENTENCE_TAIL_HOLD_SEC = 1.2
# 결과 단어 자체 내레이션(뜻+발음)이 다 끝난 뒤 문장 카드가 뜨기까지의 짧은 정적.
COMPOSE_SENTENCE_CARD_PAUSE_SEC = 0.2
# ko/en: 둘째=한자 — 꼬리 N초 전에 다음 단어(뜻 TTS) 시작
TTS_NEXT_WORD_LEAD_BEFORE_SECOND_END_SEC = 0.5
# zh: 둘째=한국어 뜻 — 다음 한자로 전환 (ko/en과 동일 0.5s)
TTS_ZH_MODE_KO_LEAD_BEFORE_NEXT_WORD_SEC = 0.5
CTA_PRE_REGROW_HOLD_SEC = 1.0
FINAL_TILE_REGROW_HOLD_SEC = 3.0
# 레이저 유리 — 전 카드 오픈 후 동시 레이저·역디졸브 피날레
GLASS_FINALE_HOLD_SEC = 1.0
# 영어 TTS 재생 볼륨 (1.0=원본)
TTS_EN_PLAYBACK_VOLUME = 0.78
# 단어 외우기 효과음 채널·볼륨 (runner: set_num_channels(9) → 0~8)
_PICK_EFFECT_CHANNEL = 4
_TILE_FALL_EFFECT_CHANNEL = 3
_HAMER_EFFECT_CHANNEL = 2
_LASER_EFFECT_CHANNEL = 5
_SPARK_EFFECT_CHANNEL = 6
_COMPOSE_BLOCK_EFFECT_CHANNEL = 0
_COMPOSE_BRUSH_EFFECT_CHANNEL = 1
_COMPOSE_OPEN_EFFECT_CHANNEL = 7
_COMPOSE_POP_EFFECT_CHANNEL = 8
_EFFECT_CHANNEL_VOLUMES: dict[int, float] = {
    _PICK_EFFECT_CHANNEL: 0.2,
    _TILE_FALL_EFFECT_CHANNEL: 0.2,
    _HAMER_EFFECT_CHANNEL: 0.15,
    _LASER_EFFECT_CHANNEL: 0.20,
    _SPARK_EFFECT_CHANNEL: 0.58,
    _COMPOSE_BLOCK_EFFECT_CHANNEL: 0.35,
    _COMPOSE_BRUSH_EFFECT_CHANNEL: 0.35,
    _COMPOSE_OPEN_EFFECT_CHANNEL: 0.4,
    _COMPOSE_POP_EFFECT_CHANNEL: 0.45,
}

WordSubstep = Literal[
    "",
    "quiz_reveal",
    "quiz_fade_out",
    "glass_reveal_wait",
    "compose",
    "mining",
    "trap_regrow",
    "cta_pre_regrow",
    "final_pre_regrow",
    "first",
    "second",
    "glass_finale_hold",
    "glass_finale_close",
]


def _normalize_meaning_lang(raw: str) -> MeaningLang:
    lang = (raw or "ko").strip().lower()
    if lang in ("zh", "ch", "cn"):
        return "zh"
    if lang == "en":
        return "en"
    return "ko"


def _word_memorize_recording_topic(layout_path: Path) -> str:
    """녹화 파일명용 주제 — 배치 JSON stem."""
    raw = (layout_path.stem or "").strip()
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", raw)
    return cleaned.strip() or "untitled"


class WordMemorizeStudio(IStudio):
    def __init__(
        self,
        *,
        layout_path: str,
        meaning_lang: MeaningLang = "ko",
        quiz_mode: bool = True,
    ) -> None:
        self._layout_path = Path(layout_path)
        self._layout = load_layout(self._layout_path)
        self._meaning_lang = _normalize_meaning_lang(str(meaning_lang))
        self._quiz_mode = bool(quiz_mode)
        self._renderer = WordMemorizeRenderer(show_images=bool(self._layout.show_images))
        self._renderer.set_background(
            self._layout.background_value, self._meaning_lang
        )
        csv_path = Path(DEFAULT_WORDS_TABLE_CSV)
        if self._meaning_lang == "en":
            self._card_meaning_by_id = load_en_meaning_by_id(csv_path)
        else:
            self._card_meaning_by_id = load_ko_meaning_by_id(csv_path)
        self._compose_component_ids_by_result = load_word_components_by_id(csv_path)
        self._compose_example_sentences_by_id = load_word_example_sentences_by_id(csv_path)
        self._compose_tray: list[int] = []
        self._compose_sound_stage = 0
        self._compose_timing = ComposeTiming()
        self._compose_sentence = ComposeSentenceInfo()
        self._compose_elapsed_total_sec = 0.0
        self._sequence: list[WordMemorizeBox] = []
        self._seq_index = 0
        self._phase = "intro"
        self._word_substep: WordSubstep = ""
        self._timer = 0.0
        self._hold_sec = (
            COMPOSE_PREVIEW_HOLD_SEC
            if layout_uses_compose(self._layout)
            else INTRO_HOLD_SEC
        )
        self._active_key: str | None = None
        self._revealed_keys: set[str] = set()
        self._revealed_rows_by_key: dict[str, int] = {}
        self._queued_second_path: Path | None = None
        self._queued_second_len = 0.0
        self._active_word_elapsed_sec = 0.0
        self._active_word_duration_sec = 0.0
        self._pick_mining_elapsed_sec = 0.0
        self._pick_mining_last_swing_index = -1
        self._trap_regrow_elapsed_sec = 0.0
        self._trap_regrow_duration_sec = float(TRAP_REGROW_SEC)
        self._trap_regrow_revealed_keys: set[str] = set()
        self._trap_regrow_revealed_rows: dict[str, int] = {}
        self._tiles_fully_restored = False
        self._done = False
        self._last_config: Any = None
        self._bg_player: Any = None
        self._active_effect_sound_until: dict[str, float] = {}
        self._glass_finale_elapsed_sec = 0.0
        self._laser_effect_played = False
        self._glass_spark_timer = 0.0
        self._glass_spark_interval = GLASS_SPARK_SOUND_INTERVAL_MIN_SEC
        self._quiz_fade_elapsed_sec = 0.0
        self._quiz_consumed_first_tts = False
        self._quiz_gage_display_ratio = 1.0
        self._quiz_tts_channel: Any = None

    def _uses_pick_mining(self) -> bool:
        """퀴즈 모드 — 곡괭이·타일 파괴 채굴."""
        return self._quiz_mode and layout_uses_pick_mining(self._layout)

    def _uses_laser_glass(self) -> bool:
        """퀴즈 모드 — 레이저 유리 흐림·디졸브."""
        return self._quiz_mode and layout_uses_laser_glass(self._layout)

    def _uses_laser_highlight(self) -> bool:
        """배치 selection_highlight가 레이저 빔 (퀴즈·일반 공통)."""
        kind = normalize_selection_highlight(
            getattr(self._layout, "selection_highlight", "")
        )
        return is_laser_selection_highlight(kind)

    def _needs_final_tile_regrow(self) -> bool:
        """퀴즈 타일 모드 — 마지막 단어 후 trap 카드 없어도 타일 복구."""
        return (
            self._quiz_mode
            and self._uses_pick_mining()
            and not self._tiles_fully_restored
        )

    def init(self, config: Any = None) -> None:
        self._last_config = config
        load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
        self._sequence = [
            b
            for b in self._layout.sorted_boxes()
            if resolve_box_word(b) is not None
        ]
        if not self._sequence:
            logger.warning("단어 외우기: 배치에 표시할 단어가 없습니다 — %s", self._layout_path)
        self._init_bg_player()
        self._reset_playback()
        self._renderer.reset_scorch_layer()
        self._renderer.reset_mining_particles()

    def _init_bg_player(self) -> None:
        from studio.shorts.bg_audio import ShortsBackgroundPlayer

        self._bg_player = ShortsBackgroundPlayer(
            on_bg_started=self._log_bg_insert_sound,
            is_recording=self._is_recording_mode,
            volume=STUDIO_WORD_MEMORIZE_BG_AUDIO_LINEAR_GAIN,
        )
        abs_bg = self._resolve_layout_bg_absolute()
        if abs_bg:
            self._bg_player.set_fixed_bg_path(abs_bg)

    def _resolve_layout_bg_absolute(self) -> str | None:
        from extra.table_editor.services.shorts_editor_choices import (
            is_bg_short_rel_path,
        )

        raw = (self._layout.bg_music_path or "").strip()
        if not raw or not is_bg_short_rel_path(raw):
            return None
        p = get_repo_root() / raw.replace("\\", "/")
        if p.is_file():
            return str(p.resolve())
        logger.warning("단어 외우기: 배경음 파일 없음 — %s", raw)
        return None

    def start_playback(self) -> None:
        if self._bg_player is None:
            return
        self._bg_player.start_session(
            duration_hint_sec=self._bg_duration_hint_sec(self._last_config),
            reload=True,
        )

    def begin_recording_session(self, config: Any) -> None:
        self._last_config = config
        if self._bg_player is None:
            return
        self._bg_player.start_session(
            duration_hint_sec=self._bg_duration_hint_sec(config),
            reload=True,
        )

    def stop_background_audio(self) -> None:
        if self._bg_player is not None:
            self._bg_player.stop_session()

    def _bg_duration_hint_sec(self, config: Any) -> float:
        if config is not None and getattr(config, "recording_log_event", None) is not None:
            return max(60.0, float(getattr(config, "record_max_sec", 3600.0) or 3600.0))
        return 3600.0

    def _log_bg_insert_sound(self, path: str, duration_sec: float) -> None:
        if not path:
            return
        log = getattr(self._last_config, "recording_log_event", None)
        if log is None:
            return
        try:
            rel = path
            try:
                rel = str(Path(path).resolve().relative_to(get_repo_root())).replace(
                    "\\", "/"
                )
            except ValueError:
                pass
            from studio.recording_events import InsertSound, recording_log_event

            timeline_sec = float(
                getattr(self._last_config, "recording_time_sec", 0.0) or 0.0
            )
            recording_log_event(
                log,
                InsertSound(
                    timeline_sec=timeline_sec,
                    path=rel,
                    duration_sec=max(0.0, float(duration_sec)),
                    linear_gain=float(STUDIO_WORD_MEMORIZE_BG_AUDIO_LINEAR_GAIN),
                ),
            )
        except Exception:
            return

    def _reset_playback(self) -> None:
        self._seq_index = 0
        self._phase = "intro"
        self._word_substep = ""
        self._timer = 0.0
        self._hold_sec = (
            COMPOSE_PREVIEW_HOLD_SEC
            if layout_uses_compose(self._layout)
            else INTRO_HOLD_SEC
        )
        self._compose_tray = []
        self._compose_sound_stage = 0
        self._active_key = None
        self._revealed_keys = set()
        self._revealed_rows_by_key = {}
        self._queued_second_path = None
        self._queued_second_len = 0.0
        self._active_word_elapsed_sec = 0.0
        self._active_word_duration_sec = 0.0
        self._pick_mining_elapsed_sec = 0.0
        self._pick_mining_last_swing_index = -1
        self._trap_regrow_elapsed_sec = 0.0
        self._trap_regrow_duration_sec = float(TRAP_REGROW_SEC)
        self._trap_regrow_revealed_keys: set[str] = set()
        self._trap_regrow_revealed_rows: dict[str, int] = {}
        self._tiles_fully_restored = False
        self._done = False
        self._active_effect_sound_until.clear()
        self._glass_finale_elapsed_sec = 0.0
        self._quiz_fade_elapsed_sec = 0.0
        self._quiz_consumed_first_tts = False
        self._quiz_gage_display_ratio = 1.0
        self._quiz_tts_channel: Any = None
        self._reset_laser_glass_sound_state()

    def get_title(self) -> str:
        return f"LVPD Studio - 단어 외우기 ({self._layout_path.stem})"

    def recording_shorts_bg_linear_gain(self) -> float:
        """녹화 mux 시 bg_short InsertSound 기본 게인(이벤트 linear_gain 없을 때 폴백)."""
        return float(STUDIO_WORD_MEMORIZE_BG_AUDIO_LINEAR_GAIN)

    def handle_events(self, events: list, config: Any = None) -> bool:
        for ev in events:
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_q):
                return False
        return True

    def update(self, config: Any = None) -> None:
        self._last_config = config
        if self._bg_player is not None and not self._done:
            self._bg_player.tick(
                duration_hint_sec=self._bg_duration_hint_sec(config)
            )
        if self._done:
            return
        dt = float(getattr(config, "dt_sec", 1.0 / 30.0) or (1.0 / 30.0))
        self._compose_elapsed_total_sec += dt
        self._renderer.tick_mining_particles(dt)
        self._renderer.tick_background_video(dt)
        if self._phase == "word":
            if self._word_substep == "mining":
                self._pick_mining_elapsed_sec += dt
                self._sync_pick_swing_sound()
            elif self._word_substep == "trap_regrow":
                prev_trap = self._trap_regrow_elapsed_sec
                self._trap_regrow_elapsed_sec += dt
                self._sync_trap_fall_impacts(prev_trap, self._trap_regrow_elapsed_sec)
            elif self._word_substep == "quiz_fade_out":
                self._quiz_fade_elapsed_sec += dt
            elif self._word_substep == "glass_finale_close":
                self._glass_finale_elapsed_sec += dt
            elif self._word_substep == "compose":
                self._sync_compose_sounds(self._timer + dt)
            elif self._word_substep not in (
                "glass_finale_hold",
                "quiz_reveal",
                "quiz_fade_out",
            ):
                self._active_word_elapsed_sec += dt
                self._sync_laser_glass_revealed()
            if self._uses_laser_highlight() and self._word_substep not in (
                "quiz_reveal",
                "quiz_fade_out",
            ):
                self._sync_laser_sounds(dt)
            if self._word_substep == "mining":
                self._sync_pick_revealed_keys()
        self._timer += dt
        if self._phase == "word" and self._word_substep == "quiz_reveal":
            target_ratio = quiz_timer_remaining_ratio(
                timer_sec=self._timer,
                hold_sec=self._hold_sec,
            )
            smooth = 1.0 - math.exp(-dt * 60.0)
            self._quiz_gage_display_ratio += (
                target_ratio - self._quiz_gage_display_ratio
            ) * smooth
        if self._timer < self._hold_sec:
            return
        if self._phase == "outro":
            # 여기서 타이머를 0으로 리셋하지 않는다 — outro는 끝이라 이후 프레임이
            # 없으므로, 마지막으로 그려질 프레임이 hold_sec 근처(복습 화면 페이드
            # 아웃 완료 시점)를 그대로 유지해야 영상 시작 프레임과 이어붙였을 때
            # 자연스럽다. 0으로 리셋하면 이 마지막 프레임만 다시 완전히 보이는
            # 상태로 튀어 시작 프레임과 어긋나 보인다.
            self._done = True
            self.stop_background_audio()
            return
        self._timer = 0.0
        if self._phase == "intro":
            self._begin_word(0)
        elif self._phase == "word":
            self._advance_word_step()

    def _uses_revealed_keys(self) -> bool:
        """채굴·레이저 유리 모드 — 카드 노출 상태 추적."""
        return self._uses_pick_mining() or self._uses_laser_glass()

    def _reveal_all_laser_glass_cards(self) -> None:
        """피날레 — base 제외 전 카드를 디졸브 완료(노출) 상태로."""
        for box in self._layout.sorted_boxes():
            if resolve_box_word(box) is None:
                continue
            if is_base_slot_box(box, self._layout):
                continue
            self._revealed_keys.add(box_runtime_key(box))

    def _begin_glass_finale(self) -> None:
        """전 카드 오픈 후 1초 대기 → 동시 레이저·역디졸브."""
        self._reveal_all_laser_glass_cards()
        self._phase = "word"
        self._word_substep = "glass_finale_hold"
        self._active_key = None
        self._glass_finale_elapsed_sec = 0.0
        self._hold_sec = float(GLASS_FINALE_HOLD_SEC)

    def _reset_laser_glass_sound_state(self) -> None:
        """레이저·디졸브 spark 효과음 상태 초기화."""
        self._laser_effect_played = False
        self._glass_spark_timer = 0.0
        self._glass_spark_interval = random.uniform(
            GLASS_SPARK_SOUND_INTERVAL_MIN_SEC,
            GLASS_SPARK_SOUND_INTERVAL_MAX_SEC,
        )

    def _finish_quiz_fade_to_word(self) -> None:
        """퀴즈 페이드 종료 → (레이저 유리) 디졸브 후 한자 TTS."""
        self._quiz_fade_elapsed_sec = 0.0
        if self._uses_laser_glass():
            self._word_substep = "glass_reveal_wait"
            self._reset_laser_glass_sound_state()
            self._active_word_elapsed_sec = 0.0
            box = self._active_mining_box()
            if box is not None:
                self._active_word_duration_sec = self._word_play_duration_sec(box)
            self._hold_sec = glass_dissolve_total_sec()
            return
        self._begin_word_content()

    def _play_laser_sound(self) -> None:
        """레이저 발사 효과음 — 1회."""
        self._play_effect_sound(
            word_memorize_laser_sound_path(),
            channel=_LASER_EFFECT_CHANNEL,
            label="레이저 효과음",
        )

    def _play_random_spark_sound(self) -> None:
        """유리 디졸브 — spark 폴더에서 랜덤 재생."""
        path = pick_random_word_memorize_spark_sound_path()
        if path is None:
            logger.debug("디졸브 spark 효과음 없음: resource/sound/effect/spark")
            return
        self._play_effect_sound(
            path,
            channel=_SPARK_EFFECT_CHANNEL,
            label="디졸브 spark 효과음",
        )

    def _sync_glass_dissolve_spark_sounds(self, dt: float, *, impact_t: float) -> None:
        """레이저 적중 후 디졸브 구간에서 spark를 랜덤 간격으로 반복."""
        if impact_t <= 0.0:
            self._glass_spark_timer = 0.0
            return
        self._glass_spark_timer += dt
        if self._glass_spark_timer < self._glass_spark_interval:
            return
        self._glass_spark_timer = 0.0
        self._glass_spark_interval = random.uniform(
            GLASS_SPARK_SOUND_INTERVAL_MIN_SEC,
            GLASS_SPARK_SOUND_INTERVAL_MAX_SEC,
        )
        self._play_random_spark_sound()

    def _sync_laser_sounds(self, dt: float) -> None:
        """레이저 — 발사 1회(퀴즈·일반). 퀴즈 유리 모드만 디졸브 spark 반복."""
        if self._word_substep == "glass_finale_hold":
            return
        if self._word_substep == "glass_finale_close":
            if not self._uses_laser_glass():
                return
            elapsed = self._glass_finale_elapsed_sec
            if not self._laser_effect_played:
                self._play_laser_sound()
                self._laser_effect_played = True
            impact_t = laser_impact_elapsed_sec(elapsed)
            if impact_t > 0.0 and glass_dissolve_t_reverse(impact_t) > 1e-4:
                self._sync_glass_dissolve_spark_sounds(dt, impact_t=impact_t)
            else:
                self._glass_spark_timer = 0.0
            return
        if self._phase != "word" or not self._active_key:
            return
        box = self._active_mining_box()
        if box is None or is_base_slot_box(box, self._layout):
            return
        if (
            self._uses_laser_glass()
            and self._active_key in self._revealed_keys
            and self._word_substep in ("first", "second", "")
        ):
            self._glass_spark_timer = 0.0
            return
        elapsed = self._active_word_elapsed_sec
        if not self._laser_effect_played:
            self._play_laser_sound()
            self._laser_effect_played = True
        if not self._uses_laser_glass():
            return
        impact_t = laser_impact_elapsed_sec(elapsed)
        if impact_t > 0.0 and not glass_dissolve_complete(elapsed):
            self._sync_glass_dissolve_spark_sounds(dt, impact_t=impact_t)
        else:
            self._glass_spark_timer = 0.0

    def _sync_laser_glass_revealed(self) -> None:
        """레이저 적중 후 디졸브 완료 시 카드를 영구 노출로 표시."""
        if not self._uses_laser_glass():
            return
        if self._phase != "word" or not self._active_key:
            return
        box = self._active_mining_box()
        if box is None or is_base_slot_box(box, self._layout):
            return
        if glass_dissolve_complete(self._active_word_elapsed_sec):
            self._revealed_keys.add(self._active_key)

    def _mark_laser_glass_revealed_on_advance(self) -> None:
        """단어 전환 시 현재 카드 유리 가림 해제 상태 확정."""
        if not self._uses_laser_glass() or not self._active_key:
            return
        box = self._active_mining_box()
        if box is None or is_base_slot_box(box, self._layout):
            return
        self._revealed_keys.add(self._active_key)

    def _sync_pick_revealed_keys(self) -> None:
        """곡괭이로 제거된 타일 행을 누적 저장."""
        if not self._uses_pick_mining():
            return
        if self._phase != "word" or not self._active_key:
            return
        box = self._active_mining_box()
        if box is None:
            return
        from extra.table_editor.services.word_memorize_layout import game_tile_display_px

        tile_px = game_tile_display_px(frame_width=int(self._layout.frame_width))
        key = self._active_key
        prev = int(self._revealed_rows_by_key.get(key, 0))
        state = card_mining_state(
            box,
            self._pick_mining_elapsed_sec,
            tile_px=tile_px,
            stored_completed_rows=prev,
        )
        new_rows = max(prev, state.completed_rows)
        self._revealed_rows_by_key[key] = new_rows
        if new_rows > prev:
            self._play_tile_fall_sound()
            self._renderer.spawn_mining_row_particles(
                self._layout,
                box,
                from_row=prev,
                to_row=new_rows,
                tile_px=tile_px,
                revealed_box_keys=self._revealed_keys,
                words_by_id=self._words_by_id_for_draw(),
                card_meaning_by_id=self._card_meaning_by_id,
                meaning_lang=self._meaning_lang,
            )
        if state.is_complete:
            self._revealed_keys.add(key)

    def _sync_pick_swing_sound(self) -> None:
        """곡괭이 스윙 시작마다 pick.mp3 재생."""
        if not self._uses_pick_mining():
            return
        if self._phase != "word" or self._word_substep != "mining" or not self._active_key:
            return
        box = self._active_mining_box()
        if box is None:
            return
        tile_px = game_tile_display_px(frame_width=int(self._layout.frame_width))
        swing_index = card_mining_swing_index(
            box,
            self._pick_mining_elapsed_sec,
            tile_px=tile_px,
        )
        if swing_index <= self._pick_mining_last_swing_index:
            return
        self._play_pick_sound()
        self._pick_mining_last_swing_index = swing_index

    def _prune_active_effect_sounds(self) -> None:
        """재생이 끝난 효과음 키를 제거한다."""
        now = time.monotonic()
        expired = [key for key, until in self._active_effect_sound_until.items() if until <= now]
        for key in expired:
            del self._active_effect_sound_until[key]

    def _effect_sound_path_key(self, path: Path) -> str:
        return str(path.resolve())

    def _is_same_effect_sound_playing(self, path: Path) -> bool:
        """동일 파일이 아직 재생 중이면 True — pick·fall 동시 재생은 경로가 달라 허용."""
        self._prune_active_effect_sounds()
        return self._effect_sound_path_key(path) in self._active_effect_sound_until

    def _mark_effect_sound_playing(self, path: Path, duration_sec: float) -> None:
        key = self._effect_sound_path_key(path)
        self._active_effect_sound_until[key] = time.monotonic() + max(
            0.02, float(duration_sec)
        )

    def _effect_volume_for_channel(self, channel: int) -> float:
        """채널별 효과음 선형 볼륨 (0~1)."""
        return max(0.0, min(1.0, float(_EFFECT_CHANNEL_VOLUMES.get(channel, 1.0))))

    def _play_effect_sound(
        self,
        path: Path,
        *,
        channel: int,
        label: str,
    ) -> None:
        """효과음 — 미리보기 재생·녹화 InsertSound."""
        if not path.is_file():
            logger.debug("%s 없음: %s", label, path)
            return
        if self._is_same_effect_sound_playing(path):
            return
        try:
            if pygame.mixer.get_init() is None:
                from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
            snd = pygame.mixer.Sound(str(path))
            dur = float(snd.get_length())
            self._mark_effect_sound_playing(path, dur)
            vol = self._effect_volume_for_channel(channel)
            if vol < 1.0:
                snd.set_volume(vol)
            if self._is_recording_mode():
                self._log_insert_sound(
                    path,
                    dur,
                    linear_gain=vol if vol < 1.0 else None,
                )
                return
            pygame.mixer.Channel(channel).play(snd)
        except Exception as e:
            key = self._effect_sound_path_key(path)
            self._active_effect_sound_until.pop(key, None)
            logger.debug("%s 재생 실패: %s", label, e)

    def _play_pick_sound(self) -> None:
        """곡괭이 타격 효과음."""
        self._play_effect_sound(
            word_memorize_pick_sound_path(),
            channel=_PICK_EFFECT_CHANNEL,
            label="곡괭이 효과음",
        )

    def _play_tile_fall_sound(self) -> None:
        """타일 파괴 효과음 — fall 폴더에서 랜덤."""
        path = pick_random_word_memorize_fall_sound_path()
        if path is None:
            logger.debug("타일 파괴 효과음 없음: resource/sound/effect/fall")
            return
        self._play_effect_sound(
            path,
            channel=_TILE_FALL_EFFECT_CHANNEL,
            label="타일 파괴 효과음",
        )

    def _play_random_hamer_sound(self) -> None:
        """타일 재생성(hamer) — hamer 폴더에서 랜덤 재생."""
        path = pick_random_word_memorize_hamer_sound_path()
        if path is None:
            logger.debug("타일 재생성 효과음 없음: resource/sound/effect/hamer")
            return
        self._play_effect_sound(
            path,
            channel=_HAMER_EFFECT_CHANNEL,
            label="타일 재생성 효과음",
        )

    def _play_compose_block_sound(self) -> None:
        """조합형 — 부품 타일 등장 (block1/block2 랜덤)."""
        self._play_effect_sound(
            pick_random_compose_block_sound_path(),
            channel=_COMPOSE_BLOCK_EFFECT_CHANNEL,
            label="조합형 부품 타일 효과음",
        )

    def _play_compose_brush_sound(self) -> None:
        """조합형 — 획 그어짐(화살표 등장)."""
        self._play_effect_sound(
            compose_brush_sound_path(),
            channel=_COMPOSE_BRUSH_EFFECT_CHANNEL,
            label="조합형 획 효과음",
        )

    def _play_compose_open_sound(self) -> None:
        """조합형 — 뜻 팝업."""
        self._play_effect_sound(
            compose_open_sound_path(),
            channel=_COMPOSE_OPEN_EFFECT_CHANNEL,
            label="조합형 뜻 팝업 효과음",
        )

    def _play_compose_pop_sound(self) -> None:
        """조합형 — 결과 단어(합성어) 등장(임팩트)."""
        self._play_effect_sound(
            compose_pop_sound_path(),
            channel=_COMPOSE_POP_EFFECT_CHANNEL,
            label="조합형 결과 단어 등장 효과음",
        )

    def _sync_compose_sounds(self, t: float) -> None:
        """조합형 — 타이머가 각 등장 시점을 지날 때 1회씩 효과음·TTS 재생."""
        stage = self._compose_sound_stage
        timing = self._compose_timing
        if stage < 1 and t >= timing.part_a_stamp:
            self._play_compose_block_sound()
            stage = 1
        if stage < 2 and t >= timing.part_b_stamp:
            self._play_compose_block_sound()
            stage = 2
        if stage < 3 and timing.has_part_c and t >= timing.part_c_stamp:
            self._play_compose_block_sound()
            stage = 3
        elif stage < 3 and not timing.has_part_c:
            stage = 3
        if stage < 4 and t >= timing.arrow_pop:
            self._play_compose_brush_sound()
            stage = 4
        if stage < 5 and t >= timing.meaning_pop:
            self._play_compose_open_sound()
            stage = 5
        if stage < 6 and t >= timing.impact:
            self._play_compose_pop_sound()
            stage = 6
        self._compose_sound_stage = stage
        self._sync_compose_narration(t)

    def _compose_tts_pair_for_word(self, word_id: int) -> tuple[Path | None, Path | None]:
        """(첫 TTS, 둘째 TTS) — meaning_lang 순서 그대로(ko/en→중국어, zh→한국어). CTA 없음."""
        from audio.vocab_meaning_ko import resolve_vocab_meaning_ko_audio_path
        from audio.word_memorize_en import resolve_word_memorize_en_audio_path
        from audio.word_memorize_zh import resolve_word_memorize_zh_audio_path

        zh_path = resolve_word_memorize_zh_audio_path(word_id)
        ko_path = resolve_vocab_meaning_ko_audio_path(word_id)
        en_path = resolve_word_memorize_en_audio_path(word_id)
        if self._meaning_lang == "zh":
            return zh_path, ko_path
        if self._meaning_lang == "en":
            return en_path, zh_path
        return ko_path, zh_path

    def _compose_tts_pair_for_sentence(self, word_id: int) -> tuple[Path | None, Path | None]:
        """(한국어 번역 문장, 중국어 문장) — meaning_lang과 무관하게 항상 한국어→중국어 순."""
        from audio.word_memorize_compose_sentence import (
            resolve_compose_sentence_ko_audio_path,
            resolve_compose_sentence_zh_audio_path,
        )

        return (
            resolve_compose_sentence_ko_audio_path(word_id),
            resolve_compose_sentence_zh_audio_path(word_id),
        )

    def _compose_word_tts_cut_sec(self, tts_len: float) -> float:
        """부품/결과 단어 뜻(한국어) TTS 조기 종료(초) — quiz reveal보다 더 공격적."""
        return max(0.0, float(tts_len)) * COMPOSE_WORD_TTS_CUT_RATIO

    def _compose_word_zh_cut_sec(self, tts_len: float) -> float:
        """부품/결과 단어 발음(중국어) TTS 조기 종료(초) — 뜻보다는 보수적으로."""
        return max(0.0, float(tts_len)) * COMPOSE_WORD_ZH_CUT_RATIO

    def _sync_compose_narration(self, t: float) -> None:
        """조합형 — 부품1→부품2→결과 순서로, 각자 등장 시점부터 겹치지 않게 TTS 재생.

        뜻(한국어)·발음(중국어) TTS 둘 다 quiz reveal처럼 끝부분을 잘라 재생한다
        (뜻은 _compose_word_tts_cut_sec, 발음은 더 보수적인 _compose_word_zh_cut_sec).
        뜻 텍스트가 긴 부품(예: 电="전기, 전기의")이 있으면 안 잘라낼 경우 다음
        부품의 내레이션이 고정 타이밍(다음 부품 등장·화살표·임팩트)보다 한참 늦게
        시작돼 화면과 어긋나 보인다. 문장 카드(kind=="sentence")는 둘 다 끝까지
        재생한다(완료 후 다음 단계로 넘어가야 함)."""
        if (
            not self._compose_narration_second_done
            and self._compose_narration_second_path is not None
            and t >= self._compose_narration_second_at
        ):
            self._compose_narration_second_done = True
            second_full = self._audio_duration(self._compose_narration_second_path)
            second_cut_cap = (
                None
                if self._compose_narration_second_kind == "sentence"
                else second_full - self._compose_word_zh_cut_sec(second_full)
            )
            second_len = self._play_audio(
                self._compose_narration_second_path, max_len_sec=second_cut_cap
            )
            self._compose_narration_ready_at = max(
                self._compose_narration_ready_at, t + max(0.0, second_len)
            )

        if self._compose_narration_idx >= len(self._compose_narration_queue):
            return
        if not self._compose_narration_second_done:
            return
        earliest, wid, kind = self._compose_narration_queue[self._compose_narration_idx]
        start_at = max(earliest, self._compose_narration_ready_at)
        if t < start_at:
            return
        self._compose_narration_idx += 1

        if kind == "sentence":
            first_path, second_path = self._compose_tts_pair_for_sentence(wid)
        else:
            first_path, second_path = self._compose_tts_pair_for_word(wid)
        first_len = 0.0
        if first_path is not None:
            first_full = self._audio_duration(first_path)
            # 문장(sentence) 카드는 한국어 번역이 끝까지 재생 완료된 뒤에 중국어
            # 문장이 시작돼야 하므로(부품/결과 단어 내레이션과 달리 뒤에 고정
            # 화면 이벤트가 없어 잘라낼 이유가 없음) 끝부분을 자르지 않는다.
            cut_cap = None if kind == "sentence" else first_full - self._compose_word_tts_cut_sec(first_full)
            first_len = self._play_audio(
                first_path,
                volume=self._first_tts_playback_volume(),
                max_len_sec=cut_cap,
            )
            if first_len <= 0:
                first_len = first_full
        second_len_est = self._audio_duration(second_path)
        if second_path is not None and second_len_est > 0:
            self._compose_narration_second_path = second_path
            self._compose_narration_second_kind = kind
            self._compose_narration_second_at = t + first_len + COMPOSE_TTS_SECOND_GAP_SEC
            self._compose_narration_second_done = False
            self._compose_narration_ready_at = self._compose_narration_second_at
        else:
            self._compose_narration_second_path = None
            self._compose_narration_second_done = True
            self._compose_narration_ready_at = t + first_len

    def _sync_trap_fall_impacts(self, prev_sec: float, curr_sec: float) -> None:
        """trap 타일 낙하 착지 프레임마다 임팩트 파티클."""
        if self._word_substep != "trap_regrow":
            return
        impacts = collect_trap_fall_land_impacts(
            self._layout,
            prev_elapsed_sec=prev_sec,
            curr_elapsed_sec=curr_sec,
            frame_width=int(self._layout.frame_width),
            frame_height=int(self._layout.frame_height),
            revealed_box_keys=self._trap_regrow_revealed_keys,
            revealed_rows_by_key=self._trap_regrow_revealed_rows,
            words_by_id=self._words_by_id_for_draw(),
            card_meaning_by_id=self._card_meaning_by_id,
            meaning_lang=self._meaning_lang,
        )
        if not impacts:
            return
        for _ in impacts:
            self._play_random_hamer_sound()
        from extra.table_editor.services.word_memorize_layout import game_tile_display_px

        tile_px = game_tile_display_px(frame_width=int(self._layout.frame_width))
        self._renderer.spawn_trap_fall_land_particles(
            self._layout,
            impacts,
            tile_px=tile_px,
        )

    def _active_mining_box(self) -> WordMemorizeBox | None:
        if 0 <= self._seq_index < len(self._sequence):
            return self._sequence[self._seq_index]
        return None

    def _box_active_key(self, box: WordMemorizeBox) -> str:
        return box_runtime_key(box)

    def _outro_hold_sec(self) -> float:
        """마지막 음성 이후 종료 대기 시간 (녹화는 즉시 종료)."""
        return 0.0 if self._is_recording_mode() else END_HOLD_SEC

    def _mining_hold_sec(self, box: WordMemorizeBox) -> float:
        """곡괭이 채굴 구간 길이 (행 수와 무관하게 카드당 고정)."""
        _ = box
        return float(PICK_REVEAL_SEC)

    def _ensure_mining_complete(self) -> None:
        """채굴 타이머 만료 시 카드 행·완료 상태를 강제 반영."""
        if not self._uses_pick_mining() or not self._active_key:
            return
        box = self._active_mining_box()
        if box is None:
            return
        tile_px = game_tile_display_px(frame_width=int(self._layout.frame_width))
        row_count = card_mining_row_count(box, tile_px)
        prev = int(self._revealed_rows_by_key.get(self._active_key, 0))
        if row_count > prev:
            self._play_tile_fall_sound()
            self._renderer.spawn_mining_row_particles(
                self._layout,
                box,
                from_row=prev,
                to_row=row_count,
                tile_px=tile_px,
                revealed_box_keys=self._revealed_keys,
                words_by_id=self._words_by_id_for_draw(),
                card_meaning_by_id=self._card_meaning_by_id,
                meaning_lang=self._meaning_lang,
            )
        self._revealed_rows_by_key[self._active_key] = row_count
        self._revealed_keys.add(self._active_key)

    def _begin_trap_regrow(self) -> None:
        """trap 카드 채굴 완료 후 — 현재 타일 상태에서 중력 낙하로 벽 복구."""
        from extra.table_editor.services.word_memorize_layout import game_tile_display_px
        from studio.studios.word_memorize_pick import card_mining_row_count

        self._word_substep = "trap_regrow"
        self._trap_regrow_elapsed_sec = 0.0
        self._trap_regrow_revealed_keys = set(self._revealed_keys)
        self._trap_regrow_revealed_rows = dict(self._revealed_rows_by_key)
        if self._active_key:
            self._trap_regrow_revealed_keys.add(self._active_key)
            box = self._active_mining_box()
            if box is not None:
                tile_px = game_tile_display_px(frame_width=int(self._layout.frame_width))
                self._trap_regrow_revealed_rows[self._active_key] = card_mining_row_count(
                    box, tile_px
                )
        self._trap_regrow_duration_sec = layout_trap_regrow_duration_sec(
            self._layout,
            revealed_box_keys=self._trap_regrow_revealed_keys,
            revealed_rows_by_key=self._trap_regrow_revealed_rows,
            words_by_id=self._words_by_id_for_draw(),
            card_meaning_by_id=self._card_meaning_by_id,
            meaning_lang=self._meaning_lang,
        )
        self._hold_sec = self._trap_regrow_duration_sec
        self._renderer.reset_scorch_layer()

    def _finish_trap_regrow(self) -> None:
        """타일 복구 완료 — 종료."""
        self._trap_regrow_elapsed_sec = 0.0
        self._word_substep = ""
        self._tiles_fully_restored = True
        self._phase = "outro"
        self._active_key = None
        self._hold_sec = self._outro_hold_sec()

    def _begin_cta_pre_regrow(self) -> None:
        """CTA 음성 종료 후 1초 대기 — 이후 타일 복구."""
        self._word_substep = "cta_pre_regrow"
        self._hold_sec = float(CTA_PRE_REGROW_HOLD_SEC)

    def _begin_final_pre_regrow(self) -> None:
        """마지막 단어 종료 후 대기 — 이후 타일 복구."""
        self._word_substep = "final_pre_regrow"
        self._hold_sec = float(FINAL_TILE_REGROW_HOLD_SEC)

    def _apply_word_audio_hold(
        self,
        box: WordMemorizeBox,
        *,
        first_len: float,
        second_len: float,
        second_lead: float,
        next_lead: float,
    ) -> None:
        """첫·둘째 TTS 또는 CTA 단일 음성 대기 시간 설정."""
        if box_uses_cta_audio(box):
            self._word_substep = "first"
            self._hold_sec = max(0.0, first_len)
            self._queued_second_path = None
            self._queued_second_len = 0.0
            return
        self._word_substep = "first"
        if first_len > 0:
            self._hold_sec = max(0.0, first_len - second_lead)
            return
        if second_len > 0:
            self._word_substep = "second"
            self._hold_sec = max(0.0, second_len - next_lead)
            return
        self._word_substep = "second"
        self._hold_sec = 0.0

    def _start_tts_after_mining(self) -> None:
        """채굴 완료 후 TTS·하이라이트 타이머 시작."""
        box = self._active_mining_box()
        if box is None:
            self._word_substep = "second"
            self._hold_sec = 0.0
            return
        self._active_word_elapsed_sec = 0.0
        self._active_word_duration_sec = self._word_play_duration_sec(box)
        self._queued_second_path = None
        self._queued_second_len = 0.0
        if self._quiz_mode and box_uses_mining_regrow(box):
            self._renderer.reset_scorch_layer()
        if self._apply_word_audio_after_quiz_first(box):
            return
        first_len, second_path, second_len = self._word_tts_paths(box)
        second_lead, next_lead = self._word_tts_leads()
        self._queued_second_path = second_path
        self._queued_second_len = second_len
        self._apply_word_audio_hold(
            box,
            first_len=first_len,
            second_len=second_len,
            second_lead=second_lead,
            next_lead=next_lead,
        )

    def _should_show_quiz_reveal(self, box: WordMemorizeBox) -> bool:
        """퀴즈 모드 — 단어 공개 전 두루마리 UI (ko/zh, CTA·base 슬롯 제외)."""
        if layout_uses_compose(self._layout):
            return False
        if not self._quiz_mode or self._meaning_lang not in ("ko", "zh"):
            return False
        if box_uses_cta_audio(box):
            return False
        if is_base_slot_box(box, self._layout):
            return False
        return resolve_box_word(box) is not None

    def _quiz_reveal_tts_path(self, box: WordMemorizeBox) -> Path | None:
        """퀴즈 두루마리 TTS — ko=한글 뜻, zh=한자."""
        from audio.vocab_meaning_ko import resolve_vocab_meaning_ko_audio_path
        from audio.word_memorize_zh import resolve_word_memorize_zh_audio_path

        try:
            wid = resolve_box_word_id(box)
        except (TypeError, ValueError):
            return None
        if wid is None:
            return None
        if self._meaning_lang == "zh":
            return resolve_word_memorize_zh_audio_path(wid)
        return resolve_vocab_meaning_ko_audio_path(wid)

    def _begin_quiz_reveal(self, box: WordMemorizeBox) -> None:
        """두루마리 UI + TTS → 대기 → 페이드 아웃."""
        self._word_substep = "quiz_reveal"
        self._quiz_fade_elapsed_sec = 0.0
        self._quiz_consumed_first_tts = False
        self._quiz_gage_display_ratio = 1.0
        path = self._quiz_reveal_tts_path(box)
        tts_len = 0.0
        if path is not None and path.is_file():
            tts_len = self._play_quiz_reveal_tts(path)
            if tts_len <= 0:
                tts_len = self._audio_duration(path)
            self._quiz_consumed_first_tts = True
        else:
            try:
                wid = resolve_box_word_id(box)
            except (TypeError, ValueError):
                wid = None
            label = "한자" if self._meaning_lang == "zh" else "한글"
            logger.warning(
                "퀴즈 TTS 없음 (word_id=%s, %s). TTS 생성 후 실행하세요.",
                wid,
                label,
            )
        self._hold_sec = quiz_reveal_hold_sec(tts_len)

    def _stop_quiz_tts(self) -> None:
        """퀴즈 reveal TTS 조기 종료 — 페이드 시작 시 호출."""
        ch = self._quiz_tts_channel
        if ch is not None:
            try:
                ch.stop()
            except Exception:
                pass
        self._quiz_tts_channel = None

    def _play_quiz_reveal_tts(self, path: Path) -> float:
        """퀴즈 두루마리 TTS 재생. 재생 채널을 보관해 조기 종료에 사용."""
        self._stop_quiz_tts()
        try:
            snd = pygame.mixer.Sound(str(path))
            dur = float(snd.get_length())
            if self._is_recording_mode():
                self._log_insert_sound(path, dur)
                return dur
            self._quiz_tts_channel = snd.play()
            return dur
        except Exception as e:
            logger.debug("퀴즈 TTS 재생 실패 (%s): %s", path, e)
            return 0.0

    def _apply_word_audio_after_quiz_first(self, box: WordMemorizeBox) -> bool:
        """퀴즈에서 첫 TTS를 이미 재생했으면 둘째부터 시작. 처리했으면 True."""
        if not self._quiz_consumed_first_tts:
            return False
        self._quiz_consumed_first_tts = False
        self._active_word_elapsed_sec = 0.0
        self._active_word_duration_sec = self._word_play_duration_sec(box)
        self._queued_second_path = None
        self._queued_second_len = 0.0
        _, second_path, second_len = self._word_tts_durations(box)
        _, next_lead = self._word_tts_leads()
        if second_path is not None and second_len > 0:
            self._word_substep = "second"
            self._play_audio(second_path)
            self._hold_sec = max(0.0, second_len - next_lead)
            return True
        self._word_substep = ""
        self._hold_sec = 0.0
        return True

    def _compose_narration_total_sec(self, wid: int) -> float:
        """부품/결과 단어 하나의 예상 내레이션 총 길이(뜻·발음 TTS 둘 다 잘라낸 길이
        + 간격) — 실제로 재생하지 않고 파일 길이만 재서 화면 등장 타이밍
        (build_compose_timing)을 미리 계산하는 데 쓴다. _sync_compose_narration의
        실제 재생 컷과 동일한 비율을 써야 화면과 오디오가 어긋나지 않는다."""
        if not wid:
            return 0.0
        first_path, second_path = self._compose_tts_pair_for_word(wid)
        first_full = self._audio_duration(first_path)
        first_len = max(0.0, first_full - self._compose_word_tts_cut_sec(first_full)) if first_full > 0 else 0.0
        second_full = self._audio_duration(second_path)
        if second_full <= 0:
            return first_len
        second_len = max(0.0, second_full - self._compose_word_zh_cut_sec(second_full))
        return first_len + COMPOSE_TTS_SECOND_GAP_SEC + second_len

    def _build_compose_sentence_info(self, result_id: int | None) -> ComposeSentenceInfo:
        """4단 활용 문장 카드 데이터 — words.csv example_sentence/example_translation +
        문장 TTS 길이를 미리 재서 채운다(실제 재생 전, 화면 가라오케 워프 타이밍용).
        문장이 없는 단어는 빈 ComposeSentenceInfo()를 반환해 카드가 그려지지 않는다."""
        if not result_id:
            return ComposeSentenceInfo()
        pair = self._compose_example_sentences_by_id.get(int(result_id))
        if pair is None:
            return ComposeSentenceInfo()
        sentence_zh, translation_ko = pair
        if not sentence_zh:
            return ComposeSentenceInfo()
        ko_path, zh_path = self._compose_tts_pair_for_sentence(int(result_id))
        ko_full = self._audio_duration(ko_path)
        zh_full = self._audio_duration(zh_path)
        # 결과 단어 자체 내레이션(뜻+발음)이 완전히 끝난 뒤 잠깐 쉬었다가 카드가
        # 뜨고, 카드가 뜨는 시점부터 문장 한국어 TTS가 시작된다 — 이 계산이
        # _sync_compose_narration의 실제 큐잉(start_at = max(earliest, ready_at))과
        # 어긋나면 가라오케 워프가 실제 재생보다 앞서가거나 늦어져 보인다.
        result_ready_at = self._compose_timing.impact + self._compose_narration_total_sec(
            int(result_id)
        )
        card_start = result_ready_at + COMPOSE_SENTENCE_CARD_PAUSE_SEC
        zh_start = card_start + ko_full + COMPOSE_TTS_SECOND_GAP_SEC
        return ComposeSentenceInfo(
            sentence_zh=sentence_zh,
            translation_ko=translation_ko,
            card_start=card_start,
            zh_start=zh_start,
            zh_duration=zh_full,
        )

    def _begin_compose_word(self) -> None:
        """조합형 — 부품 2개·결과 단어 TTS(한국어 뜻→중국어 단어)는 각자 등장
        시점부터 순서대로 재생(겹치지 않게 큐잉). 부품 타일·화살표 등장 시점은
        고정이 기본이지만, 부품 내레이션이 그보다 길면 build_compose_timing이
        뒤로 늦춰 화면이 오디오보다 앞서가지 않게 한다."""
        self._word_substep = "compose"
        self._hold_sec = COMPOSE_B_TOTAL_SEC
        self._compose_sound_stage = 0

        box = self._active_mining_box()
        result_id: int | None = None
        if box is not None:
            try:
                result_id = resolve_box_word_id(box)
            except (TypeError, ValueError):
                result_id = None
        component_ids = (
            self._compose_component_ids_by_result.get(int(result_id), ())
            if result_id is not None
            else ()
        )
        self._compose_timing = build_compose_timing(
            *(self._compose_narration_total_sec(cid) for cid in component_ids)
        )
        self._compose_sentence = self._build_compose_sentence_info(result_id)
        if self._compose_sentence.sentence_zh:
            sentence_end = self._compose_sentence.zh_start + self._compose_sentence.zh_duration
            # 문장 카드(부품 내레이션·결과 내레이션 뒤에 재생)가 고정 10초 예산을 넘기면
            # 중국어 문장이 끝나기도 전에 다음 B 구간으로 넘어가 버린다 — 필요한
            # 만큼만 구간 길이를 늘린다(짧은 단어는 기존 10초 그대로 유지).
            self._hold_sec = max(
                self._hold_sec, sentence_end + COMPOSE_SENTENCE_TAIL_HOLD_SEC
            )

        part_stamps = (
            self._compose_timing.part_a_stamp,
            self._compose_timing.part_b_stamp,
            self._compose_timing.part_c_stamp,
        )
        queue: list[tuple[float, int, str]] = []
        for earliest, wid in zip(part_stamps, component_ids):
            if wid:
                queue.append((earliest, int(wid), "word"))
        if result_id:
            queue.append((self._compose_timing.impact, int(result_id), "word"))
        if self._compose_sentence.sentence_zh and result_id:
            queue.append((self._compose_sentence.card_start, int(result_id), "sentence"))
        self._compose_narration_queue = queue
        self._compose_narration_idx = 0
        self._compose_narration_ready_at = 0.0
        self._compose_narration_second_path = None
        self._compose_narration_second_kind = "word"
        self._compose_narration_second_at = 0.0
        self._compose_narration_second_done = True

    def _begin_word_content(self) -> None:
        """퀴즈 공개 후 본격 단어 진행 (조합형 · 채굴 · TTS)."""
        if layout_uses_compose(self._layout):
            self._begin_compose_word()
            return
        box = self._active_mining_box()
        if box is None:
            return
        self._active_word_elapsed_sec = 0.0
        self._pick_mining_elapsed_sec = 0.0
        self._pick_mining_last_swing_index = -1
        if self._uses_laser_highlight() and not is_base_slot_box(box, self._layout):
            self._reset_laser_glass_sound_state()
        self._active_word_duration_sec = self._word_play_duration_sec(box)
        self._queued_second_path = None
        self._queued_second_len = 0.0
        if self._uses_pick_mining():
            self._word_substep = "mining"
            self._hold_sec = self._mining_hold_sec(box)
            return
        if self._apply_word_audio_after_quiz_first(box):
            return
        first_len, second_path, second_len = self._word_tts_paths(box)
        second_lead, next_lead = self._word_tts_leads()
        self._queued_second_path = second_path
        self._queued_second_len = second_len
        self._apply_word_audio_hold(
            box,
            first_len=first_len,
            second_len=second_len,
            second_lead=second_lead,
            next_lead=next_lead,
        )

    def _begin_word(self, index: int) -> None:
        if index >= len(self._sequence):
            self._phase = "outro"
            self._active_key = None
            self._word_substep = ""
            self._hold_sec = (
                COMPOSE_REVIEW_HOLD_SEC
                if layout_uses_compose(self._layout)
                else self._outro_hold_sec()
            )
            return
        box = self._sequence[index]
        self._seq_index = index
        self._phase = "word"
        self._active_key = self._box_active_key(box)
        self._quiz_fade_elapsed_sec = 0.0
        self._quiz_consumed_first_tts = False
        self._quiz_gage_display_ratio = 1.0
        self._quiz_tts_channel: Any = None
        if self._should_show_quiz_reveal(box):
            self._begin_quiz_reveal(box)
            return
        self._begin_word_content()

    def _advance_word_step(self) -> None:
        if self._word_substep == "quiz_reveal":
            self._stop_quiz_tts()
            self._word_substep = "quiz_fade_out"
            self._quiz_fade_elapsed_sec = 0.0
            self._hold_sec = float(QUIZ_FADE_OUT_SEC)
            return
        if self._word_substep == "quiz_fade_out":
            self._finish_quiz_fade_to_word()
            return
        if self._word_substep == "glass_reveal_wait":
            self._begin_word_content()
            return
        if self._word_substep == "compose":
            box = self._active_mining_box()
            if box is not None:
                try:
                    wid = resolve_box_word_id(box)
                except (TypeError, ValueError):
                    wid = None
                if wid is not None:
                    self._compose_tray.append(int(wid))
            self._word_substep = ""
            self._advance_after_trap()
            return
        if self._word_substep == "mining":
            self._ensure_mining_complete()
            self._start_tts_after_mining()
            return
        if self._word_substep == "cta_pre_regrow":
            self._begin_trap_regrow()
            return
        if self._word_substep == "final_pre_regrow":
            self._begin_trap_regrow()
            return
        if self._word_substep == "glass_finale_hold":
            self._word_substep = "glass_finale_close"
            self._glass_finale_elapsed_sec = 0.0
            self._reset_laser_glass_sound_state()
            self._hold_sec = glass_finale_close_duration_sec()
            return
        if self._word_substep == "glass_finale_close":
            self._revealed_keys.clear()
            self._word_substep = ""
            self._glass_finale_elapsed_sec = 0.0
            self._active_key = None
            self._done = True
            self.stop_background_audio()
            return
        if self._word_substep == "trap_regrow":
            if self._renderer.trap_land_smoke_visible():
                self._hold_sec = float(TRAP_REGROW_SMOKE_POLL_SEC)
                return
            self._finish_trap_regrow()
            return
        if self._word_substep == "first":
            box = self._active_mining_box()
            if box is not None and box_uses_cta_audio(box):
                if self._quiz_mode and box_uses_mining_regrow(box):
                    self._begin_cta_pre_regrow()
                    return
                self._word_substep = ""
                self._queued_second_path = None
                self._queued_second_len = 0.0
                self._advance_after_trap()
                return
            self._word_substep = "second"
            _, next_lead = self._word_tts_leads()
            if self._queued_second_path is not None and self._queued_second_len > 0:
                self._play_audio(self._queued_second_path)
                self._hold_sec = max(0.0, self._queued_second_len - next_lead)
            else:
                self._hold_sec = 0.0
            self._queued_second_path = None
            self._queued_second_len = 0.0
            return
        self._word_substep = ""
        self._queued_second_path = None
        self._queued_second_len = 0.0
        self._sync_pick_revealed_keys()
        self._mark_laser_glass_revealed_on_advance()
        self._advance_after_trap()

    def _advance_after_trap(self) -> None:
        """trap 복구 또는 일반 단어 종료 후 다음 단어로."""
        nxt = self._seq_index + 1
        if nxt < len(self._sequence):
            self._begin_word(nxt)
            return
        if self._needs_final_tile_regrow():
            self._begin_final_pre_regrow()
            return
        if self._uses_laser_glass():
            self._begin_glass_finale()
        else:
            self._phase = "outro"
            self._active_key = None
            self._hold_sec = (
                COMPOSE_REVIEW_HOLD_SEC
                if layout_uses_compose(self._layout)
                else self._outro_hold_sec()
            )

    def _is_recording_mode(self) -> bool:
        return getattr(self._last_config, "recording_log_event", None) is not None

    def _path_for_recording(self, path: Path) -> str:
        try:
            from core.paths import get_repo_root

            return str(path.resolve().relative_to(get_repo_root())).replace("\\", "/")
        except ValueError:
            return str(path.resolve()).replace("\\", "/")

    def _log_insert_sound(
        self,
        path: Path,
        duration_sec: float,
        *,
        linear_gain: float | None = None,
    ) -> None:
        if duration_sec <= 0:
            return
        log = getattr(self._last_config, "recording_log_event", None)
        if log is None:
            return
        try:
            from studio.recording_events import InsertSound, recording_log_event

            timeline_sec = float(
                getattr(self._last_config, "recording_time_sec", 0.0) or 0.0
            )
            recording_log_event(
                log,
                InsertSound(
                    timeline_sec=timeline_sec,
                    path=self._path_for_recording(path),
                    duration_sec=float(duration_sec),
                    linear_gain=linear_gain,
                ),
            )
        except Exception:
            return

    def _audio_duration(self, path: Path | None) -> float:
        if path is None or not path.is_file():
            return 0.0
        try:
            return float(pygame.mixer.Sound(str(path)).get_length())
        except Exception:
            return 0.0

    def _first_tts_playback_volume(self) -> float:
        if self._meaning_lang == "en":
            return TTS_EN_PLAYBACK_VOLUME
        return 1.0

    def _word_tts_leads(self) -> tuple[float, float]:
        """(첫→둘째 겹침 초, 둘째→다음 단어 앞당김 초)."""
        second_lead = TTS_SECOND_LEAD_BEFORE_FIRST_END_SEC
        if self._meaning_lang == "zh":
            next_lead = TTS_ZH_MODE_KO_LEAD_BEFORE_NEXT_WORD_SEC
        else:
            next_lead = TTS_NEXT_WORD_LEAD_BEFORE_SECOND_END_SEC
        return second_lead, next_lead

    def _word_tts_pair(
        self, box: WordMemorizeBox
    ) -> tuple[Path | None, Path | None, str, str, str, str]:
        """(첫 TTS, 둘째 TTS, 첫 라벨, 둘째 라벨, 첫 파일 힌트, 둘째 파일 힌트)."""
        from audio.vocab_meaning_ko import resolve_vocab_meaning_ko_audio_path
        from audio.word_memorize_en import resolve_word_memorize_en_audio_path
        from audio.word_memorize_zh import resolve_word_memorize_zh_audio_path
        from extra.table_editor.services.word_memorize_layout import (
            box_card_type,
            box_cta_audio_path,
            card_type_label_for_value,
        )

        cta_path = box_cta_audio_path(box, meaning_lang=self._meaning_lang)
        if cta_path is not None:
            label = card_type_label_for_value(box_card_type(box))
            return (cta_path, None, label, "", cta_path.name, "")

        try:
            wid = resolve_box_word_id(box)
        except (TypeError, ValueError):
            return None, None, "", "", "", ""
        if wid is None:
            return None, None, "", "", "", ""

        zh_path = resolve_word_memorize_zh_audio_path(wid)
        ko_path = resolve_vocab_meaning_ko_audio_path(wid)
        en_path = resolve_word_memorize_en_audio_path(wid)
        if self._meaning_lang == "zh":
            return (
                zh_path,
                ko_path,
                "중국어",
                "한국어",
                f"wm_zh_word_{wid}_0.mp3",
                f"ko_word_{wid}_0.mp3",
            )
        if self._meaning_lang == "en":
            return (
                en_path,
                zh_path,
                "영어",
                "중국어",
                f"en_word_{wid}_0.mp3",
                f"wm_zh_word_{wid}_0.mp3",
            )
        return (
            ko_path,
            zh_path,
            "한국어",
            "중국어",
            f"ko_word_{wid}_0.mp3",
            f"wm_zh_word_{wid}_0.mp3",
        )

    def _word_tts_durations(
        self, box: WordMemorizeBox
    ) -> tuple[float, Path | None, float]:
        """(첫 TTS 길이, 둘째 TTS 경로, 둘째 TTS 길이) — 재생 없이 길이만."""
        first_path, second_path, _, _, _, _ = self._word_tts_pair(box)
        first_len = self._audio_duration(first_path)
        second_len = self._audio_duration(second_path)
        return first_len, second_path, second_len

    def _word_play_duration_sec(self, box: WordMemorizeBox) -> float:
        """단어 1개 재생 구간(첫·둘째 TTS) 총 길이 — 레이저 스프라이트 동기화용."""
        if box_uses_cta_audio(box):
            from extra.table_editor.services.word_memorize_layout import box_cta_audio_path

            path = box_cta_audio_path(box, meaning_lang=self._meaning_lang)
            if path is not None:
                return max(self._audio_duration(path), 0.15)
        first_len, _, second_len = self._word_tts_durations(box)
        second_lead, next_lead = self._word_tts_leads()
        total = 0.0
        if first_len > 0:
            total += max(0.0, first_len - second_lead)
            if second_len > 0:
                total += max(0.0, second_len - next_lead)
        elif second_len > 0:
            total += max(0.0, second_len - next_lead)
        return max(total, 0.15)

    def _word_tts_paths(
        self, box: WordMemorizeBox
    ) -> tuple[float, Path | None, float]:
        """(첫 TTS 재생 길이, 대기 둘째 TTS 경로, 둘째 TTS 길이)."""
        first_path, second_path, first_label, second_label, first_hint, second_hint = (
            self._word_tts_pair(box)
        )
        try:
            wid = int(box.word_id)
        except (TypeError, ValueError):
            return 0.0, None, 0.0

        if first_path is None:
            if box_uses_cta_audio(box):
                logger.warning(
                    "card_type=%s: CTA 음성 없음 (%s).",
                    box.card_type,
                    first_hint,
                )
            else:
                logger.warning(
                    "word_id=%s: %s TTS 없음 (%s). TTS 생성 후 실행하세요.",
                    wid,
                    first_label,
                    first_hint,
                )
        if second_path is None:
            logger.warning(
                "word_id=%s: %s TTS 없음 (%s). TTS 생성 후 실행하세요.",
                wid,
                second_label,
                second_hint,
            )

        second_len = self._audio_duration(second_path)
        if first_path is not None:
            first_len = self._play_audio(
                first_path, volume=self._first_tts_playback_volume()
            )
            if first_len <= 0:
                first_len = self._audio_duration(first_path)
            return first_len, second_path, second_len
        if second_path is not None:
            second_len = self._play_audio(second_path)
            if second_len <= 0:
                second_len = self._audio_duration(second_path)
        return 0.0, second_path, second_len

    def _play_audio(
        self, path: Path, *, volume: float = 1.0, max_len_sec: float | None = None
    ) -> float:
        """max_len_sec을 주면 그 길이에서 재생을 끊는다(quiz reveal TTS 조기 종료와 동일한
        기법 — 끝부분을 잘라 다음 타이밍이 밀리지 않게 함). 녹화 모드에도 동일하게
        반영되도록 로그에 남기는 길이도 잘라낸다."""
        try:
            snd = pygame.mixer.Sound(str(path))
            dur = float(snd.get_length())
            effective = dur if max_len_sec is None else max(0.0, min(dur, max_len_sec))
            if self._is_recording_mode():
                self._log_insert_sound(path, effective)
                return effective
            vol = max(0.0, min(1.0, float(volume)))
            if vol < 1.0:
                snd.set_volume(vol)
            maxtime_ms = 0 if max_len_sec is None else int(effective * 1000)
            snd.play(maxtime=maxtime_ms)
            return effective
        except Exception as e:
            logger.debug("TTS 재생 실패 (%s): %s", path, e)
            return 0.0

    def _words_by_id_for_draw(self) -> dict[int, Any]:
        """렌더용 단어 dict — CTA 타입 포함. 조합형은 박스에 없는 부품 단어도 포함해야 함."""
        out: dict[int, Any] = {}
        for box in self._layout.boxes:
            word = resolve_box_word(box, words_by_id=out)
            if word is not None:
                out[int(word.id)] = word
        if layout_uses_compose(self._layout):
            for component_ids in self._compose_component_ids_by_result.values():
                for cid in component_ids:
                    if cid and cid not in out:
                        w = get_word(cid)
                        if w is not None:
                            out[cid] = w
        return out

    def draw(self, screen: Any, config: Any) -> None:
        self._last_config = config
        words_by_id: dict[int, Any] = self._words_by_id_for_draw()

        highlight = (
            self._phase == "word"
            and self._active_key is not None
            and self._word_substep not in ("quiz_reveal", "quiz_fade_out")
        )
        glass_finale = self._word_substep in ("glass_finale_hold", "glass_finale_close")
        active_box_key: str | None = self._active_key if highlight else None
        quiz_overlay = self._word_substep in ("quiz_reveal", "quiz_fade_out")
        quiz_box = self._active_mining_box() if quiz_overlay else None
        quiz_y_offset = 0
        if self._word_substep == "quiz_fade_out":
            quiz_y_offset = quiz_fade_y_offset_px(
                int(self._layout.frame_height),
                fade_elapsed_sec=self._quiz_fade_elapsed_sec,
            )
        quiz_alpha = (
            quiz_fade_alpha(
                self._word_substep,
                fade_elapsed_sec=self._quiz_fade_elapsed_sec,
            )
            if quiz_overlay
            else 0
        )
        quiz_time_ratio: float | None = None
        if self._word_substep == "quiz_reveal":
            quiz_time_ratio = self._quiz_gage_display_ratio
        pick_mining = self._uses_pick_mining()
        revealed = frozenset(self._revealed_keys) if self._uses_revealed_keys() else frozenset()
        cta_caption = ""
        if highlight and self._word_substep == "first":
            cta_caption = active_cta_caption_for_box(
                self._active_mining_box(),
                meaning_lang=self._meaning_lang,
            )
        use_mining_elapsed = (
            highlight and pick_mining and self._word_substep == "mining"
        )
        self._renderer.draw(
            screen,
            self._layout,
            words_by_id,
            self._card_meaning_by_id,
            active_box_key=active_box_key,
            dim_inactive=False,
            config=config,
            use_video_background=(
                str(getattr(self._layout, "background_type", "video")) == "video"
            ),
            active_word_elapsed_sec=(
                self._active_word_elapsed_sec if highlight else 0.0
            ),
            active_word_duration_sec=(
                self._active_word_duration_sec if highlight else 0.0
            ),
            active_mining_elapsed_sec=(
                self._pick_mining_elapsed_sec if use_mining_elapsed else 0.0
            ),
            active_use_mining_elapsed=use_mining_elapsed,
            show_mining_pick=use_mining_elapsed,
            revealed_box_keys=revealed,
            revealed_rows_by_key=dict(self._revealed_rows_by_key),
            trap_regrow_active=self._word_substep == "trap_regrow",
            trap_regrow_elapsed_sec=(
                self._trap_regrow_elapsed_sec
                if self._word_substep == "trap_regrow"
                else 0.0
            ),
            trap_regrow_duration_sec=(
                self._trap_regrow_duration_sec
                if self._word_substep == "trap_regrow"
                else 0.0
            ),
            trap_regrow_box_key=(
                self._active_key
                if self._word_substep == "trap_regrow"
                else None
            ),
            trap_regrow_revealed_keys=(
                self._trap_regrow_revealed_keys
                if self._word_substep == "trap_regrow"
                else None
            ),
            trap_regrow_revealed_rows=(
                self._trap_regrow_revealed_rows
                if self._word_substep == "trap_regrow"
                else None
            ),
            cta_caption_text=cta_caption,
            meaning_lang=self._meaning_lang,
            quiz_mode=self._quiz_mode,
            tiles_fully_restored=self._tiles_fully_restored,
            glass_finale_substep=(
                self._word_substep if glass_finale else None
            ),
            glass_finale_elapsed_sec=self._glass_finale_elapsed_sec,
            quiz_overlay_box=quiz_box,
            quiz_overlay_alpha=quiz_alpha,
            quiz_overlay_lang=self._meaning_lang,
            quiz_time_remaining_ratio=quiz_time_ratio,
            quiz_overlay_y_offset=quiz_y_offset,
            compose_mode=layout_uses_compose(self._layout),
            compose_phase=self._phase,
            compose_word_substep=self._word_substep,
            compose_timer_sec=self._timer,
            compose_active_word_id=self._compose_active_word_id(),
            compose_sequence_word_ids=self._compose_sequence_word_ids(),
            compose_tray_word_ids=list(self._compose_tray),
            compose_component_ids_by_result=self._compose_component_ids_by_result,
            compose_timing=self._compose_timing,
            compose_absolute_time_sec=self._compose_elapsed_total_sec,
            compose_sentence=self._compose_sentence,
            compose_topic=self._layout.compose_topic,
        )

    def _compose_active_word_id(self) -> int | None:
        if self._phase != "word":
            return None
        box = self._active_mining_box()
        if box is None:
            return None
        try:
            return resolve_box_word_id(box)
        except (TypeError, ValueError):
            return None

    def _compose_sequence_word_ids(self) -> list[int]:
        out: list[int] = []
        for box in self._sequence:
            try:
                wid = resolve_box_word_id(box)
            except (TypeError, ValueError):
                wid = None
            if wid is not None:
                out.append(int(wid))
        return out

    def get_recording_prefix(self) -> Optional[str]:
        topic = _word_memorize_recording_topic(self._layout_path)
        if self._quiz_mode:
            return f"[중국어 단어 퀴즈] {topic}"
        return f"[중국어 단어] {topic}"

    def should_stop_recording(self) -> bool:
        return self._done
