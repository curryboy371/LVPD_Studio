"""성조 아이콘 PNG 경로·파일명 매핑 및 표면 캐시."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

from core.paths import DEFAULT_TONE_ICON_DIR

# 발음 성조(숫자) → 파일 stem: {stem}.png
# 3.5(반3성)은 전용 파일명.
_TONE_STEM: dict[float, str] = {
    1.0: "1성",
    2.0: "2성",
    3.0: "3성",
    4.0: "4성",
    5.0: "5성",
    3.5: "3성반",
}


def tone_stem_for_phonetic(tone: float) -> Optional[str]:
    """발음 성조 값에 대응하는 에셋 stem (확장자 제외)."""
    if tone == 3.5:
        return _TONE_STEM[3.5]
    try:
        k = float(int(tone)) if tone == int(tone) else tone
    except (TypeError, ValueError):
        return None
    if k in (1, 2, 3, 4, 5):
        return _TONE_STEM[float(k)]
    return None


def tone_icon_path(
    tone: float,
    *,
    is_mismatch: bool,
    icon_dir: Optional[Path] = None,
) -> Optional[Path]:
    """로드할 PNG 경로. 에셋이 없으면 None."""
    stem = tone_stem_for_phonetic(tone)
    if not stem:
        return None
    _ = is_mismatch
    name = f"{stem}.png"
    base = icon_dir if icon_dir is not None else DEFAULT_TONE_ICON_DIR
    p = Path(base) / name
    if p.is_file():
        return p
    return None


class ToneIconSurfaceCache:
    """pygame Surface LRU 캐시 (경로+변조 여부 키)."""

    def __init__(self, cap: int = 128) -> None:
        self._cap = cap
        self._cache: "OrderedDict[str, Any]" = OrderedDict()

    def get(self, path: Path, *, is_mismatch: bool = False) -> Optional[Any]:
        key = f"{path.resolve()}|mismatch={int(is_mismatch)}"
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, path: Path, surf: Any, *, is_mismatch: bool = False) -> None:
        key = f"{path.resolve()}|mismatch={int(is_mismatch)}"
        self._cache[key] = surf
        self._cache.move_to_end(key)
        while len(self._cache) > self._cap:
            self._cache.popitem(last=False)


_default_cache: Optional[ToneIconSurfaceCache] = None


def get_tone_icon_surface_cache() -> ToneIconSurfaceCache:
    global _default_cache
    if _default_cache is None:
        _default_cache = ToneIconSurfaceCache()
    return _default_cache


def _apply_orange_mismatch_tint(surf: Any, pygame_module: Any) -> Any:
    """변조 표시용 주황색 틴트 오버레이."""
    tinted = surf.copy()
    # 알파(투명도)는 유지하고 RGB만 밝게 더해 사각형 오버레이를 방지한다.
    tinted.fill((255, 140, 0), special_flags=pygame_module.BLEND_RGB_ADD)
    return tinted


def load_tone_icon_surface(path: Path, pygame_module: Any, *, is_mismatch: bool = False) -> Optional[Any]:
    """캐시된 pygame Surface 반환."""
    cache = get_tone_icon_surface_cache()
    hit = cache.get(path, is_mismatch=is_mismatch)
    if hit is not None:
        return hit
    try:
        surf = pygame_module.image.load(str(path)).convert_alpha()
    except Exception:
        return None
    if is_mismatch:
        try:
            surf = _apply_orange_mismatch_tint(surf, pygame_module)
        except Exception:
            return None
    cache.put(path, surf, is_mismatch=is_mismatch)
    return surf


def resolve_tone_icon_dir(explicit: Optional[Path] = None) -> Path:
    return Path(explicit) if explicit is not None else DEFAULT_TONE_ICON_DIR


__all__ = [
    "DEFAULT_TONE_ICON_DIR",
    "ToneIconSurfaceCache",
    "get_tone_icon_surface_cache",
    "load_tone_icon_surface",
    "resolve_tone_icon_dir",
    "tone_icon_path",
    "tone_stem_for_phonetic",
]
