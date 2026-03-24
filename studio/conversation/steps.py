"""회화 스튜디오 쉐도잉 단계(ShadowingStep)별 상태 머신 Step 구현."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from studio.recording_events import is_recording

from .constants import ShadowingStep
from .step1_video_draw import draw_impl_step1, draw_step1_video
from .step2_draw import draw_util_screen


class ConversationStepContext:
    """Step이 공유 리소스(스튜디오 인스턴스)에 접근할 때 사용하는 얇은 컨텍스트."""

    __slots__ = ("studio",)

    def __init__(self, studio: Any) -> None:
        self.studio = studio


class IConversationStep(ABC):
    """쉐도잉 단계 하나: enter/update/draw/exit 및 선택적 완료 조건."""

    @abstractmethod
    def enter(self) -> None:
        """단계 진입 시 초기화."""

    @abstractmethod
    def update(self, config: Any) -> None:
        """프레임당 로직 (config.dt_sec 등)."""

    @abstractmethod
    def draw(self, screen: Any, config: Any) -> None:
        """배경 채우기 이후 본문 그리기. paused/debug 오버레이는 스튜디오가 이어서 처리."""

    @abstractmethod
    def exit(self) -> None:
        """단계 이탈 시 정리."""

    def is_complete(self) -> bool:
        """다음 단계로 자동 전환할지 (현재 제품은 키 1/2/3 수동 전환만 사용)."""
        return False


class VideoShadowingStep(IConversationStep):
    """ShadowingStep.VIDEO: 동영상만 (페이드·듣기 UI 없음)."""

    def __init__(self, ctx: ConversationStepContext) -> None:
        self._ctx = ctx

    def enter(self) -> None:
        s = self._ctx.studio
        s._fade_alpha = 0.0
        s._ui_visible = False

    def update(self, config: Any) -> None:
        pass

    def draw(self, screen: Any, config: Any) -> None:
        draw_step1_video(self._ctx.studio, screen, config)

    def exit(self) -> None:
        pass


class ListenShadowingStep(IConversationStep):
    """ShadowingStep.LISTEN: 영상 + 페이드 + 병음/한자/해석 UI (멈춤 시)."""

    def __init__(self, ctx: ConversationStepContext) -> None:
        self._ctx = ctx

    def enter(self) -> None:
        pass

    def update(self, config: Any) -> None:
        if config is not None and is_recording(config):
            return
        self._ctx.studio._update_step1(config)

    def draw(self, screen: Any, config: Any) -> None:
        draw_impl_step1(self._ctx.studio, screen, config)

    def exit(self) -> None:
        pass


class UtilShadowingStep(IConversationStep):
    """ShadowingStep.UTIL: 자막 + 단어 카드 (문장 활용)."""

    def __init__(self, ctx: ConversationStepContext) -> None:
        self._ctx = ctx

    def enter(self) -> None:
        s = self._ctx.studio
        s._fade_alpha = 0.0
        s._ui_visible = False

    def update(self, config: Any) -> None:
        pass

    def draw(self, screen: Any, config: Any) -> None:
        draw_util_screen(self._ctx.studio, screen, config)

    def exit(self) -> None:
        pass


def build_shadowing_steps(ctx: ConversationStepContext) -> dict[ShadowingStep, IConversationStep]:
    """ShadowingStep 열거형과 Step 인스턴스 매핑."""
    return {
        ShadowingStep.VIDEO: VideoShadowingStep(ctx),
        ShadowingStep.LISTEN: ListenShadowingStep(ctx),
        ShadowingStep.UTIL: UtilShadowingStep(ctx),
    }
