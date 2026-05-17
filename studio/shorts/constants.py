"""숏츠 스튜디오 상수."""

from __future__ import annotations

from pathlib import Path

from core.paths import get_repo_root

_REPO_ROOT = get_repo_root()

# 화면 구역 높이 비율 (합 1.0)
ZONE_TOP_RATIO = 0.30
ZONE_MIDDLE_RATIO = 0.40
ZONE_BOTTOM_RATIO = 0.30

# 리소스 경로
SHORTS_IMAGE_DIR = _REPO_ROOT / "resource" / "image" / "shorts"
SHORTS_PANDA_DIR = SHORTS_IMAGE_DIR / "panda"
SHORTS_BG_DEFAULT = SHORTS_IMAGE_DIR / "bg_default.png"

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
