"""
단어장 스튜디오: IStudio. 집계된 단어 목록 표시 및 녹화 종료 신호(SPACE).
단어는 `VocabularyWordRow`(words.id 참조)로 보관한다.
폰트는 회화 스튜디오와 동일하게 `config.conversation_render`·`load_font_*` 경로를 쓴다.
레이아웃: 좌 20% 한자 목록, 우 80% 상단 단어 정보·하단 연상 이미지 / 획순 슬롯.
"""

from __future__ import annotations

import logging
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
from utils.fonts import attach_font_fgcolor, load_font_chinese, load_font_korean

logger = logging.getLogger(__name__)

# --- 레이아웃 (뷰포트 비율) ---
_LEFT_PANEL_RATIO = 0.20
_RIGHT_UPPER_RATIO = 0.40  # 메인 영역(헤더 제외) 높이 중 상단 단어 정보 비율
_LIST_ROW_H = 56
_LIST_SCROLL_STEP = 48
_HEADER_H = 72
_LOWER_GAP = 10  # 하단 좌·우 슬롯 사이


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
        self._font_hint: Optional[pygame.font.Font] = None
        self._font_title: Optional[pygame.font.Font] = None
        self._recording_done: bool = False
        self._list_scroll_px: int = 0
        self._selected_index: int = 0
        self._image_cache: dict[tuple[int, str], pygame.Surface] = {}

    def init(self, config: Any = None) -> None:
        """회화 스튜디오와 동일한 폰트 로드(`ConversationStudio._load_fonts`와 동일 소스)."""
        if self._font_cn_big is not None:
            return
        settings = _resolve_conversation_render_settings(config)
        fs = settings.font_sizes

        self._font_cn_big = load_font_chinese(fs.cn_big, WHITE)
        hero_size = min(160, max(72, int(round(fs.cn_big * 1.35))))
        self._font_cn_hero = load_font_chinese(hero_size, WHITE) or self._font_cn_big
        self._font_cn = load_font_chinese(fs.cn, RED)
        self._font_kr = load_font_korean(fs.kr, GRAY_MUTED)

        if self._font_cn_big is None:
            from core.paths import DEFAULT_FONT_DIR, FONT_CN_FILENAME

            self._font_cn_big = attach_font_fgcolor(pygame.font.Font(None, fs.cn_big), WHITE)
            self._font_cn_hero = attach_font_fgcolor(pygame.font.Font(None, hero_size), WHITE)
            logger.warning(
                "단어장: 중국어 폰트 미로드 → 기본 폰트(중국어 네모 가능). %s → %s",
                FONT_CN_FILENAME,
                DEFAULT_FONT_DIR.resolve(),
            )
        if self._font_cn_hero is None:
            self._font_cn_hero = self._font_cn_big
        if self._font_cn is None:
            self._font_cn = attach_font_fgcolor(pygame.font.Font(None, fs.cn), RED)
        if self._font_kr is None:
            self._font_kr = attach_font_fgcolor(pygame.font.Font(None, fs.kr), GRAY_MUTED)

        hint_size = max(16, int(round(fs.kr * 0.82)))
        self._font_hint = load_font_korean(hint_size, (140, 140, 150)) or self._font_kr
        self._font_title = load_font_korean(fs.kr, (230, 230, 235)) or self._font_kr

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
            if e.type == pygame.MOUSEWHEEL:
                delta = int(getattr(e, "y", 0) or 0)
                if delta != 0 and n > 0:
                    max_scroll = max(0, n * _LIST_ROW_H - panel_inner_h)
                    self._list_scroll_px = max(
                        0, min(max_scroll, self._list_scroll_px - delta * _LIST_SCROLL_STEP)
                    )
                continue

            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                w = int(getattr(config, "width", 0) or 0) if config is not None else 0
                h = int(getattr(config, "height", 0) or 0) if config is not None else 0
                if w <= 0 or h <= 0:
                    continue
                left_w = int(w * _LEFT_PANEL_RATIO)
                mx, my = e.pos
                if 0 <= mx < left_w and _HEADER_H <= my < h:
                    rel_y = my - _HEADER_H - 8 + self._list_scroll_px
                    if rel_y >= 0:
                        hit = rel_y // _LIST_ROW_H
                        if 0 <= hit < n:
                            self._selected_index = hit
                            self._scroll_selection_into_view(panel_inner_h)
                continue

            if e.type != pygame.KEYDOWN:
                continue
            if e.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self._recording_done = True
                continue
            if e.key in (pygame.K_UP, pygame.K_k):
                if n > 0:
                    self._selected_index = max(0, self._selected_index - 1)
                    self._scroll_selection_into_view(panel_inner_h)
                continue
            if e.key in (pygame.K_DOWN, pygame.K_j):
                if n > 0:
                    self._selected_index = min(n - 1, self._selected_index + 1)
                    self._scroll_selection_into_view(panel_inner_h)
                continue
        return True

    def update(self, config: Any = None) -> None:
        _ = config

    def _hanzi_only(self, row: VocabularyWordRow) -> str:
        w = get_word(row.word_id)
        if w is not None and (w.word or "").strip():
            return (w.word or "").strip()
        return f"(id={row.word_id})"

    def _pronunciation_subline(self, row: VocabularyWordRow) -> str:
        m = (row.pronunciation_mask or "").strip()
        if m:
            return m
        w = get_word(row.word_id)
        if w is not None and (w.pinyin or "").strip():
            return (w.pinyin or "").strip()
        return ""

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

    def draw(self, screen: Any, config: Any) -> None:
        bg = getattr(config, "bg_color", (20, 20, 25))
        screen.fill(bg)
        if self._font_cn_big is None:
            self.init(config)
        assert self._font_cn_big is not None
        assert self._font_cn_hero is not None
        assert self._font_cn is not None
        assert self._font_kr is not None
        assert self._font_hint is not None
        assert self._font_title is not None

        w, h = int(config.width), int(config.height)
        title = self._font_title.render("단어 정리", True, (230, 230, 235))
        screen.blit(title, (24, 20))

        hint = self._font_hint.render(
            "SPACE/Enter: 완료 · ↑↓/k j: 단어 · 휠: 목록 스크롤",
            True,
            (140, 140, 150),
        )
        screen.blit(hint, (24, 48))

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
            surf = self._font_cn_big.render(hanzi, True, (220, 220, 225))
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

        rx = right_rect.x + 20
        ry = main_top + 12
        hero_text = self._hanzi_only(cur)
        hero_surf = self._font_cn_hero.render(hero_text, True, (245, 245, 248))
        screen.blit(hero_surf, (rx, ry))
        ry += hero_surf.get_height() + 12

        pinyin = self._pronunciation_subline(cur)
        meaning = (word.meaning or "").strip() if word else ""
        pos = (word.pos or "").strip() if word else ""

        def line_kv(label: str, value: str) -> None:
            nonlocal ry
            if not value:
                return
            lab = self._font_hint.render(label, True, (160, 160, 170))
            screen.blit(lab, (rx, ry))
            ry += lab.get_height() + 2
            val_s = self._font_kr.render(value, True, (210, 210, 218))
            screen.blit(val_s, (rx, ry))
            ry += val_s.get_height() + 8

        line_kv("병음 (Pinyin)", pinyin)
        line_kv("뜻 (Korean)", meaning)
        line_kv("품사 (POS)", pos)

        # --- 하단: 연상 이미지 | 획순 슬롯 ---
        slot_y = lower_top + 8
        slot_h = max(80, lower_h - 16)
        half_gap = _LOWER_GAP // 2
        img_slot_w = (right_w - 40 - _LOWER_GAP) // 2
        img_slot_x = right_x + 20
        stroke_slot_x = img_slot_x + img_slot_w + _LOWER_GAP

        def draw_slot_frame(rect: pygame.Rect, title: str) -> None:
            pygame.draw.rect(screen, (32, 32, 38), rect, border_radius=6)
            pygame.draw.rect(screen, (70, 70, 78), rect, 1, border_radius=6)
            t = self._font_hint.render(title, True, (120, 120, 130))
            screen.blit(t, (rect.x + 10, rect.y + 8))

        img_rect = pygame.Rect(img_slot_x, slot_y, img_slot_w, slot_h)
        stroke_rect = pygame.Rect(stroke_slot_x, slot_y, img_slot_w, slot_h)

        draw_slot_frame(img_rect, "연상 이미지")
        draw_slot_frame(stroke_rect, "획순 애니메이션 (준비 중)")

        img_path = (word.img_path if word else "") or ""
        scaled: Optional[pygame.Surface] = None
        if word and img_path:
            raw = self._get_scaled_word_image(word.id, img_path)
            if raw is not None:
                iw = img_rect.width - 20
                ih = img_rect.height - 36
                scaled = _scale_surface_to_fit(raw, max(1, iw), max(1, ih))

        if scaled is not None:
            ix = img_rect.x + (img_rect.width - scaled.get_width()) // 2
            iy = img_rect.y + (img_rect.height - scaled.get_height()) // 2 + 6
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

        # 획순: Word 확장 필드(예: stroke_anim_path) 연동 예정 — 현재는 슬롯만 표시
        ph2 = self._font_hint.render("리소스 연동 예정", True, (100, 100, 110))
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
