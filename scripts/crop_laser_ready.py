"""(레거시) 스프라이트 시트에서 레이저 한 줄을 잘라 가로 PNG로 저장.

런타임은 resource/image/icon/laser.png (꼬리←머리 가로) 를 직접 사용한다.
사용: python scripts/crop_laser_ready.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pygame

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "resource" / "image" / "word_memorize" / "laser.png"
OUT = REPO / "resource" / "image" / "icon" / "laser.png"

# 맨 아랫줄 3번째 하늘색 레이저 (laser.png 픽셀 좌표, 383×411 기준)
# crop_laser_interactive.py 로 미세 조정 가능
CROP_X = 154
CROP_Y = 226
CROP_W = 42
CROP_H = 171
BG_KEY_THRESHOLD = 32


def _strip_black_to_alpha(surf: pygame.Surface, *, threshold: int) -> pygame.Surface:
    w, h = surf.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            c = surf.get_at((x, y))
            if len(c) == 4:
                r, g, b, a = c
            else:
                r, g, b = int(c[0]), int(c[1]), int(c[2])
                a = 255
            if a < 8:
                continue
            if r <= threshold and g <= threshold and b <= threshold:
                continue
            out.set_at((x, y), (r, g, b, min(255, a)))
    return out


def main() -> int:
    if not SRC.is_file():
        print(f"소스 없음: {SRC}", file=sys.stderr)
        return 1

    pygame.display.init()
    pygame.display.set_mode((1, 1))

    sheet = pygame.image.load(str(SRC)).convert_alpha()
    sw, sh = sheet.get_size()
    crop_rect = pygame.Rect(CROP_X, CROP_Y, CROP_W, CROP_H)
    crop_rect.clamp_ip(pygame.Rect(0, 0, sw, sh))

    single_laser = sheet.subsurface(crop_rect).copy()
    ready_laser = pygame.transform.rotate(single_laser, -90)
    ready_laser = _strip_black_to_alpha(ready_laser, threshold=BG_KEY_THRESHOLD)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(ready_laser, str(OUT))
    print(f"저장 완료: {OUT} ({ready_laser.get_width()}×{ready_laser.get_height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
