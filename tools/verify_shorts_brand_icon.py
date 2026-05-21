"""숏츠 브랜드 아이콘 렌더 검증 — runner와 동일 경로, 실패 시 exit 1."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
os.chdir(_REPO)

OUT_PATH = _REPO / "output" / "verify_shorts_brand_icon.png"
CROP_PATH = _REPO / "output" / "verify_shorts_brand_icon_crop.png"
RUNNER_CAPTURE = _REPO / "output" / "verify_runner_subprocess.png"


def _icon_region_stats(surf, x: int, y: int, w: int, h: int) -> dict:
    bright = 0
    max_luma = 0
    for px in range(x, min(x + w, surf.get_width())):
        for py in range(y, min(y + h, surf.get_height())):
            r, g, b, *_ = surf.get_at((px, py))
            luma = int(r) + int(g) + int(b)
            if luma > max_luma:
                max_luma = luma
            if luma > 120:
                bright += 1
    return {"bright": bright, "max_luma": max_luma, "area": w * h}


def _capture_inprocess() -> dict:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from core.paths import (
        DEFAULT_BASE_SENTENCES_CSV,
        DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV,
        DEFAULT_WORDS_TABLE_CSV,
        SHORTS_HEIGHT,
        SHORTS_WIDTH,
    )
    from studio.shorts.brand_icon import load_brand_icon_plate
    from studio.shorts.constants import (
        SHORTS_BRAND_ICON_H,
        SHORTS_BRAND_ICON_W,
        shorts_brand_icon_xy,
    )
    from data.table_manager import load_base_sentences_from_csv, load_words_table_from_csv
    from studio.runner import StudioConfig, _warm_shorts_brand_icon
    from studio.shorts.studio import ShortsStudio

    pygame.mixer.pre_init(48000, -16, 2, 4096)
    pygame.init()
    pygame.display.set_mode((1, 1))

    load_base_sentences_from_csv(DEFAULT_BASE_SENTENCES_CSV)
    load_words_table_from_csv(DEFAULT_WORDS_TABLE_CSV)

    config = StudioConfig(SHORTS_WIDTH, SHORTS_HEIGHT, 30)
    studio = ShortsStudio(
        shorts_mode="conversation",
        clips_csv_path=str(DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV),
        session_topics=["fruit_store"],
    )
    studio.init(config)
    _warm_shorts_brand_icon(studio, pygame)

    buffer = pygame.Surface((config.width, config.height))
    for _ in range(90):
        studio.update(config)
    studio.draw(buffer, config)

    plate = load_brand_icon_plate()
    if plate is None:
        print("FAIL: plate load")
        return {"bright": 0, "max_luma": 0, "area": 0}
    pw, ph = plate.get_size()
    ix, iy = shorts_brand_icon_xy(
        config.width, config.height, icon_width=pw, icon_height=ph
    )
    stats = _icon_region_stats(
        buffer, ix, iy, max(pw, SHORTS_BRAND_ICON_W) + 8, max(ph, SHORTS_BRAND_ICON_H) + 8
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(buffer, str(OUT_PATH))
    crop_w = min(pw + 40, config.width)
    crop_h = min(ph + 40, config.height)
    crop_x = max(0, ix + pw // 2 - crop_w // 2)
    crop_y = max(0, iy + ph // 2 - crop_h // 2)
    crop = buffer.subsurface(pygame.Rect(crop_x, crop_y, crop_w, crop_h))
    pygame.image.save(crop, str(CROP_PATH))
    return stats


def main() -> int:
    print("=== in-process capture (CTA stage) ===")
    stats = _capture_inprocess()
    print("stats:", stats)
    print("saved:", OUT_PATH, CROP_PATH)

    ok = stats["bright"] >= 500 and stats["max_luma"] >= 200
    if not ok:
        print("FAIL: icon region empty")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
