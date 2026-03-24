"""LISTEN Step1: 병음/한자/해석 및 성조 곡선(그래프) 그리기."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import pygame

from utils.pinyin_processor import (
    diff_lexical_phonetic_per_syllable,
    get_pinyin_processor,
    parse_tone_from_syllable,
)
from .constants import _REPO_ROOT
from .draw_helpers import draw_dotted_line as _draw_dotted_line


def draw_step1_base_sentence(studio: Any, screen: Any, config: Any, item: dict) -> dict:
    """Step 1 base: 병음·한자·해석 및 성조 곡선(L1/L2 진행). 반환 ctx는 word_cards용."""
    w, h = config.width, config.height
    font_kr = studio._font_kr or pygame.font.Font(None, 28)
    font_cn = studio._font_cn or pygame.font.Font(None, 28)
    font_cn_big = studio._font_cn_big or pygame.font.Font(None, 36)
    font_kr_step1 = studio._font_kr_step1 or font_kr

    sentences = item.get("sentence") or []
    if isinstance(sentences, str):
        sentences = [sentences.strip()] if sentences.strip() else []
    translations = item.get("translation") or []
    pinyin_text = (item.get("pinyin") or "").strip()
    pinyin_lexical = (item.get("pinyin_lexical") or "").strip()
    pinyin_phonetic = (item.get("pinyin_phonetic") or "").strip()
    sen_text = " ".join(str(x) for x in sentences) if sentences else "(문장 없음)"
    trans_text = " ".join(str(x) for x in translations) if translations else ""

    if not pinyin_text and sen_text and sen_text != "(문장 없음)":
        processor = get_pinyin_processor()
        if processor.available:
            pinyin_text = processor.full_convert(sen_text)
            lex_list = processor.get_lexical_pinyin(sen_text)
            ph_list = processor.get_phonetic_pinyin(sen_text)
            pinyin_lexical = " ".join(lex_list) if lex_list else ""
            pinyin_phonetic = " ".join(ph_list) if ph_list else ""

    cx = w // 2
    center_top = int(h * 0.38)
    line_gap = 96
    hanzi_drawn = False
    slot_left_list: list[float] = []
    slot_width_list: list[float] = []
    use_speed = False

    pinyin_ft = studio._font_cn_step1_pinyin_ft or studio._font_cn_ft
    # 발음 병음도 같은 폰트(pinyin_ft)로 그려야 표기 병음과 위아래 정렬이 맞음 (폰트 차이로 틀어짐 방지)
    diff_ft = pinyin_ft
    _tone_contour_enabled = True   # 병음 위 성조 이미지 표시
    _phonetic_diff_enabled = True  # 발음 병음(주황 텍스트) 표시
    _punct_set = frozenset("?.,，．？!！、。；;：:")

    def _is_punct_only(s: str) -> bool:
        t = s.strip()
        return len(t) <= 2 and all(c in _punct_set for c in t)

    def _align_pinyin_with_hanzi(sen_chars: str, syllables: list[str]) -> tuple[str, list[str], bool]:
        """한자 문장(구두점 포함)과 병음 음절을 1:1로 맞춰, 병음 줄에 구두점을 끼워 넣은 문자열과 음절별 prefix 반환.
        반환: (display_pinyin, prefix_before_syllable, aligned). aligned=False면 prefix는 사용하지 않고 호출처에서 기존 방식으로 계산.
        """
        parts: list[str] = []
        syl_idx = 0
        for c in sen_chars:
            if c in _punct_set or c.isspace():
                parts.append(c)
            else:
                if syl_idx < len(syllables):
                    parts.append(syllables[syl_idx])
                    syl_idx += 1
        if syl_idx != len(syllables):
            return (" ".join(syllables), [], False)

        # 음절 사이에만 공백, 구두점은 붙여서
        display = ""
        prefix_before_syllable: list[str] = []
        for i, p in enumerate(parts):
            if p not in _punct_set and not p.isspace():
                prefix_before_syllable.append(display)
            display += p
            if i + 1 < len(parts) and p not in _punct_set and not p.isspace() and parts[i + 1] not in _punct_set and not parts[i + 1].isspace():
                display += " "
        prefix_before_syllable.append(display)
        return (display, prefix_before_syllable, True)

    if pinyin_text:
        studio._step1_sparkline_data = None
        syllables = pinyin_text.strip().split()
        diff_per = diff_lexical_phonetic_per_syllable(pinyin_lexical, pinyin_phonetic)
        while len(diff_per) < len(syllables):
            diff_per.append(None)
        diff_per = diff_per[: len(syllables)]
        def _render_syllable(font_ft: Any, font_pg: Any, text: str, color: tuple) -> tuple[Any, Any]:
            if font_ft is not None:
                try:
                    surf, rect = font_ft.render(text, color)
                    return surf, rect
                except Exception:
                    pass
            surf = font_pg.render(text, True, color)
            return surf, surf.get_rect()

        # 한자와 칸 맞춤: 병음 줄에 구두점(! , ? 등)을 같은 위치에 끼워 넣기
        sen_chars = "".join(str(x) for x in sentences)
        display_pinyin, prefix_before_syllable, pinyin_aligned = _align_pinyin_with_hanzi(sen_chars, syllables)
        display_syllables: list[tuple[str, Optional[str]]] = [
            (syllables[i], diff_per[i] if i < len(diff_per) else None)
            for i in range(len(syllables))
            if not _is_punct_only(syllables[i])
        ]
        # 본래 성조: diff에 성조가 없을 때 pinyin_lexical 음절 참고
        lexical_syllables = (pinyin_lexical or "").strip().split()
        while len(lexical_syllables) < len(syllables):
            lexical_syllables.append("")
        lexical_syllables = lexical_syllables[: len(syllables)]
        lexical_for_display: list[str] = [
            lexical_syllables[i]
            for i in range(len(syllables))
            if not _is_punct_only(syllables[i])
        ]

        space_surf, space_rect = _render_syllable(pinyin_ft, font_cn, " ", (220, 70, 70))
        space_w = space_rect.width if space_rect else 8
        y_red_top = center_top
        pinyin_hanzi_gap = 180  # 병음 아래 ~ 한자 위 여유
        contour_gap = 4
        contour_height = 16
        line_color = (255, 180, 80)
        line_thickness = 5  # 성조선 진하게

        # 표기 병음: 한 줄 렌더 (구두점 포함) → 칸 위치 계산용; 실제 그리기는 slot_left_list 반영 후 아래에서
        line_surf, line_rect = _render_syllable(pinyin_ft, font_cn, display_pinyin, (220, 70, 70))
        x_start = cx - line_rect.width // 2
        # 칸 위치: 실제로 그리는 display_pinyin의 앞부분을 잘라서 측정 → 뒷부분 커닝/위치 일치
        n_syl = len(display_syllables)
        prefix_w: list[float] = []
        if pinyin_aligned and len(prefix_before_syllable) >= n_syl + 1:
            for i in range(n_syl + 1):
                # prefix_before_syllable[i]와 같은 길이의 display_pinyin 앞부분으로 측정 (한 번에 그린 줄과 동일 커닝)
                prefix_len = len(prefix_before_syllable[i])
                chunk = display_pinyin[:prefix_len] if prefix_len <= len(display_pinyin) else prefix_before_syllable[i]
                _, r = _render_syllable(pinyin_ft, font_cn, chunk, (220, 70, 70))
                prefix_w.append(r.width)
        else:
            # 정렬 실패 시에도 실제 그린 줄에서 음절 시작 위치를 찾아 동그라미 위치 맞춤
            fallback_pinyin = " ".join(syllables)
            pos = 0
            syllable_starts: list[int] = []
            for syl, _ in display_syllables:
                idx = fallback_pinyin.find(syl, pos)
                if idx >= 0:
                    syllable_starts.append(idx)
                    pos = idx + len(syl)
                else:
                    syllable_starts.append(pos)
            for i in range(n_syl + 1):
                if i == 0:
                    prefix_w.append(0.0)
                elif i < len(syllable_starts):
                    chunk = fallback_pinyin[: syllable_starts[i]]
                    _, r = _render_syllable(pinyin_ft, font_cn, chunk, (220, 70, 70))
                    prefix_w.append(r.width)
                else:
                    prefix_w.append(line_rect.width)

        # 속도 시각화: syllable_times가 있으면 구간 길이에 비례해 자간 배분
        syllable_times_l1 = item.get("syllable_times_l1") or []
        syllable_times_l2 = item.get("syllable_times_l2") or []
        has_l1 = len(syllable_times_l1) == n_syl + 1
        has_l2 = len(syllable_times_l2) == n_syl + 1
        use_speed = n_syl > 0 and (has_l1 or has_l2)
        base_x = cx - line_rect.width // 2
        total_width_f = float(line_rect.width)
        if use_speed:
            t_list = syllable_times_l2 if has_l2 else syllable_times_l1
            durations = [t_list[i + 1] - t_list[i] for i in range(n_syl)]
            total_d = sum(durations)
            if total_d < 1e-9:
                total_d = 1.0
            slot_left_list = [base_x + total_width_f * sum(durations[:i]) / total_d for i in range(n_syl)]
            slot_width_list = [total_width_f * d / total_d for d in durations]
        else:
            slot_left_list = [base_x + prefix_w[i] for i in range(n_syl)]
            slot_width_list = []
            for i in range(n_syl):
                w = prefix_w[i + 1] - prefix_w[i]
                if not pinyin_aligned and i < n_syl - 1:
                    w -= space_w
                slot_width_list.append(max(1, int(w)))

        # 표기 병음: 속도 기반이면 음절별로 그리기, 아니면 한 줄로
        if use_speed:
            _syl_surfs = []
            for i in range(n_syl):
                syl = display_syllables[i][0]
                syl_surf, syl_rect = _render_syllable(pinyin_ft, font_cn, syl, (220, 70, 70))
                _syl_surfs.append((syl_surf, syl_rect))
            # 슬롯 폭이 음절 텍스트보다 좁으면 겹침 발생 → 최소 여백(min_pad) 확보 후 재배치
            min_pad = 8
            adjusted_lefts = list(slot_left_list)
            for i in range(n_syl):
                sw = slot_width_list[i]
                tw = _syl_surfs[i][1].width
                if tw + min_pad > sw:
                    # 슬롯 중심 기준으로 텍스트 배치, 다음 음절과 겹치면 밀어냄
                    center = slot_left_list[i] + sw / 2
                    adjusted_lefts[i] = center - tw / 2
            for i in range(1, n_syl):
                prev_right = adjusted_lefts[i - 1] + _syl_surfs[i - 1][1].width + min_pad
                if adjusted_lefts[i] < prev_right:
                    adjusted_lefts[i] = prev_right
            for i in range(n_syl):
                syl_surf, syl_rect = _syl_surfs[i]
                sw = slot_width_list[i]
                sx = int(adjusted_lefts[i])
                screen.blit(syl_surf, (sx, y_red_top))
        else:
            screen.blit(line_surf, (x_start, y_red_top))

        # 성조 표기 규칙: 표기 병음에서 성조가 붙는 모음(āéǐ 등) 위치 = 병음이 표기되는 정확한 위치
        _TONED_VOWELS = frozenset("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ")

        def _tonic_vowel_index(s: str) -> Optional[int]:
            """표기 병음 문자열에서 성조가 붙은 모음의 인덱스. 없으면 None(경성 등)."""
            for i, c in enumerate(s):
                if c in _TONED_VOWELS:
                    return i
            return None

        def _tonic_center_x(slot_left: int, syl: str) -> int:
            """붉은 표기 병음에서 성조가 붙는 모음(병음표시 위치) 바로 위에 동그라미 → 해당 모음 중심 x."""
            idx = _tonic_vowel_index(syl)
            if idx is None:
                _, r = _render_syllable(pinyin_ft, font_cn, syl, (220, 70, 70))
                return slot_left + r.width // 2
            _, r_prefix = _render_syllable(pinyin_ft, font_cn, syl[:idx], (220, 70, 70))
            _, r_char = _render_syllable(pinyin_ft, font_cn, syl[idx], (220, 70, 70))
            return slot_left + r_prefix.width + r_char.width // 2

        def _draw_tone_contour(surf: Any, left: int, bottom: int, width: int, tone: float) -> None:
            """성조 시각화: 1=고평, 2=상승, 3=V자, 3.5=반3성, 4=하강, 5/0=경성(점선)."""
            top = bottom - contour_height
            mid_y = (top + bottom) // 2
            right = left + width
            mid_x = (left + right) // 2
            left, right, top, bottom = int(left), int(right), int(top), int(bottom)
            mid_x, mid_y = int(mid_x), int(mid_y)
            is_neutral = tone <= 0.5 or tone >= 4.5
            is_half_third = 3.4 <= tone <= 3.6

            def _line(a: tuple, b: tuple) -> None:
                if is_neutral:
                    _draw_dotted_line(surf, line_color, a, b, line_thickness, dash_length=5)
                else:
                    pygame.draw.line(surf, line_color, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), line_thickness)

            if is_neutral:
                _line((left, mid_y), (right, mid_y))
            elif 1 <= tone < 1.5:
                _line((left, top), (right, top))
            elif 2 <= tone < 2.5:
                _line((left, bottom), (right, top))
            elif is_half_third:
                _line((left, mid_y), (mid_x, bottom))
            elif 2.9 <= tone <= 3.1:
                _line((left, mid_y), (mid_x, bottom))
                _line((mid_x, bottom), (right, mid_y))
            elif 4 <= tone < 4.5:
                _line((left, top), (right, bottom))
            else:
                _line((left, mid_y), (right, mid_y))

        def _tone_contour_point(left: float, bottom: float, width: float, height: float, tone: float, t: float) -> tuple[float, float]:
            """성조 곡선: 1~5도 척도. 1도=bottom(낮음), 5도=top(높음). y = bottom - (level-1)*(height/4)."""
            top = bottom - height
            t = max(0.0, min(1.0, t))
            x = left + t * width

            def level_to_y(level: float) -> float:
                return bottom - (level - 1.0) * (height / 4.0)

            is_half_third = 3.4 <= tone <= 3.6
            if tone <= 0.5 or tone >= 4.5:
                return (x, level_to_y(3.0))
            if 1 <= tone < 1.5:
                return (x, level_to_y(5.0))
            if 2 <= tone < 2.5:
                return (x, level_to_y(3.0 + 2.0 * t))
            if is_half_third:
                return (x, level_to_y(2.0 - t))
            if 2.9 <= tone <= 3.1:
                if t <= 0.5:
                    level = 2.0 - 2.0 * t
                else:
                    level = 1.0 + 6.0 * (t - 0.5)
                return (x, level_to_y(level))
            if 4 <= tone < 4.5:
                return (x, level_to_y(5.0 - 4.0 * t))
            return (x, level_to_y(3.0))

        # 발음 라인 위치: 성조 표기 규칙으로 정확한 위치 추정 → 그 위치에 성조 이미지 표시
        ref_phonetic_height = 28
        y_phonetic_top = y_red_top - 8 - ref_phonetic_height
        contour_bottom_y = y_phonetic_top - contour_gap
        contour_center_y = contour_bottom_y - contour_height // 2
        circle_radius = 6  # 성조 이미지 없을 때 폴백용
        icon_dir = _REPO_ROOT / "resource" / "image" / "icon"

        def _tone_to_filename(t: float) -> str:
            """성조 값 → 아이콘 파일명 (tone1~5, tone3_5)."""
            if t <= 0.5 or t >= 4.5:
                return "경성.png"   # 경성
            if 1 <= t < 1.5:
                return "1성.png"
            if 2 <= t < 2.5:
                return "2성.png"
            if 3.4 <= t <= 3.6:
                return "3_5성.png"
            if 2.9 <= t <= 3.1:
                return "3성.png"
            if 4 <= t < 4.5:
                return "4성.png"
            return "경성.png"

        tone_icon_max_h = 96  # 성조 아이콘 표시 높이 (비율 유지, 작은 이미지는 확대)

        def _get_tone_surface(filename: str) -> Optional[Any]:
            """성조 아이콘 Surface 캐시 로드. 높이를 tone_icon_max_h로 맞춤."""
            if filename in studio._tone_surfaces:
                return studio._tone_surfaces[filename]
            path = icon_dir / filename
            if path.exists():
                try:
                    surf = pygame.image.load(str(path))
                    if surf.get_alpha() is None:
                        surf = surf.convert()
                    else:
                        surf = surf.convert_alpha()
                    h = surf.get_height()
                    if h != tone_icon_max_h:
                        scale = tone_icon_max_h / h
                        w = max(1, int(surf.get_width() * scale))
                        surf = pygame.transform.smoothscale(surf, (w, tone_icon_max_h))
                    studio._tone_surfaces[filename] = surf
                    return surf
                except Exception:
                    pass
            return None

        for i, (syl, diff_val) in enumerate(display_syllables):
            slot_left = int(slot_left_list[i])
            slot_width = max(1, int(round(slot_width_list[i])))
            slot_rect = (slot_left, y_phonetic_top, slot_width, ref_phonetic_height)
            if _tone_contour_enabled:
                tone = parse_tone_from_syllable(diff_val) if (diff_val and parse_tone_from_syllable(diff_val) is not None) else (parse_tone_from_syllable(lexical_for_display[i]) if i < len(lexical_for_display) else parse_tone_from_syllable(syl))
                if tone is not None:
                    circle_x = _tonic_center_x(slot_left, syl)
                    tone_fname = _tone_to_filename(tone)
                    tone_surf = _get_tone_surface(tone_fname)
                    if tone_surf is not None:
                        tw, th = tone_surf.get_size()
                        screen.blit(tone_surf, (circle_x - tw // 2, contour_center_y - th // 2))
                    else:
                        pygame.draw.circle(screen, (220, 220, 220), (circle_x, contour_center_y), circle_radius, 2)
            if diff_val and _phonetic_diff_enabled:
                pass  # 주황 발음 텍스트 비표시


        # 작은 사각형: 전체 성조 곡선 항상 표시. 녹색 따라움직임은 L1 재생 시에만 (L2는 syllable 없음 → 진행선 없음)
        if n_syl > 0:
            l1_playing = (
                studio._step1_l1_channel is not None and studio._step1_l1_channel.get_busy()
            ) or studio._step1_l1_play_start_time is not None
            # 진행 위치: L1 재생 중이고 L1 syllable_times 있을 때만
            if l1_playing and has_l1:
                t_list = syllable_times_l1
                play_start = studio._step1_l1_play_start_time
            else:
                t_list = []
                play_start = None
            current_sec = (time.time() - play_start) if play_start is not None else None
            cur_i = 0
            blend = 0.0
            if current_sec is not None and t_list and len(t_list) >= n_syl + 1:
                t0, t1 = t_list[0], t_list[-1]
                current_sec = max(t0, min(current_sec, t1 + 0.01))
                for k in range(n_syl):
                    if t_list[k] <= current_sec < t_list[k + 1]:
                        cur_i = k
                        seg_dur = t_list[k + 1] - t_list[k]
                        blend = (current_sec - t_list[k]) / seg_dur if seg_dur > 1e-6 else 0.0
                        blend = max(0.0, min(1.0, blend))
                        break
                    if current_sec >= t_list[-1]:
                        cur_i = n_syl - 1
                        blend = 1.0
                        break
            target_pos = cur_i + blend
            item_id = (id(item), tuple(t_list) if t_list else ())
            if getattr(studio, "_step1_tone_last_item_id", None) != item_id:
                studio._step1_tone_last_item_id = item_id
                studio._step1_tone_smooth_pos = target_pos
            studio._step1_tone_smooth_pos += (target_pos - studio._step1_tone_smooth_pos) * 0.25
            smooth_pos = max(0.0, min(n_syl - 0.001, studio._step1_tone_smooth_pos))
            cur_i = int(smooth_pos)
            blend = smooth_pos - cur_i
            box_w, box_h = 640, 160
            box_x = cx - box_w // 2
            box_y = int(h * 0.06) + 56 + 30
            box_rect = pygame.Rect(box_x, box_y, box_w, box_h)
            contour_left = float(box_x)
            contour_bottom = float(box_y + box_h)
            contour_top = float(box_y)
            contour_width = float(box_w)
            contour_height = float(box_h)
            grid_color = (80, 80, 90)
            pygame.draw.rect(screen, (60, 60, 70), box_rect)
            for lev in range(5):
                y_lev = contour_top + (contour_bottom - contour_top) * lev / 4
                pygame.draw.line(screen, grid_color, (int(contour_left), int(y_lev)), (int(contour_left + contour_width), int(y_lev)), 1)
            pygame.draw.rect(screen, (0, 0, 0), box_rect, 2)
            font_small = studio._font_kr or pygame.font.Font(None, 20)
            for lev in range(5):
                y_lev = contour_top + (contour_bottom - contour_top) * lev / 4
                lbl = font_small.render(str(lev + 1), True, (120, 120, 130))
                screen.blit(lbl, (int(contour_left) - 14, int(y_lev) - 8))

            def _get_tone_for_syl(i: int) -> float:
                if i < 0 or i >= n_syl:
                    return 0.0
                syl, diff_val = display_syllables[i]
                lex_syl = lexical_for_display[i] if i < len(lexical_for_display) else syl
                t = parse_tone_from_syllable(diff_val) if (diff_val and parse_tone_from_syllable(diff_val) is not None) else parse_tone_from_syllable(lex_syl)
                return t if t is not None else 0.0

            def _pt(l: float, b: float, w: float, h: float, tone_val: float, t: float) -> tuple[float, float]:
                return _tone_contour_point(l, b, w, h, tone_val, t)

            n_seg = 16
            seg_w_full = contour_width / max(1, n_syl)
            full_pts: list[tuple[float, float]] = []
            for i in range(n_syl):
                tone_i = _get_tone_for_syl(i)
                left_i = contour_left + i * seg_w_full
                for k in range(n_seg + 1):
                    t = k / n_seg
                    full_pts.append(_pt(left_i, contour_bottom, seg_w_full, contour_height, tone_i, t))

            white_color = (255, 255, 255)
            pron_start_color = (160, 160, 165)
            fade_tail_color = (100, 100, 105)
            green_color = (100, 255, 120)
            green_start_color = (70, 180, 95)
            thick_bold = 12
            thick_start = 2
            pts_per_syl = n_seg + 1
            actual_ratio = 0.8   # 0~80% 구간에서 점점 진해짐
            fade_tail_ratio = 0.2  # 80%부터 끝까지 얇아짐
            cap_radius = max(2, thick_bold // 2)  # 녹색 진행 끝 둥글게
            # 흰색 라인 끝은 물방울 모양: 선과 같은 색의 작은 원으로 끝나게
            droplet_cap_radius = max(4, thick_bold // 2)

            progress_count = cur_i * (n_seg + 1) + min(n_seg, int(round(blend * n_seg)))
            progress_count = min(progress_count + 1, len(full_pts))
            show_green = play_start is not None  # L1 재생 시에만 녹색 진행선

            for i in range(n_syl):
                start_pt = i * pts_per_syl
                end_actual_pt = i * pts_per_syl + int(actual_ratio * pts_per_syl)
                actual_len = max(1, min(end_actual_pt, len(full_pts) - 1) - start_pt)
                tail_len = max(1, int(fade_tail_ratio * pts_per_syl))
                end_tail_pt = min(end_actual_pt + tail_len, (i + 1) * pts_per_syl - 1, len(full_pts) - 1)

                # 본체 구간 (0~80%): L1 재생 시에만 녹색이 지난 부분 녹색, 나머지 흰색
                for idx in range(start_pt, min(end_actual_pt, len(full_pts) - 1)):
                    progress = (idx - start_pt) / actual_len
                    thick = max(thick_start, int(thick_start + (thick_bold - thick_start) * progress))
                    if show_green and idx < progress_count - 1:
                        seg_r = int(green_start_color[0] + (green_color[0] - green_start_color[0]) * progress)
                        seg_g = int(green_start_color[1] + (green_color[1] - green_start_color[1]) * progress)
                        seg_b = int(green_start_color[2] + (green_color[2] - green_start_color[2]) * progress)
                    else:
                        seg_r = int(pron_start_color[0] + (white_color[0] - pron_start_color[0]) * progress)
                        seg_g = int(pron_start_color[1] + (white_color[1] - pron_start_color[1]) * progress)
                        seg_b = int(pron_start_color[2] + (white_color[2] - pron_start_color[2]) * progress)
                    seg_color = (min(255, max(0, seg_r)), min(255, max(0, seg_g)), min(255, max(0, seg_b)))
                    a = (full_pts[idx][0], full_pts[idx][1])
                    b_pt = (full_pts[idx + 1][0], full_pts[idx + 1][1])
                    pygame.draw.line(screen, seg_color, (int(a[0]), int(a[1])), (int(b_pt[0]), int(b_pt[1])), thick)

                # 꼬리 구간 (80%~끝): L1 재생 시에만 녹색
                for idx in range(end_actual_pt, end_tail_pt):
                    if idx + 1 >= len(full_pts):
                        break
                    color = (green_color if (show_green and idx < progress_count - 1) else white_color)
                    a = (full_pts[idx][0], full_pts[idx][1])
                    b_pt = (full_pts[idx + 1][0], full_pts[idx + 1][1])
                    pygame.draw.line(screen, color, (int(a[0]), int(a[1])), (int(b_pt[0]), int(b_pt[1])), thick_bold)

            # 녹색 진행 곡선 끝 둥글게 (L1 재생 시에만)
            if show_green and progress_count > 0 and full_pts:
                end_idx = min(progress_count, len(full_pts) - 1)
                prog_pt = full_pts[end_idx]
                pygame.draw.circle(screen, green_color, (int(prog_pt[0]), int(prog_pt[1])), cap_radius)

        # 한자 위치: 실제 병음 줄 높이만큼 띄워서 겹침 방지 (ref_height 고정값 대신 line_rect.height 사용)
        center_top = y_red_top + line_rect.height + pinyin_hanzi_gap

        # 속도 기반일 때 한자 음절별로 그리기 (자간 반영)
        hanzi_bottom_y = center_top + 62  # 폴백: 중심 + 폰트 절반
        if use_speed and n_syl > 0:
            hanzi_font_ft_inner = studio._font_cn_step1_ft or studio._font_cn_big_ft
            hanzi_chars = [c for c in sen_chars if c not in _punct_set and not c.isspace()]
            if len(hanzi_chars) == n_syl and hanzi_font_ft_inner is not None:
                _max_bottom = center_top
                for i in range(n_syl):
                    char = hanzi_chars[i]
                    try:
                        c_surf, c_rect = hanzi_font_ft_inner.render(char, (255, 255, 255))
                    except Exception:
                        c_surf = font_cn_big.render(char, True, (255, 255, 255))
                        c_rect = c_surf.get_rect()
                    cx_char = slot_left_list[i] + slot_width_list[i] / 2
                    blit_x = int(cx_char - c_rect.width / 2 - getattr(c_rect, "x", 0))
                    blit_y = int(center_top - c_rect.height / 2 - getattr(c_rect, "y", 0))
                    screen.blit(c_surf, (blit_x, blit_y))
                    _max_bottom = max(_max_bottom, blit_y + c_rect.height)
                hanzi_bottom_y = _max_bottom
                hanzi_drawn = True
        # 스파크라인 그리기용 데이터 (한자 위 미니맵)
        studio._step1_sparkline_data = (slot_left_list, slot_width_list, n_syl, display_syllables, lexical_for_display, center_top)
    else:
        studio._step1_sparkline_data = None

    # 한자 (큰 글자): 렌더 rect 기준으로 화면 가운데 정확히 배치 (속도 기반이 아닐 때)
    if not hanzi_drawn:
        hanzi_font_ft = studio._font_cn_step1_ft or studio._font_cn_big_ft
        if hanzi_font_ft is not None:
            try:
                sen_surf, sen_rect = hanzi_font_ft.render(sen_text[:80], (255, 255, 255))
                blit_x = cx - sen_rect.width // 2 - sen_rect.x
                blit_y = center_top - sen_rect.height // 2 - sen_rect.y
                screen.blit(sen_surf, (blit_x, blit_y))
                hanzi_bottom_y = blit_y + sen_rect.height
            except Exception:
                sen_surf = font_cn_big.render(sen_text[:80], True, (255, 255, 255))
                sr = sen_surf.get_rect(center=(cx, center_top))
                screen.blit(sen_surf, sr)
                hanzi_bottom_y = sr.bottom
        else:
            sen_surf = font_cn_big.render(sen_text[:80], True, (255, 255, 255))
            sr = sen_surf.get_rect(center=(cx, center_top))
            screen.blit(sen_surf, sr)
            hanzi_bottom_y = sr.bottom
    center_top += line_gap + 56  # 한자–뜻(해석) 간격 넓게

    # 해석 (한국어): 화면 가운데 정확히 배치
    if trans_text:
        trans_surf = font_kr_step1.render(trans_text[:80], True, (200, 200, 200))
        tr = trans_surf.get_rect(center=(cx, center_top))
        screen.blit(trans_surf, tr)

    return {
        "hanzi_bottom_y": hanzi_bottom_y,
        "slot_left_list": slot_left_list,
        "slot_width_list": slot_width_list,
        "use_speed": use_speed,
        "sentences": sentences,
        "cx": cx,
        "_punct_set": _punct_set,
    }
