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
# 1080×1920 기준 좌상단 앵커(해상도에 비례 스케일)
SHORTS_BRAND_ICON_X = 20
SHORTS_BRAND_ICON_Y = 250


def shorts_brand_icon_xy(frame_width: int, frame_height: int) -> tuple[int, int]:
    """프레임 크기에 맞춘 브랜드 아이콘 좌상단 좌표."""
    w = max(1, int(frame_width))
    h = max(1, int(frame_height))
    sx = w / float(SHORTS_WIDTH)
    sy = h / float(SHORTS_HEIGHT)
    return int(SHORTS_BRAND_ICON_X * sx), int(SHORTS_BRAND_ICON_Y * sy)

# FSM 타이밍(초)
HOOK_FADE_IN_SEC = 1.0
CTA_HOLD_SEC = 2.5
CLIP_TRANSITION_FADE_SEC = 0.3

# 노래방 색상
KARAOKE_ACTIVE_HANZI = (255, 230, 120)
KARAOKE_PAST_HANZI = (200, 200, 210)
KARAOKE_INACTIVE_HANZI = (255, 255, 255)
KARAOKE_ACTIVE_PINYIN = (255, 230, 120)
KARAOKE_PAST_PINYIN = (160, 165, 180)
KARAOKE_INACTIVE_PINYIN = (140, 145, 160)
