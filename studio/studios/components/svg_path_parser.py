"""
SVG path 문자열을 pygame 렌더용 폴리라인으로 변환한다.
"""

from __future__ import annotations

import re
from typing import Iterable

Point = tuple[float, float]

_TOKEN_RE = re.compile(r"[MmLlQqCcZz]|-?(?:\d+(?:\.\d*)?|\.\d+)")


def _sample_quadratic(p0: Point, p1: Point, p2: Point, steps: int) -> list[Point]:
    out: list[Point] = []
    for i in range(1, steps + 1):
        t = i / float(steps)
        omt = 1.0 - t
        x = omt * omt * p0[0] + 2.0 * omt * t * p1[0] + t * t * p2[0]
        y = omt * omt * p0[1] + 2.0 * omt * t * p1[1] + t * t * p2[1]
        out.append((x, y))
    return out


def _sample_cubic(p0: Point, p1: Point, p2: Point, p3: Point, steps: int) -> list[Point]:
    out: list[Point] = []
    for i in range(1, steps + 1):
        t = i / float(steps)
        omt = 1.0 - t
        x = (
            (omt**3) * p0[0]
            + 3.0 * (omt**2) * t * p1[0]
            + 3.0 * omt * (t**2) * p2[0]
            + (t**3) * p3[0]
        )
        y = (
            (omt**3) * p0[1]
            + 3.0 * (omt**2) * t * p1[1]
            + 3.0 * omt * (t**2) * p2[1]
            + (t**3) * p3[1]
        )
        out.append((x, y))
    return out


def parse_svg_path_to_polyline(path_d: str, curve_steps: int = 14) -> list[Point]:
    """`M/L/Q/C/Z`를 폴리라인으로 변환한다."""
    tokens = _TOKEN_RE.findall(path_d or "")
    if not tokens:
        return []

    i = 0
    cmd = ""
    curr: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    out: list[Point] = []

    def read_float() -> float:
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        tok = tokens[i]
        if re.fullmatch(r"[MmLlQqCcZz]", tok):
            cmd = tok
            i += 1
        if not cmd:
            break

        if cmd in ("M", "m"):
            x = read_float()
            y = read_float()
            if cmd == "m":
                x += curr[0]
                y += curr[1]
            curr = (x, y)
            start = curr
            out.append(curr)
            cmd = "L" if cmd == "M" else "l"
            continue

        if cmd in ("L", "l"):
            if i + 1 >= len(tokens):
                break
            x = read_float()
            y = read_float()
            if cmd == "l":
                x += curr[0]
                y += curr[1]
            curr = (x, y)
            out.append(curr)
            continue

        if cmd in ("Q", "q"):
            if i + 3 >= len(tokens):
                break
            x1, y1, x, y = read_float(), read_float(), read_float(), read_float()
            if cmd == "q":
                x1 += curr[0]
                y1 += curr[1]
                x += curr[0]
                y += curr[1]
            samples = _sample_quadratic(curr, (x1, y1), (x, y), steps=curve_steps)
            out.extend(samples)
            curr = (x, y)
            continue

        if cmd in ("C", "c"):
            if i + 5 >= len(tokens):
                break
            x1, y1 = read_float(), read_float()
            x2, y2 = read_float(), read_float()
            x, y = read_float(), read_float()
            if cmd == "c":
                x1 += curr[0]
                y1 += curr[1]
                x2 += curr[0]
                y2 += curr[1]
                x += curr[0]
                y += curr[1]
            samples = _sample_cubic(curr, (x1, y1), (x2, y2), (x, y), steps=curve_steps)
            out.extend(samples)
            curr = (x, y)
            continue

        if cmd in ("Z", "z"):
            if out and curr != start:
                out.append(start)
                curr = start
            cmd = ""
            continue

        # 미지원 명령은 안전하게 종료
        break

    return out


def path_bounds(paths: Iterable[list[Point]]) -> tuple[float, float, float, float] | None:
    """폴리라인 묶음의 (min_x, min_y, max_x, max_y)를 계산한다."""
    xs: list[float] = []
    ys: list[float] = []
    for pts in paths:
        for x, y in pts:
            xs.append(x)
            ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))
