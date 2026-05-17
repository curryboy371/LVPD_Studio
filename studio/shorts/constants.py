"""숏츠 스튜디오 상수."""

from __future__ import annotations

from pathlib import Path

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
# 1080×1920 기준 하단 중앙 — 아이콘 하단 여백(해상도에 비례 스케일)
SHORTS_BRAND_ICON_BOTTOM_MARGIN = 280
SHORTS_BRAND_TITLE_TEXT = "#중국어 여포판다"
SHORTS_BRAND_TITLE_COLOR = (64, 64, 64)
SHORTS_BRAND_TITLE_FONT_SIZE = 30
SHORTS_BRAND_TITLE_GAP_ABOVE_ICON = 10
# 1080×1920 기준 — 훅 타이틀 Y(화면 최상단부터, 상단 30% 구역을 넘어설 수 있음)
SHORTS_HOOK_TITLE_Y = 420
# 하위 호환 이름
SHORTS_HOOK_TITLE_Y_OFFSET = SHORTS_HOOK_TITLE_Y
SHORTS_HOOK_TITLE_LINE_GAP = 0
# 훅 타이틀 2줄: 윗줄(첫 줄) / 아랫줄(\n 이후)
HOOK_TITLE_LINE1_COLOR = (120, 210, 255)
HOOK_TITLE_LINE2_COLOR = (255, 255, 255)
# 1080×1920 기준 — 중앙 노래방 문장 y 보정(양수 = 아래)
SHORTS_MIDDLE_Y_OFFSET = 72
# 1080×1920 기준 — 병음 줄 추가 y 보정(양수 = 아래)
SHORTS_PINYIN_Y_OFFSET = 72
# 1080×1920 기준 — 병음↔한자 줄 간격(기본 line_gap보다 좁게)
SHORTS_PINYIN_HANZI_GAP = 52
# 1080×1920 기준 — 한자↔번역(뜻) 추가 간격
SHORTS_TRANSLATION_EXTRA_GAP = 28


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
) -> tuple[int, int]:
    """프레임 크기에 맞춘 브랜드 아이콘 좌상단 좌표(하단 중앙 정렬)."""
    w = max(1, int(frame_width))
    h = max(1, int(frame_height))
    iw = max(1, int(icon_width))
    ih = max(1, int(icon_height))
    sy = h / float(SHORTS_HEIGHT)
    margin = int(SHORTS_BRAND_ICON_BOTTOM_MARGIN * sy)
    x = (w - iw) // 2
    y = max(0, h - ih - margin)
    return x, y

# FSM 타이밍(초)
HOOK_FADE_IN_SEC = 1.0
CTA_HOLD_SEC = 2.5
CLIP_TRANSITION_FADE_SEC = 0.3
SHORTS_SOUND_PLAY_COUNT = 2
SHORTS_VIDEO_END_HOLD_SEC = 0.6
SHORTS_VIDEO_FADE_OUT_SEC = 0.8
# 페이드 후에도 비디오가 남도록 최소 알파(0=완전 숨김, 255=그대로)
SHORTS_VIDEO_AFTER_ALPHA = 30

# 노래방 색상
KARAOKE_ACTIVE_HANZI = (255, 230, 120)
KARAOKE_PAST_HANZI = (255, 255, 255)
KARAOKE_INACTIVE_HANZI = (255, 255, 255)
KARAOKE_ACTIVE_PINYIN = (255, 60, 60)
KARAOKE_PAST_PINYIN = (255, 255, 255)
KARAOKE_INACTIVE_PINYIN = (255, 255, 255)
