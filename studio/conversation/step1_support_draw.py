"""LISTEN Step1: 타이틀·듣기 아이콘·단어 카드·성조 안내·활용(util) 화면."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import pygame

from utils.fonts import load_font_korean
from utils.pinyin_processor import SANDHI_TYPE_LABELS

from .constants import _POS_COLORS, _REPO_ROOT
from .step1_sentence_draw import draw_step1_base_sentence
from .step2_draw import draw_step2_sentence_block


def draw_step1_base_title(studio: Any, screen: Any, config: Any) -> None:
    """상단 타이틀 '쉐도잉 훈련 Step 1: 원어민 속도 듣기'."""
    w, h = config.width, config.height
    title_font = getattr(studio, "_font_step1_title", None) or load_font_korean(52, weight="bold") or load_font_korean(52, weight="extrabold") or load_font_korean(52)
    studio._font_step1_title = title_font
    if title_font is not None:
        cx = w // 2
        title_y = int(h * 0.06)
        part1 = title_font.render("쉐도잉 훈련 Step 1:", True, (255, 255, 255))
        part2 = title_font.render(" 원어민 속도 듣기", True, (255, 140, 0))
        r1, r2 = part1.get_rect(), part2.get_rect()
        total_w = r1.width + r2.width
        x1 = cx - total_w // 2
        screen.blit(part1, (x1, title_y))
        screen.blit(part2, (x1 + r1.width, title_y))


def draw_step1_base_listen_icon(studio: Any, screen: Any, config: Any) -> None:
    """좌측 듣기 이미지(판다)."""
    font_kr = studio._font_kr or pygame.font.Font(None, 28)
    left_x, left_y = config.get_pos(0.02, 0.20)
    left_w, left_h = config.get_size(0.20, 0.36)
    icon_dir = _REPO_ROOT / "resource" / "image" / "icon"
    listen_path = icon_dir / "listen_panda.png"
    if (studio._listen_panda_cached_size != (left_w, left_h) or studio._listen_panda_surface is None) and listen_path.exists():
        try:
            surf = pygame.image.load(str(listen_path))
            if surf.get_alpha() is None:
                surf = surf.convert()
            else:
                surf = surf.convert_alpha()
            studio._listen_panda_surface = pygame.transform.smoothscale(surf, (left_w, left_h))
            studio._listen_panda_cached_size = (left_w, left_h)
        except Exception:
            studio._listen_panda_surface = None
            studio._listen_panda_cached_size = (0, 0)
    if studio._listen_panda_surface is not None:
        screen.blit(studio._listen_panda_surface, (left_x, left_y))
    else:
        placeholder = font_kr.render("듣기 이미지 (추가 예정)", True, (140, 140, 150))
        pr = placeholder.get_rect(center=(left_x + left_w // 2, left_y + left_h // 2))
        screen.blit(placeholder, pr)


def draw_step1_base_word_cards(studio: Any, screen: Any, item: dict, ctx: dict) -> None:
    """단어 카드(품사별 색상). ctx에는 hanzi_bottom_y, slot_left_list 등."""
    words_list = item.get("words") or []
    if not words_list:
        return
    try:
        from data.table_manager import get_word_info_for_display

        _DEFAULT_BG = (45, 50, 65)
        _DEFAULT_FG = (200, 200, 200)
        font_word_kr = studio._font_kr or pygame.font.Font(None, 24)
        card_gap = 12
        card_pad_x, card_pad_y = 16, 10
        card_min_w = 80
        hanzi_bottom_y = ctx["hanzi_bottom_y"]
        slot_left_list = ctx.get("slot_left_list", [])
        slot_width_list = ctx.get("slot_width_list", [])
        use_speed = ctx.get("use_speed", False)
        sentences = ctx["sentences"]
        cx = ctx["cx"]
        _punct_set = ctx["_punct_set"]

        _sen_chars_plain = [c for c in "".join(str(x) for x in sentences) if c not in _punct_set and not c.isspace()]

        def _word_slot_cx(word: str) -> int:
            if not (use_speed and slot_left_list and slot_width_list):
                return cx
            word_chars = [c for c in word if c not in _punct_set and not c.isspace()]
            if not word_chars:
                return cx
            n_wc = len(word_chars)
            start_idx = -1
            for si in range(len(_sen_chars_plain) - n_wc + 1):
                if _sen_chars_plain[si : si + n_wc] == word_chars:
                    start_idx = si
                    break
            if start_idx < 0:
                return cx
            end_idx = start_idx + n_wc - 1
            if end_idx >= len(slot_left_list):
                return cx
            x_left = slot_left_list[start_idx]
            x_right = slot_left_list[end_idx] + slot_width_list[end_idx]
            return int((x_left + x_right) / 2)

        card_infos: list[tuple[list[Any], tuple, tuple, int, int, int]] = []
        for word in words_list:
            info = get_word_info_for_display(word)
            if not info:
                continue
            pos_strs = info["pos"]
            meaning_strs = info["meaning"]
            anchor_cx = _word_slot_cx(word)
            n = max(len(pos_strs), len(meaning_strs))
            word_cards: list[tuple[list[Any], tuple, tuple, int, int]] = []
            for k in range(n):
                pos = pos_strs[k] if k < len(pos_strs) else ""
                meaning = meaning_strs[k] if k < len(meaning_strs) else ""
                bg, fg = _POS_COLORS.get(pos, (_DEFAULT_BG, _DEFAULT_FG))
                meaning_surf = font_word_kr.render(meaning[:40], True, (255, 255, 255)) if meaning else None
                line_surfs: list[Any] = []
                if meaning_surf:
                    line_surfs.append(meaning_surf)
                if not line_surfs:
                    continue
                content_w = max(s.get_width() for s in line_surfs)
                line_h = font_word_kr.get_height()
                content_h = line_h * len(line_surfs) + 4 * (len(line_surfs) - 1)
                c_w = max(card_min_w, content_w + card_pad_x * 2)
                c_h = content_h + card_pad_y * 2
                word_cards.append((line_surfs, bg, fg, c_w, c_h))
            for wc in word_cards:
                card_infos.append((*wc, anchor_cx))

        if not card_infos:
            return
        card_y_top = hanzi_bottom_y - 10
        line_h = font_word_kr.get_height()
        anchor_groups: dict[int, list[int]] = defaultdict(list)
        for idx, ci in enumerate(card_infos):
            anchor_groups[ci[5]].append(idx)
        for anchor_cx_key, idxs in anchor_groups.items():
            group_w = sum(card_infos[i][3] for i in idxs) + card_gap * (len(idxs) - 1)
            gx = anchor_cx_key - group_w // 2
            for i in idxs:
                line_surfs, bg, fg, c_w, c_h, _ = card_infos[i]
                card_rect = pygame.Rect(gx, card_y_top, c_w, c_h)
                pygame.draw.rect(screen, bg, card_rect, border_radius=8)
                pygame.draw.rect(screen, fg, card_rect, 2, border_radius=8)
                y_text = card_y_top + card_pad_y
                for s in line_surfs:
                    screen.blit(s, (gx + (c_w - s.get_width()) // 2, y_text))
                    y_text += line_h + 4
                gx += c_w + card_gap
    except Exception as _e:
        logging.getLogger(__name__).debug("단어 카드 오류(step1): %s", _e)


def draw_step1_base_sandhi(studio: Any, screen: Any, config: Any, item: dict) -> None:
    """좌측 하단 발음상 성조 변화."""
    sandhi_types_raw = item.get("pinyin_sandhi_types") or []
    _sandhi_skip = {"tone3_half", "bu_to_4", "neutral_char"}
    unique_sandhi = list(dict.fromkeys(t for t in sandhi_types_raw if t and t not in _sandhi_skip))
    if not unique_sandhi:
        return
    h = config.height
    font_kr = studio._font_kr or pygame.font.Font(None, 28)
    left_margin = 20
    line_height = 28
    box_y = h - 40 - (len(unique_sandhi) + 1) * line_height
    title_surf = font_kr.render("발음상 성조 변화", True, (200, 200, 180))
    screen.blit(title_surf, (left_margin, box_y))
    for j, st in enumerate(unique_sandhi):
        label = SANDHI_TYPE_LABELS.get(st, st)
        line_surf = font_kr.render(label, True, (255, 220, 100))
        screen.blit(line_surf, (left_margin, box_y + line_height + j * line_height))


def draw_step1_base_hint(studio: Any, screen: Any, config: Any) -> None:
    """맨 아래 안내 문구."""
    w, h = config.width, config.height
    font_kr = studio._font_kr or pygame.font.Font(None, 28)
    hint = "눈으로 보면서 원어민 리듬을 익히세요"
    hint_surf = font_kr.render(hint, True, (180, 190, 200))
    hint_r = hint_surf.get_rect(center=(w // 2, h - 40))
    screen.blit(hint_surf, hint_r)


def draw_step1_util(studio: Any, screen: Any, config: Any) -> None:
    """활용 페이지: 현재(util) 문장만 Step 1과 동일 위치·크기."""
    w, h = config.width, config.height
    cx = w // 2
    item = studio._data_list[studio._current_index]

    title_font = getattr(studio, "_font_step1_title", None) or load_font_korean(52, weight="bold") or load_font_korean(52)
    if title_font:
        y_top = int(h * 0.06)
        part1 = title_font.render("쉐도잉 훈련 Step 2:", True, (255, 255, 255))
        part2 = title_font.render(" 문장의 활용", True, (255, 140, 0))
        r1, r2 = part1.get_rect(), part2.get_rect()
        total_w = r1.width + r2.width
        x1 = cx - total_w // 2
        screen.blit(part1, (x1, y_top))
        screen.blit(part2, (x1 + r1.width, y_top))

    y_base = int(h * 0.38)
    draw_step2_sentence_block(studio, screen, item, w, y_base, line_gap=130)


def draw_step1_base(studio: Any, screen: Any, config: Any) -> None:
    """slot_index 0(base) 문장용 UI."""
    item = studio._data_list[studio._current_index]
    draw_step1_base_title(studio, screen, config)
    draw_step1_base_listen_icon(studio, screen, config)
    ctx = draw_step1_base_sentence(studio, screen, config, item)
    draw_step1_base_word_cards(studio, screen, item, ctx)
    draw_step1_base_sandhi(studio, screen, config, item)
    draw_step1_base_hint(studio, screen, config)


def draw_step1(studio: Any, screen: Any, config: Any) -> None:
    """셰도잉 Step 1: base 또는 util."""
    w, h = config.width, config.height
    font_kr = studio._font_kr or pygame.font.Font(None, 28)

    if not studio._data_list:
        msg = font_kr.render("데이터 없음 (CSV 로드 실패 또는 비어 있음)", True, (180, 180, 180))
        r = msg.get_rect(center=(w // 2, h // 2))
        screen.blit(msg, r)
        return

    item = studio._data_list[studio._current_index]
    if item.get("type") == "util":
        draw_step1_util(studio, screen, config)
        return

    draw_step1_base(studio, screen, config)
