"""단어 외우기 — 배치 JSON 순차 하이라이트·TTS 재생(뜻 ko/en → 중국어 한자)."""
from __future__ import annotations

import logging
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
    WordMemorizeBox,
    box_runtime_key,
    load_layout,
)
from studio.studios.word_memorize_renderer import (
    WordMemorizeRenderer,
    load_en_meaning_by_id,
    load_ko_meaning_by_id,
)

MeaningLang = Literal["ko", "en"]

logger = logging.getLogger(__name__)

INTRO_HOLD_SEC = 0.8
END_HOLD_SEC = 0.6
TTS_MISSING_HOLD_SEC = 1.2
# 영어 mp3 종료 TTS_ZH_LEAD_BEFORE_EN_END_SEC 초 전에 한자 TTS 시작
TTS_ZH_LEAD_BEFORE_EN_END_SEC = 0.8
# 한자 mp3 종료 TTS_NEXT_WORD_LEAD_BEFORE_ZH_END_SEC 초 전에 다음 단어(영어) 시작
TTS_NEXT_WORD_LEAD_BEFORE_ZH_END_SEC = 0.5
# 영어 TTS 재생 볼륨 (1.0=원본)
TTS_EN_PLAYBACK_VOLUME = 0.78

WordSubstep = Literal["", "en", "zh"]


class WordMemorizeStudio(IStudio):
    def __init__(self, *, layout_path: str, meaning_lang: MeaningLang = "ko") -> None:
        self._layout_path = Path(layout_path)
        self._layout = load_layout(self._layout_path)
        self._meaning_lang: MeaningLang = (
            "ko" if str(meaning_lang).strip().lower() == "ko" else "en"
        )
        self._renderer = WordMemorizeRenderer()
        self._renderer.set_background_stem(self._layout.background_value)
        csv_path = Path(DEFAULT_WORDS_TABLE_CSV)
        if self._meaning_lang == "ko":
            self._card_meaning_by_id = load_ko_meaning_by_id(csv_path)
        else:
            self._card_meaning_by_id = load_en_meaning_by_id(csv_path)
        self._sequence: list[WordMemorizeBox] = []
        self._seq_index = 0
        self._phase = "intro"
        self._word_substep: WordSubstep = ""
        self._timer = 0.0
        self._hold_sec = INTRO_HOLD_SEC
        self._active_key: str | None = None
        self._queued_zh_path: Path | None = None
        self._queued_zh_len = 0.0
        self._done = False
        self._last_config: Any = None
        self._bg_player: Any = None

    def init(self, config: Any = None) -> None:
        self._last_config = config
        load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)
        self._sequence = [
            b
            for b in self._layout.sorted_boxes()
            if get_word(int(b.word_id)) is not None
        ]
        if not self._sequence:
            logger.warning("단어 외우기: 배치에 표시할 단어가 없습니다 — %s", self._layout_path)
        self._init_bg_player()
        self._reset_playback()

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
        self._queued_zh_path = None
        self._queued_zh_len = 0.0
        self._done = False

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
        self._renderer.tick_background_video(dt)
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

    def _box_active_key(self, box: WordMemorizeBox) -> str:
        return box_runtime_key(box)

    def _outro_hold_sec(self) -> float:
        """마지막 음성 이후 종료 대기 시간 (녹화는 즉시 종료)."""
        return 0.0 if self._is_recording_mode() else END_HOLD_SEC

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
        self._queued_zh_path: Path | None = None
        self._queued_zh_len = 0.0
        en_len, zh_path, zh_len = self._word_tts_paths(box)
        self._word_substep = "en"
        if en_len > 0:
            self._hold_sec = max(0.0, en_len - TTS_ZH_LEAD_BEFORE_EN_END_SEC)
            self._queued_zh_path = zh_path
            self._queued_zh_len = zh_len
        elif zh_len > 0:
            self._word_substep = "zh"
            self._hold_sec = max(0.0, zh_len - TTS_NEXT_WORD_LEAD_BEFORE_ZH_END_SEC)
            self._queued_zh_path = None
            self._queued_zh_len = 0.0
        else:
            self._word_substep = "zh"
            self._hold_sec = 0.0
            return

    def _advance_word_step(self) -> None:
        box = self._sequence[self._seq_index]
        if self._word_substep == "en":
            self._word_substep = "zh"
            if self._queued_zh_path is not None and self._queued_zh_len > 0:
                self._play_audio(self._queued_zh_path)
                self._hold_sec = max(
                    0.0,
                    self._queued_zh_len - TTS_NEXT_WORD_LEAD_BEFORE_ZH_END_SEC,
                )
            else:
                self._hold_sec = 0.0
            self._queued_zh_path = None
            self._queued_zh_len = 0.0
            return
        self._word_substep = ""
        self._queued_zh_path = None
        self._queued_zh_len = 0.0
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

    def _log_insert_sound(self, path: Path, duration_sec: float) -> None:
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

    def _word_tts_paths(
        self, box: WordMemorizeBox
    ) -> tuple[float, Path | None, float]:
        """(첫 TTS 재생 길이, 대기 한자 경로, 한자 길이) — 한자는 첫 TTS 종료 전 lead 만큼 앞당겨 재생."""
        from audio.vocab_meaning_ko import resolve_vocab_meaning_ko_audio_path
        from audio.word_memorize_en import resolve_word_memorize_en_audio_path
        from audio.word_memorize_zh import resolve_word_memorize_zh_audio_path

        try:
            wid = int(box.word_id)
        except (TypeError, ValueError):
            return 0.0, None, 0.0

        if self._meaning_lang == "ko":
            meaning_path = resolve_vocab_meaning_ko_audio_path(wid)
            meaning_label = "한국어"
            meaning_file_hint = f"ko_word_{wid}_0.mp3"
        else:
            meaning_path = resolve_word_memorize_en_audio_path(wid)
            meaning_label = "영어"
            meaning_file_hint = f"en_word_{wid}_0.mp3"
        zh_path = resolve_word_memorize_zh_audio_path(wid)
        if meaning_path is None:
            logger.warning(
                "word_id=%s: %s TTS 없음 (%s). TTS 생성 후 실행하세요.",
                wid,
                meaning_label,
                meaning_file_hint,
            )
        if zh_path is None:
            logger.warning(
                "word_id=%s: 중국어 TTS 없음 (wm_zh_word_%s_0.mp3). TTS 생성 후 실행하세요.",
                wid,
                wid,
            )

        zh_len = self._audio_duration(zh_path)
        meaning_volume = 1.0 if self._meaning_lang == "ko" else TTS_EN_PLAYBACK_VOLUME
        if meaning_path is not None:
            meaning_len = self._play_audio(meaning_path, volume=meaning_volume)
            if meaning_len <= 0:
                meaning_len = self._audio_duration(meaning_path)
            return meaning_len, zh_path, zh_len
        if zh_path is not None:
            zh_len = self._play_audio(zh_path)
            if zh_len <= 0:
                zh_len = self._audio_duration(zh_path)
        return 0.0, zh_path, zh_len

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

    def draw(self, screen: Any, config: Any) -> None:
        self._last_config = config
        words_by_id: dict[int, Any] = {}
        for box in self._layout.boxes:
            try:
                wid = int(box.word_id)
            except (TypeError, ValueError):
                continue
            w = get_word(wid)
            if w is not None:
                words_by_id[wid] = w

        highlight = self._phase == "word" and self._active_key is not None
        self._renderer.draw(
            screen,
            self._layout,
            words_by_id,
            self._card_meaning_by_id,
            active_box_key=self._active_key if highlight else None,
            dim_inactive=False,
            config=config,
            use_video_background=True,
        )

    def get_recording_prefix(self) -> Optional[str]:
        stem = self._layout_path.stem.replace(" ", "_")
        return f"여포판다_단어외우기_{stem}"

    def should_stop_recording(self) -> bool:
        return self._done
