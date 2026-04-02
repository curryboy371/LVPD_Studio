"""Substage sequence: timer, enter callbacks, and transitions."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from ..core.types import FrameContext


def normalize_stage_key(stage: Any) -> str:
    """Enum/str 등 서로 다른 stage 표현을 콜백 딕셔너리 조회용 키로 통일한다."""
    if isinstance(stage, Enum):
        return str(stage.value)
    return str(stage)


class StageSequenceEngine:
    """시퀀스 기반 substage 상태, 타이머, 진입/종료/틱/만료 콜백."""

    def __init__(self) -> None:
        self._sequence: list[str] = []
        self._index_map: dict[str, int] = {}
        self._stage: str | None = None
        self._stage_entered: bool = False
        self._remain_sec: float | None = None
        self._on_enter: dict[str, Callable[[], None]] = {}
        self._on_end: dict[str, Callable[[], None]] = {}
        self._on_tick: dict[str, Callable[[FrameContext], None]] = {}
        self._on_remain_expired: dict[str, Callable[[], None]] = {}
        # remain 만료 후 시퀀스 기본 진행(다음 stage). BaseStep이 _set_stage/on_stage_end와 연결한다.
        self._default_advance: Callable[[], bool] | None = None

    @staticmethod
    def normalize_key(stage: Any) -> str:
        return normalize_stage_key(stage)

    @property
    def current_stage(self) -> str | None:
        return self._stage

    @property
    def stage_entered(self) -> bool:
        return self._stage_entered

    @property
    def substage_remain_sec(self) -> float | None:
        return self._remain_sec

    @property
    def sequence(self) -> list[str]:
        return list(self._sequence)

    @property
    def index_map(self) -> dict[str, int]:
        return dict(self._index_map)

    def clear_callbacks(self) -> None:
        self._on_enter.clear()
        self._on_end.clear()
        self._on_tick.clear()
        self._on_remain_expired.clear()

    def configure(
        self,
        stages: list[str] | tuple[str, ...],
        *,
        initial: Any | None = None,
    ) -> None:
        seq = [self.normalize_key(s) for s in stages]
        if not seq:
            raise ValueError("stages must not be empty")
        initial_key = seq[0] if initial is None else self.normalize_key(initial)
        if initial_key not in seq:
            raise ValueError("initial stage must be included in stages")
        self._sequence = seq
        self._index_map = {name: idx for idx, name in enumerate(seq)}
        self.clear_callbacks()
        self._init_state(initial_key)

    def bind_enter(self, stage: Any, fn: Callable[[], None]) -> None:
        self._on_enter[self.normalize_key(stage)] = fn

    def bind_end(self, stage: Any, fn: Callable[[], None]) -> None:
        self._on_end[self.normalize_key(stage)] = fn

    def bind_tick(self, stage: Any, fn: Callable[[FrameContext], None]) -> None:
        self._on_tick[self.normalize_key(stage)] = fn

    def bind_remain_expired(self, stage: Any, fn: Callable[[], None]) -> None:
        self._on_remain_expired[self.normalize_key(stage)] = fn

    def set_default_advance(self, fn: Callable[[], bool] | None) -> None:
        """remain 만료 시 커스텀 핸들러가 없을 때 호출. True면 진행됨."""
        self._default_advance = fn

    def set_timer(self, sec: float) -> None:
        """현재 substage 남은 시간(초). 0 이하면 다음 remain 틱에서 즉시 만료 처리."""
        self._remain_sec = float(sec)

    def _init_state(self, stage: Any) -> None:
        self._stage = self.normalize_key(stage)
        self._stage_entered = True
        self._remain_sec = None

    def transition_to(self, stage: Any) -> Any | None:
        """전환이 일어나면 이전 stage 값(키 문자열), 같으면 None.

        순서: (1) 이전 stage의 `bind_end` 콜백 (2) 새 stage로 상태 커밋.
        BaseStep은 이어서 `on_stage_end(이전)`를 호출하므로, 자식에서는 보통
        UI는 `on_stage_end`만, 엔진 등록형 정리는 `bind_end`만 쓰는 편이 낫다.
        """
        next_key = self.normalize_key(stage)
        prev_raw = self._stage
        prev_key = self.normalize_key(prev_raw) if prev_raw is not None else None
        if prev_key == next_key:
            return None
        if prev_key is not None and prev_key in self._on_end:
            try:
                self._on_end[prev_key]()
            except Exception:
                pass
        prev_for_hook = prev_raw
        self._stage = next_key
        self._stage_entered = True
        self._remain_sec = None
        return prev_for_hook

    def goto_stage(self, stage: Any) -> Any | None:
        return self.transition_to(stage)

    def _goto_next_stage_internal(self) -> bool:
        if self._stage is None or self._stage not in self._index_map:
            return False
        idx = self._index_map[self._stage]
        next_idx = idx + 1
        if next_idx >= len(self._sequence):
            return False
        self.transition_to(self._sequence[next_idx])
        return True

    def goto_next_stage(self) -> bool:
        """엔진 단독 사용 시. BaseStep에서는 `set_default_advance`로 위임하는 것이 안전하다."""
        return self._goto_next_stage_internal()

    def _apply_remain_expired(self) -> None:
        key = self._stage or ""
        if key in self._on_remain_expired:
            try:
                self._on_remain_expired[key]()
            except Exception:
                pass
            return
        if self._default_advance is not None:
            try:
                self._default_advance()
            except Exception:
                pass
            return
        self._goto_next_stage_internal()

    def tick_remain(self, ctx: FrameContext) -> None:
        if self._remain_sec is None:
            return
        rem = self._remain_sec
        if rem <= 0.0:
            self._remain_sec = None
            self._apply_remain_expired()
            return
        dt = float(ctx.dt_sec)
        self._remain_sec = rem - dt
        if self._remain_sec <= 0.0:
            self._remain_sec = None
            self._apply_remain_expired()

    def tick_enter(
        self,
        *,
        on_fallback: Callable[[Any], None] | None = None,
    ) -> None:
        if not self._stage_entered:
            return
        self._stage_entered = False
        key = self._stage or ""
        if key in self._on_enter:
            try:
                self._on_enter[key]()
            except Exception:
                pass
            return
        if on_fallback is not None:
            try:
                on_fallback(self._stage)
            except Exception:
                pass

    def tick_stage_tick(
        self,
        ctx: FrameContext,
        *,
        on_fallback: Callable[[Any, FrameContext], None] | None = None,
    ) -> None:
        stage = self._stage
        key = stage or ""
        if key in self._on_tick:
            try:
                self._on_tick[key](ctx)
            except Exception:
                pass
            return
        if on_fallback is not None:
            try:
                on_fallback(stage, ctx)
            except Exception:
                pass

    def tick(
        self,
        ctx: FrameContext,
        *,
        on_stage_first_tick_fallback: Callable[[Any], None] | None = None,
        on_stage_tick_fallback: Callable[[Any, FrameContext], None] | None = None,
    ) -> None:
        self.tick_enter(on_fallback=on_stage_first_tick_fallback)
        self.tick_stage_tick(ctx, on_fallback=on_stage_tick_fallback)
        self.tick_remain(ctx)
