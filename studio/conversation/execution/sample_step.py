"""BaseStep + StageSequenceEngine 사용법 **교육용** 샘플.

이 파일은 런타임에서 꼭 import할 필요가 없고, 복사·참고용 템플릿이다.
실제 대화 스튜디오에 붙이려면 `PlaybackManager` / `ConversationStudio` 쪽 Step
등록 절차를 따르면 된다.

---------------------------------------------------------------------------
[개념] 한 Step 안에 “substage” 시퀀스가 있다
---------------------------------------------------------------------------
- `configure_stages(...)`: 이 Step이 거칠 **이름 있는 단계들의 순서**를 등록한다.
- 각 단계가 시작되면 `bind_enter`로 등록한 콜백이 **첫 프레임에 한 번** 호출된다.
- `set_timer(sec)`: 현재 substage에서 **남은 시간**을 초 단위로 설정한다. 매 프레임
  줄어들다가 0이 되면 “remain 만료” 처리가 된다.
- remain 만료 시:
  - 해당 stage에 `bind_remain_expired`가 있으면 **그것만** 실행하고 끝.
  - 없으면 기본 동작: 시퀀스에서 **다음 substage**로 이동한다.
  - `finish_step_on_last_remain_expired=True`이고 **마지막 substage**에서
    만료되면, `bind_remain_expired`가 없을 때 `_end_main_stage()`가 호출된다
    → 보통 `on_main_end`에서 `transition_signal = True` 등으로 **다음 Step**으로 넘긴다.

---------------------------------------------------------------------------
[프레임 순서] update 한 번에 일어나는 일(요약)
---------------------------------------------------------------------------
1. (선택) `sync_item_identity(item)` — 아이템이 바뀌었는지 검사 후 리셋
2. drawer 페이드 등 부가 틱
3. `_tick_stage(ctx)` — 메인 틱 + substage 틱(진입 콜백 → 매 프레임 tick → remain)

---------------------------------------------------------------------------
[스테이지를 떠날 때] bind_end vs on_stage_end
---------------------------------------------------------------------------
- 엔진 `transition_to`: **먼저** 떠나는 stage의 `bind_end`, **그다음** 새 stage로 상태 갱신.
- BaseStep: 그 후 `on_stage_end(이전 stage)` 훅 호출.
- 정리: **bind_end → (상태 변경) → on_stage_end**. UI 전환은 보통 `on_stage_end`만 써도 된다.

---------------------------------------------------------------------------
[아이템 동기화] 대화 아이템이 바뀔 때 시나리오를 처음부터
---------------------------------------------------------------------------
- `_item_identity_key(item)`을 오버라이드해 “같은 아이템인지” 판별 키를 반환한다.
- 키가 바뀌면 `_reset_step_on_item_change`가 호출된다(기본: main 종료 플래그·전환 프레임 리셋).
- 학습 Step처럼 TITLE으로 돌아가야 하면 여기서 `_goto_stage(Stage.XXX)`를 호출한다.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import pygame

from ..core.types import ConversationItemLike, FrameContext
from .base import BaseStep


class SampleStep(BaseStep):
    """아주 단순한 3단계 시나리오 예시: 인트로 → 본문 대기 → 아웃트로 대기 후 Step 종료.

    시퀀스(순서가 곧 스토리):
      INTRO   : 짧은 타이머만 돌린 뒤 자동으로 다음으로
      CONTENT : 사용자에게 볼 시간을 줌 (`set_timer`)
      OUTRO   : 마지막 대기 후 `finish_step_on_last_remain_expired`로 Step 종료
    """

    class Stage(str, Enum):
        INTRO = "sample_intro"
        CONTENT = "sample_content"
        OUTRO = "sample_outro"

    STAGE_SEQUENCE = (Stage.INTRO, Stage.CONTENT, Stage.OUTRO)

    def __init__(self, *, drawer: Any, video_player: Any) -> None:
        super().__init__(drawer=drawer, video_player=video_player)

        # -----------------------------------------------------------------
        # 1) 시퀀스 등록
        #    - 내부적으로 substage 엔진이 비어 있던 콜백 딕셔너리를 비우고
        #      `register_main_stage_callbacks` → `register_stage_callbacks` 순으로 호출한다.
        #    - initial 을 생략하면 시퀀스의 **첫 번째**가 시작 stage가 된다.
        #    - finish_step_on_last_remain_expired:
        #        마지막 substage(여기서는 OUTRO)에서 remain 이 끝나면
        #        별도의 bind_remain_expired 없이도 _end_main_stage() → on_main_end 로 이어진다.
        # -----------------------------------------------------------------
        self.configure_stages(
            self.STAGE_SEQUENCE,
            # initial=self.Stage.CONTENT,  # 필요하면 시작 지점만 바꿀 수 있음
            finish_step_on_last_remain_expired=True,
        )

        # 샘플용 상태 (실제 Step에서는 스타일·문자열 등을 둔다)
        self._label: str = "Sample"

    # -------------------------------------------------------------------------
    # 2) 시나리오 “등록” — 이 메서드만 읽어도 흐름이 보이게 쓰는 것이 목표
    # -------------------------------------------------------------------------
    def register_stage_callbacks(self) -> None:
        """configure_stages() 직후 자동으로 한 번 호출된다. 여기서 bind_* 를 채운다."""

        S = self.Stage

        # [bind_enter] 해당 substage에 **처음 들어온 프레임**에 딱 한 번 실행.
        # 보통 여기서 set_timer 로 “이 단계에서 얼마나 머물지”를 연다.
        self.bind_enter(
            S.INTRO,
            lambda: self.set_timer(0.8),  # 0.8초 후 remain 만료 → 기본으로 다음 substage
        )

        self.bind_enter(
            S.CONTENT,
            lambda: self.set_timer(2.0),  # 본문 2초 대기
        )

        self.bind_enter(
            S.OUTRO,
            lambda: self.set_timer(1.0),  # 마지막 1초. 끝나면 _end_main_stage (위 옵션 덕분)
        )

        # [bind_remain_expired] — 특정 stage에서 타이머가 끝났을 때 **커스텀**하고 싶을 때.
        # 예: INTRO에서만 로그를 남기고 다음으로 넘기고 싶다면 (주석 해제):
        # self.bind_remain_expired(
        #     S.INTRO,
        #     lambda: print("intro done") or self._goto_next_substage()  # 직접 다음으로
        # )
        #
        # 등록하지 않으면 기본값: 다음 substage로 자동 진행(마지막이면 finish 옵션에 따라 종료).

        # [bind_end] — 이 substage를 **떠날 때** (다음으로 전환되기 직전, 엔진 내부).
        # on_stage_end 보다 먼저 호출된다. 리소스 해제·카운터 집계 등에 쓸 수 있다.
        # self.bind_end(S.INTRO, lambda: print("leave intro"))

        # [bind_tick] — 매 프레임마다 (대부분의 Step은 enter + timer 만으로 충분해서 안 씀).
        # self.bind_tick(S.CONTENT, lambda ctx: None)

    # -------------------------------------------------------------------------
    # 3) 스테이지 전환 시 UI 부수효과 — “그림”은 여기/ render 에 맡기기 쉽다
    # -------------------------------------------------------------------------
    def on_stage_end(self, stage: Any) -> None:
        """substage를 떠날 때 호출. stage 인자는 떠나는 쪽(이전)의 키/Enum 값."""

        # StrEnum 이면 문자열과 비교해도 됨: self.Stage.INTRO == "sample_intro"
        if stage == self.Stage.INTRO:
            # 예: 인트로 끝나면 문장 채널 페이드 온 등 (실제로는 drawer 사용)
            pass

    def on_main_end(self) -> None:
        """_end_main_stage() 가 불리면 최종적으로 한 번 호출됨.

        다음 Step으로 넘어가도 될 때 PlaybackManager 가 `transition_signal` 을 본다.
        """
        # 학습 Step과 같이 배경 프레임을 넘기고 싶으면 bg_frame 복사 등을 여기서.
        self.transition_signal = True

    # -------------------------------------------------------------------------
    # 4) 아이템이 바뀔 때 — 대화 한 줄이 바뀌면 시나리오를 처음부터
    # -------------------------------------------------------------------------
    def _item_identity_key(self, item: ConversationItemLike) -> Any:
        """같은 아이템이면 같은 키를 반환. 바뀌면 sync_item_identity 가 리셋한다."""

        return str(item.get("id") or "")

    def _reset_step_on_item_change(self, item: ConversationItemLike) -> None:
        """아이템 변경 시: 공통 리셋 후, 시작 substage 로 되돌린다."""

        super()._reset_step_on_item_change(item)
        self._goto_stage(self.Stage.INTRO)

    # -------------------------------------------------------------------------
    # 5) 매 프레임
    # -------------------------------------------------------------------------
    def update(self, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        # 아이템 변경 감지(키가 같으면 아무 것도 안 함)
        self.sync_item_identity(item)

        # drawer 페이드가 있다면 매 프레임 진행 (LearningStep 과 동일 패턴)
        if hasattr(self.drawer, "fade_tick"):
            self.drawer.fade_tick(float(ctx.dt_sec))

        # substage + 메인 틱 (필수)
        self._tick_stage(ctx)

    def render(self, screen: pygame.Surface, ctx: FrameContext, *, item: ConversationItemLike) -> None:
        """화면에 그리기. substage 와 무관하게 매 프레임 호출된다."""

        frame = self.bg_frame or self.video_player.get_frame(ctx.width, ctx.height)
        if frame is not None:
            screen.blit(frame, (0, 0))

        # 디버그: 현재 substage 이름을 겹쳐 그리기 (실제 서비스에서는 제거)
        try:
            font = pygame.font.Font(None, 28)
            stage_name = str(self.substage.current_stage or "?")
            surf = font.render(f"{self._label} | {stage_name}", True, (255, 255, 0))
            screen.blit(surf, (16, 16))
        except Exception:
            pass

        _ = item
