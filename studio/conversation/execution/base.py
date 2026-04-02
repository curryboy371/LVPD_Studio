"""Step interfaces and base implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

import pygame

from ..core.types import ConversationItemLike, FrameContext
from .stage_sequence import StageSequenceEngine


class IStep(ABC):
    """단계별 실행 로직 인터페이스."""

    def __init__(self) -> None:
        self.is_done: bool = False
        # 다음 Step으로 넘어가도 된다는 "전환 시그널".
        # PlaybackManager는 이 값이 True일 때만 step_sequence를 진행한다.
        self.transition_signal: bool = False

    @abstractmethod
    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """프레임당 로직 업데이트."""

    @abstractmethod
    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """프레임 렌더링."""


class BaseStep(IStep):
    """공통 편의 기능을 제공하는 기본 Step."""

    def __init__(self, *, drawer: Any, video_player: Any) -> None:
        super().__init__()
        self.drawer = drawer
        self.video_player = video_player
        # 직전 step의 마지막 프레임을 다음 step의 배경으로 쓰기 위한 스냅샷.
        # PlaybackManager가 step 전환 시점에 캡처해서 주입할 수 있다.
        self.bg_frame: pygame.Surface | None = None
        # step이 전환 직전에 "다음 step으로 넘길 프레임"을 직접 합성했을 때 사용.
        self.transition_bg_frame: pygame.Surface | None = None
        # substage 시퀀스/타이머/콜백
        self.substage = StageSequenceEngine()
        self.substage.set_default_advance(self._on_remain_default_advance)
        self._finish_step_on_last_remain_expired: bool = False
        self._active_item_key: Any | None = None
        self._main_on_first_tick: Callable[[], None] | None = None
        self._main_on_tick: Callable[[FrameContext], None] | None = None
        self._main_on_end: Callable[[], None] | None = None
        self._main_entered: bool = True
        self._main_ended: bool = False

    @staticmethod
    def _stage_callback_key(stage: Any) -> str:
        """Enum/str 등 서로 다른 stage 표현을 콜백 딕셔너리 조회용 키로 통일한다."""
        return StageSequenceEngine.normalize_key(stage)

    def configure_stages(
        self,
        stages: list[str] | tuple[str, ...],
        *,
        initial: Any | None = None,
        finish_step_on_last_remain_expired: bool = False,
    ) -> None:
        """문자열 기반 substage 시퀀스를 구성하고 초기 stage를 설정한다.

        finish_step_on_last_remain_expired:
            True이면 시퀀스의 **마지막** 스테이지에서 remain 타이머가 만료될 때
            `bind_remain_expired`가 없어도 `_end_main_stage()`를 호출한다.
        """
        self.substage.configure(stages, initial=initial)
        self._finish_step_on_last_remain_expired = bool(finish_step_on_last_remain_expired)
        self._main_on_first_tick = None
        self._main_on_tick = None
        self._main_on_end = None
        self._main_entered = True
        self._main_ended = False
        self.register_main_stage_callbacks()
        self.register_stage_callbacks()

    def _configure_substages(
        self,
        stages: list[str] | tuple[str, ...],
        *,
        initial: Any | None = None,
        finish_step_on_last_remain_expired: bool = False,
    ) -> None:
        """`configure_stages`와 동일(하위 호환 이름)."""
        self.configure_stages(
            stages,
            initial=initial,
            finish_step_on_last_remain_expired=finish_step_on_last_remain_expired,
        )

    def bind_enter(self, stage: Any, fn: Callable[[], None]) -> None:
        """substage 진입 직후 첫 프레임에서 한 번 호출될 콜백을 등록한다."""
        self.substage.bind_enter(stage, fn)

    def bind_end(self, stage: Any, fn: Callable[[], None]) -> None:
        """떠나는 substage에 대한 콜백. 다음 stage로 넘어가기 직전, 이전 stage 기준으로 호출된다."""
        self.substage.bind_end(stage, fn)

    def bind_tick(self, stage: Any, fn: Callable[[FrameContext], None]) -> None:
        """substage 매 프레임 콜백을 등록한다."""
        self.substage.bind_tick(stage, fn)

    def bind_remain_expired(self, stage: Any, fn: Callable[[], None]) -> None:
        """remain 타이머 만료 시 호출(등록 없으면 시퀀스 다음 stage로 이동)."""
        self.substage.bind_remain_expired(stage, fn)

    def set_timer(self, sec: float) -> None:
        """현재 substage remain 타이머(초) 설정."""
        self.substage.set_timer(sec)

    def _register_main_stage_callbacks(
        self,
        *,
        on_first_tick: Callable[[], None] | None = None,
        on_tick: Callable[[FrameContext], None] | None = None,
        on_end: Callable[[], None] | None = None,
    ) -> None:
        """현재 Step(메인 stage) 콜백을 등록한다."""
        if on_first_tick is not None:
            self._main_on_first_tick = on_first_tick
        if on_tick is not None:
            self._main_on_tick = on_tick
        if on_end is not None:
            self._main_on_end = on_end

    def register_main_stage_callbacks(self) -> None:
        """메인 stage 콜백을 등록하는 가상 함수."""
        return

    def register_stage_callbacks(self) -> None:
        """substage별 콜백을 등록하는 가상 함수."""
        return

    def _set_substage_remain_sec(self, sec: float) -> None:
        """`set_timer`와 동일(하위 호환 이름)."""
        self.set_timer(sec)

    def _goto_stage(self, stage: Any) -> None:
        """지정한 stage로 전환한다."""
        self._set_stage(stage)

    def _on_remain_default_advance(self) -> bool:
        """remain 만료 시 `bind_remain_expired`가 없을 때: 다음 stage 또는 마지막에서 Step 종료."""
        st = self.substage.current_stage
        seq = self.substage.sequence
        if (
            self._finish_step_on_last_remain_expired
            and st is not None
            and seq
            and st == seq[-1]
        ):
            self._end_main_stage()
            return True
        return self._goto_next_substage()

    def _goto_next_substage(self) -> bool:
        """시퀀스 기준 다음 stage로 전환한다."""
        st = self.substage.current_stage
        seq = self.substage.sequence
        imap = self.substage.index_map
        if st is None or st not in imap:
            return False
        idx = imap[st]
        next_idx = idx + 1
        if next_idx >= len(seq):
            return False
        self._set_stage(seq[next_idx])
        return True

    def _goto_next_stage(self) -> bool:
        """시퀀스 기준 다음 stage로 전환한다."""
        return self._goto_next_substage()

    def on_main_first_tick(self) -> None:
        """현재 Step의 첫 프레임 처리 훅(등록된 main first-tick이 없을 때 호출)."""
        return

    def on_main_tick(self, ctx: FrameContext) -> None:
        """현재 Step의 매 프레임 처리 훅(등록된 main tick이 없을 때 호출)."""
        _ = ctx

    def on_main_end(self) -> None:
        """현재 Step 종료 처리 훅(등록된 main end가 없을 때 호출)."""
        return

    def _tick_main_enter(self) -> None:
        """현재 Step의 첫 프레임 처리를 수행한다."""
        if not self._main_entered:
            return
        self._main_entered = False
        if self._main_on_first_tick is not None:
            try:
                self._main_on_first_tick()
            except Exception:
                pass
            return
        try:
            self.on_main_first_tick()
        except Exception:
            pass

    def _tick_main(self, ctx: FrameContext) -> None:
        """현재 Step의 매 프레임 처리를 수행한다."""
        if self._main_on_tick is not None:
            try:
                self._main_on_tick(ctx)
            except Exception:
                pass
            return
        try:
            self.on_main_tick(ctx)
        except Exception:
            pass

    def _end_main_stage(self) -> None:
        """현재 Step을 종료 상태로 전환하고 main end 콜백을 1회 호출한다."""
        if self._main_ended:
            return
        self._main_ended = True
        if self._main_on_end is not None:
            try:
                self._main_on_end()
            except Exception:
                pass
            return
        try:
            self.on_main_end()
        except Exception:
            pass

    def _restart_main_stage(self) -> None:
        """현재 Step의 main stage 라이프사이클을 새로 시작한다."""
        self._main_entered = True
        self._main_ended = False

    def _tick_stage(self, ctx: FrameContext) -> None:
        """현재 Step(main)과 stage(sub)의 first-tick/on_tick을 순서대로 호출한다."""
        self._tick_main_enter()
        self._tick_main(ctx)
        self.substage.tick(ctx)

    def _item_identity_key(self, item: ConversationItemLike) -> Any:
        """아이템이 바뀌었는지 판별하는 키. 기본은 None(항상 동일 아이템으로 간주)."""
        _ = item
        return None

    def _reset_step_on_item_change(self, item: ConversationItemLike) -> None:
        """아이템이 바뀌었을 때 호출. substage·전환 플래그를 초기화한다."""
        _ = item
        self._restart_main_stage()
        self.transition_bg_frame = None
        self.transition_signal = False

    def sync_item_identity(self, item: ConversationItemLike) -> bool:
        """`_item_identity_key` 기준으로 아이템이 바뀌었으면 `_reset_step_on_item_change` 후 True."""
        key = self._item_identity_key(item)
        if key == self._active_item_key:
            return False
        self._active_item_key = key
        self._reset_step_on_item_change(item)
        return True

    def _set_stage(self, stage: Any) -> None:
        """stage 전환. `transition_to`에서 떠나는 stage의 `bind_end`를 호출한 뒤 상태를 갱신한다."""
        self.substage.transition_to(stage)

    @property
    def _stage(self) -> Any:
        """현재 substage 키(문자열). 하위·디버깅 호환용."""
        return self.substage.current_stage
