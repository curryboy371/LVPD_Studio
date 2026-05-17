"""숏츠 3구역 UI 그리기."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pygame

from studio.conversation.core.types import FrameContext, build_sentence_render_data_with_tone_icons
from studio.conversation.tools.common_drawer import CommonDrawer
from studio.conversation.tools.fade_controller import FadeController
from studio.conversation.tools.fonts import WHITE
from studio.shorts.clip_types import CLIP_TYPE_VOCABULARY
from studio.shorts import brand_icon as brand_icon_module
from studio.shorts.constants import SHORTS_BG_DEFAULT
from studio.shorts.layout import ShortsLayoutZones
from studio.shorts.tools.fonts import ShortsFontSizes, build_font_bundle
from studio.shorts.tools.karaoke_renderer import KaraokeRenderer
from utils.fonts import load_font_korean

_HOOK_TITLE_COLOR = (255, 232, 140)


class ShortsDrawer:
    """상단 훅·중앙 학습·하단 CTA 렌더."""

    def __init__(self, *, font_sizes: ShortsFontSizes) -> None:
        self._font_sizes = font_sizes
        self._fonts = build_font_bundle(font_sizes)
        self._drawer = CommonDrawer(fonts=self._fonts)
        self._fade = FadeController()
        self._karaoke = KaraokeRenderer(drawer=self._drawer)
        size = int(font_sizes.hook_title)
        self._hook_font = load_font_korean(size, _HOOK_TITLE_COLOR, weight="bold")
        self._bottom_font = load_font_korean(int(font_sizes.bottom_kr), WHITE)
        self._cta_font = load_font_korean(int(font_sizes.cta), (200, 210, 255))
        self._bg_surface: Optional[pygame.Surface] = None
        self._hook_image_cache: dict[str, pygame.Surface] = {}

    @property
    def fade(self) -> FadeController:
        return self._fade

    @property
    def common(self) -> CommonDrawer:
        return self._drawer

    def tick_fade(self, dt_sec: float) -> None:
        self._fade.tick(dt_sec)

    def fade_alpha(self, channel: str) -> int:
        return self._fade.alpha(channel)

    def _ensure_bg(self, width: int, height: int) -> None:
        if self._bg_surface is not None and self._bg_surface.get_size() == (width, height):
            return
        surf = pygame.Surface((width, height))
        surf.fill((18, 20, 28))
        if SHORTS_BG_DEFAULT.exists():
            try:
                img = pygame.image.load(str(SHORTS_BG_DEFAULT)).convert()
                img = pygame.transform.smoothscale(img, (width, height))
                surf.blit(img, (0, 0))
            except Exception:
                pass
        self._bg_surface = surf
        brand_icon_module.draw_brand_icon(self._bg_surface)

    def draw_background(self, screen: pygame.Surface, ctx: FrameContext) -> None:
        screen.set_clip(None)
        zones = ShortsLayoutZones.from_surface(screen, ctx)
        self._ensure_bg(zones.top.width, zones.top.height + zones.middle.height + zones.bottom.height)
        if self._bg_surface is not None:
            screen.blit(self._bg_surface, (0, 0))

    def _load_hook_image(self, path: str, max_w: int, max_h: int) -> Optional[pygame.Surface]:
        key = f"{path}|{max_w}|{max_h}"
        if key in self._hook_image_cache:
            return self._hook_image_cache[key]
        if not path or not Path(path).exists():
            return None
        try:
            raw = pygame.image.load(path)
        except Exception:
            return None
        try:
            img = raw.convert_alpha()
        except pygame.error:
            try:
                img = raw.convert()
            except pygame.error:
                img = raw
        sw, sh = img.get_width(), img.get_height()
        if sw <= 0 or sh <= 0:
            return None
        scale = min(float(max_w) / sw, float(max_h) / sh, 1.0)
        tw = max(1, int(sw * scale))
        th = max(1, int(sh * scale))
        scaled = pygame.transform.smoothscale(img, (tw, th)) if scale < 1.0 else img
        self._hook_image_cache[key] = scaled
        return scaled

    def _render_hook_title(self, title: str) -> Optional[pygame.Surface]:
        text = (title or "").strip()
        if not text:
            return None
        size = int(self._font_sizes.hook_title)
        for font in (
            self._bottom_font,
            self._hook_font,
            load_font_korean(size, _HOOK_TITLE_COLOR, weight="regular"),
        ):
            if font is None:
                continue
            try:
                surf = font.render(text, True, _HOOK_TITLE_COLOR)
            except Exception:
                continue
            if surf is not None and surf.get_width() > 0:
                return surf
        return None

    def draw_brand_icon(self, screen: pygame.Surface) -> bool:
        """브랜드 아이콘 — brand_icon 모듈 단일 경로."""
        return brand_icon_module.draw_brand_icon(screen)

    def warm_brand_icon(self) -> None:
        brand_icon_module.warm_brand_icon()

    def draw_hook_title(
        self,
        screen: pygame.Surface,
        *,
        zones: ShortsLayoutZones,
        hook_title: str,
    ) -> int:
        """상단 훅 타이틀. 페이드·clip 영향 없음. 반환: 판다 이미지 배치 시작 y."""
        screen.set_clip(None)
        rect = zones.top
        pad = 16
        title = (hook_title or "").strip()
        if not title:
            return rect.top + pad

        surf = self._render_hook_title(title)
        if surf is None:
            return rect.top + pad

        tx = rect.centerx - surf.get_width() // 2
        ty = rect.top + max(pad, (rect.height - surf.get_height()) // 2 - pad)
        ty = max(rect.top + pad, min(ty, rect.bottom - surf.get_height() - pad))
        screen.blit(surf, (tx, ty))
        return ty + surf.get_height() + 12

    def draw_top_zone(
        self,
        screen: pygame.Surface,
        *,
        zones: ShortsLayoutZones,
        hook_image_path: str,
        channel: str,
        image_y: int,
    ) -> None:
        """상단 30%: 판다 이미지(페이드). 타이틀은 draw_hook_title에서 처리."""
        img_alpha = self.fade_alpha(channel)
        if img_alpha <= 0:
            return

        rect = zones.top
        pad = 16
        img_h = max(64, rect.bottom - image_y - pad)
        img = self._load_hook_image(hook_image_path, rect.width - pad * 2, img_h)
        if img is None:
            return

        x = rect.centerx - img.get_width() // 2
        y = min(image_y, rect.bottom - img.get_height() - pad)
        if img_alpha < 255:
            img = img.copy()
            img.set_alpha(img_alpha)
        screen.blit(img, (x, y))

    def draw_middle(
        self,
        screen: pygame.Surface,
        *,
        zones: ShortsLayoutZones,
        item: dict[str, Any],
        elapsed_sec: float,
        syllable_times: list[float],
        sound_duration_sec: float,
        style: Any,
    ) -> None:
        """clip_type에 따라 상황극(노래방) 또는 단어 중앙 UI."""
        if (item.get("clip_type") or "") == CLIP_TYPE_VOCABULARY:
            self.draw_middle_word(
                screen,
                zones=zones,
                item=item,
                elapsed_sec=elapsed_sec,
                syllable_times=syllable_times,
                sound_duration_sec=sound_duration_sec,
                style=style,
            )
            return
        self.draw_middle_karaoke(
            screen,
            zones=zones,
            item=item,
            elapsed_sec=elapsed_sec,
            syllable_times=syllable_times,
            sound_duration_sec=sound_duration_sec,
            style=style,
        )

    def draw_middle_karaoke(
        self,
        screen: pygame.Surface,
        *,
        zones: ShortsLayoutZones,
        item: dict[str, Any],
        elapsed_sec: float,
        syllable_times: list[float],
        sound_duration_sec: float,
        style: Any,
    ) -> None:
        data = build_sentence_render_data_with_tone_icons(item)
        self._karaoke.draw(
            screen,
            data=data,
            rect=zones.middle,
            style=style,
            elapsed_sec=elapsed_sec,
            syllable_times=syllable_times,
            sound_duration_sec=sound_duration_sec,
        )

    def draw_middle_word(
        self,
        screen: pygame.Surface,
        *,
        zones: ShortsLayoutZones,
        item: dict[str, Any],
        elapsed_sec: float,
        syllable_times: list[float],
        sound_duration_sec: float,
        style: Any,
    ) -> None:
        """단어 숏츠: 연상 이미지 + 노래방(한 글자/음절)."""
        rect = zones.middle
        img_path = str(item.get("word_img_path") or "").strip()
        img = self._load_hook_image(img_path, int(rect.width * 0.5), int(rect.height * 0.35))
        y_top = rect.top + 8
        if img is not None:
            screen.blit(img, (rect.centerx - img.get_width() // 2, y_top))
            y_top += img.get_height() + 12
        sub_rect = pygame.Rect(rect.left, y_top, rect.width, rect.bottom - y_top)
        data = build_sentence_render_data_with_tone_icons(item)
        self._karaoke.draw(
            screen,
            data=data,
            rect=sub_rect,
            style=style,
            elapsed_sec=elapsed_sec,
            syllable_times=syllable_times,
            sound_duration_sec=sound_duration_sec,
        )

    def draw_bottom_zone(
        self,
        screen: pygame.Surface,
        *,
        zones: ShortsLayoutZones,
        situation_subtitle: str,
        cta_text: str,
        channel: str,
        show_cta: bool,
    ) -> None:
        alpha = self.fade_alpha(channel)
        if alpha <= 0:
            return
        rect = zones.bottom
        pad = 20
        y = rect.top + pad
        sub = (situation_subtitle or "").strip()
        if sub:
            surf = self._bottom_font.render(sub, True, (220, 225, 235))
            if alpha < 255:
                surf.set_alpha(alpha)
            screen.blit(surf, (rect.centerx - surf.get_width() // 2, y))
            y += surf.get_height() + 16
        if show_cta:
            cta = (cta_text or "").strip()
            if cta:
                surf = self._cta_font.render(cta, True, (180, 200, 255))
                if alpha < 255:
                    surf.set_alpha(alpha)
                screen.blit(surf, (rect.centerx - surf.get_width() // 2, y))
                y += surf.get_height() + 12
            arrow = self._cta_font.render("⬇", True, (255, 220, 100))
            if alpha < 255:
                arrow.set_alpha(alpha)
            screen.blit(arrow, (rect.centerx - arrow.get_width() // 2, y))
