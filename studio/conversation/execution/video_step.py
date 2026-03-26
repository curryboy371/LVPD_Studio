"""Video-only step."""

from __future__ import annotations

import pygame

from ..core.types import ConversationItemLike, FrameContext
from .base import BaseStep


class VideoStep(BaseStep):
    """비디오 프레임만 그리는 Step."""

    def __init__(self, *, drawer, video_player) -> None:
        super().__init__(drawer=drawer, video_player=video_player)
        self._fade_out_sec: float = 1.2
        self._fade_elapsed: float = 0.0
        self._is_fading: bool = False
        self._fade_max_alpha: int = int(255 * 0.8)

    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        _ = (ctx, item)
        # 비디오 재생(시간 진행)은 PlaybackManager가 tick()으로 담당.
        # 여기서는 "해당 아이템의 세그먼트가 끝났는지"를 감지해
        # fadeout 완료 후 transition_signal을 올린다.
        try:
            end_sec = float(self.video_player.get_effective_end_sec())
            pts = float(self.video_player.get_pts())
            at_end = self.video_player.is_paused() and pts >= end_sec - 1e-3
            if not at_end:
                # 사용자가 seek/restart 했거나 아직 재생 중이면 페이드 상태를 리셋
                self._is_fading = False
                self._fade_elapsed = 0.0
                self.transition_signal = False
                self.transition_bg_frame = None
                return

            # 재생이 끝난 프레임에서 fadeout을 진행하고, fade가 끝나면 전환 시그널을 올린다.
            if not self._is_fading:
                self._is_fading = True
                self._fade_elapsed = 0.0
                self.transition_signal = False
                self.transition_bg_frame = None
            else:
                self._fade_elapsed += float(ctx.dt_sec)
                if self._fade_elapsed >= self._fade_out_sec:
                    # 다음 step 배경으로 넘길 "페이드 적용된 마지막 프레임" 스냅샷 생성
                    self.transition_bg_frame = self._build_faded_snapshot(ctx, fade_t=1.0)
                    self.transition_signal = True
        except Exception:
            return

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        _ = item
        frame = self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        if self._is_fading:
            # 마지막 프레임 위로 검은색 페이드 아웃 오버레이
            denom = self._fade_out_sec if self._fade_out_sec > 1e-6 else 1e-6
            t = max(0.0, min(1.0, self._fade_elapsed / denom))
            alpha = int(self._fade_max_alpha * t)
            if alpha > 0:
                overlay = pygame.Surface((ctx.width, ctx.height), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, alpha))
                screen.blit(overlay, (0, 0))

    def _build_faded_snapshot(self, ctx: FrameContext, *, fade_t: float) -> pygame.Surface | None:
        """현재 비디오 프레임 위에 fade를 합성한 스냅샷을 만든다."""
        frame = self.video_player.get_frame(ctx.width, ctx.height)
        if frame is None:
            return None
        snap = frame.copy()
        t = max(0.0, min(1.0, float(fade_t)))
        alpha = int(self._fade_max_alpha * t)
        if alpha > 0:
            overlay = pygame.Surface((ctx.width, ctx.height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha))
            snap.blit(overlay, (0, 0))
        return snap

