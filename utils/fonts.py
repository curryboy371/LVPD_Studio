"""
resource/font 경로에서 중국어·한국어 폰트 로드. pygame에서 사용.
weight 옵션(thin, light, regular, bold, extrabold 등)에 따라 파일명으로 폰트 선택.
"""
import logging
from pathlib import Path
from typing import Optional

try:
    import pygame
except ImportError:
    pygame = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# weight 옵션: 파일명 stem에 포함된 키워드로 매칭 (무거운 순으로 검사해 더 구체적인 것 우선)
# 값은 가벼움(0) ~ 무거움(6) 순서. 동일 weight면 먼저 찾은 파일 사용.
WEIGHT_KEYWORDS: list[tuple[str, int]] = [
    ("extrabold", 6), ("extra bold", 6), ("black", 6), ("heavy", 6),
    ("bold", 5),
    ("semibold", 4), ("semi bold", 4), ("demibold", 4),
    ("medium", 3),
    ("regular", 2), ("normal", 2),
    ("light", 1),
    ("thin", 0), ("hairline", 0),
]
# 사용자 지정 weight → 선호하는 숫자 (가장 가까운 파일 선택)
WEIGHT_PREFERRED: dict[str, int] = {
    "thin": 0, "hairline": 0,
    "light": 1,
    "regular": 2, "normal": 2,
    "medium": 3,
    "semibold": 4, "demibold": 4,
    "bold": 5,
    "extrabold": 6, "black": 6, "heavy": 6,
}
DEFAULT_WEIGHT = 2  # regular


def _font_path(filename: str) -> Path:
    from core.paths import DEFAULT_FONT_DIR
    return DEFAULT_FONT_DIR / filename


def _weight_from_stem(stem: str) -> int:
    """파일명 stem에서 감지한 weight 값 (0=thin ~ 6=extrabold). 매칭 없으면 regular(2)."""
    s = stem.lower()
    for keyword, value in WEIGHT_KEYWORDS:
        if keyword in s:
            return value
    return DEFAULT_WEIGHT


def find_font_path_in_dir(
    font_dir: Path,
    weight: str = "regular",
    lang_hint: Optional[str] = None,
) -> Optional[Path]:
    """resource/font 하위 .ttf/.otf 중 weight·lang_hint에 맞는 파일 하나 반환.
    weight: thin, light, regular, medium, semibold, bold, extrabold, black 등.
    lang_hint: 'kr'이면 한글 폰트(kr, korean, maruburi) 우선, 'chn'이면 중국어(sc, cjk 등) 우선.
    """
    if not font_dir.is_dir():
        return None
    target = WEIGHT_PREFERRED.get(weight.lower().strip(), DEFAULT_WEIGHT)
    candidates: list[tuple[Path, int, int]] = []  # (path, weight_diff, lang_score)
    for ext in ("*.ttf", "*.otf"):
        for p in font_dir.glob(ext):
            w = _weight_from_stem(p.stem)
            diff = abs(w - target)
            lang_score = 0
            if lang_hint:
                stem_lower = p.stem.lower()
                if lang_hint.lower() == "kr":
                    if any(x in stem_lower for x in ("kr", "korean", "maruburi", "notosanskr")):
                        lang_score = 2
                    elif "noto" in stem_lower or "sans" in stem_lower:
                        lang_score = 1
                elif lang_hint.lower() in ("chn", "cn", "chinese"):
                    if any(x in stem_lower for x in ("sc", "cjk", "chinese", "han", "simhei", "yahei")):
                        lang_score = 2
                    if any(x in stem_lower for x in ("kr", "korean", "maruburi", "jp", "japanese")):
                        lang_score = -1
            candidates.append((p, diff, -lang_score))
    if not candidates:
        return None
    # weight 차이 작은 순, 그 다음 lang_score 좋은 순
    candidates.sort(key=lambda x: (x[1], x[2]))
    return candidates[0][0]


def load_font(
    size: int = 28,
    weight: str = "regular",
    lang_hint: Optional[str] = None,
    font_dir: Optional[Path] = None,
) -> "Optional[pygame.font.Font]":
    """weight·lang에 맞는 폰트 로드. 타이틀은 weight='bold' 또는 'extrabold' 권장.
    font_dir 미지정 시 core.paths.DEFAULT_FONT_DIR 사용.
    """
    if pygame is None:
        return None
    from core.paths import DEFAULT_FONT_DIR
    directory = font_dir or DEFAULT_FONT_DIR
    path = find_font_path_in_dir(directory, weight=weight, lang_hint=lang_hint)
    if path is None:
        path = find_font_path_in_dir(directory, weight="regular", lang_hint=lang_hint)
    if path is None:
        fallback = list(directory.glob("*.ttf")) + list(directory.glob("*.otf"))
        path = fallback[0] if fallback else None
    if path is None:
        return None
    return _load_font_at(path, size)


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


def load_font_chinese(size: int = 28, weight: str = "regular") -> "Optional[pygame.font.Font]":
    """중국어용 폰트 (문장·병음). weight: thin, light, regular, bold, extrabold 등."""
    from core.paths import DEFAULT_FONT_DIR
    if pygame is None:
        return None
    path = find_font_path_in_dir(DEFAULT_FONT_DIR, weight=weight, lang_hint="chn")
    if path is not None:
        font = _load_font_at(path, size)
        if font is not None:
            return font
    for path in find_chinese_font_paths_in_dir(DEFAULT_FONT_DIR):
        font = _load_font_at(path, size)
        if font is not None:
            return font
    from core.paths import FONT_CN_FILENAME
    font = _load_font_at(_font_path(FONT_CN_FILENAME), size)
    if font is not None:
        return font
    for name in ("NotoSerifSC-Regular.otf", "NotoSansSC-Regular.otf", "NotoSansCJKsc-Regular.otf"):
        font = _load_font_at(DEFAULT_FONT_DIR / name, size)
        if font is not None:
            return font
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


def load_font_korean(size: int = 28, weight: str = "regular") -> "Optional[pygame.font.Font]":
    """한국어용 폰트 (번역·UI·타이틀). weight: thin, light, regular, bold, extrabold 등. 타이틀은 bold/extrabold 권장."""
    from core.paths import DEFAULT_FONT_DIR, FONT_KR_FILENAME
    if pygame is None:
        return None
    path = find_font_path_in_dir(DEFAULT_FONT_DIR, weight=weight, lang_hint="kr")
    if path is not None:
        font = _load_font_at(path, size)
        if font is not None:
            return font
    path = _font_path(FONT_KR_FILENAME)
    if not path.exists():
        logger.warning("한국어 폰트 파일 없음: %s (기대: %s)", path.resolve(), FONT_KR_FILENAME)
    font = _load_font_at(path, size)
    if font is not None:
        return font
    for name in ("MaruBuri-Regular.otf", "MaruBuri-Light.otf", "NotoSansKR-Regular.ttf", "NotoSansKR-Bold.otf"):
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
