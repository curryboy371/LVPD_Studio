"""
음절 타이밍 파싱: 엑셀/CSV의 syllable_times_*_ms 문자열 → 초 단위 리스트.
"""
from typing import List


def parse_syllable_times_ms(s: str) -> List[float]:
    """쉼표 구분 ms 문자열을 초 단위 float 리스트로 반환.
    예: '0,350,700,1050' -> [0.0, 0.35, 0.7, 1.05]
    빈 문자열 또는 잘못된 값은 빈 리스트.
    """
    if not s or not isinstance(s, str):
        return []
    out: List[float] = []
    for part in s.strip().split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ms = float(part)
            out.append(ms / 1000.0)
        except ValueError:
            continue
    return out
