"""laser.png에서 마우스 드래그로 레이저 영역을 잘라 laser_ready.png 저장.

사용: 프로젝트 루트에서
  python scripts/crop_laser_interactive.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pygame

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "resource" / "image" / "icon" / "laser.png"
OUT = REPO / "resource" / "image" / "icon" / "laser_cropped.png"
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
        print(f"파일 없음: {SRC}")
        return 1

    pygame.init()
    img = pygame.image.load(str(SRC)).convert_alpha()
    screen = pygame.display.set_mode(img.get_size())
    pygame.display.set_caption("마우스로 원하는 레이저를 드래그하세요!")

    drawing = False
    start_pos = (0, 0)
    end_pos = (0, 0)
    running = True
    saved = False

    print(f"소스: {SRC}")
    print(f"저장: {OUT}")
    print("창에서 레이저 주변을 드래그한 뒤 마우스를 놓으면 저장됩니다.")

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                drawing = True
                start_pos = event.pos
                end_pos = event.pos
            elif event.type == pygame.MOUSEMOTION:
                if drawing:
                    end_pos = event.pos
            elif event.type == pygame.MOUSEBUTTONUP:
                drawing = False
                end_pos = event.pos
                x = min(start_pos[0], end_pos[0])
                y = min(start_pos[1], end_pos[1])
                w = abs(start_pos[0] - end_pos[0])
                h = abs(start_pos[1] - end_pos[1])
                if w > 5 and h > 5:
                    crop_rect = pygame.Rect(x, y, w, h)
                    cropped = img.subsurface(crop_rect).copy()
                    ready = pygame.transform.rotate(cropped, -90)
                    ready = _strip_black_to_alpha(ready, threshold=BG_KEY_THRESHOLD)
                    OUT.parent.mkdir(parents=True, exist_ok=True)
                    pygame.image.save(ready, str(OUT))
                    print(
                        f"저장 완료: crop=({x},{y},{w},{h}) "
                        f"→ {ready.get_width()}×{ready.get_height()} → {OUT}"
                    )
                    saved = True
                    running = False

        screen.blit(img, (0, 0))
        if drawing:
            x = min(start_pos[0], end_pos[0])
            y = min(start_pos[1], end_pos[1])
            w = abs(start_pos[0] - end_pos[0])
            h = abs(start_pos[1] - end_pos[1])
            pygame.draw.rect(screen, (255, 0, 0), (x, y, w, h), 2)
        pygame.display.flip()

    pygame.quit()
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
