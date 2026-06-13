"""단어 외우기 — 배치 JSON 순차 하이라이트·TTS 재생(ko/en→한자, zh 모드는 한자→한국어)."""
from __future__ import annotations

import logging
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
from data.table_manager import load_words_table_from_csv
from extra.table_editor.services.word_memorize_layout import (
    PICK_REVEAL_SEC,
    TRAP_REGROW_SEC,
    TRAP_REGROW_SMOKE_POLL_SEC,
    WordMemorizeBox,
    box_runtime_key,
    box_uses_mining_regrow,
    box_uses_trap,
    game_tile_display_px,
    layout_uses_pick_mining,
    load_layout,
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
    word_memorize_pick_sound_path,
)
from studio.studios.word_memorize_renderer import (
    WordMemorizeRenderer,
    load_en_meaning_by_id,
    load_ko_meaning_by_id,
)

MeaningLang = Literal["ko", "en", "zh"]

logger = logging.getLogger(__name__)

INTRO_HOLD_SEC = 0.8
END_HOLD_SEC = 0.6
TTS_MISSING_HOLD_SEC = 1.2
# 첫 TTS 종료 N초 전에 둘째 TTS 시작 (겹침)
TTS_SECOND_LEAD_BEFORE_FIRST_END_SEC = 0.8
# ko/en: 둘째=한자 — 꼬리 N초 전에 다음 단어(뜻 TTS) 시작
TTS_NEXT_WORD_LEAD_BEFORE_SECOND_END_SEC = 0.5
# zh: 둘째=한국어 뜻 — 다음 한자로 전환 (ko/en과 동일 0.5s)
TTS_ZH_MODE_KO_LEAD_BEFORE_NEXT_WORD_SEC = 0.5
CTA_PRE_REGROW_HOLD_SEC = 1.0
# 영어 TTS 재생 볼륨 (1.0=원본)
TTS_EN_PLAYBACK_VOLUME = 0.78
# 단어 외우기 효과음 채널·볼륨 (runner: set_num_channels(8) → 0~7)
_PICK_EFFECT_CHANNEL = 4
_TILE_FALL_EFFECT_CHANNEL = 3
_HAMER_EFFECT_CHANNEL = 2
_EFFECT_CHANNEL_VOLUMES: dict[int, float] = {
    _PICK_EFFECT_CHANNEL: 1.0,
    _TILE_FALL_EFFECT_CHANNEL: 0.6,
    _HAMER_EFFECT_CHANNEL: 0.4,
}

WordSubstep = Literal[
    "",
    "mining",
    "trap_regrow",
    "cta_pre_regrow",
    "first",
    "second",
]


def _normalize_meaning_lang(raw: str) -> MeaningLang:
    lang = (raw or "ko").strip().lower()
    if lang in ("zh", "ch", "cn"):
        return "zh"
    if lang == "en":
        return "en"
    return "ko"


def _recording_lang_tag(meaning_lang: MeaningLang) -> str:
    """녹화 파일명용 언어 코드 (ko / en / ch)."""
    if meaning_lang == "en":
        return "en"
    if meaning_lang == "zh":
        return "ch"
    return "ko"


class WordMemorizeStudio(IStudio):
    def __init__(
        self,
        *,
        layout_path: str,
        meaning_lang: MeaningLang = "ko",
    ) -> None:
        self._layout_path = Path(layout_path)
        self._layout = load_layout(self._layout_path)
        self._meaning_lang = _normalize_meaning_lang(str(meaning_lang))
        self._renderer = WordMemorizeRenderer(show_images=bool(self._layout.show_images))
        self._renderer.set_background(
            self._layout.background_value, self._meaning_lang
        )
        csv_path = Path(DEFAULT_WORDS_TABLE_CSV)
        if self._meaning_lang == "en":
            self._card_meaning_by_id = load_en_meaning_by_id(csv_path)
        else:
            self._card_meaning_by_id = load_ko_meaning_by_id(csv_path)
        self._sequence: list[WordMemorizeBox] = []
        self._seq_index = 0
        self._phase = "intro"
        self._word_substep: WordSubstep = ""
        self._timer = 0.0
        self._hold_sec = INTRO_HOLD_SEC
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
        self._hold_sec = INTRO_HOLD_SEC
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
        # 녹화에서는 시작 직후 첫 단어를 바로 노출/재생한다.
        if self._phase == "intro" and self._is_recording_mode():
            self._timer = 0.0
            self._begin_word(0)
            return
        dt = float(getattr(config, "dt_sec", 1.0 / 30.0) or (1.0 / 30.0))
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
            else:
                self._active_word_elapsed_sec += dt
            if self._word_substep == "mining":
                self._sync_pick_revealed_keys()
        self._timer += dt
        if self._timer < self._hold_sec:
            return
        self._timer = 0.0
        if self._phase == "intro":
            self._begin_word(0)
        elif self._phase == "word":
            self._advance_word_step()
        elif self._phase == "outro":
            self._done = True
            self.stop_background_audio()

    def _sync_pick_revealed_keys(self) -> None:
        """곡괭이로 제거된 타일 행을 누적 저장."""
        if not layout_uses_pick_mining(self._layout):
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
        if not layout_uses_pick_mining(self._layout):
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
        if not layout_uses_pick_mining(self._layout) or not self._active_key:
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
        if box_uses_mining_regrow(box):
            self._renderer.reset_scorch_layer()
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
            self._hold_sec = self._outro_hold_sec()
            return
        box = self._sequence[index]
        self._seq_index = index
        self._phase = "word"
        self._active_key = self._box_active_key(box)
        self._active_word_elapsed_sec = 0.0
        self._pick_mining_elapsed_sec = 0.0
        self._pick_mining_last_swing_index = -1
        self._active_word_duration_sec = self._word_play_duration_sec(box)
        self._queued_second_path = None
        self._queued_second_len = 0.0
        if layout_uses_pick_mining(self._layout):
            self._word_substep = "mining"
            self._hold_sec = self._mining_hold_sec(box)
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
        if self._word_substep == "second" and self._hold_sec <= 0.0:
            return

    def _advance_word_step(self) -> None:
        if self._word_substep == "mining":
            self._ensure_mining_complete()
            self._start_tts_after_mining()
            return
        if self._word_substep == "cta_pre_regrow":
            self._begin_trap_regrow()
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
                if box_uses_mining_regrow(box):
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
        self._advance_after_trap()

    def _advance_after_trap(self) -> None:
        """trap 복구 또는 일반 단어 종료 후 다음 단어로."""
        nxt = self._seq_index + 1
        if nxt < len(self._sequence):
            self._begin_word(nxt)
        else:
            self._phase = "outro"
            self._active_key = None
            self._hold_sec = self._outro_hold_sec()

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

    def _play_audio(self, path: Path, *, volume: float = 1.0) -> float:
        try:
            snd = pygame.mixer.Sound(str(path))
            dur = float(snd.get_length())
            if self._is_recording_mode():
                self._log_insert_sound(path, dur)
                return dur
            vol = max(0.0, min(1.0, float(volume)))
            if vol < 1.0:
                snd.set_volume(vol)
            snd.play()
            return dur
        except Exception as e:
            logger.debug("TTS 재생 실패 (%s): %s", path, e)
            return 0.0

    def _words_by_id_for_draw(self) -> dict[int, Any]:
        """렌더용 단어 dict — CTA 타입 포함."""
        out: dict[int, Any] = {}
        for box in self._layout.boxes:
            word = resolve_box_word(box, words_by_id=out)
            if word is not None:
                out[int(word.id)] = word
        return out

    def draw(self, screen: Any, config: Any) -> None:
        self._last_config = config
        words_by_id: dict[int, Any] = self._words_by_id_for_draw()

        highlight = self._phase == "word" and self._active_key is not None
        active_box_key: str | None = self._active_key if highlight else None
        pick_mining = layout_uses_pick_mining(self._layout)
        revealed = frozenset(self._revealed_keys) if pick_mining else frozenset()
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
                str(getattr(self._layout, "background_type", "image")) == "video"
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
            tiles_fully_restored=self._tiles_fully_restored,
        )

    def get_recording_prefix(self) -> Optional[str]:
        stem = self._layout_path.stem.replace(" ", "_")
        lang = _recording_lang_tag(self._meaning_lang)
        return f"여포판다_단어외우기_{stem}_{lang}"

    def should_stop_recording(self) -> bool:
        return self._done
