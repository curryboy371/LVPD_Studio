"""회화 스튜디오 공통 상수·열거형."""
from enum import IntEnum
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# 품사별 단어 카드 색상 (배경, 전경). draw에서 공통 사용.
_POS_COLORS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "명사":   ((30, 60, 110),  (120, 170, 255)),
    "동사":   ((80, 30, 30),   (255, 110, 110)),
    "형용사": ((30, 80, 50),   (100, 220, 140)),
    "부사":   ((70, 50, 10),   (240, 190,  60)),
    "조사":   ((60, 30, 80),   (190, 120, 240)),
    "감탄사": ((10, 70, 70),   ( 80, 210, 210)),
    "수사":   ((60, 55, 10),   (220, 200,  60)),
    "양사":   ((20, 60, 60),   ( 80, 200, 200)),
    "대명사": ((60, 35, 10),   (240, 150,  60)),
    "접속사": ((40, 20, 60),   (180,  90, 220)),
    "전치사": ((10, 50, 60),   ( 60, 180, 210)),
}
_DEFAULT_CARD_BG = (40, 44, 60)
_DEFAULT_CARD_FG = (200, 200, 200)


class ShadowingStep(IntEnum):
    """쉐도잉 훈련 단계. 그리기/업데이트 분기용."""

    LISTEN = 1  # Step 1: 원어민 속도로 듣기, 멈추면 병음/한자/해석 UI
    UTIL = 2    # Step 2: 문장 활용 (슬롯 변형 문장)


class Step1SoundState(IntEnum):
    """Step 1 일시정지 시 L1→L2 사운드 재생 상태."""

    Idle = 0
    PlayingL1 = 1
    PlayingL2 = 2


# Step 2 슬롯 머신형 롤링 UI
STEP2_SLOT_BLOCK_HEIGHT = 112   # 한 문장 블록 높이 (한자+병음+번역+간격)
STEP2_SLOT_BLOCK_GAP = 24       # 블록 간 세로 간격
STEP2_SLOT_CENTER_RATIO = 0.42  # 중앙 줄 y = h * this
STEP2_SLOT_ALPHA_PREV = 100     # 이전 문장 alpha (흐릿하게)
STEP2_SLOT_ALPHA_NEXT = 150     # 다음 문장 alpha (대기 중)
