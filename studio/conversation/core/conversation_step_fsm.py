"""ConversationStep 내부 Stage(FSM) — SceneKind·장면 전환 연출과 별개.

`FSMConversationStep` / `StageConfig` 는 한 SceneKind 슬롯 안의 로컬 상태만 다룬다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .types import ConversationItemLike, FrameContext
from .conversation_step import IConversationStep


@dataclass
class StageConfig:
    """한 ConversationStep 안에서만 쓰는 FSM Stage 정의(SceneKind 전환과 별개)."""
    on_enter: Optional[Callable[[], float]] = None
    on_update: Optional[Callable[[float], None]] = None
    on_exit: Optional[Callable[[], None]] = None
    next_stage: Optional[Any] = None
    transition_condition: Optional[Callable[[], bool]] = None


class FSMConversationStep(IConversationStep):
    """IConversationStep 이지만 내부 로직을 Stage(FSM)로 나눈 베이스.

    `Stage` / `StageConfig` 는 SceneKind(장면 종류) 전환과 별개로, 한 화면 안의 상태만 다룬다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.stage = None
        self.stage_table: dict[Any, StageConfig] = {}
        self.timer: float = 0.0

    # ------------------------
    # Stage Control
    # ------------------------
    def set_stage(self, stage: Any) -> None:
        """내부 Stage 전환 (exit → enter)."""
        if stage not in self.stage_table:
            raise KeyError(f"Stage {stage} not defined")

        # exit
        if self.stage is not None:
            prev = self.stage_table[self.stage]
            if prev.on_exit:
                prev.on_exit()

        # enter
        self.stage = stage
        config = self.stage_table[stage]

        if config.on_enter:
            self.timer = config.on_enter()
        else:
            self.timer = 0.0

    # ------------------------
    # Update (FSM Core)
    # ------------------------
    def on_update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        dt = float(ctx.dt_sec)
        config = self.stage_table[self.stage]

        # 1. 상태 업데이트
        if config.on_update:
            config.on_update(dt)

        # 2. 타이머 기반 상태만 감소
        if not config.transition_condition:
            self.timer -= dt

        # 3. 전이 조건 판단
        should_transition = False

        if config.transition_condition:
            should_transition = config.transition_condition()
        elif self.timer <= 0:
            should_transition = True

        # 4. 전이
        if should_transition and config.next_stage is not None:
            self.set_stage(config.next_stage)
