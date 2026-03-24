"""UTIL 단계(문장 활용): 비디오·자막 블록·단어 카드 그리기."""
from __future__ import annotations

import logging
from typing import Any

import pygame

from .constants import _DEFAULT_CARD_BG, _DEFAULT_CARD_FG, _POS_COLORS


def draw_step2_video(studio: Any, screen: Any, w: int, h: int) -> None:
    """Step 2: 비디오 프레임 또는 '(비디오 없음)' 플레이스홀더."""
    vid_surf = studio._video_player.get_frame(w, h)
    if vid_surf is not None:
        screen.blit(vid_surf, (0, 0))
    else:
        pygame.draw.rect(screen, (40, 40, 50), (0, 0, w, h))
        font_kr = studio._font_kr or pygame.font.Font(None, 28)
        no_vid = font_kr.render("(비디오 없음)", True, (180, 180, 180))
        screen.blit(no_vid, (w // 2 - 50, h // 2 - 14))


def draw_step2_sentence_block(
    studio: Any,
    screen: Any,
    item: dict,
    w: int,
    y_base: int,
    line_gap: int = 130,
) -> None:
    """한 문장 블록(한자+병음+번역)을 y_base에 그리기. Step 1과 동일한 큰 폰트·가운데 정렬."""
    font_cn_big = studio._font_cn_big or pygame.font.Font(None, 36)
    font_cn = studio._font_cn or pygame.font.Font(None, 28)
    font_kr = studio._font_kr or pygame.font.Font(None, 28)
    hanzi_ft = studio._font_cn_step1_ft or studio._font_cn_big_ft
    hanzi_pg = font_cn_big
    pinyin_ft = studio._font_cn_step1_pinyin_ft or studio._font_cn_ft
    pinyin_pg = font_cn
    trans_font = studio._font_kr_step1 or font_kr
    sentences = item.get("sentence") or []
    translations = item.get("translation") or []
    pinyin_text = item.get("pinyin") or ""
    sen_text = " ".join(str(x) for x in sentences[:3]) if sentences else "(문장 없음)"
    trans_text = " ".join(str(x) for x in translations[:3]) if translations else ""
    y_pos = y_base

    def _blit_centered(surf: Any, y: int) -> None:
        if surf is not None:
            x = (w - surf.get_width()) // 2
            screen.blit(surf, (max(20, x), y))

    sen_surf = None
    if hanzi_ft is not None:
        try:
            sen_surf, _ = hanzi_ft.render(sen_text[:80], (255, 255, 255))
        except Exception:
            pass
    if sen_surf is None:
        sen_surf = hanzi_pg.render(sen_text[:80], True, (255, 255, 255))
    _blit_centered(sen_surf, y_pos)
    y_pos += line_gap

    if pinyin_text:
        pinyin_surf = None
        if pinyin_ft is not None:
            try:
                pinyin_surf, _ = pinyin_ft.render(pinyin_text[:120], (220, 70, 70))
            except Exception:
                pass
        if pinyin_surf is None:
            pinyin_surf = pinyin_pg.render(pinyin_text[:120], True, (220, 70, 70))
        _blit_centered(pinyin_surf, y_pos)
        y_pos += line_gap
    if trans_text:
        trans_surf = trans_font.render(trans_text[:80], True, (200, 200, 200))
        _blit_centered(trans_surf, y_pos)


def draw_step2_subtitles(studio: Any, screen: Any, curr_item: dict, w: int, h: int) -> int:
    """현재 문장만 그리기. 단어 카드 시작 y 반환."""
    line_gap = 130
    y_base = int(h * 0.38)
    draw_step2_sentence_block(studio, screen, curr_item, w, y_base, line_gap)
    trans_font = studio._font_kr_step1 or studio._font_kr or pygame.font.Font(None, 28)
    card_y = y_base + line_gap * 2 + trans_font.get_height() + 8
    return card_y


def draw_step2_word_cards(studio: Any, screen: Any, item: dict, card_y: int) -> None:
    """단어(품사별 색상) 카드 한 줄."""
    words_list = item.get("words") or []
    if not words_list:
        return
    try:
        from data.table_manager import get_word_info_for_display

        font_wk = studio._font_kr or pygame.font.Font(None, 22)
        card_gap, card_pad_x, card_pad_y = 10, 12, 8
        card_infos: list[tuple[list[Any], tuple, tuple, int, int]] = []
        for hanzi in words_list:
            info = get_word_info_for_display(hanzi)
            if not info:
                continue
            pos_strs = info["pos"]
            meaning_strs = info["meaning"]
            n = max(len(pos_strs), len(meaning_strs))
            for k in range(n):
                pos = pos_strs[k] if k < len(pos_strs) else ""
                meaning = meaning_strs[k] if k < len(meaning_strs) else ""
                bg, fg = _POS_COLORS.get(pos, (_DEFAULT_CARD_BG, _DEFAULT_CARD_FG))
                pos_surf = font_wk.render(pos, True, fg) if pos else None
                meaning_surf = font_wk.render(meaning[:40], True, (255, 255, 255)) if meaning else None
                line_surfs: list[Any] = []
                if pos_surf:
                    line_surfs.append(pos_surf)
                if meaning_surf:
                    line_surfs.append(meaning_surf)
                if not line_surfs:
                    continue
                content_w = max(s.get_width() for s in line_surfs)
                line_h = font_wk.get_height()
                content_h = line_h * len(line_surfs) + 4 * (len(line_surfs) - 1)
                c_w = max(70, content_w + card_pad_x * 2)
                c_h = content_h + card_pad_y * 2
                card_infos.append((line_surfs, bg, fg, c_w, c_h))
        card_x = 20
        line_h = font_wk.get_height()
        for (line_surfs, bg, fg, c_w, c_h) in card_infos:
            card_rect = pygame.Rect(card_x, card_y, c_w, c_h)
            pygame.draw.rect(screen, bg, card_rect, border_radius=6)
            pygame.draw.rect(screen, fg, card_rect, 2, border_radius=6)
            y_text = card_y + card_pad_y
            for s in line_surfs:
                screen.blit(s, (card_x + (c_w - s.get_width()) // 2, y_text))
                y_text += line_h + 4
            card_x += c_w + card_gap
    except Exception as e:
        logging.getLogger(__name__).debug("단어 카드 오류(일반): %s", e)


def draw_util_screen(studio: Any, screen: Any, config: Any) -> None:
    """UTIL 단계 전체: 비디오 + 자막 + 단어 카드 (데이터 없음 메시지 포함)."""
    w, h = config.width, config.height
    if not studio._data_list:
        font_kr = studio._font_kr or pygame.font.Font(None, 28)
        msg = font_kr.render("데이터 없음 (CSV 로드 실패 또는 비어 있음)", True, (180, 180, 180))
        screen.blit(msg, (20, h // 2 - 14))
        return
    curr_item = studio._data_list[studio._current_index]
    draw_step2_video(studio, screen, w, h)
    card_y = draw_step2_subtitles(studio, screen, curr_item, w, h)
    draw_step2_word_cards(studio, screen, curr_item, card_y)
