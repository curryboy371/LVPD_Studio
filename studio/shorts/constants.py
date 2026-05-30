"""숏츠 스튜디오 상수."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from core.paths import SHORTS_HEIGHT, SHORTS_WIDTH, get_repo_root

_REPO_ROOT = get_repo_root()

# 화면 구역 높이 비율 (합 1.0)
ZONE_TOP_RATIO = 0.30
ZONE_MIDDLE_RATIO = 0.40
ZONE_BOTTOM_RATIO = 0.30

# 리소스 경로
SHORTS_IMAGE_DIR = _REPO_ROOT / "resource" / "image" / "shorts"
SHORTS_PANDA_DIR = SHORTS_IMAGE_DIR / "panda"
SHORTS_BG_DEFAULT = SHORTS_IMAGE_DIR / "bg_default.png"
SHORTS_BRAND_ICON = _REPO_ROOT / "resource" / "image" / "icon" / "icon.png"
# 1080 기준 — 전체 실루엣(머리+발)이 들어가도록 (원본 높이 ~1028px 크롭 기준)
SHORTS_BRAND_ICON_W = 200
SHORTS_BRAND_ICON_H = 120
# 1080×1920 기준 하단 중앙 — 아이콘 하단 여백(해상도에 비례 스케일, 작을수록 아래)
SHORTS_BRAND_ICON_BOTTOM_MARGIN = 50
# 회화 conv: 영상 바로 아래 main_slot 단어 이미지·한자:뜻 (1080×1920 기준)
SHORTS_CONV_MAIN_WORD_SCALE = 1.4
SHORTS_CONV_MAIN_WORD_IMG_MAX = 160
SHORTS_CONV_MAIN_WORD_BELOW_VIDEO_GAP = 12
SHORTS_CONV_MAIN_WORD_LABEL_GAP = 10
SHORTS_CONV_MAIN_WORD_HANZI_PINYIN_GAP = 10
SHORTS_CONV_MAIN_WORD_LABEL_FONT_SIZE = 34
SHORTS_BRAND_TITLE_TEXT = ""
SHORTS_BRAND_TITLE_COLOR = (64, 64, 64)
SHORTS_BRAND_TITLE_FONT_SIZE = 30
SHORTS_BRAND_TITLE_GAP_ABOVE_ICON = 10
# 1080×1920 기준 — 훅 타이틀 Y(화면 최상단부터, 작을수록 위)
SHORTS_HOOK_TITLE_Y = 250
# 하위 호환 이름
SHORTS_HOOK_TITLE_Y_OFFSET = SHORTS_HOOK_TITLE_Y
SHORTS_HOOK_TITLE_LINE_GAP = 0
# 훅 타이틀 2줄: 윗줄(첫 줄) / 아랫줄(\n 이후)
HOOK_TITLE_LINE1_COLOR = (255, 110, 175)
HOOK_TITLE_LINE2_COLOR = (255, 255, 255)
# 1080×1920 기준 — 중앙 노래방 문장 y 보정(양수 = 아래)
SHORTS_MIDDLE_Y_OFFSET = 72
# 1080×1920 기준 — 병음 줄 추가 y 보정(양수 = 아래)
SHORTS_PINYIN_Y_OFFSET = 72
# 1080×1920 기준 — 병음↔한자 줄 간격(기본 line_gap보다 좁게)
SHORTS_PINYIN_HANZI_GAP = 60
# 1080×1920 기준 — 한자↔번역(뜻) 추가 간격
SHORTS_TRANSLATION_EXTRA_GAP = 28
# 단어 숏츠 연상 이미지 — inner 패딩·최대 크기(비디오 영역 대비)
SHORTS_VOCAB_WORD_IMG_PAD = 32
SHORTS_VOCAB_WORD_IMG_MAX_RATIO = 0.90
# 단어 숏츠 품사 줄 — 뜻(kr) 대비 글자 크기 비율
SHORTS_VOCAB_POS_FONT_RATIO = 0.62
# 한자 하단 ↔ 품사 줄 간격 (1080×1920 기준)
SHORTS_VOCAB_POS_AFTER_HANZI_GAP = 40
# 품사 ↔ TTS 뜻 자막 간격
SHORTS_VOCAB_MEANING_SUBTITLE_GAP = 10
# TTS 자막(뜻) 하단 ↔ tip 상단 (1080×1920 기준)
SHORTS_VOCAB_MEANING_TO_TIP_GAP = 28
# (레거시) icon 기준 tip — 미사용
SHORTS_VOCAB_TIP_ABOVE_ICON_GAP = 48
SHORTS_VOCAB_TIP_ABOVE_BRAND_GAP = SHORTS_VOCAB_TIP_ABOVE_ICON_GAP
# 연상 이미지 슬롯 하단 ↔ 병음 상단 (1080×1920, 양수=아래·이미지와 분리)
SHORTS_VOCAB_CN_BELOW_IMAGE_GAP = 12
# 품사(병음·한자 블록) 하단 ↔ 뜻 상단
SHORTS_VOCAB_CN_ABOVE_MEANING_GAP = 12
# tip 글자 크기 (ko_subtitle 대비)
SHORTS_VOCAB_TIP_FONT_RATIO = 0.78
# tip 줄 간격 (1080×1920 기준, `\n` 줄바꿈)
SHORTS_VOCAB_TIP_LINE_GAP = 6
# CTA_HOLD(마지막 대기) — tip 하단 ↔ last_hold_text 상단 (1080×1920)
SHORTS_LAST_HOLD_BELOW_TIP_GAP = 28
# 훅 타이틀 하단 ↔ 연상 이미지 상단 간격 (1080×1920 기준)
SHORTS_VOCAB_BELOW_HOOK_GAP = 4
# 훅 타이틀 제외 — 단어 모드 본문(병음·한자·품사·뜻) y 보정 (1080×1920, 양수=아래)
SHORTS_VOCAB_TEXT_Y_OFFSET = 16
# 연상 이미지·비디오 슬롯 y 보정 (1080×1920, 음수=위·병음·한자 텍스트는 그대로)
SHORTS_VOCAB_IMAGE_Y_OFFSET = -56
# 연상 이미지 슬롯 높이 — middle − 양쪽 패딩(비디오 contain 영역과 동일)
# 이미지/동영상 슬롯 하단 ↔ 뜻·TTS 자막 상단 (슬롯 밖으로, 1080×1920 기준)
SHORTS_VOCAB_MEANING_BELOW_SLOT_GAP = 24
# (레거시) 슬롯 안 하단 여백 — 뜻 Y 계산에는 미사용
SHORTS_VOCAB_OVERLAY_BOTTOM_PAD = 24
# 병음 줄 고정 슬롯 높이(병음 없어도 한자 Y 유지)
SHORTS_VOCAB_PINYIN_SLOT_H = 42
# 단어 모드 병음↔한자 추가 간격 (1080×1920)
SHORTS_VOCAB_PINYIN_HANZI_GAP = 18
# 연상 이미지 위 병음·한자·품사 배경 (알파 ≈80%)
SHORTS_VOCAB_OVERLAY_BG_RGBA = (0, 0, 0, 204)
SHORTS_VOCAB_OVERLAY_BG_PAD_X = 20
SHORTS_VOCAB_OVERLAY_BG_PAD_Y = 10


class VocabOverlayLayout(NamedTuple):
    """이미지 → 병음·한자·품사 → 뜻·TTS → tip."""

    pinyin_y: int
    hanzi_y: int
    tip_y: int
    meaning_y: int
    meaning_anchor_bottom: int


def shorts_vocab_below_hook_gap(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(8, int(SHORTS_VOCAB_BELOW_HOOK_GAP * sy))


def shorts_vocab_text_y_offset(frame_height: int) -> int:
    """단어 숏츠 — 훅 타이틀 제외 텍스트·연상 이미지 y 보정."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(0, int(SHORTS_VOCAB_TEXT_Y_OFFSET * sy))


def shorts_vocab_image_y_offset(frame_height: int) -> int:
    """연상 이미지만 y 보정(음수면 위)."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return int(SHORTS_VOCAB_IMAGE_Y_OFFSET * sy)


def shorts_vocab_content_y_offset(frame_height: int) -> int:
    """하위 호환 alias."""
    return shorts_vocab_text_y_offset(frame_height)


def shorts_vocab_layout_top(
    middle_top: int,
    frame_height: int,
    *,
    hook_title_bottom_y: int = 0,
) -> int:
    """단어 숏츠 본문(이미지·병음·한자…) 시작 Y — 훅 타이틀과 겹치지 않게."""
    dy = shorts_vocab_text_y_offset(frame_height)
    base = int(middle_top) + dy
    if hook_title_bottom_y > 0:
        return max(base, int(hook_title_bottom_y) + shorts_vocab_below_hook_gap(frame_height) + dy)
    return base


def shorts_vocab_word_img_pad(frame_height: int) -> int:
    """연상 이미지·비디오 공통 inner 패딩(프레임 높이 스케일)."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(16, int(SHORTS_VOCAB_WORD_IMG_PAD * sy))


def shorts_vocab_word_img_inner_size(
    middle_width: int,
    middle_height: int,
    frame_height: int,
) -> tuple[int, int]:
    """middle 안 연상 이미지 최대 크기(inner 패딩 + MAX_RATIO)."""
    mw = max(1, int(middle_width))
    mh = max(1, int(middle_height))
    pad = shorts_vocab_word_img_pad(frame_height)
    r = float(SHORTS_VOCAB_WORD_IMG_MAX_RATIO)
    w = max(1, int((mw - pad * 2) * r))
    h = max(1, int((mh - pad * 2) * r))
    return w, h


def shorts_vocab_image_band_height(middle_height: int, *, frame_height: int = 0) -> int:
    """middle 구역 상단 연상 이미지 고정 밴드(비디오 inner 높이)."""
    fh = int(frame_height) if frame_height > 0 else SHORTS_HEIGHT
    return shorts_vocab_word_img_inner_size(1, middle_height, fh)[1]


def shorts_vocab_layout_metrics(
    middle_top: int,
    middle_height: int,
    middle_bottom: int,
    frame_height: int,
    *,
    hook_title_bottom_y: int = 0,
) -> tuple[int, int]:
    """(layout_top, img_band_h) — 훅 타이틀 아래 본문 배치."""
    layout_top = shorts_vocab_layout_top(
        middle_top, frame_height, hook_title_bottom_y=hook_title_bottom_y
    )
    default_band = shorts_vocab_image_band_height(middle_height, frame_height=frame_height)
    room = int(middle_bottom) - int(layout_top)
    img_band_h = max(48, min(default_band, room))
    return layout_top, img_band_h


def shorts_vocab_overlay_bottom_pad(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(8, int(SHORTS_VOCAB_OVERLAY_BOTTOM_PAD * sy))


def shorts_vocab_meaning_below_slot_gap(frame_height: int) -> int:
    """연상·동영상 슬롯 바로 아래 — 뜻/TTS가 영상을 가리지 않게."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(12, int(SHORTS_VOCAB_MEANING_BELOW_SLOT_GAP * sy))


def shorts_vocab_ko_subtitle_line_height(
    frame_height: int, *, ko_subtitle_pt: int = 46
) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(28, int(int(ko_subtitle_pt) * 1.15 * sy))


def shorts_vocab_tip_line_height(
    frame_height: int, *, ko_subtitle_pt: int = 46
) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    pt = shorts_vocab_tip_font_pt(ko_subtitle_pt=ko_subtitle_pt)
    return max(20, int(int(pt) * 1.15 * sy))


def shorts_vocab_tip_line_gap(frame_height: int) -> int:
    """tip 여러 줄(`\\n`) 사이 간격."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(2, int(SHORTS_VOCAB_TIP_LINE_GAP * sy))


def parse_vocab_tip_lines(text: str) -> list[str]:
    """words.csv tip — `\\n` 또는 실제 줄바꿈."""
    raw = (text or "").replace("\\n", "\n").strip()
    if not raw:
        return []
    return [ln.strip() for ln in raw.split("\n") if ln.strip()]


parse_last_hold_lines = parse_vocab_tip_lines


def shorts_last_hold_below_tip_gap(frame_height: int) -> int:
    """CTA_HOLD last_hold_text — tip 블록 바로 아래."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(4, int(SHORTS_LAST_HOLD_BELOW_TIP_GAP * sy))


def measure_vocab_tip_block_height(
    text: str,
    frame_height: int,
    *,
    ko_subtitle_pt: int = 46,
) -> int:
    """tip 여러 줄 블록 높이(px)."""
    lines = parse_vocab_tip_lines(text)
    if not lines:
        return 0
    line_h = shorts_vocab_tip_line_height(frame_height, ko_subtitle_pt=ko_subtitle_pt)
    gap = shorts_vocab_tip_line_gap(frame_height)
    return len(lines) * line_h + max(0, len(lines) - 1) * gap


def shorts_vocab_meaning_to_tip_gap(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(6, int(SHORTS_VOCAB_MEANING_TO_TIP_GAP * sy))


def shorts_vocab_tip_above_icon_gap(frame_height: int) -> int:
    """tip 하단과 icon 상단 사이 간격."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(8, int(SHORTS_VOCAB_TIP_ABOVE_ICON_GAP * sy))


def shorts_vocab_tip_above_brand_gap(frame_height: int) -> int:
    return shorts_vocab_tip_above_icon_gap(frame_height)


def shorts_vocab_cn_below_image_gap(frame_height: int) -> int:
    """이미지 슬롯 바로 아래 — 병음·한자가 영상/PNG를 가리지 않게."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(4, int(SHORTS_VOCAB_CN_BELOW_IMAGE_GAP * sy))


def shorts_vocab_cn_above_meaning_gap(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(6, int(SHORTS_VOCAB_CN_ABOVE_MEANING_GAP * sy))


def shorts_brand_icon_top_y(
    frame_width: int,
    frame_height: int,
    *,
    icon_width: int = 0,
    icon_height: int = 0,
    y_offset: int = 0,
) -> int:
    """브랜드 icon.png 좌상단 Y."""
    w = max(1, int(frame_width))
    h = max(1, int(frame_height))
    sx = w / float(SHORTS_WIDTH)
    sy = h / float(SHORTS_HEIGHT)
    iw = max(1, int(icon_width) if icon_width > 0 else int(SHORTS_BRAND_ICON_W * sx))
    ih = max(1, int(icon_height) if icon_height > 0 else int(SHORTS_BRAND_ICON_H * sy))
    _, y = shorts_brand_icon_xy(w, h, icon_width=iw, icon_height=ih, y_offset=y_offset)
    return int(y)


def shorts_brand_title_top_y(
    frame_width: int,
    frame_height: int,
    *,
    y_offset: int = 0,
) -> int:
    """하단 브랜드 '#중국어 여포판다' 텍스트 상단 Y."""
    h = max(1, int(frame_height))
    icon_y = shorts_brand_icon_top_y(
        frame_width, frame_height, y_offset=y_offset
    )
    gap = shorts_brand_title_gap(h)
    title_h = max(14, int(shorts_brand_title_font_size(h) * 1.2))
    return max(0, int(icon_y) - gap - title_h)


def shorts_vocab_tip_before_cn_gap(frame_height: int) -> int:
    """하위 호환."""
    return shorts_vocab_cn_above_meaning_gap(frame_height)


def shorts_vocab_meaning_below_tip_gap(frame_height: int) -> int:
    """하위 호환."""
    return shorts_vocab_meaning_to_tip_gap(frame_height)


def shorts_vocab_overlay_layout(
    layout_top: int,
    img_band_h: int,
    frame_height: int,
    *,
    frame_width: int = 0,
    has_pos: bool = True,
    has_tip: bool = False,
    cn_font_pt: int = 84,
    kr_font_pt: int = 36,
    ko_subtitle_pt: int = 46,
) -> VocabOverlayLayout:
    """이미지 아래: 병음·한자·품사 → 뜻·TTS → tip."""
    fw = max(1, int(frame_width) if frame_width > 0 else SHORTS_WIDTH)
    fh = max(1, int(frame_height))
    slot_bottom = int(layout_top) + int(img_band_h)
    meaning_gap = shorts_vocab_meaning_subtitle_gap(fh)

    pinyin_y = slot_bottom + shorts_vocab_cn_below_image_gap(fh)
    hanzi_line_h = shorts_vocab_hanzi_line_height(fh, cn_font_pt=cn_font_pt)
    hanzi_y = (
        pinyin_y
        + shorts_vocab_pinyin_slot_height(fh)
        + shorts_vocab_pinyin_hanzi_gap(fh)
    )

    if has_pos:
        cn_block_bottom = (
            int(hanzi_y)
            + int(hanzi_line_h)
            + shorts_vocab_pos_after_hanzi_gap(fh)
            + shorts_vocab_pos_line_height(fh, kr_font_pt=kr_font_pt)
        )
    else:
        cn_block_bottom = int(hanzi_y) + int(hanzi_line_h)

    meaning_y = max(
        slot_bottom + shorts_vocab_meaning_below_slot_gap(fh),
        cn_block_bottom + shorts_vocab_cn_above_meaning_gap(fh),
    )
    meaning_anchor_bottom = meaning_y - meaning_gap

    if has_tip:
        subtitle_h = shorts_vocab_ko_subtitle_line_height(
            fh, ko_subtitle_pt=ko_subtitle_pt
        )
        # clip_scene TTS: anchor.bottom(=meaning_anchor_bottom-1) + meaning_subtitle_gap
        tts_top = int(meaning_anchor_bottom) - 1 + shorts_vocab_meaning_subtitle_gap(fh)
        tts_bottom = tts_top + subtitle_h
        meaning_bottom = int(meaning_y) + subtitle_h
        tip_y = (
            max(tts_bottom, meaning_bottom) + shorts_vocab_meaning_to_tip_gap(fh)
        )
    else:
        tip_y = 0

    return VocabOverlayLayout(
        pinyin_y=pinyin_y,
        hanzi_y=hanzi_y,
        tip_y=tip_y,
        meaning_y=meaning_y,
        meaning_anchor_bottom=meaning_anchor_bottom,
    )


def shorts_vocab_pinyin_slot_height(frame_height: int) -> int:
    """병음 유무와 관계없이 확보하는 줄 높이."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(24, int(SHORTS_VOCAB_PINYIN_SLOT_H * sy))


def shorts_vocab_pinyin_hanzi_gap(frame_height: int) -> int:
    """단어 모드 병음·한자 줄 사이 간격."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(4, int(SHORTS_VOCAB_PINYIN_HANZI_GAP * sy))


def shorts_vocab_mode_hint_above_pinyin_gap(frame_height: int) -> int:
    """병음 위 듣기·말하기 안내 문구 간격."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(6, int(10 * sy))


def shorts_vocab_hanzi_y(
    layout_top: int,
    img_band_h: int,
    frame_height: int,
    *,
    has_pos: bool = True,
    cn_font_pt: int = 84,
    kr_font_pt: int = 36,
) -> int:
    """한자 상단 Y — 이미지 슬롯 위 오버레이."""
    return shorts_vocab_overlay_layout(
        layout_top,
        img_band_h,
        frame_height,
        has_pos=has_pos,
        cn_font_pt=cn_font_pt,
        kr_font_pt=kr_font_pt,
    ).hanzi_y


def shorts_vocab_hanzi_line_height(frame_height: int, *, cn_font_pt: int = 84) -> int:
    """한자 한 줄 높이(품사·자막 앵커용)."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(44, int(int(cn_font_pt) * 1.1 * sy))


def shorts_vocab_pos_line_height(frame_height: int, *, kr_font_pt: int = 36) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(16, int(int(kr_font_pt) * float(SHORTS_VOCAB_POS_FONT_RATIO) * 1.2 * sy))


def shorts_vocab_tip_after_meaning_gap(frame_height: int) -> int:
    """하위 호환 — tip↔뜻 간격(뜻이 tip 아래)."""
    return shorts_vocab_meaning_below_tip_gap(frame_height)


def shorts_vocab_tip_font_pt(*, ko_subtitle_pt: int = 46) -> int:
    return max(20, int(int(ko_subtitle_pt) * float(SHORTS_VOCAB_TIP_FONT_RATIO)))


def shorts_vocab_meaning_subtitle_gap(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(4, int(SHORTS_VOCAB_MEANING_SUBTITLE_GAP * sy))


def shorts_vocab_text_stack_bottom(
    layout_top: int,
    img_band_h: int,
    frame_height: int,
    *,
    cn_font_pt: int = 84,
    kr_font_pt: int = 36,
    has_pos: bool = True,
    ko_subtitle_pt: int = 46,
) -> int:
    """TTS 뜻 자막 anchor rect bottom Y."""
    return shorts_vocab_overlay_layout(
        layout_top,
        img_band_h,
        frame_height,
        has_pos=has_pos,
        has_tip=False,
        cn_font_pt=cn_font_pt,
        kr_font_pt=kr_font_pt,
        ko_subtitle_pt=ko_subtitle_pt,
    ).meaning_anchor_bottom


def shorts_middle_y_offset(frame_height: int) -> int:
    """프레임 높이에 맞춘 중앙 문장 y 오프셋."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return int(SHORTS_MIDDLE_Y_OFFSET * sy)


def shorts_pinyin_y_offset(frame_height: int) -> int:
    """프레임 높이에 맞춘 병음 줄 y 오프셋."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return int(SHORTS_PINYIN_Y_OFFSET * sy)


def shorts_pinyin_hanzi_gap(frame_height: int) -> int:
    """프레임 높이에 맞춘 병음·한자 줄 간격."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(8, int(SHORTS_PINYIN_HANZI_GAP * sy))


def shorts_vocab_pos_after_hanzi_gap(frame_height: int) -> int:
    """한자·병음 블록과 품사 줄 사이 간격."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(8, int(SHORTS_VOCAB_POS_AFTER_HANZI_GAP * sy))


def shorts_translation_extra_gap(frame_height: int) -> int:
    """프레임 높이에 맞춘 한자·번역(뜻) 추가 간격."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(4, int(SHORTS_TRANSLATION_EXTRA_GAP * sy))


def shorts_hook_title_y(frame_height: int) -> int:
    """프레임 높이에 맞춘 훅 타이틀 앵커 Y(화면 상단 기준)."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return int(SHORTS_HOOK_TITLE_Y * sy)


def shorts_hook_title_y_offset(frame_height: int) -> int:
    """하위 호환 alias."""
    return shorts_hook_title_y(frame_height)


def shorts_hook_title_line_gap(frame_height: int) -> int:
    """프레임 높이에 맞춘 훅 타이틀 줄 간격."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(0, int(SHORTS_HOOK_TITLE_LINE_GAP * sy))


def shorts_brand_title_font_size(frame_height: int) -> int:
    """프레임 높이에 맞춘 하단 브랜드 타이틀 폰트 크기."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(12, int(SHORTS_BRAND_TITLE_FONT_SIZE * sy))


def shorts_brand_title_gap(frame_height: int) -> int:
    """아이콘 위 브랜드 타이틀 간격."""
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(2, int(SHORTS_BRAND_TITLE_GAP_ABOVE_ICON * sy))


def shorts_brand_icon_xy(
    frame_width: int,
    frame_height: int,
    *,
    icon_width: int,
    icon_height: int,
    y_offset: int = 0,
) -> tuple[int, int]:
    """프레임 크기에 맞춘 브랜드 아이콘 좌상단 좌표(하단 중앙 정렬)."""
    w = max(1, int(frame_width))
    h = max(1, int(frame_height))
    iw = max(1, int(icon_width))
    ih = max(1, int(icon_height))
    sy = h / float(SHORTS_HEIGHT)
    margin = int(SHORTS_BRAND_ICON_BOTTOM_MARGIN * sy)
    x = (w - iw) // 2
    y = max(0, h - ih - margin + int(y_offset))
    return x, y

# FSM 타이밍(초)
HOOK_FADE_IN_SEC = 1.0
CTA_HOLD_SEC = 2.5
# 회화·단어 마지막 대기: shorts_*_clips.last_hold_sec (비우면 CTA_HOLD_SEC)
CLIP_TRANSITION_FADE_SEC = 0.3
SHORTS_SOUND_PLAY_COUNT = 2
# 학습 1·2회(원음) 화면 자막
SHORTS_NATIVE_LISTEN_LABEL = "원어민 발음을 잘 들어보세요"
# 학습 3회 follow_along.mp3 TTS + 3·4회 화면 자막
SHORTS_FOLLOW_ALONG_LABEL = "따라해보세요"
# 단어 모드: 병음 위 듣기·말하기 안내 (F5 단어장·숏츠 단어 공통)
VOCAB_CN_LISTEN_HINT = "잘 들어보세요"
VOCAB_CN_SPEAK_HINT = "따라 말해보세요"
VOCAB_CN_LISTEN_HINT_COLOR = (46, 204, 113)
VOCAB_CN_SPEAK_HINT_COLOR = (255, 159, 67)
# 단어 모드: 연속 중국어 재생 사이 대기(초)
SHORTS_VOCAB_CN_REPLAY_PAUSE_SEC = 0.8
# 회화 conv_script: 중국어 mp3 재생 사이·문장 간 TTS 시작 전 대기(초)
SHORTS_CONV_CN_REPLAY_PAUSE_SEC = 0.7
# 단어 모드: 중국어 발음 최소 재생 횟수(sound_repeat_count 와 큰 값 사용)
SHORTS_VOCAB_CN_MIN_PLAY_COUNT = 2
# 4단계 BG: 노래방은 sound_path 길이 + 이 값(초) 만큼 더 느리게 진행
SHORTS_BG_KARAOKE_SLOW_EXTRA_SEC = 1.5
SHORTS_BG_PRACTICE_MIN_SEC = 4.0
SHORTS_VIDEO_END_HOLD_SEC = 0.6
SHORTS_VIDEO_FADE_OUT_SEC = 0.8
# 페이드 후에도 비디오가 남도록 최소 알파(0=완전 숨김, 255=그대로)
SHORTS_VIDEO_AFTER_ALPHA = 30

# 숏츠 회화 모드 ko_narration TTS 합성 속도 (1.0=기본, edge-tts rate / gtts 근사)
SHORTS_CONVERSATION_KO_TTS_RATE_MULTIPLIER = 1.2
# 회화 conv: 같은 멘트 내 연속 seq(ko→ko) 끝난 뒤 다음 cue까지 대기(초)
SHORTS_CONVERSATION_KO_SEQ_TAIL_SEC = 0.02

# 노래방 색상 (좌→우 진행 채움: inactive=미재생, active=재생됨)
KARAOKE_ACTIVE_HANZI = (255, 230, 120)
KARAOKE_INACTIVE_HANZI = (120, 125, 140)
KARAOKE_ACTIVE_PINYIN = (255, 60, 60)
KARAOKE_INACTIVE_PINYIN = (120, 125, 140)
# 한국어 내레이션(TTS) 하단 자막
KO_KARAOKE_ACTIVE = (255, 240, 180)
KO_KARAOKE_INACTIVE = (120, 125, 140)
KO_SUBTITLE_BG_RGBA = (0, 0, 0, 160)
KO_SUBTITLE_ON_VIDEO_BG_RGBA = (0, 0, 0, 210)
KO_SUBTITLE_BG_PAD_X = 20
KO_SUBTITLE_BG_PAD_Y = 10
# TTS 자막: 비디오 프레임 하단과 자막 상단 사이 간격 (1080×1920 기준 px)
SHORTS_KO_SUBTITLE_BELOW_VIDEO_GAP = 8
SHORTS_KO_SUBTITLE_ON_VIDEO_BOTTOM_GAP = 20
SHORTS_KO_SUBTITLE_FONT_SIZE = 46


def shorts_ko_subtitle_on_video_bottom_gap(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(8, int(SHORTS_KO_SUBTITLE_ON_VIDEO_BOTTOM_GAP * sy))


def shorts_ko_subtitle_below_video_gap(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(4, int(SHORTS_KO_SUBTITLE_BELOW_VIDEO_GAP * sy))


def shorts_ko_subtitle_font_size(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(28, int(SHORTS_KO_SUBTITLE_FONT_SIZE * sy))


def shorts_conv_main_word_img_max(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    scale = float(SHORTS_CONV_MAIN_WORD_SCALE)
    return max(80, int(SHORTS_CONV_MAIN_WORD_IMG_MAX * sy * scale))


def shorts_conv_main_word_below_video_gap(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(8, int(SHORTS_CONV_MAIN_WORD_BELOW_VIDEO_GAP * sy))


def shorts_conv_main_word_label_gap(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(6, int(SHORTS_CONV_MAIN_WORD_LABEL_GAP * sy))


def shorts_conv_main_word_hanzi_pinyin_gap(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    return max(4, int(SHORTS_CONV_MAIN_WORD_HANZI_PINYIN_GAP * sy))


def shorts_conv_main_word_label_font_size(frame_height: int) -> int:
    h = max(1, int(frame_height))
    sy = h / float(SHORTS_HEIGHT)
    scale = float(SHORTS_CONV_MAIN_WORD_SCALE)
    return max(22, int(SHORTS_CONV_MAIN_WORD_LABEL_FONT_SIZE * sy * scale))
