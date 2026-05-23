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
from studio.conversation.bg_audio import ConversationBackgroundPlayer
from studio.conversation.core.types import (
    ColorStyle,
    LayoutStyle,
    SentenceStyleConfig,
    TextStyle,
    build_sentence_render_data_with_tone_icons,
)
from studio.conversation.tools.common_drawer import CommonDrawer
from studio.conversation.tools.fonts import (
    DEFAULT_CONVERSATION_RENDER_SETTINGS,
    ConversationFontSizes,
    ConversationRenderSettings,
    GRAY_MUTED,
    RED,
    WHITE,
)
from studio.shorts.tools.fonts import ShortsFontSizes, build_font_bundle
from studio.shorts.tools.karaoke_renderer import KaraokeRenderer
from studio.studios.components.hanzi_animator import HanziAnimator
from utils.pinyin_masking import get_masked_pinyin_marks
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
_AUTO_MEANING_GAP_SEC = 0.5
# 한자 블록 아래 품사·뜻 (숏츠 단어 모드와 동일: 품사 → 뜻)
_VOCAB_POS_AFTER_HANZI_GAP = 16
_VOCAB_MEANING_AFTER_POS_GAP = 12
# words.sound_path 없음·파일 없음·길이 0일 때 자동 시퀀스 타이밍(초)
_FALLBACK_SOUND_LEN_SEC = 1.0
_AUTO_REPLAY_SIMILARITY_THRESHOLD = 0.70
_STROKE_FIXED_PLAY_SPEED = 1.0
_IMAGE_CORNER_RADIUS = 16
_TITLE_INTRO_FADE_SEC = 1.4

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
        self._title_image_surface: Optional[pygame.Surface] = None
        self._conversation_title_reference_surface: Optional[pygame.Surface] = None
        self._recording_done: bool = False
        self._list_scroll_px: int = 0
        self._selected_index: int = 0
        self._image_cache: dict[tuple[int, str], pygame.Surface] = {}
        self._sound_len_cache: dict[str, float] = {}
        self._auto_started: bool = False
        self._auto_phase: str = "idle"
        self._auto_phase_elapsed: float = 0.0
        self._auto_phase_duration: float = 0.0
        self._auto_cycle_index: int = 0
        self._auto_sound_path: str = ""
        self._auto_sound_len: float = 0.0
        self._auto_meaning_ko_path: str = ""
        self._auto_meaning_ko_len: float = 0.0
        self._auto_word_elapsed: float = 0.0
        self._auto_word_target_duration: float = 0.0
        self._auto_hanzi_replay_enabled: bool = False
        self._auto_hanzi_replayed: bool = False
        self._hanzi_animator = HanziAnimator()
        self._hanzi_anim_key: tuple[int, str] | None = None
        self._last_config: Any = None
        self._intro_total_sec: float = _TITLE_INTRO_FADE_SEC
        self._intro_remaining_sec: float = _TITLE_INTRO_FADE_SEC
        self._bg_player: ConversationBackgroundPlayer | None = None
        self._common_drawer: CommonDrawer | None = None
        self._karaoke: KaraokeRenderer | None = None
        self._karaoke_style: SentenceStyleConfig | None = None
        self._render_font_sizes: ConversationFontSizes | None = None

    def init(self, config: Any = None) -> None:
        """회화 스튜디오와 동일한 폰트 로드(`ConversationStudio._load_fonts`와 동일 소스)."""
        self._last_config = config
        # 모드 재진입(또는 동일 인스턴스 재초기화) 시에도 타이틀 인트로를 항상 다시 시작한다.
        self._intro_total_sec = _TITLE_INTRO_FADE_SEC
        self._intro_remaining_sec = _TITLE_INTRO_FADE_SEC
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
        self._title_image_surface = self._load_title_image_surface("단어_공부하기.png")
        self._conversation_title_reference_surface = self._load_title_image_surface("문장_이해하기.png")
        self._bg_player = ConversationBackgroundPlayer(
            on_bg_started=self._log_bg_insert_sound,
            is_recording=self._is_recording_mode,
        )
        fs = _resolve_conversation_render_settings(config).font_sizes
        self._render_font_sizes = fs
        self._init_karaoke_drawer(fs)

    def start_playback(self) -> None:
        """F5 debug: 창 표시·mixer 준비 후 배경음 재생."""
        if self._bg_player is None:
            return
        self._bg_player.start_session(
            duration_hint_sec=self._bg_duration_hint_sec(self._last_config),
            reload=True,
        )

    def begin_recording_session(self, config: Any) -> None:
        """record 루프 직전: 녹화 타임라인용 bg InsertSound 기록."""
        self._last_config = config
        if self._bg_player is None:
            return
        self._bg_player.start_session(duration_hint_sec=self._bg_duration_hint_sec(config))

    def stop_background_audio(self) -> None:
        if self._bg_player is not None:
            self._bg_player.stop_session()

    def _is_recording_mode(self) -> bool:
        cfg = self._last_config
        return getattr(cfg, "recording_log_event", None) is not None

    def _bg_duration_hint_sec(self, config: Any) -> float:
        if config is not None and getattr(config, "recording_log_event", None) is not None:
            return max(60.0, float(getattr(config, "record_max_sec", 3600.0) or 3600.0))
        return 3600.0

    def _log_bg_insert_sound(self, path: str, duration_sec: float) -> None:
        if not path:
            return
        cfg = self._last_config
        log = getattr(cfg, "recording_log_event", None) if cfg is not None else None
        if log is None:
            return
        try:
            from studio.recording_events import InsertSound, recording_log_event

            timeline_sec = float(getattr(cfg, "recording_time_sec", 0.0) or 0.0)
            recording_log_event(
                log,
                InsertSound(
                    timeline_sec=timeline_sec,
                    path=str(path),
                    duration_sec=max(0.0, float(duration_sec)),
                ),
            )
        except Exception:
            return

    def _load_title_image_surface(self, filename: str) -> Optional[pygame.Surface]:
        root = Path(__file__).resolve().parents[2]
        candidates = (
            root / "resource" / "image" / "icon" / filename,
            root / "resource" / "image" / "title" / filename,
            root / "resource" / "image" / filename,
        )
        for path in candidates:
            if not path.exists():
                continue
            try:
                return pygame.image.load(str(path))
            except Exception:
                continue
        return None

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
        if dt <= 0.0 and config is not None:
            fps = float(getattr(config, "fps", 30) or 30)
            dt = 1.0 / max(1.0, fps)
        if self._intro_remaining_sec > 0.0:
            self._intro_remaining_sec = max(0.0, self._intro_remaining_sec - max(0.0, dt))
            if self._bg_player is not None:
                self._bg_player.tick(duration_hint_sec=self._bg_duration_hint_sec(config))
            return
        if self._bg_player is not None:
            self._bg_player.tick(duration_hint_sec=self._bg_duration_hint_sec(config))
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
        hanzi = (w.word or "").strip()
        if hanzi:
            try:
                generated = get_masked_pinyin_marks(hanzi, (w.masking or "").strip())
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

    def _init_karaoke_drawer(self, fs: ConversationFontSizes) -> None:
        sizes = ShortsFontSizes(
            cn=max(48, int(fs.cn_step1_hanzi)),
            pinyin=max(28, int(fs.cn_step1_pinyin)),
            kr=max(28, int(fs.kr_step1)),
        )
        self._common_drawer = CommonDrawer(fonts=build_font_bundle(sizes))
        self._karaoke = KaraokeRenderer(drawer=self._common_drawer)
        self._karaoke_style = SentenceStyleConfig(
            colors=ColorStyle(hanzi_color=WHITE, pinyin_color=RED, translation_color=GRAY_MUTED),
            layout=LayoutStyle(line_gap_px=20, translation_extra_gap_px=8, min_margin_x=16),
            text=TextStyle(max_hanzi=12, max_pinyin=80, max_translation=120),
        )

    def _word_karaoke_item(self, row: VocabularyWordRow, word: Any) -> dict:
        hanzi = self._hanzi_only(row)
        pinyin = self._pronunciation_subline(row)
        meanings = self._parse_meaning_items((word.meaning or "").strip() if word else "")
        meaning_line = " · ".join(meanings) if meanings else ""
        return {
            "sentence": [hanzi],
            "pinyin": pinyin,
            "pinyin_marks": pinyin,
            "translation": [meaning_line] if meaning_line else [],
        }

    def _vocab_karaoke_timing(self) -> tuple[str, float, float]:
        """('meaning'|'hanzi'|'', elapsed, duration) — 자동 재생 구간 노래방."""
        if not self._auto_started:
            return ("", 0.0, 0.0)
        ph = self._auto_phase
        if ph == "play_meaning_ko":
            return ("meaning", float(self._auto_phase_elapsed), float(self._auto_phase_duration))
        if ph == "wait_after_meaning_ko":
            sl = max(0.0, float(self._auto_meaning_ko_len))
            return ("meaning", sl, sl)
        if ph == "play_sound":
            return ("hanzi", float(self._auto_phase_elapsed), float(self._auto_phase_duration))
        if ph == "wait_after_play":
            sl = max(0.0, float(self._auto_sound_len))
            return ("hanzi", sl, sl)
        if ph == "wait_sound_len":
            return ("hanzi", float(self._auto_phase_elapsed), float(self._auto_phase_duration))
        if ph in ("wait_after_len", "wait_sync_hold"):
            sl = max(0.0, float(self._auto_sound_len))
            return ("hanzi", sl, sl)
        return ("", 0.0, 0.0)

    def _draw_vocab_cn_detail_block(
        self,
        screen: pygame.Surface,
        *,
        center_x: int,
        main_top: int,
        upper_h: int,
        row: VocabularyWordRow,
        cn_karaoke_active: bool = False,
    ) -> dict[str, int]:
        """상단: 병음·한자만. 노래방 구간에서는 정적 blit 생략(이중 흰색 방지)."""
        pinyin = self._pronunciation_subline(row)
        hero_text = self._hanzi_only(row)
        top_pad = 14
        layout_rows: list[tuple[pygame.Surface | None, int, str, bool]] = []

        pinyin_surf = self._render_pinyin_surface(pinyin) if pinyin else None
        if pinyin_surf is not None:
            layout_rows.append((pinyin_surf, 16, "pinyin", not cn_karaoke_active))
        hanzi_surf = self._font_cn_hero_detail.render(hero_text, True, WHITE)
        layout_rows.append((hanzi_surf, 24, "hanzi", not cn_karaoke_active))

        total_h = sum(
            (surf.get_height() if surf is not None else 0) for surf, g, _, _ in layout_rows
        ) + sum(g for surf, g, _, _ in layout_rows[:-1])
        upper_center_y = main_top + (upper_h // 2)
        draw_y = max(main_top + top_pad, upper_center_y - total_h // 2)
        y_map: dict[str, int] = {"block_bottom": draw_y, "hanzi_height": hanzi_surf.get_height()}
        for surf, gap_after, kind, do_blit in layout_rows:
            if surf is None:
                continue
            y_map[kind] = draw_y
            if do_blit:
                draw_x = center_x - (surf.get_width() // 2)
                screen.blit(surf, (draw_x, draw_y))
            draw_y += surf.get_height() + gap_after
        y_map["block_bottom"] = draw_y
        return y_map

    def _render_vocab_meaning_surface(self, word: Any) -> pygame.Surface | None:
        meaning_items = self._parse_meaning_items((word.meaning or "").strip() if word else "")
        meaning_parts = [(m, GRAY_MUTED) for m in meaning_items]
        if not meaning_parts:
            return None
        rendered = [
            self._font_kr_detail.render(text, True, color) for text, color in meaning_parts
        ]
        if len(rendered) == 1:
            return rendered[0]
        gap = 36
        total_w = sum(s.get_width() for s in rendered) + gap * (len(rendered) - 1)
        row_h = max(s.get_height() for s in rendered)
        meaning_surf = pygame.Surface((max(1, total_w), max(1, row_h)), pygame.SRCALPHA)
        x = 0
        for idx, surf in enumerate(rendered):
            y = (row_h - surf.get_height()) // 2
            meaning_surf.blit(surf, (x, y))
            x += surf.get_width() + (gap if idx < len(rendered) - 1 else 0)
        return meaning_surf

    def _draw_vocab_meaning_pos_block(
        self,
        screen: pygame.Surface,
        *,
        center_x: int,
        cn_layout: dict[str, int],
        lower_top: int,
        word: Any,
        pos_items: list[str],
    ) -> dict[str, int]:
        """한자 아래: 품사 → 뜻 (숏츠 단어 모드와 동일 순서)."""
        y_map: dict[str, int] = {}
        meta_top = int(cn_layout.get("block_bottom", cn_layout.get("hanzi", 0))) + _VOCAB_POS_AFTER_HANZI_GAP

        pos_parts: list[pygame.Surface] = []
        if pos_items:
            pos_row_font = self._font_kr_pos_detail
            assert pos_row_font is not None
            pos_parts = [
                pos_row_font.render(pos, True, _POS_COLOR_TABLE.get(pos, _POS_DEFAULT_COLOR))
                for pos in pos_items
            ]

        meaning_surf = self._render_vocab_meaning_surface(word)
        pos_h = max((s.get_height() for s in pos_parts), default=0)
        pos_gap = _VOCAB_MEANING_AFTER_POS_GAP if pos_parts and meaning_surf is not None else 0
        meaning_h = meaning_surf.get_height() if meaning_surf is not None else 0
        total_h = pos_h + pos_gap + meaning_h
        if total_h <= 0:
            return y_map

        limit_y = lower_top - 10
        if meta_top + total_h > limit_y:
            meta_top = max(int(cn_layout.get("hanzi", meta_top)), limit_y - total_h)

        draw_y = meta_top
        if pos_parts:
            gap = 36
            total_w = sum(s.get_width() for s in pos_parts) + gap * (len(pos_parts) - 1)
            row_h = max(s.get_height() for s in pos_parts)
            y_map["pos"] = draw_y
            x = center_x - total_w // 2
            for i, surf in enumerate(pos_parts):
                screen.blit(surf, (x, draw_y))
                x += surf.get_width() + (gap if i < len(pos_parts) - 1 else 0)
            draw_y += row_h + pos_gap

        if meaning_surf is not None:
            y_map["meaning"] = draw_y
            screen.blit(meaning_surf, (center_x - meaning_surf.get_width() // 2, draw_y))
            draw_y += meaning_h

        y_map["meta_bottom"] = draw_y
        return y_map

    def _draw_vocab_karaoke(
        self,
        screen: pygame.Surface,
        *,
        karaoke_rect: pygame.Rect,
        layout: dict[str, int],
        row: VocabularyWordRow,
        word: Any,
    ) -> None:
        if self._karaoke is None or self._karaoke_style is None:
            return
        mode, elapsed, duration = self._vocab_karaoke_timing()
        if not mode or duration <= 1e-6:
            return
        item = self._word_karaoke_item(row, word)
        fs = self._render_font_sizes
        kr_pt = int(fs.kr_step1) if fs is not None else 56
        pinyin_y = int(layout.get("pinyin", karaoke_rect.top + 40))
        hanzi_y = int(layout.get("hanzi", pinyin_y + 28))
        meaning_y = int(layout.get("meaning", layout.get("block_bottom", hanzi_y + 40)))
        item_cn = dict(item)
        item_cn["translation"] = []
        data_cn = build_sentence_render_data_with_tone_icons(item_cn)
        cn_elapsed = float(elapsed)
        cn_dur = max(1e-6, float(duration))
        if mode == "meaning":
            cn_elapsed = 0.0
            cn_dur = 1.0
        elif mode == "hanzi" and elapsed <= 1e-6:
            cn_elapsed = 0.0
        self._karaoke.draw(
            screen,
            data=data_cn,
            rect=karaoke_rect,
            style=self._karaoke_style,
            elapsed_sec=cn_elapsed,
            syllable_times=[],
            sound_duration_sec=cn_dur,
            fixed_pinyin_y=pinyin_y,
            fixed_hanzi_y=hanzi_y,
            pinyin_hanzi_gap=12,
        )
        meanings = self._parse_meaning_items((word.meaning or "").strip() if word else "")
        meaning_text = " · ".join(meanings)
        if not meaning_text:
            return
        meaning_rect = pygame.Rect(
            karaoke_rect.left,
            max(karaoke_rect.top, meaning_y - 4),
            karaoke_rect.width,
            max(32, self._font_kr_detail.get_height() + 8),
        )
        if mode == "meaning":
            self._karaoke.draw_meaning_karaoke(
                screen,
                text=meaning_text,
                rect=meaning_rect,
                elapsed_sec=elapsed,
                sound_duration_sec=duration,
                vocab_kr_font_pt=kr_pt,
            )

    def _resolve_vocab_meaning_ko_path(self, word_id: int) -> str:
        """batch_tts 모드 2 산출: resource/sound/shorts/ko_word_{word_id}_0.mp3"""
        from core.paths import DEFAULT_KO_NARRATION_SOUND_DIR

        wid = int(word_id)
        if wid < 1:
            return ""
        for name in (f"ko_word_{wid}_0.mp3", f"ko_word_{wid}.mp3"):
            p = DEFAULT_KO_NARRATION_SOUND_DIR / name
            if p.is_file():
                return str(p.resolve())
        return ""

    def _one_cn_follow_cycle_sec(self) -> float:
        """중국어 1회 + gap + 따라발음(주황) + gap."""
        sl = max(0.0, float(self._auto_sound_len))
        return sl + _AUTO_SOUND_GAP_SEC + sl * _AUTO_WAIT_SOUND_LEN_SCALE + _AUTO_SOUND_GAP_SEC

    def _try_begin_extra_cn_follow_cycle(self) -> bool:
        """단어 타임라인에 여유가 있으면 TTS 없이 중국어→따라발음만 한 번 더."""
        remain = max(0.0, float(self._auto_word_target_duration) - float(self._auto_word_elapsed))
        need = self._one_cn_follow_cycle_sec()
        if remain < need * 0.9:
            return False
        self._auto_cycle_index = 0
        self._begin_phase("play_sound", self._auto_sound_len)
        return True

    def _begin_phase(self, phase: str, duration: float) -> None:
        self._auto_phase = phase
        self._auto_phase_duration = max(0.0, float(duration))
        self._auto_phase_elapsed = 0.0
        if phase == "play_meaning_ko" and self._auto_meaning_ko_path:
            self._play_sound_now(self._auto_meaning_ko_path)
        elif phase == "play_sound" and self._auto_sound_path:
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
        raw_sound_len = self._get_sound_length_sec(self._auto_sound_path)
        p = (self._auto_sound_path or "").strip()
        path_exists = bool(p) and Path(p).is_file()
        if (not path_exists) or raw_sound_len <= 1e-9:
            logger.warning(
                "단어장: 사운드 없음 (word_id=%s, path=%s) — %ss로 진행",
                cur.word_id,
                p or "(지정 없음)",
                _FALLBACK_SOUND_LEN_SEC,
            )
            self._auto_sound_len = float(_FALLBACK_SOUND_LEN_SEC)
        else:
            self._auto_sound_len = raw_sound_len
        self._auto_cycle_index = 0
        self._auto_word_elapsed = 0.0
        self._auto_meaning_ko_path = self._resolve_vocab_meaning_ko_path(cur.word_id)
        self._auto_meaning_ko_len = (
            self._get_sound_length_sec(self._auto_meaning_ko_path)
            if self._auto_meaning_ko_path
            else 0.0
        )
        meaning_lead_sec = (
            (self._auto_meaning_ko_len + _AUTO_MEANING_GAP_SEC)
            if self._auto_meaning_ko_len > 1e-6
            else 0.0
        )
        sound_cycle_duration = (
            self._auto_sound_len
            + _AUTO_SOUND_GAP_SEC
            + (self._auto_sound_len * _AUTO_WAIT_SOUND_LEN_SCALE)
            + _AUTO_SOUND_GAP_SEC
        )
        sound_total_duration = meaning_lead_sec + sound_cycle_duration * _AUTO_SOUND_REPEAT_COUNT
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
        if self._auto_meaning_ko_len > 1e-6:
            self._begin_phase("play_meaning_ko", self._auto_meaning_ko_len)
        else:
            self._auto_cycle_index = 0
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
        if n <= 0:
            # 녹화 until-content-done에서 단어 행이 비어 있으면 즉시 종료 신호를 올린다.
            self._recording_done = True
            return
        if self._recording_done:
            return
        if not self._auto_started:
            # 단어장은 항상 id 1(정렬 첫 행)부터 시작
            self._selected_index = 0
            self._auto_started = True
            self._setup_current_word_cycle()
            return

        self._auto_word_elapsed += dt

        if self._auto_phase == "play_meaning_ko":
            self._auto_phase_elapsed += dt
            if self._auto_phase_elapsed < self._auto_phase_duration:
                return
            self._begin_phase("wait_after_meaning_ko", _AUTO_MEANING_GAP_SEC)
            return

        if self._auto_phase == "wait_after_meaning_ko":
            self._auto_phase_elapsed += dt
            if self._auto_phase_elapsed < self._auto_phase_duration:
                return
            self._auto_cycle_index = 0
            self._begin_phase("play_sound", self._auto_sound_len)
            return

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
            if self._try_begin_extra_cn_follow_cycle():
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
        main_top = _HEADER_H
        title_img = self._title_image_surface
        intro_alpha = 255
        if self._intro_total_sec > 1e-6 and self._intro_remaining_sec > 0.0:
            intro_alpha = int(
                max(
                    0,
                    min(
                        255,
                        round(
                            (1.0 - (self._intro_remaining_sec / self._intro_total_sec))
                            * 255.0
                        ),
                    ),
                )
            )
        if title_img is not None:
            margin_left = 44
            margin_top = 18
            sw, sh = int(title_img.get_width()), int(title_img.get_height())
            if sw > 0 and sh > 0:
                # 회화 타이틀("문장 이해하기")의 실제 렌더 크기를 기준으로 맞춘다.
                max_w = int(w * 0.54)
                max_h = 114
                ref = self._conversation_title_reference_surface
                if ref is not None:
                    rw, rh = int(ref.get_width()), int(ref.get_height())
                else:
                    rw, rh = 0, 0
                if rw > 0 and rh > 0:
                    ref_scale = min(float(max_w) / float(rw), float(max_h) / float(rh), 1.0)
                    tw = max(1, int(round(rw * ref_scale)))
                    th = max(1, int(round(rh * ref_scale)))
                else:
                    scale = min(float(max_w) / float(sw), float(max_h) / float(sh), 1.0)
                    tw = max(1, int(round(sw * scale)))
                    th = max(1, int(round(sh * scale)))
                # 요청: 단어 모드 타이틀은 세로 높이만 소폭 줄인다.
                th = max(1, int(round(th * 0.70)))
                draw = (
                    pygame.transform.smoothscale(title_img, (tw, th))
                    if (tw != sw or th != sh)
                    else title_img
                )
                if intro_alpha < 255:
                    draw = draw.copy()
                    draw.set_alpha(intro_alpha)
                screen.blit(draw, (margin_left, margin_top))
                main_top = max(_HEADER_H, margin_top + th + 8)
        else:
            title = self._font_title.render("단어 정리", True, WHITE)
            if intro_alpha < 255:
                title.set_alpha(intro_alpha)
            title_x = (w - title.get_width()) // 2
            title_y = max(0, (_HEADER_H - title.get_height()) // 2)
            screen.blit(title, (title_x, title_y))

        if self._intro_remaining_sec > 0.0:
            return

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

        pos_items = self._parse_pos_items((word.pos or "").strip() if word else "")
        center_x = right_rect.x + right_rect.width // 2
        karaoke_rect = pygame.Rect(
            right_x + 24,
            main_top + 12,
            max(80, right_w - 48),
            max(80, upper_h - 24),
        )
        karaoke_mode, _, _ = self._vocab_karaoke_timing()
        cn_layout = self._draw_vocab_cn_detail_block(
            screen,
            center_x=center_x,
            main_top=main_top,
            upper_h=upper_h,
            row=cur,
            cn_karaoke_active=bool(karaoke_mode),
        )
        meta_layout = self._draw_vocab_meaning_pos_block(
            screen,
            center_x=center_x,
            cn_layout=cn_layout,
            lower_top=lower_top,
            word=word,
            pos_items=pos_items,
        )
        text_layout = {**cn_layout, **meta_layout}
        if karaoke_mode:
            self._draw_vocab_karaoke(
                screen,
                karaoke_rect=karaoke_rect,
                layout=text_layout,
                row=cur,
                word=word,
            )

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

    def recording_stop_summary(self) -> str:
        """녹화가 단어장 자동 순회 완료로 끝났을 때 터미널에 찍을 한 줄 요약."""
        n = len(self._rows)
        topics = sorted(
            {str(r.topic or "").strip() for r in self._rows if str(r.topic or "").strip()}
        )
        topics_s = ",".join(topics) if topics else "(미지정)"
        return f"단어장: 단어 {n}개, topic=[{topics_s}], 종료 시 선택 idx={int(self._selected_index)}"
