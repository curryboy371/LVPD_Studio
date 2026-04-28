"""
단어장 스튜디오: IStudio. 집계된 단어 목록 표시 및 녹화 종료 신호(SPACE).
단어는 `VocabularyWordRow`(words.id 참조)로 보관한다.
폰트는 회화 스튜디오와 동일하게 `config.conversation_render`·`load_font_*` 경로를 쓴다.
레이아웃: 좌 20% 한자 목록, 우 80% 상단 단어 정보·하단 연상 이미지 / 획순 슬롯.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import pygame

from core.paths import get_repo_root
from data.models import VocabularyWordRow
from data.table_manager import get_word, get_word_by_hanzi
from studio.conversation.tools.fonts import (
    DEFAULT_CONVERSATION_RENDER_SETTINGS,
    ConversationRenderSettings,
    GRAY_MUTED,
    RED,
    WHITE,
)
from studio.studios.components.hanzi_animator import HanziAnimator
from utils.pinyin_processor import get_pinyin_processor
from utils.fonts import attach_font_fgcolor, load_font_chinese, load_font_chinese_freetype, load_font_korean

logger = logging.getLogger(__name__)

# --- 레이아웃 (뷰포트 비율) ---
_LEFT_PANEL_RATIO = 0.20
_RIGHT_UPPER_RATIO = 0.55  # 우측 메인 높이 중 상단(단어 정보) 비율 — 클수록 연상/획순 슬롯은 더 아래·세로 비중 감소
_LIST_ROW_H = 56
_LIST_SCROLL_STEP = 48
_HEADER_H = 48  # 제목 한 줄만 (조작 안내 문구 없음)
_LOWER_GAP = 10  # 하단 좌·우 슬롯 사이
# 하단 슬롯 가로 비율: 연상 이미지(왼) : 획순 애니메이션(오) — 오른쪽이 더 넓게
_LOWER_SLOT_WIDTH_RATIO_IMG = 3
_LOWER_SLOT_WIDTH_RATIO_STROKE = 7
_LOWER_SLOTS_TOP_PAD = 22  # 구분선 아래 ~슬롯 시작까지 여백 (슬롯 y를 더 내림)
_LOWER_SLOTS_BOTTOM_PAD = 14  # 슬롯 하단 여백
_AUTO_SOUND_GAP_SEC = 1.5
_AUTO_SOUND_REPEAT_COUNT = 2
_AUTO_WAIT_SOUND_LEN_SCALE = 1.5
_AUTO_REPLAY_SIMILARITY_THRESHOLD = 0.70
_STROKE_FIXED_PLAY_SPEED = 1.0
_GAUGE_H = 18
_GAUGE_PAD_TOP = 10
_IMAGE_CORNER_RADIUS = 16

# 품사 색상 테이블 (정확 매칭 우선, 미매칭은 기본 회색)
_POS_COLOR_TABLE: dict[str, tuple[int, int, int]] = {
    "명사": (120, 185, 255),
    "동사": (255, 160, 105),
    "형용사": (165, 230, 155),
    "부사": (200, 170, 255),
    "대명사": (255, 205, 120),
    "수사": (120, 220, 210),
    "양사": (250, 170, 210),
    "조사": (185, 185, 195),
    "감탄사": (255, 145, 170),
    "접속사": (170, 190, 255),
    "개사": (215, 205, 150),
}
_POS_DEFAULT_COLOR: tuple[int, int, int] = GRAY_MUTED


def _resolve_conversation_render_settings(config: Any) -> ConversationRenderSettings:
    if config is not None:
        cr = getattr(config, "conversation_render", None)
        if isinstance(cr, ConversationRenderSettings):
            return cr
    return DEFAULT_CONVERSATION_RENDER_SETTINGS


def _rows_from_hanzi_strings(entries: list[str]) -> list[VocabularyWordRow]:
    """레거시 한자 문자열 목록을 단어장 행으로 변환한다(마스터에 있는 단어만)."""
    seen_id: set[int] = set()
    out: list[VocabularyWordRow] = []
    seq = 0
    for s in entries:
        key = (s or "").strip()
        if not key:
            continue
        w = get_word_by_hanzi(key)
        if w is None or w.id in seen_id:
            continue
        seen_id.add(w.id)
        seq += 1
        out.append(
            VocabularyWordRow(
                id=seq,
                topic="",
                word_id=w.id,
                pronunciation_mask="",
            )
        )
    return out


def _resolve_under_repo_root(rel: str) -> Optional[Path]:
    raw = (rel or "").strip()
    if not raw:
        return None
    root = get_repo_root().resolve()
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        logger.warning("단어장: 이미지 경로가 저장소 밖입니다: %s", raw)
        return None
    return candidate if candidate.is_file() else None


def _scale_surface_to_fit(surf: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
    sw, sh = surf.get_size()
    if sw <= 0 or sh <= 0:
        return surf
    scale = min(max_w / sw, max_h / sh, 1.0)
    nw = max(1, int(sw * scale))
    nh = max(1, int(sh * scale))
    if hasattr(pygame.transform, "smoothscale"):
        return pygame.transform.smoothscale(surf, (nw, nh))
    return pygame.transform.scale(surf, (nw, nh))


def _round_surface_corners(surf: pygame.Surface, radius: int) -> pygame.Surface:
    sw, sh = surf.get_size()
    if sw <= 0 or sh <= 0:
        return surf
    r = max(0, min(int(radius), min(sw, sh) // 2))
    if r <= 0:
        return surf
    rounded = surf.copy()
    mask = pygame.Surface((sw, sh), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), pygame.Rect(0, 0, sw, sh), border_radius=r)
    rounded.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return rounded


class VocabularyStudio:
    """좌측 한자 목록 + 우측 상세(병음·뜻·품사·이미지·획순 슬롯). SPACE로 학습 완료(녹화 until-done 시 종료)."""

    def __init__(
        self,
        word_rows: Optional[list[VocabularyWordRow]] = None,
        word_entries: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        _ = kwargs
        if word_rows is not None:
            self._rows: list[VocabularyWordRow] = list(word_rows)
        else:
            self._rows = _rows_from_hanzi_strings(list(word_entries or []))
        self._font_cn_big: Optional[pygame.font.Font] = None
        self._font_cn_hero: Optional[pygame.font.Font] = None
        self._font_cn: Optional[pygame.font.Font] = None
        self._font_kr: Optional[pygame.font.Font] = None
        self._font_cn_detail: Optional[pygame.font.Font] = None
        self._font_cn_detail_ft: Any = None
        self._font_cn_hero_detail: Optional[pygame.font.Font] = None
        self._font_kr_detail: Optional[pygame.font.Font] = None
        self._font_kr_pos_detail: Optional[pygame.font.Font] = None
        self._font_hint: Optional[pygame.font.Font] = None
        self._font_title: Optional[pygame.font.Font] = None
        self._recording_done: bool = False
        self._list_scroll_px: int = 0
        self._selected_index: int = 0
        self._image_cache: dict[tuple[int, str], pygame.Surface] = {}
        self._sound_len_cache: dict[str, float] = {}
        self._auto_started: bool = False
        self._auto_phase: str = "play_sound"
        self._auto_phase_elapsed: float = 0.0
        self._auto_phase_duration: float = 0.0
        self._auto_cycle_index: int = 0
        self._auto_sound_path: str = ""
        self._auto_sound_len: float = 0.0
        self._auto_word_elapsed: float = 0.0
        self._auto_word_target_duration: float = 0.0
        self._auto_hanzi_replay_enabled: bool = False
        self._auto_hanzi_replayed: bool = False
        self._hanzi_animator = HanziAnimator()
        self._hanzi_anim_key: tuple[int, str] | None = None
        self._last_config: Any = None

    def init(self, config: Any = None) -> None:
        """회화 스튜디오와 동일한 폰트 로드(`ConversationStudio._load_fonts`와 동일 소스)."""
        self._last_config = config
        if self._font_cn_big is not None:
            return
        settings = _resolve_conversation_render_settings(config)
        fs = settings.font_sizes

        # 회화 모드와 동일한 폰트 로더/기본 크기를 사용한다.
        cn_big_size = fs.cn_big
        cn_size = fs.cn
        kr_size = fs.kr

        self._font_cn_big = load_font_chinese(cn_big_size, WHITE)
        hero_size = min(160, max(72, int(round(fs.cn_big * 1.35))))
        self._font_cn_hero = load_font_chinese(hero_size, WHITE) or self._font_cn_big
        self._font_cn = load_font_chinese(cn_size, RED)
        self._font_kr = load_font_korean(kr_size, GRAY_MUTED)

        # 단어장 상세(병음/한자/뜻/품사) 전용 폰트
        detail_scale = 2.0
        # 병음은 회화 모드와 동일한 크기/렌더 경로를 사용해 두 화면의 체감 굵기를 맞춘다.
        cn_detail_size = fs.cn_step1_pinyin
        hero_detail_size = max(72, int(round(hero_size * detail_scale)))
        kr_detail_size = max(24, int(round(kr_size * detail_scale)))
        pos_detail_size = max(24, int(round(kr_size * detail_scale * 0.82)))
        self._font_cn_detail_ft = load_font_chinese_freetype(cn_detail_size, RED)
        self._font_cn_detail = load_font_chinese(cn_detail_size, RED)
        self._font_cn_hero_detail = load_font_chinese(hero_detail_size, WHITE)
        self._font_kr_detail = load_font_korean(kr_detail_size, GRAY_MUTED)
        self._font_kr_pos_detail = load_font_korean(pos_detail_size, GRAY_MUTED)

        if self._font_cn_big is None:
            from core.paths import DEFAULT_FONT_DIR, FONT_CN_FILENAME

            self._font_cn_big = attach_font_fgcolor(pygame.font.Font(None, cn_big_size), WHITE)
            self._font_cn_hero = attach_font_fgcolor(pygame.font.Font(None, hero_size), WHITE)
            logger.warning(
                "단어장: 중국어 폰트 미로드 → 기본 폰트(중국어 네모 가능). %s → %s",
                FONT_CN_FILENAME,
                DEFAULT_FONT_DIR.resolve(),
            )
        if self._font_cn_hero is None:
            self._font_cn_hero = self._font_cn_big
        if self._font_cn is None:
            self._font_cn = attach_font_fgcolor(pygame.font.Font(None, cn_size), RED)
        if self._font_kr is None:
            self._font_kr = attach_font_fgcolor(pygame.font.Font(None, kr_size), GRAY_MUTED)
        if self._font_cn_detail is None:
            self._font_cn_detail = attach_font_fgcolor(pygame.font.Font(None, cn_detail_size), RED)
        if self._font_cn_hero_detail is None:
            self._font_cn_hero_detail = attach_font_fgcolor(
                pygame.font.Font(None, hero_detail_size), WHITE
            )
        if self._font_kr_detail is None:
            self._font_kr_detail = attach_font_fgcolor(pygame.font.Font(None, kr_detail_size), GRAY_MUTED)
        if self._font_kr_pos_detail is None:
            self._font_kr_pos_detail = attach_font_fgcolor(
                pygame.font.Font(None, pos_detail_size), GRAY_MUTED
            )
        hint_size = max(16, int(round(fs.kr * 0.82)))
        self._font_hint = load_font_korean(hint_size, (140, 140, 150)) or self._font_kr
        title_size = fs.kr
        self._font_title = load_font_korean(title_size, (230, 230, 235)) or self._font_kr

    def get_title(self) -> str:
        return "LVPD Studio - 단어"

    def _ordered_rows(self) -> list[VocabularyWordRow]:
        return sorted(
            self._rows,
            key=lambda r: (r.id if r.id else 10**9, r.topic, r.word_id),
        )

    def _clamp_selection(self, n: int) -> None:
        if n <= 0:
            self._selected_index = 0
        else:
            self._selected_index = max(0, min(self._selected_index, n - 1))

    def _scroll_selection_into_view(self, panel_inner_h: int) -> None:
        """선택 행이 좌측 패널 안에 오도록 `_list_scroll_px` 조정."""
        row_h = _LIST_ROW_H
        n = len(self._ordered_rows())
        if n <= 0:
            return
        sel = self._selected_index
        row_top = sel * row_h
        row_bottom = row_top + row_h
        scroll = self._list_scroll_px
        if row_top < scroll:
            self._list_scroll_px = row_top
        elif row_bottom > scroll + panel_inner_h:
            self._list_scroll_px = max(0, row_bottom - panel_inner_h)
        max_scroll = max(0, n * row_h - panel_inner_h)
        self._list_scroll_px = max(0, min(self._list_scroll_px, max_scroll))

    def handle_events(self, events: list, config: Any = None) -> bool:
        _ = config
        ordered = self._ordered_rows()
        n = len(ordered)
        main_h = 0
        if config is not None:
            main_h = max(0, int(config.height) - _HEADER_H)
        panel_inner_h = max(1, main_h - 16)

        for e in events:
            if e.type != pygame.KEYDOWN:
                continue
            if e.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self._recording_done = True
                continue
        return True

    def update(self, config: Any = None) -> None:
        self._last_config = config
        dt = float(getattr(config, "dt_sec", 0.0) or 0.0) if config is not None else 0.0
        self._tick_auto_sequence(dt)
        ordered = self._ordered_rows()
        self._clamp_selection(len(ordered))
        if ordered:
            self._sync_hanzi_anim_for_selected_word()
        else:
            if self._hanzi_anim_key is not None:
                self._hanzi_anim_key = None
                self._hanzi_animator.reset()
        self._hanzi_animator.update(dt)
        if (
            ordered
            and self._auto_hanzi_replay_enabled
            and not self._auto_hanzi_replayed
            and not self._hanzi_animator.is_playing()
            and self._hanzi_animator.has_data()
        ):
            self._hanzi_animator.replay()
            self._auto_hanzi_replayed = True

    def _hanzi_only(self, row: VocabularyWordRow) -> str:
        w = get_word(row.word_id)
        if w is not None and (w.word or "").strip():
            return (w.word or "").strip()
        return f"(id={row.word_id})"

    def _pronunciation_subline(self, row: VocabularyWordRow) -> str:
        w = get_word(row.word_id)
        if w is None:
            return ""
        mask_raw = (row.pronunciation_mask or "").strip()
        hanzi = (w.word or "").strip()
        if hanzi:
            try:
                pp = get_pinyin_processor()
                if pp.available:
                    lexical_list = pp.get_lexical_pinyin(hanzi)
                    if lexical_list:
                        # pronunciation_mask 규칙:
                        # - 0: 해당 음절 성조 유지
                        # - 1~5: 해당 음절 성조 강제(5=경성)
                        # 마스크 길이가 짧으면 남은 음절은 유지한다.
                        mask_tokens = [m for m in re.split(r"[\s,|]+", mask_raw) if m] if mask_raw else []
                        if len(mask_tokens) == 1 and len(mask_tokens[0]) == len(lexical_list):
                            mask_tokens = list(mask_tokens[0])
                        adjusted: list[str] = []
                        for i, syl in enumerate(lexical_list):
                            base, tone = pp._split_tone(syl)  # 기존 모듈 파서 재사용
                            if not base:
                                adjusted.append(syl)
                                continue
                            cur_tone = int(tone) if tone is not None else 0
                            if i < len(mask_tokens):
                                tok = mask_tokens[i].strip()
                                if tok.isdigit():
                                    v = int(tok)
                                    if v == 0:
                                        pass
                                    elif 1 <= v <= 5:
                                        cur_tone = v
                            adjusted_num = f"{base}{cur_tone}" if cur_tone > 0 else base
                            adjusted.append(pp.tone3_to_mark(adjusted_num))
                        generated = " ".join(adjusted).strip()
                        if generated:
                            return generated
            except Exception:
                pass
        if (w.pinyin or "").strip():
            return (w.pinyin or "").strip()
        return ""

    def _parse_pos_items(self, pos_raw: str) -> list[str]:
        """품사 문자열을 다중 항목으로 분리한다. (|, ,, / 지원)"""
        raw = (pos_raw or "").strip()
        if not raw:
            return []
        parts = re.split(r"[|,/]+", raw)
        out: list[str] = []
        seen: set[str] = set()
        for p in parts:
            token = p.strip()
            if not token or token in seen:
                continue
            seen.add(token)
            out.append(token)
        return out

    def _render_pinyin_surface(self, text: str) -> Optional[pygame.Surface]:
        content = (text or "").strip()
        if not content:
            return None
        if self._font_cn_detail_ft is not None:
            try:
                surf, _ = self._font_cn_detail_ft.render(content, RED)
                return surf
            except Exception:
                pass
        if self._font_cn_detail is None:
            return None
        return self._font_cn_detail.render(content, True, RED)

    def _parse_meaning_items(self, meaning_raw: str) -> list[str]:
        """뜻 문자열을 `|` 기준으로 다중 항목 분리한다."""
        raw = (meaning_raw or "").strip()
        if not raw:
            return []
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        out: list[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    def _get_scaled_word_image(self, word_id: int, img_path: str) -> Optional[pygame.Surface]:
        key = (word_id, (img_path or "").strip())
        if key in self._image_cache:
            return self._image_cache[key]
        resolved = _resolve_under_repo_root(img_path)
        if resolved is None:
            return None
        try:
            surf = pygame.image.load(str(resolved)).convert_alpha()
        except (pygame.error, OSError, ValueError) as ex:
            logger.debug("단어장 이미지 로드 실패 word_id=%s: %s", word_id, ex)
            return None
        self._image_cache[key] = surf
        return surf

    def _resolve_sound_abs(self, sound_path: str) -> str:
        raw = (sound_path or "").strip()
        if not raw:
            return ""
        p = Path(raw)
        if p.is_absolute():
            return str(p)
        return str((get_repo_root().resolve() / raw).resolve())

    def _get_sound_length_sec(self, sound_abs_path: str) -> float:
        key = (sound_abs_path or "").strip()
        if not key:
            return 0.0
        if key in self._sound_len_cache:
            return self._sound_len_cache[key]
        try:
            if pygame.mixer.get_init() is None:
                from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
            length = float(pygame.mixer.Sound(key).get_length() or 0.0)
        except Exception:
            length = 0.0
        self._sound_len_cache[key] = length
        return length

    def _play_sound_now(self, sound_abs_path: str) -> None:
        key = (sound_abs_path or "").strip()
        if not key:
            return
        try:
            if pygame.mixer.get_init() is None:
                from core.paths import STUDIO_AUDIO_SAMPLE_RATE

                pygame.mixer.init(STUDIO_AUDIO_SAMPLE_RATE, -16, 2, 4096)
            snd = pygame.mixer.Sound(key)
            ch = pygame.mixer.Channel(7)
            ch.play(snd)
            self._log_insert_sound_event(key, snd)
        except Exception as ex:
            logger.debug("단어장 사운드 재생 실패: %s", ex)

    def _log_insert_sound_event(self, sound_abs_path: str, snd: Any) -> None:
        """녹화 모드면 단어장 사운드 재생을 InsertSound 이벤트로 기록한다."""
        cfg = self._last_config
        log = getattr(cfg, "recording_log_event", None) if cfg is not None else None
        if log is None:
            return
        try:
            from studio.recording_events import InsertSound, recording_log_event

            timeline_sec = float(getattr(cfg, "recording_time_sec", 0.0) or 0.0)
            duration_sec = float(getattr(snd, "get_length", lambda: 0.0)() or 0.0)
            recording_log_event(
                log,
                InsertSound(
                    timeline_sec=timeline_sec,
                    path=str(sound_abs_path),
                    duration_sec=duration_sec,
                ),
            )
        except Exception:
            return

    def _begin_phase(self, phase: str, duration: float) -> None:
        self._auto_phase = phase
        self._auto_phase_duration = max(0.0, float(duration))
        self._auto_phase_elapsed = 0.0
        if phase == "play_sound" and self._auto_sound_path:
            self._play_sound_now(self._auto_sound_path)

    def _sync_hanzi_anim_for_selected_word(self) -> None:
        ordered = self._ordered_rows()
        if not ordered:
            if self._hanzi_anim_key is not None:
                self._hanzi_anim_key = None
                self._hanzi_animator.reset()
            return
        self._clamp_selection(len(ordered))
        cur = ordered[self._selected_index]
        w = get_word(cur.word_id)
        hanzi = (w.word or "").strip() if w else ""
        key = (cur.word_id, hanzi)
        if self._hanzi_anim_key != key:
            self._hanzi_anim_key = key
            self._hanzi_animator.set_text(hanzi, play_speed=_STROKE_FIXED_PLAY_SPEED)

    def _setup_current_word_cycle(self) -> None:
        ordered = self._ordered_rows()
        if not ordered:
            return
        self._clamp_selection(len(ordered))
        self._sync_hanzi_anim_for_selected_word()
        cur = ordered[self._selected_index]
        w = get_word(cur.word_id)
        self._auto_sound_path = self._resolve_sound_abs((w.sound_path if w else "") or "")
        self._auto_sound_len = self._get_sound_length_sec(self._auto_sound_path)
        self._auto_cycle_index = 0
        self._auto_word_elapsed = 0.0
        sound_cycle_duration = (
            self._auto_sound_len
            + _AUTO_SOUND_GAP_SEC
            + (self._auto_sound_len * _AUTO_WAIT_SOUND_LEN_SCALE)
            + _AUTO_SOUND_GAP_SEC
        )
        sound_total_duration = sound_cycle_duration * _AUTO_SOUND_REPEAT_COUNT
        hanzi_total_duration = self._hanzi_animator.total_duration_sec()
        similarity_ratio = 0.0
        if sound_cycle_duration > 1e-6 and hanzi_total_duration > 1e-6:
            similarity_ratio = min(sound_cycle_duration, hanzi_total_duration) / max(
                sound_cycle_duration, hanzi_total_duration
            )
        self._auto_hanzi_replay_enabled = similarity_ratio >= _AUTO_REPLAY_SIMILARITY_THRESHOLD
        self._auto_hanzi_replayed = False
        hanzi_target_duration = (
            hanzi_total_duration * 2.0 if self._auto_hanzi_replay_enabled else hanzi_total_duration
        )
        self._auto_word_target_duration = max(sound_total_duration, hanzi_target_duration)
        self._begin_phase("play_sound", self._auto_sound_len)

    def _advance_to_next_word_or_done(self, rows_count: int) -> None:
        if self._selected_index >= rows_count - 1:
            self._recording_done = True
            return
        self._selected_index += 1
        self._setup_current_word_cycle()

    def _tick_auto_sequence(self, dt_sec: float) -> None:
        ordered = self._ordered_rows()
        n = len(ordered)
        dt = max(0.0, float(dt_sec))
        if n <= 0 or self._recording_done:
            return
        if not self._auto_started:
            # 단어장은 항상 id 1(정렬 첫 행)부터 시작
            self._selected_index = 0
            self._auto_started = True
            self._setup_current_word_cycle()
            return

        self._auto_word_elapsed += dt

        if self._auto_phase == "play_sound":
            self._auto_phase_elapsed += dt
            if self._auto_phase_elapsed < self._auto_phase_duration:
                return
            self._begin_phase("wait_after_play", _AUTO_SOUND_GAP_SEC)
            return

        if self._auto_phase == "wait_after_play":
            self._auto_phase_elapsed += dt
            if self._auto_phase_elapsed >= self._auto_phase_duration:
                self._begin_phase("wait_sound_len", self._auto_sound_len * _AUTO_WAIT_SOUND_LEN_SCALE)
                return
            return

        if self._auto_phase == "wait_sound_len":
            self._auto_phase_elapsed += dt
            if self._auto_phase_elapsed < self._auto_phase_duration:
                return
            self._begin_phase("wait_after_len", _AUTO_SOUND_GAP_SEC)
            return

        if self._auto_phase == "wait_after_len":
            self._auto_phase_elapsed += dt
            if self._auto_phase_elapsed < self._auto_phase_duration:
                return
            if self._auto_cycle_index + 1 < _AUTO_SOUND_REPEAT_COUNT:
                self._auto_cycle_index += 1
                self._begin_phase("play_sound", self._auto_sound_len)
                return
            remain = max(0.0, self._auto_word_target_duration - self._auto_word_elapsed)
            if remain > 1e-6:
                self._begin_phase("wait_sync_hold", remain)
                return
            self._advance_to_next_word_or_done(n)
            return

        if self._auto_phase == "wait_sync_hold":
            self._auto_phase_elapsed += dt
            if self._auto_phase_elapsed < self._auto_phase_duration:
                return
            self._advance_to_next_word_or_done(n)
            return

    def draw(self, screen: Any, config: Any) -> None:
        bg = getattr(config, "bg_color", (20, 20, 25))
        screen.fill(bg)
        if self._font_cn_big is None:
            self.init(config)
        assert self._font_cn_big is not None
        assert self._font_cn_hero is not None
        assert self._font_cn is not None
        assert self._font_kr is not None
        assert self._font_cn_detail is not None
        assert self._font_cn_hero_detail is not None
        assert self._font_kr_detail is not None
        assert self._font_kr_pos_detail is not None
        assert self._font_hint is not None
        assert self._font_title is not None

        w, h = int(config.width), int(config.height)
        title = self._font_title.render("단어 정리", True, WHITE)
        title_x = (w - title.get_width()) // 2
        title_y = max(0, (_HEADER_H - title.get_height()) // 2)
        screen.blit(title, (title_x, title_y))

        main_top = _HEADER_H
        main_h = max(1, h - main_top)
        left_w = max(80, int(w * _LEFT_PANEL_RATIO))
        right_x = left_w
        right_w = w - left_w

        left_rect = pygame.Rect(0, main_top, left_w, main_h)
        panel_bg = (26, 26, 32)
        pygame.draw.rect(screen, panel_bg, left_rect)
        pygame.draw.line(screen, (55, 55, 62), (left_w, main_top), (left_w, h), 1)

        ordered = self._ordered_rows()
        self._clamp_selection(len(ordered))
        panel_inner_h = max(1, main_h - 16)
        self._scroll_selection_into_view(panel_inner_h)

        if not ordered:
            line = self._font_hint.render(
                "(이번 회차에서 추출된 단어 없음)", True, (160, 160, 170)
            )
            screen.blit(line, (right_x + 24, main_top + 24))
            return

        # --- 좌측 한자 목록 (클리핑) ---
        list_pad_top = main_top + 8
        list_pad_x = 0
        inner_h = main_h - 16
        old_clip = screen.get_clip()
        clip_r = pygame.Rect(list_pad_x, list_pad_top, left_w, inner_h)
        screen.set_clip(clip_r)
        row_h = _LIST_ROW_H
        scroll = self._list_scroll_px
        for i, row in enumerate(ordered):
            y_base = list_pad_top + i * row_h - scroll
            if y_base > main_top + main_h or y_base + row_h < main_top:
                continue
            hanzi = self._hanzi_only(row)
            if i < self._selected_index:
                text_color = (140, 140, 150)  # 지나간 단어: 회색
            elif i == self._selected_index:
                text_color = (110, 180, 255)  # 현재 단어: 파란색
            else:
                text_color = (220, 220, 225)  # 아직 안 지난 단어: 기본색
            surf = self._font_cn_big.render(hanzi, True, text_color)
            cx = list_pad_x + left_w // 2
            ty = y_base + (row_h - surf.get_height()) // 2
            if i == self._selected_index:
                sel_rect = pygame.Rect(list_pad_x + 4, y_base + 2, left_w - 8, row_h - 4)
                pygame.draw.rect(screen, (48, 52, 72), sel_rect, border_radius=4)
            tx = cx - surf.get_width() // 2
            screen.blit(surf, (tx, ty))
        screen.set_clip(old_clip)

        # --- 우측 ---
        right_rect = pygame.Rect(right_x, main_top, right_w, main_h)
        cur = ordered[self._selected_index]
        word = get_word(cur.word_id)

        upper_h = max(120, int(main_h * _RIGHT_UPPER_RATIO))
        lower_top = main_top + upper_h
        lower_h = main_h - upper_h
        pygame.draw.line(screen, (55, 55, 62), (right_x, lower_top), (w, lower_top), 1)

        pinyin = self._pronunciation_subline(cur)
        meaning_items = self._parse_meaning_items((word.meaning or "").strip() if word else "")
        pos_items = self._parse_pos_items((word.pos or "").strip() if word else "")
        hero_text = self._hanzi_only(cur)

        # 요청 UI: 병음(빨강) → 한자(흰색, 가장 크게) → 뜻(회색) → 품사(회색), 모두 가운데 정렬
        # 품사는 전용 폰트(대형)로 렌더링한다.
        center_x = right_rect.x + right_rect.width // 2
        top_pad = 14
        block_items: list[tuple[pygame.Surface, int]] = []

        def compose_inline_row(
            items: list[tuple[str, tuple[int, int, int]]],
            font: pygame.font.Font,
            item_gap: int,
        ) -> Optional[pygame.Surface]:
            rendered = [font.render(text, True, color) for text, color in items if text]
            if not rendered:
                return None
            if len(rendered) == 1:
                return rendered[0]
            total_w = sum(s.get_width() for s in rendered) + item_gap * (len(rendered) - 1)
            row_h = max(s.get_height() for s in rendered)
            row = pygame.Surface((max(1, total_w), max(1, row_h)), pygame.SRCALPHA)
            x = 0
            for idx, surf in enumerate(rendered):
                y = (row_h - surf.get_height()) // 2
                row.blit(surf, (x, y))
                x += surf.get_width()
                if idx < len(rendered) - 1:
                    x += item_gap
            return row

        if pinyin:
            pinyin_surf = self._render_pinyin_surface(pinyin)
            if pinyin_surf is not None:
                block_items.append((pinyin_surf, 16))
        block_items.append((self._font_cn_hero_detail.render(hero_text, True, WHITE), 24))
        meaning_row = compose_inline_row(
            [(meaning, GRAY_MUTED) for meaning in meaning_items],
            self._font_kr_detail,
            item_gap=36,
        )
        if meaning_row is not None:
            block_items.append((meaning_row, 12))
        pos_row = compose_inline_row(
            [(pos, _POS_COLOR_TABLE.get(pos, _POS_DEFAULT_COLOR)) for pos in pos_items],
            self._font_kr_pos_detail,
            item_gap=36,
        )
        if pos_row is not None:
            block_items.append((pos_row, 0))

        total_h = 0
        for idx, (surf, gap_after) in enumerate(block_items):
            total_h += surf.get_height()
            if idx < len(block_items) - 1:
                total_h += gap_after
        upper_center_y = main_top + (upper_h // 2)
        start_y = max(main_top + top_pad, upper_center_y - total_h // 2)

        draw_y = start_y
        for idx, (surf, gap_after) in enumerate(block_items):
            draw_x = center_x - (surf.get_width() // 2)
            screen.blit(surf, (draw_x, draw_y))
            draw_y += surf.get_height()
            if idx < len(block_items) - 1:
                draw_y += gap_after

        # 진행 게이지:
        # - 오디오 재생 구간: 파란색
        # - 오디오 길이 대기 구간: 주황색
        gauge_color: Optional[tuple[int, int, int]] = None
        gauge_progress: float = 0.0
        if self._auto_phase == "play_sound":
            gauge_color = (90, 220, 120)
            gauge_progress = (
                min(1.0, max(0.0, self._auto_phase_elapsed / self._auto_phase_duration))
                if self._auto_phase_duration > 0
                else 1.0
            )
        elif self._auto_phase == "wait_after_play":
            gauge_color = (90, 220, 120)
            gauge_progress = 1.0
        elif self._auto_phase == "wait_sound_len":
            gauge_color = (255, 170, 85)
            gauge_progress = (
                min(1.0, max(0.0, self._auto_phase_elapsed / self._auto_phase_duration))
                if self._auto_phase_duration > 0
                else 1.0
            )
        elif self._auto_phase == "wait_after_len":
            gauge_color = (255, 170, 85)
            gauge_progress = 1.0
        elif self._auto_phase == "wait_sync_hold":
            gauge_color = (255, 170, 85)
            gauge_progress = 1.0
        if gauge_color is not None:
            gauge_w = min(max(140, int(right_w * 0.62)), max(140, right_w - 60))
            gauge_x = right_x + (right_w - gauge_w) // 2
            gauge_y = int(draw_y + _GAUGE_PAD_TOP)
            gauge_y = min(gauge_y, lower_top - _GAUGE_H - 8)
            gauge_y = max(main_top + 6, gauge_y)
            gauge_bg = pygame.Rect(gauge_x, gauge_y, gauge_w, _GAUGE_H)
            pygame.draw.rect(screen, (55, 55, 62), gauge_bg, border_radius=8)
            fill_w = int(gauge_w * min(1.0, max(0.0, gauge_progress)))
            if fill_w > 0:
                gauge_fg = pygame.Rect(gauge_x, gauge_y, fill_w, _GAUGE_H)
                pygame.draw.rect(screen, gauge_color, gauge_fg, border_radius=8)

        # --- 하단: 연상 이미지 | 획순 슬롯 ---
        slot_y = lower_top + _LOWER_SLOTS_TOP_PAD
        slot_h = max(1, lower_h - _LOWER_SLOTS_TOP_PAD - _LOWER_SLOTS_BOTTOM_PAD)
        # 우측 패널 좌우 20px 여백, 가운데 `_LOWER_GAP`, 남은 폭을 비율 상수대로 분할
        _rsum = _LOWER_SLOT_WIDTH_RATIO_IMG + _LOWER_SLOT_WIDTH_RATIO_STROKE
        lower_inner_w = max(1, right_w - 40 - _LOWER_GAP)
        img_slot_w = (lower_inner_w * _LOWER_SLOT_WIDTH_RATIO_IMG) // _rsum
        stroke_slot_w = lower_inner_w - img_slot_w
        img_slot_x = right_x + 20
        stroke_slot_x = img_slot_x + img_slot_w + _LOWER_GAP

        def draw_slot_frame(rect: pygame.Rect) -> None:
            pygame.draw.rect(screen, (32, 32, 38), rect, border_radius=6)
            pygame.draw.rect(screen, (70, 70, 78), rect, 1, border_radius=6)

        img_rect = pygame.Rect(img_slot_x, slot_y, img_slot_w, slot_h)
        stroke_rect = pygame.Rect(stroke_slot_x, slot_y, stroke_slot_w, slot_h)

        draw_slot_frame(img_rect)
        draw_slot_frame(stroke_rect)

        img_path = (word.img_path if word else "") or ""
        scaled: Optional[pygame.Surface] = None
        if word and img_path:
            raw = self._get_scaled_word_image(word.id, img_path)
            if raw is not None:
                image_inner_pad = 16
                iw = img_rect.width - (image_inner_pad * 2)
                ih = img_rect.height - (image_inner_pad * 2)
                scaled = _scale_surface_to_fit(raw, max(1, iw), max(1, ih))

        if scaled is not None:
            scaled = _round_surface_corners(scaled, _IMAGE_CORNER_RADIUS)
            ix = img_rect.x + (img_rect.width - scaled.get_width()) // 2
            iy = img_rect.y + (img_rect.height - scaled.get_height()) // 2
            screen.blit(scaled, (ix, iy))
        else:
            ph = self._font_hint.render("이미지 없음 또는 로드 실패", True, (100, 100, 110))
            screen.blit(
                ph,
                (
                    img_rect.x + (img_rect.width - ph.get_width()) // 2,
                    img_rect.y + img_rect.height // 2,
                ),
            )

        if not self._hanzi_animator.draw(screen, stroke_rect):
            ph2 = self._font_hint.render("획순 데이터 없음", True, (100, 100, 110))
            screen.blit(
                ph2,
                (
                    stroke_rect.x + (stroke_rect.width - ph2.get_width()) // 2,
                    stroke_rect.y + stroke_rect.height // 2,
                ),
            )

    def get_recording_prefix(self) -> Optional[str]:
        return None

    def should_stop_recording(self) -> bool:
        return self._recording_done
