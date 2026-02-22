"""
resource/font 경로에서 중국어·한국어 폰트 로드. pygame에서 사용.
"""
import logging
from pathlib import Path
from typing import Optional

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _font_path(filename: str) -> Path:
    from core.paths import DEFAULT_FONT_DIR
    return DEFAULT_FONT_DIR / filename


def _load_font_at(path: Path, size: int) -> "Optional[pygame.font.Font]":
    """resource/font 하위 경로에서 .ttf/.otf 로드. 없으면 None."""
    if pygame is None:
        return None
    to_try = [path] if path.exists() else [
        path.parent / f"{path.stem}{ext}" for ext in (".ttf", ".otf")
        if (path.parent / f"{path.stem}{ext}").exists()
    ]
    for p in to_try:
        try:
            font = pygame.font.Font(str(p), size)
            logger.info("폰트 로드 성공: %s (size=%d)", p, size)
            return font
        except Exception as e:
            logger.debug("폰트 로드 실패 %s: %s", p, e)
            continue
    return None


def _sysfont_chinese(size: int) -> "Optional[pygame.font.Font]":
    """시스템에 있는 중국어 지원 폰트로 폴백 (한글이 네모로 나오지 않도록)."""
    if pygame is None:
        return None
    # Windows/맥/리눅스에서 흔한 중국어(간체) 지원 폰트 이름
    names = [
        "microsoftyahei", "microsoft yahei", "simhei", "simsun", "nsimsun",
        "noto sans cjk sc", "noto serif cjk sc", "source han sans sc",
        "dengxian", "fangsong", "kaiti", "simkai", "fangzheng",
    ]
    for name in names:
        try:
            font = pygame.font.SysFont(name, size)
            if font is not None:
                logger.info("중국어 시스템 폰트 폴백: %s (size=%d)", name, size)
                return font
        except Exception:
            continue
    return None


def load_font_chinese(size: int = 28) -> "Optional[pygame.font.Font]":
    """중국어용 폰트 (문장·병음). resource/font에서 중국어 폰트 파일 먼저 찾아 사용, 없으면 시스템 폰트."""
    from core.paths import DEFAULT_FONT_DIR
    if pygame is None:
        return None
    # 1) resource/font 하위에서 중국어로 보이는 파일 먼저 사용
    for path in find_chinese_font_paths_in_dir(DEFAULT_FONT_DIR):
        font = _load_font_at(path, size)
        if font is not None:
            return font
    # 2) 기존 설정 파일명 (FONT_CN_FILENAME 등)
    from core.paths import FONT_CN_FILENAME
    path = _font_path(FONT_CN_FILENAME)
    font = _load_font_at(path, size)
    if font is not None:
        return font
    for name in ("NotoSerifSC-Regular.otf", "NotoSansSC-Regular.otf", "NotoSansCJKsc-Regular.otf"):
        font = _load_font_at(DEFAULT_FONT_DIR / name, size)
        if font is not None:
            return font
    # 3) 시스템 폰트 폴백
    font = _sysfont_chinese(size)
    if font is not None:
        return font
    logger.warning("중국어 폰트를 찾지 못함. resource/font 에 NotoSansSC-Regular.ttf 등 중국어 .ttf/.otf 넣기.")
    return None


# resource/font에서 중국어로 보이는 파일명 패턴 (stem 소문자 기준)
_CHINESE_FONT_HINTS = ("sc", "cjk", "chinese", "han", "simsun", "simhei", "yahei", "dengxian", "fangsong", "kaiti", "source han")
_CHINESE_FONT_EXCLUDE = ("kr", "korean", "maruburi", "jp", "japanese", "tc", "tw ", "hk ")  # 한글/일본어/번체 제외


def find_chinese_font_paths_in_dir(font_dir: Path) -> list[Path]:
    """resource/font 하위 .ttf/.otf 중 파일명이 중국어(간체)로 보이는 것만 반환. MaruBuri 등 한글용 제외."""
    if not font_dir.is_dir():
        return []
    candidates: list[Path] = []
    for ext in ("*.ttf", "*.otf"):
        for p in font_dir.glob(ext):
            stem = p.stem.lower()
            if any(x in stem for x in _CHINESE_FONT_EXCLUDE):
                continue
            if any(x in stem for x in _CHINESE_FONT_HINTS):
                candidates.append(p)
    # Noto*SC*, Noto*CJK*sc 우선 정렬
    def order_key(path: Path) -> tuple[int, str]:
        s = path.stem.lower()
        if "notosanssc" in s or "notosans cjk sc" in s:
            return 0, s
        if "notoserifsc" in s:
            return 1, s
        if "sourcehan" in s and "sc" in s:
            return 2, s
        return 3, s
    candidates.sort(key=order_key)
    return candidates


def load_font_chinese_freetype(size: int = 28):
    """중국어용 pygame.freetype.Font. resource/font에서 중국어 폰트 파일 먼저 찾아 사용, 없으면 시스템 폰트."""
    try:
        import pygame.freetype
    except ImportError:
        logger.debug("pygame.freetype 없음")
        return None
    if pygame is None:
        return None
    from core.paths import DEFAULT_FONT_DIR
    # 1) resource/font 하위에서 중국어 폰트 파일 찾아서 사용
    for path in find_chinese_font_paths_in_dir(DEFAULT_FONT_DIR):
        try:
            font = pygame.freetype.Font(str(path), size=size)
            logger.info("중국어 freetype: resource/font/%s (size=%d)", path.name, size)
            return font
        except Exception as e:
            logger.debug("freetype 로드 실패 %s: %s", path, e)
            continue
    # 2) 시스템 중국어 폰트 폴백
    for name in ("microsoftyahei", "microsoft yahei", "simhei", "simsun", "dengxian", "nsimsun"):
        try:
            font = pygame.freetype.SysFont(name, size)
            if font is not None:
                logger.info("중국어 freetype: 시스템 폰트 %s (size=%d)", name, size)
                return font
        except Exception:
            continue
    logger.warning("중국어 freetype 폰트 없음. resource/font 에 NotoSansSC-Regular.ttf 등 중국어 폰트를 넣거나 시스템 폰트 설치.")
    return None


def load_font_korean(size: int = 28) -> "Optional[pygame.font.Font]":
    """한국어용 폰트 (번역·UI). resource/font. 파일 없으면 시스템 폰트 폴백."""
    from core.paths import DEFAULT_FONT_DIR, FONT_KR_FILENAME
    if pygame is None:
        return None
    path = _font_path(FONT_KR_FILENAME)
    if not path.exists():
        logger.warning("한국어 폰트 파일 없음: %s (기대: %s)", path.resolve(), FONT_KR_FILENAME)
    font = _load_font_at(path, size)
    if font is not None:
        return font
    for name in ("MaruBuri-Regular.otf", "MaruBuri-Light.otf", "NotoSansKR-Regular.ttf"):
        font = _load_font_at(DEFAULT_FONT_DIR / name, size)
        if font is not None:
            return font
    try:
        font = pygame.font.SysFont("malgungothic", size) or pygame.font.SysFont("gulim", size)
        if font is not None:
            logger.info("한국어 시스템 폰트 폴백 사용 (size=%d)", size)
            return font
    except Exception:
        pass
    return None
