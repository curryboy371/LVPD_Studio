"""숏츠 3구역 UI 그리기."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import pygame

from studio.conversation.core.types import FrameContext, build_sentence_render_data_with_tone_icons
from studio.conversation.tools.common_drawer import CommonDrawer
from studio.conversation.tools.fade_controller import FadeController
from studio.conversation.tools.fonts import WHITE
from studio.shorts.clip_types import CLIP_TYPE_VOCABULARY
from studio.shorts import brand_icon as brand_icon_module
from studio.shorts.constants import (
    SHORTS_VOCAB_POS_FONT_RATIO,
    shorts_vocab_hanzi_line_height,
    shorts_vocab_word_img_inner_size,
    shorts_vocab_layout_metrics,
    shorts_vocab_overlay_layout,
    shorts_vocab_pos_after_hanzi_gap,
    shorts_vocab_pos_line_height,
    shorts_vocab_tip_font_pt,
    HOOK_TITLE_LINE1_COLOR,
    HOOK_TITLE_LINE2_COLOR,
    KO_KARAOKE_ACTIVE,
    KO_KARAOKE_INACTIVE,
    KO_SUBTITLE_BG_PAD_X,
    KO_SUBTITLE_BG_PAD_Y,
    KO_SUBTITLE_BG_RGBA,
    KARAOKE_INACTIVE_HANZI,
    KARAOKE_INACTIVE_PINYIN,
    SHORTS_VOCAB_OVERLAY_BG_PAD_X,
    SHORTS_VOCAB_OVERLAY_BG_PAD_Y,
    SHORTS_VOCAB_OVERLAY_BG_RGBA,
    shorts_ko_subtitle_below_video_gap,
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
from utils.fonts import load_font_korean, load_font_kr_chinese

# clip_scene fade 채널과 동일 문자열
_CHANNEL_BOTTOM = "shorts_bottom"


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
        bottom_pt = int(font_sizes.bottom_kr)
        self._bottom_font = load_font_kr_chinese(bottom_pt, WHITE) or load_font_korean(
            bottom_pt, WHITE
        )
        self._ko_subtitle_font = load_font_korean(int(font_sizes.ko_subtitle_kr), WHITE)
        self._bg_surface: Optional[pygame.Surface] = None
        self._hook_image_cache: dict[str, pygame.Surface] = {}
        self._tip_font_pt = 0
        self._tip_font_kr: Any = None
        self._tip_font_cn: Any = None

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

    def _draw_alpha_panel_background(
        self,
        screen: pygame.Surface,
        *,
        center_x: int,
        top: int,
        width: int,
        height: int,
        fade_alpha: int,
        bg_rgba: tuple[int, int, int, int],
        pad_x: int,
        pad_y: int,
    ) -> None:
        """텍스트 블록 뒤 반투명 패널."""
        if width <= 0 or height <= 0:
            return
        bg_w = int(width) + pad_x * 2
        bg_h = int(height) + pad_y * 2
        bg = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
        _, _, _, base_a = bg_rgba
        a = max(0, min(255, int(base_a * fade_alpha / 255)))
        bg.fill((0, 0, 0, a))
        screen.blit(bg, (center_x - bg_w // 2, int(top) - pad_y))

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
        self._draw_alpha_panel_background(
            screen,
            center_x=center_x,
            top=y,
            width=text_w,
            height=text_h,
            fade_alpha=fade_alpha,
            bg_rgba=KO_SUBTITLE_BG_RGBA,
            pad_x=KO_SUBTITLE_BG_PAD_X,
            pad_y=KO_SUBTITLE_BG_PAD_Y,
        )

    def _measure_vocab_cn_stack(
        self,
        data: Any,
        *,
        pinyin_y: int,
        hanzi_y: int,
        hanzi_line_h: int,
        pos: str,
        frame_height: int,
    ) -> Optional[tuple[int, int, int]]:
        """병음·한자·품사 블록 (top, bottom, max_width). 없으면 None."""
        pinyin = (getattr(data, "pinyin", None) or "").strip()
        hanzi = (getattr(data, "sentence", None) or "").strip()
        pos_label = (pos or "").strip()
        if not pinyin and not hanzi and not pos_label:
            return None

        max_w = 0
        fonts = self._fonts
        if pinyin:
            surf_in, _ = self._drawer._get_cached_text_pair(
                self._drawer._cache_pinyin,
                fonts.pinyin_ft,
                fonts.pinyin_pg,
                pinyin,
                KARAOKE_INACTIVE_PINYIN,
            )
            max_w = max(max_w, surf_in.get_width())
        if hanzi:
            surf_in, _ = self._drawer._get_cached_text_pair(
                self._drawer._cache_hanzi,
                fonts.hanzi_ft,
                fonts.hanzi_pg,
                hanzi,
                KARAOKE_INACTIVE_HANZI,
            )
            max_w = max(max_w, surf_in.get_width())
        if pos_label:
            from utils.fonts import load_font_korean

            pos_pt = max(14, int(self._font_sizes.kr * SHORTS_VOCAB_POS_FONT_RATIO))
            font = load_font_korean(pos_pt, WHITE)
            if font is not None:
                max_w = max(max_w, font.render(pos_label, True, WHITE).get_width())

        top = int(pinyin_y) if pinyin else int(hanzi_y)
        bottom = int(hanzi_y) + int(hanzi_line_h)
        if pos_label:
            bottom += shorts_vocab_pos_after_hanzi_gap(frame_height)
            bottom += shorts_vocab_pos_line_height(
                frame_height, kr_font_pt=int(self._font_sizes.kr)
            )
        if bottom <= top:
            bottom = top + max(1, int(hanzi_line_h))
        return top, bottom, max(1, max_w)

    def _draw_vocab_cn_stack_background(
        self,
        screen: pygame.Surface,
        *,
        center_x: int,
        stack: tuple[int, int, int],
        fade_alpha: int,
    ) -> None:
        top, bottom, max_w = stack
        self._draw_alpha_panel_background(
            screen,
            center_x=center_x,
            top=top,
            width=max_w,
            height=bottom - top,
            fade_alpha=fade_alpha,
            bg_rgba=SHORTS_VOCAB_OVERLAY_BG_RGBA,
            pad_x=SHORTS_VOCAB_OVERLAY_BG_PAD_X,
            pad_y=SHORTS_VOCAB_OVERLAY_BG_PAD_Y,
        )

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

    def _load_hook_image(
        self,
        path: str,
        max_w: int,
        max_h: int,
        *,
        allow_upscale: bool = False,
    ) -> Optional[pygame.Surface]:
        key = f"{path}|{max_w}|{max_h}|{int(allow_upscale)}"
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
        scale = min(float(max_w) / sw, float(max_h) / sh)
        if not allow_upscale:
            scale = min(scale, 1.0)
        tw = max(1, int(sw * scale))
        th = max(1, int(sh * scale))
        if tw == sw and th == sh:
            scaled = img
        else:
            scaled = pygame.transform.smoothscale(img, (tw, th))
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

    def measure_ko_subtitle_height(self, text: str) -> int:
        sub = (text or "").strip()
        if not sub:
            return 0
        surf = self._ko_subtitle_font.render(sub, True, (255, 255, 255))
        return max(0, int(surf.get_height()))

    @staticmethod
    def _vocab_meaning_text(item: dict[str, Any]) -> str:
        """words.csv 뜻(translation) — '뜻 · 품사' 형식이면 뜻만."""
        trans_raw = item.get("translation") or []
        if isinstance(trans_raw, list):
            text = (trans_raw[0] if trans_raw else "").strip()
        else:
            text = str(trans_raw or "").strip()
        if " · " in text:
            text = text.split(" · ", 1)[0].strip()
        return text

    def _draw_vocab_meaning_line(
        self,
        screen: pygame.Surface,
        *,
        center_x: int,
        y: int,
        text: str,
        fade_alpha: int = 255,
    ) -> None:
        """이미지 위 words.csv 뜻(한국어)."""
        label = (text or "").strip()
        if not label or fade_alpha <= 0:
            return
        alpha = max(0, min(255, int(fade_alpha)))
        surf = self._ko_subtitle_font.render(label, True, KO_KARAOKE_ACTIVE)
        tw, th = surf.get_width(), surf.get_height()
        self._draw_ko_subtitle_background(
            screen, center_x=center_x, y=int(y), text_w=tw, text_h=th, fade_alpha=alpha
        )
        if alpha < 255:
            surf = surf.copy()
            surf.set_alpha(alpha)
        screen.blit(surf, (center_x - tw // 2, int(y)))

    def draw_vocab_tip(
        self,
        screen: pygame.Surface,
        *,
        center_x: int,
        y: int,
        text: str,
        fade_alpha: int = 255,
    ) -> None:
        """숏츠 단어: 뜻 TTS 자막 아래 tip (한글·한자 글자별 폰트, 흰색)."""
        tip = (text or "").strip()
        if not tip or fade_alpha <= 0:
            return
        from utils.fonts import blit_mixed_kr_cn_centered, load_font_chinese_for_tip, load_font_korean

        pt = shorts_vocab_tip_font_pt(ko_subtitle_pt=int(self._font_sizes.ko_subtitle_kr))
        color = (255, 255, 255)
        if not hasattr(self, "_tip_font_pt") or self._tip_font_pt != pt:
            self._tip_font_pt = pt
            self._tip_font_kr = load_font_korean(pt, color)
            self._tip_font_cn = load_font_chinese_for_tip(pt, color)
        blit_mixed_kr_cn_centered(
            screen,
            center_x=center_x,
            y=y,
            text=tip,
            size=pt,
            color=color,
            fade_alpha=fade_alpha,
            font_kr=getattr(self, "_tip_font_kr", None),
            font_cn=getattr(self, "_tip_font_cn", None),
        )

    def draw_ko_subtitle_overlay(
        self,
        screen: pygame.Surface,
        *,
        anchor_rect: pygame.Rect,
        text: str,
        fade_alpha: int = 255,
        subtitle_progress: Optional[float] = None,
        below_gap_fn: Optional[Callable[[int], int]] = None,
    ) -> None:
        """TTS 자막을 앵커 rect 바로 아래에 그린다."""
        sub = (text or "").strip()
        if not sub or fade_alpha <= 0:
            return
        alpha = max(0, min(255, int(fade_alpha)))
        cx = anchor_rect.centerx
        fh = max(1, int(screen.get_height()))
        if below_gap_fn is not None:
            gap = int(below_gap_fn(fh))
        else:
            gap = shorts_ko_subtitle_below_video_gap(fh)

        if subtitle_progress is not None:
            surf_in = self._ko_subtitle_font.render(sub, True, KO_KARAOKE_INACTIVE)
            surf_ac = self._ko_subtitle_font.render(sub, True, KO_KARAOKE_ACTIVE)
            tw, th = surf_in.get_width(), surf_in.get_height()
            y = anchor_rect.bottom + gap
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
        y = anchor_rect.bottom + gap
        self._draw_ko_subtitle_background(
            screen, center_x=cx, y=y, text_w=tw, text_h=th, fade_alpha=alpha
        )
        if alpha < 255:
            surf = surf.copy()
            surf.set_alpha(alpha)
        screen.blit(surf, (cx - tw // 2, y))

    def measure_hook_title_bottom_y(
        self,
        hook_title: str,
        *,
        frame_height: int,
    ) -> int:
        """훅 타이틀 하단 Y(미표시 시 0)."""
        title = (hook_title or "").strip()
        if not title:
            return 0
        surf = self._render_hook_title(title, frame_height=frame_height)
        if surf is None:
            return 0
        fh = max(1, int(frame_height))
        pad = 16
        ty = shorts_hook_title_y(fh)
        ty = max(pad, min(ty, fh - surf.get_height() - pad))
        return ty + surf.get_height()

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
        hook_title: str = "",
    ) -> None:
        """clip_type에 따라 상황극(노래방) 또는 단어 중앙 UI."""
        if (item.get("clip_type") or "") == CLIP_TYPE_VOCABULARY:
            fh = screen.get_height()
            rect = zones.middle
            hook_bottom = self.measure_hook_title_bottom_y(hook_title, frame_height=fh)
            layout_top, img_band_h = shorts_vocab_layout_metrics(
                rect.top,
                rect.height,
                rect.bottom,
                fh,
                hook_title_bottom_y=hook_bottom,
            )
            self.draw_middle_word(
                screen,
                zones=zones,
                item=item,
                elapsed_sec=elapsed_sec,
                syllable_times=syllable_times,
                sound_duration_sec=sound_duration_sec,
                style=style,
                layout_top=layout_top,
                img_band_h=img_band_h,
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

    def _draw_vocab_pos_line(
        self,
        screen: pygame.Surface,
        *,
        center_x: int,
        hanzi_y: int,
        hanzi_line_h: int,
        pos: str,
        frame_height: int,
        text_color: tuple[int, int, int],
    ) -> None:
        """품사 — 한자 바로 아래."""
        label = (pos or "").strip()
        if not label:
            return
        from utils.fonts import load_font_korean

        pos_pt = max(14, int(self._font_sizes.kr * SHORTS_VOCAB_POS_FONT_RATIO))
        font = load_font_korean(pos_pt, text_color)
        if font is None:
            return
        surf = font.render(label, True, text_color)
        gap = shorts_vocab_pos_after_hanzi_gap(frame_height)
        y = int(hanzi_y) + int(hanzi_line_h) + gap
        screen.blit(surf, (center_x - surf.get_width() // 2, y))

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
        layout_top: Optional[int] = None,
        img_band_h: Optional[int] = None,
    ) -> None:
        """단어 숏츠: 연상 이미지 + 노래방(한 글자/음절)."""
        rect = zones.middle
        fh = screen.get_height()
        if layout_top is None or img_band_h is None:
            hook_bottom = self.measure_hook_title_bottom_y(
                str(item.get("hook_title") or ""), frame_height=fh
            )
            layout_top, img_band_h = shorts_vocab_layout_metrics(
                rect.top,
                rect.height,
                rect.bottom,
                fh,
                hook_title_bottom_y=hook_bottom,
            )
        img_path = str(item.get("word_img_path") or "").strip()
        max_w, max_h = shorts_vocab_word_img_inner_size(rect.width, rect.height, fh)
        img = self._load_hook_image(
            img_path,
            max_w,
            max(max_h, int(img_band_h)),
            allow_upscale=True,
        )
        if img is not None:
            iy = int(layout_top) + max(0, (int(img_band_h) - img.get_height()) // 2)
            screen.blit(img, (rect.centerx - img.get_width() // 2, iy))
        meaning_text = self._vocab_meaning_text(item)
        pos = str(item.get("word_pos") or "").strip()
        if not pos:
            trans_raw = item.get("translation") or []
            if isinstance(trans_raw, list):
                legacy = (trans_raw[0] if trans_raw else "").strip()
            else:
                legacy = str(trans_raw or "").strip()
            if " · " in legacy:
                parts = [p.strip() for p in legacy.split(" · ", 1)]
                if len(parts) == 2 and parts[1]:
                    pos = parts[1]
        tip_text = str(item.get("word_tip") or "").strip()
        overlay = shorts_vocab_overlay_layout(
            int(layout_top),
            int(img_band_h),
            fh,
            frame_width=screen.get_width(),
            has_pos=bool(pos),
            has_tip=bool(tip_text),
            cn_font_pt=int(self._font_sizes.cn),
            kr_font_pt=int(self._font_sizes.kr),
            ko_subtitle_pt=int(self._font_sizes.ko_subtitle_kr),
        )
        pinyin_y = overlay.pinyin_y
        hanzi_y = overlay.hanzi_y
        hanzi_line_h = shorts_vocab_hanzi_line_height(fh, cn_font_pt=int(self._font_sizes.cn))
        sub_rect = pygame.Rect(
            rect.left, int(layout_top), rect.width, max(80, int(img_band_h))
        )
        item_karaoke = dict(item)
        item_karaoke["translation"] = []
        data = build_sentence_render_data_with_tone_icons(item_karaoke)
        trans_color = getattr(getattr(style, "colors", None), "translation_color", WHITE)
        fade = self.fade_alpha(_CHANNEL_BOTTOM)
        stack = self._measure_vocab_cn_stack(
            data,
            pinyin_y=pinyin_y,
            hanzi_y=hanzi_y,
            hanzi_line_h=hanzi_line_h,
            pos=pos,
            frame_height=fh,
        )
        if stack is not None:
            self._draw_vocab_cn_stack_background(
                screen, center_x=rect.centerx, stack=stack, fade_alpha=fade
            )
        self._karaoke.draw(
            screen,
            data=data,
            rect=sub_rect,
            style=style,
            elapsed_sec=elapsed_sec,
            syllable_times=syllable_times,
            sound_duration_sec=sound_duration_sec,
            fixed_pinyin_y=pinyin_y,
            fixed_hanzi_y=hanzi_y,
        )
        if pos:
            self._draw_vocab_pos_line(
                screen,
                center_x=rect.centerx,
                hanzi_y=hanzi_y,
                hanzi_line_h=hanzi_line_h,
                pos=pos,
                frame_height=fh,
                text_color=trans_color,
            )
    def draw_vocab_meaning_if_any(
        self,
        screen: pygame.Surface,
        *,
        zones: ShortsLayoutZones,
        item: dict[str, Any],
        hook_title: str = "",
        fade_alpha: int = 255,
    ) -> None:
        """단어 뜻(words.csv) — middle set_clip 밖에서 그려 하단 잘림 방지."""
        meaning_text = self._vocab_meaning_text(item)
        if not meaning_text or fade_alpha <= 0:
            return
        fh = screen.get_height()
        hook_bottom = self.measure_hook_title_bottom_y(hook_title, frame_height=fh)
        layout_top, img_band_h = shorts_vocab_layout_metrics(
            zones.middle.top,
            zones.middle.height,
            zones.middle.bottom,
            fh,
            hook_title_bottom_y=hook_bottom,
        )
        pos = str(item.get("word_pos") or "").strip()
        tip_text = str(item.get("word_tip") or "").strip()
        overlay = shorts_vocab_overlay_layout(
            int(layout_top),
            int(img_band_h),
            fh,
            frame_width=screen.get_width(),
            has_pos=bool(pos),
            has_tip=bool(tip_text),
            cn_font_pt=int(self._font_sizes.cn),
            kr_font_pt=int(self._font_sizes.kr),
            ko_subtitle_pt=int(self._font_sizes.ko_subtitle_kr),
        )
        self._draw_vocab_meaning_line(
            screen,
            center_x=zones.middle.centerx,
            y=overlay.meaning_y,
            text=meaning_text,
            fade_alpha=fade_alpha,
        )

    def draw_bottom_zone(
        self,
        screen: pygame.Surface,
        *,
        zones: ShortsLayoutZones,
        situation_subtitle: str,
        channel: str,
        subtitle_progress: Optional[float] = None,
    ) -> None:
        alpha = self.fade_alpha(channel)
        if alpha <= 0:
            return
        rect = zones.bottom
        pad = 20
        y = rect.top + pad
        sub = (situation_subtitle or "").strip()
        if sub:
            sub_color = (220, 225, 235)
            surf = self._bottom_font.render(sub, True, sub_color)
            if alpha < 255:
                surf.set_alpha(alpha)
            screen.blit(surf, (rect.centerx - surf.get_width() // 2, y))
