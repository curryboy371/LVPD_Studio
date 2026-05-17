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
from studio.shorts.constants import (
    HOOK_TITLE_LINE1_COLOR,
    HOOK_TITLE_LINE2_COLOR,
    KO_KARAOKE_ACTIVE,
    KO_KARAOKE_INACTIVE,
    KO_SUBTITLE_BG_PAD_X,
    KO_SUBTITLE_BG_PAD_Y,
    KO_SUBTITLE_BG_RGBA,
    shorts_ko_subtitle_video_bottom_margin,
    shorts_hook_title_line_gap,
    shorts_hook_title_y,
    shorts_middle_y_offset,
    shorts_pinyin_hanzi_gap,
    shorts_pinyin_y_offset,
    shorts_translation_extra_gap,
)
from studio.shorts.layout import ShortsLayoutZones
from studio.shorts.tools.fonts import ShortsFontSizes, build_font_bundle
from studio.shorts.tools.karaoke_renderer import KaraokeRenderer, blit_horizontal_karaoke_wipe
from utils.fonts import load_font_korean

class ShortsDrawer:
    """상단 훅·중앙 학습·하단 CTA 렌더."""

    def __init__(self, *, font_sizes: ShortsFontSizes) -> None:
        self._font_sizes = font_sizes
        self._fonts = build_font_bundle(font_sizes)
        self._drawer = CommonDrawer(fonts=self._fonts)
        self._fade = FadeController()
        self._karaoke = KaraokeRenderer(drawer=self._drawer)
        size = int(font_sizes.hook_title)
        self._hook_font = load_font_korean(size, HOOK_TITLE_LINE1_COLOR, weight="bold")
        self._bottom_font = load_font_korean(int(font_sizes.bottom_kr), WHITE)
        self._ko_subtitle_font = load_font_korean(int(font_sizes.ko_subtitle_kr), WHITE)
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

    def _draw_ko_subtitle_background(
        self,
        screen: pygame.Surface,
        *,
        center_x: int,
        y: int,
        text_w: int,
        text_h: int,
        fade_alpha: int,
    ) -> None:
        """TTS 자막: 검정 배경 + 알파(채널 페이드와 곱)."""
        if text_w <= 0 or text_h <= 0:
            return
        pad_x = KO_SUBTITLE_BG_PAD_X
        pad_y = KO_SUBTITLE_BG_PAD_Y
        bg_w = text_w + pad_x * 2
        bg_h = text_h + pad_y * 2
        bg = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
        _, _, _, base_a = KO_SUBTITLE_BG_RGBA
        a = max(0, min(255, int(base_a * fade_alpha / 255)))
        bg.fill((0, 0, 0, a))
        screen.blit(bg, (center_x - bg_w // 2, y - pad_y))

    def _ensure_bg(self, width: int, height: int) -> None:
        if self._bg_surface is not None and self._bg_surface.get_size() == (width, height):
            return
        surf = pygame.Surface((width, height))
        surf.fill((0, 0, 0))
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

    def _hook_title_font(self) -> Any:
        size = int(self._font_sizes.hook_title)
        for font in (
            self._hook_font,
            load_font_korean(size, HOOK_TITLE_LINE1_COLOR, weight="regular"),
        ):
            if font is not None:
                return font
        return None

    @staticmethod
    def _parse_hook_title_lines(title: str) -> tuple[str, str]:
        text = (title or "").replace("\\n", "\n").strip()
        if not text:
            return "", ""
        parts = text.split("\n", 1)
        line1 = parts[0].strip()
        line2 = parts[1].strip() if len(parts) > 1 else ""
        return line1, line2

    def _render_hook_title_line(
        self,
        font: Any,
        text: str,
        color: tuple[int, int, int],
    ) -> Optional[pygame.Surface]:
        if not text:
            return None
        try:
            surf = font.render(text, True, color)
        except Exception:
            return None
        if surf is not None and surf.get_width() > 0:
            return surf
        return None

    def _render_hook_title(self, title: str, *, frame_height: int) -> Optional[pygame.Surface]:
        line1, line2 = self._parse_hook_title_lines(title)
        if not line1 and not line2:
            return None
        font = self._hook_title_font()
        if font is None:
            return None

        rows: list[pygame.Surface] = []
        if line1:
            surf = self._render_hook_title_line(font, line1, HOOK_TITLE_LINE1_COLOR)
            if surf is not None:
                rows.append(surf)
        if line2:
            surf = self._render_hook_title_line(font, line2, HOOK_TITLE_LINE2_COLOR)
            if surf is not None:
                rows.append(surf)
        if not rows:
            return None
        if len(rows) == 1:
            return rows[0]

        line_gap = shorts_hook_title_line_gap(frame_height)
        total_w = max(s.get_width() for s in rows)
        total_h = sum(s.get_height() for s in rows) + line_gap * (len(rows) - 1)
        out = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
        y = 0
        for surf in rows:
            out.blit(surf, ((total_w - surf.get_width()) // 2, y))
            y += surf.get_height() + line_gap
        return out

    def draw_brand_icon(self, screen: pygame.Surface) -> bool:
        """브랜드 아이콘 — brand_icon 모듈 단일 경로."""
        return brand_icon_module.draw_brand_icon(screen)

    def warm_brand_icon(self) -> None:
        brand_icon_module.warm_brand_icon()

    def compute_center_video_frame_rect(
        self,
        rect: pygame.Rect,
        *,
        pad: int = 16,
        player: Any = None,
        frozen_frame: Optional[pygame.Surface] = None,
        frame_inner_size: Optional[tuple[int, int]] = None,
    ) -> Optional[pygame.Rect]:
        """contain 배치된 비디오 프레임의 화면 Rect (자막 앵커용)."""
        inner = rect.inflate(-pad * 2, -pad * 2)
        if inner.width <= 0 or inner.height <= 0:
            return None
        iw, ih = frame_inner_size or (inner.width, inner.height)
        iw, ih = max(1, int(iw)), max(1, int(ih))
        frame = frozen_frame
        if frame is None and player is not None:
            frame = player.get_frame(iw, ih, contain=True)
        if frame is None:
            return None
        fw, fh = frame.get_width(), frame.get_height()
        x = inner.centerx - fw // 2
        y = inner.centery - fh // 2
        return pygame.Rect(x, y, fw, fh)

    def draw_center_video(
        self,
        screen: pygame.Surface,
        player: Any,
        rect: pygame.Rect,
        *,
        pad: int = 16,
        frozen_frame: Optional[pygame.Surface] = None,
        alpha: int = 255,
        frame_inner_size: Optional[tuple[int, int]] = None,
    ) -> Optional[pygame.Rect]:
        """중앙 구역에 비율 유지(contain)로 비디오 프레임만 출력. 반환: 프레임 Rect."""
        frame_rect = self.compute_center_video_frame_rect(
            rect,
            pad=pad,
            player=player,
            frozen_frame=frozen_frame,
            frame_inner_size=frame_inner_size,
        )
        if frame_rect is None:
            return None
        frame = frozen_frame
        if frame is None and player is not None:
            inner = rect.inflate(-pad * 2, -pad * 2)
            iw, ih = frame_inner_size or (inner.width, inner.height)
            frame = player.get_frame(max(1, int(iw)), max(1, int(ih)), contain=True)
        if frame is None:
            return None
        a = max(0, min(255, int(alpha)))
        if a <= 0:
            return None
        if a < 255:
            frame = frame.copy()
            frame.set_alpha(a)
        screen.blit(frame, frame_rect.topleft)
        return frame_rect

    def draw_ko_subtitle_overlay(
        self,
        screen: pygame.Surface,
        *,
        anchor_rect: pygame.Rect,
        text: str,
        fade_alpha: int = 255,
        subtitle_progress: Optional[float] = None,
    ) -> None:
        """TTS 자막을 비디오(또는 middle) 하단에 겹쳐 그린다."""
        sub = (text or "").strip()
        if not sub or fade_alpha <= 0:
            return
        alpha = max(0, min(255, int(fade_alpha)))
        cx = anchor_rect.centerx
        margin = shorts_ko_subtitle_video_bottom_margin(screen.get_height())

        if subtitle_progress is not None:
            surf_in = self._ko_subtitle_font.render(sub, True, KO_KARAOKE_INACTIVE)
            surf_ac = self._ko_subtitle_font.render(sub, True, KO_KARAOKE_ACTIVE)
            tw, th = surf_in.get_width(), surf_in.get_height()
            y = anchor_rect.bottom - margin - th
            self._draw_ko_subtitle_background(
                screen, center_x=cx, y=y, text_w=tw, text_h=th, fade_alpha=alpha
            )
            if alpha < 255:
                surf_in = surf_in.copy()
                surf_ac = surf_ac.copy()
                surf_in.set_alpha(alpha)
                surf_ac.set_alpha(alpha)
            blit_horizontal_karaoke_wipe(
                screen, surf_in, surf_ac, center_x=cx, y=y, progress=subtitle_progress
            )
            return

        surf = self._ko_subtitle_font.render(sub, True, KO_KARAOKE_ACTIVE)
        tw, th = surf.get_width(), surf.get_height()
        y = anchor_rect.bottom - margin - th
        self._draw_ko_subtitle_background(
            screen, center_x=cx, y=y, text_w=tw, text_h=th, fade_alpha=alpha
        )
        if alpha < 255:
            surf = surf.copy()
            surf.set_alpha(alpha)
        screen.blit(surf, (cx - tw // 2, y))

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

        surf = self._render_hook_title(title, frame_height=screen.get_height())
        if surf is None:
            return rect.top + pad

        fh = screen.get_height()
        tx = rect.centerx - surf.get_width() // 2
        ty = shorts_hook_title_y(fh)
        ty = max(pad, min(ty, fh - surf.get_height() - pad))
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
        """판다 이미지(페이드). 타이틀 바로 아래부터 배치(상단 구역 밖으로 내려갈 수 있음)."""
        img_alpha = self.fade_alpha(channel)
        if img_alpha <= 0:
            return

        rect = zones.top
        pad = 16
        fh = screen.get_height()
        img_h = max(64, fh - image_y - pad)
        img = self._load_hook_image(hook_image_path, rect.width - pad * 2, img_h)
        if img is None:
            return

        x = rect.centerx - img.get_width() // 2
        y = max(pad, image_y)
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
        fh = screen.get_height()
        self._karaoke.draw(
            screen,
            data=data,
            rect=zones.middle,
            style=style,
            elapsed_sec=elapsed_sec,
            syllable_times=syllable_times,
            sound_duration_sec=sound_duration_sec,
            y_offset=shorts_middle_y_offset(fh),
            pinyin_y_offset=shorts_pinyin_y_offset(fh),
            pinyin_hanzi_gap=shorts_pinyin_hanzi_gap(fh),
            translation_extra_gap=shorts_translation_extra_gap(fh),
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
        y_off = shorts_middle_y_offset(screen.get_height())
        img_path = str(item.get("word_img_path") or "").strip()
        img = self._load_hook_image(img_path, int(rect.width * 0.5), int(rect.height * 0.35))
        y_top = rect.top + 8 + y_off
        if img is not None:
            screen.blit(img, (rect.centerx - img.get_width() // 2, y_top))
            y_top += img.get_height() + 12
        sub_rect = pygame.Rect(rect.left, y_top, rect.width, rect.bottom - y_top)
        data = build_sentence_render_data_with_tone_icons(item)
        fh = screen.get_height()
        self._karaoke.draw(
            screen,
            data=data,
            rect=sub_rect,
            style=style,
            elapsed_sec=elapsed_sec,
            syllable_times=syllable_times,
            sound_duration_sec=sound_duration_sec,
            y_offset=0,
            translation_extra_gap=shorts_translation_extra_gap(fh),
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
        highlight_subtitle: bool = False,
        subtitle_progress: Optional[float] = None,
    ) -> None:
        alpha = self.fade_alpha(channel)
        if alpha <= 0:
            return
        rect = zones.bottom
        pad = 20
        y = rect.top + pad
        sub = (situation_subtitle or "").strip()
        if sub and not highlight_subtitle:
            sub_color = (220, 225, 235)
            surf = self._bottom_font.render(sub, True, sub_color)
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
