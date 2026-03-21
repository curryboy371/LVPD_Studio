"""회화 스튜디오 그리기용 순수 헬퍼 (점선, 곡선, 성조 심볼, util 세그먼트 파싱)."""
import math
import re
from typing import Any

import pygame


def draw_dotted_line(
    surf: Any,
    color: tuple,
    start: tuple[float, float],
    end: tuple[float, float],
    thickness: int = 2,
    dash_length: int = 6,
) -> None:
    """Draw a dashed/dotted line (for neutral tone contour)."""
    x0, y0 = start
    x1, y1 = end
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1e-6:
        return
    n_dashes = max(1, int(length / (dash_length * 2)))
    step = 1.0 / n_dashes
    for i in range(n_dashes):
        t0 = i * step * 2
        t1 = min((i * 2 + 1) * step, 1.0)
        if t0 >= 1.0:
            break
        sx = x0 + t0 * (x1 - x0)
        sy = y0 + t0 * (y1 - y0)
        ex = x0 + t1 * (x1 - x0)
        ey = y0 + t1 * (y1 - y0)
        pygame.draw.line(surf, color, (int(sx), int(sy)), (int(ex), int(ey)), thickness)


def smooth_curve_pts(pts: list[tuple[float, float]], steps_per_segment: int = 6) -> list[tuple[float, float]]:
    """Catmull-Rom 스플라인으로 점 리스트를 부드러운 곡선 점들로 보간."""
    if len(pts) < 2:
        return list(pts)
    if len(pts) == 2:
        return list(pts)
    out: list[tuple[float, float]] = []
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[max(0, i - 1)]
        p1 = pts[i]
        p2 = pts[i + 1]
        p3 = pts[min(n - 1, i + 2)]
        for s in range(steps_per_segment):
            t = s / steps_per_segment
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(pts[-1])
    return out


def draw_sparkline_symbol(
    surf: Any,
    tone: float,
    x_center: float,
    y_center: float,
    size: int = 6,
    color: tuple = (255, 200, 120),
) -> None:
    """Draw a minimal tone symbol above a character: 1=—, 2=/, 3=V, 4=\\, 5/0=·."""
    cx, cy = int(x_center), int(y_center)
    if tone <= 0.5 or tone >= 4.5:
        pygame.draw.circle(surf, color, (cx, cy), max(1, size // 3))
        return
    if 1 <= tone < 1.5:
        pygame.draw.line(surf, color, (cx - size, cy), (cx + size, cy), 2)
        return
    if 2 <= tone < 2.5:
        pygame.draw.line(surf, color, (cx - size, cy + size), (cx + size, cy - size), 2)
        return
    if 2.9 <= tone <= 3.1:
        pygame.draw.line(surf, color, (cx - size, cy + size), (cx, cy - size), 2)
        pygame.draw.line(surf, color, (cx, cy - size), (cx + size, cy + size), 2)
        return
    if 3.4 <= tone <= 3.6:
        pygame.draw.line(surf, color, (cx - size, cy + size), (cx, cy - size), 2)
        return
    if 4 <= tone < 4.5:
        pygame.draw.line(surf, color, (cx - size, cy - size), (cx + size, cy + size), 2)
        return
    pygame.draw.circle(surf, color, (cx, cy), max(1, size // 3))


def parse_util_segments(text: str) -> list[tuple[bool, str]]:
    """Util 문장/번역에서 [] 로 감싼 슬롯 구간과 리터럴 구간을 분리.
    반환: [(is_slot, text), ...] — True면 슬롯(변화 부분), False면 리터럴(base와 동일).
    """
    if not (text or text.strip()):
        return []
    segments: list[tuple[bool, str]] = []
    pattern = re.compile(r"\[([^\]]+)\]")
    last_end = 0
    for m in pattern.finditer(text):
        if m.start() > last_end:
            literal = text[last_end : m.start()]
            if literal:
                segments.append((False, literal))
        segments.append((True, m.group(1)))
        last_end = m.end()
    if last_end < len(text):
        rest = text[last_end:]
        if rest:
            segments.append((False, rest))
    return segments
