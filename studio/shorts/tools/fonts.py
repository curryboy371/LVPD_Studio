"""숏츠 전용 폰트·렌더 설정."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from studio.conversation.tools.fonts import FontBundle


@dataclass(frozen=True)
class ShortsFontSizes:
    """middle 구역용 큰 pt."""

    cn: int = 84
    pinyin: int = 48
    kr: int = 36
    hook_title: int = 72
    bottom_kr: int = 32
    cta: int = 28


@dataclass(frozen=True)
class ShortsRenderSettings:
    """숏츠 스튜디오 렌더 설정."""

    font_sizes: ShortsFontSizes = ShortsFontSizes()


DEFAULT_SHORTS_RENDER_SETTINGS = ShortsRenderSettings()


def resolve_shorts_render_settings(config: Any) -> ShortsRenderSettings:
    """config.shorts_render가 있으면 사용."""
    if config is not None:
        sr = getattr(config, "shorts_render", None)
        if isinstance(sr, ShortsRenderSettings):
            return sr
    return DEFAULT_SHORTS_RENDER_SETTINGS


def build_font_bundle(sizes: ShortsFontSizes) -> FontBundle:
    """CommonDrawer용 FontBundle."""
    from utils.fonts import load_font_chinese, load_font_chinese_freetype, load_font_korean

    from studio.conversation.tools.fonts import WHITE

    cn = int(sizes.cn)
    py = int(sizes.pinyin)
    kr = int(sizes.kr)
    return FontBundle(
        hanzi_ft=load_font_chinese_freetype(cn, WHITE),
        hanzi_pg=load_font_chinese(cn, WHITE, weight="bold"),
        pinyin_ft=load_font_chinese_freetype(py, WHITE),
        pinyin_pg=load_font_chinese(py, WHITE),
        translation_pg=load_font_korean(kr, WHITE),
    )
