"""
렌더링 추상 인터페이스.
비디오 렌더러와 오디오 믹서의 계약을 정의하여 DI(의존성 주입)로 구현체를 교체할 수 있게 한다.

스튜디오 러너 연동용 IStudio 인터페이스: 창·이벤트·업데이트·그리기·녹화 접두사.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

import numpy as np


class IStudio(ABC):
    """스튜디오 종류별 구현의 계약. 러너가 창 생성·루프·녹화를 담당하고, 데이터/이벤트/그리기는 구현체가 담당."""

    def init(self, config: Any = None) -> None:
        """pygame.init() 이후 한 번 호출. 폰트·리소스 로드 등 초기화. 기본은 no-op."""
        pass

    @abstractmethod
    def get_title(self) -> str:
        """창 제목용 (예: 'LVPD Studio - 회화', 'LVPD Studio - 단어장')."""
        ...

    @abstractmethod
    def handle_events(self, events: list, config: Any = None) -> bool:
        """pygame 이벤트 리스트 처리. False 반환 시 러너가 루프 종료. config는 녹화 시 recording_time_sec 등 전달용."""
        ...

    def update(self, config: Any = None) -> None:
        """매 프레임 업데이트. config에 dt_sec, actual_fps 등 디버그용 값이 전달될 수 있음."""
        ...

    @abstractmethod
    def draw(self, screen: Any, config: Any) -> None:
        """화면에 그리기. screen은 pygame.Surface, config는 해상도/좌표 등 제공 객체."""
        ...

    @abstractmethod
    def get_recording_prefix(self) -> Optional[str]:
        """녹화 시작 시 파일명 접두사 (예: REC_1). 녹화 안 쓰면 None."""
        ...

    def set_recording_request_callback(
        self, callback: Optional[Callable[[bool], None]]
    ) -> None:
        """R 키 등으로 녹화 시작/중지 요청 시 러너가 주입한 콜백. 기본 구현은 무시."""
        pass

    def should_stop_recording(self) -> bool:
        """record 모드에서 콘텐츠 재생이 끝났을 때 True면 러너가 루프를 종료한다. 기본 False."""
        return False


class IVideoRenderer(ABC):
    """비디오/프레임 렌더링을 담당하는 추상 인터페이스."""

    @abstractmethod
    def render_frame(
        self,
        timestamp_sec: float,
        width: int = 1280,
        height: int = 720,
        **kwargs: Any,
    ) -> np.ndarray:
        """주어진 시점의 한 프레임을 렌더링하여 픽셀 배열로 반환한다.

        Args:
            timestamp_sec: 렌더링할 시점(초).
            width: 프레임 너비(픽셀).
            height: 프레임 높이(픽셀).
            **kwargs: 구현체별 추가 옵션(텍스트, 이미지 경로 등).

        Returns:
            RGB 형태의 numpy 배열 (height, width, 3), dtype uint8.
        """
        ...


class BaseRenderer(IVideoRenderer, ABC):
    """세그먼트·오버레이를 결합해 프레임을 만드는 렌더러의 추상 기본 클래스. IVideoRenderer를 구현한다."""

    def render_frame(
        self,
        timestamp_sec: float,
        width: int = 1280,
        height: int = 720,
        **kwargs: Any,
    ) -> np.ndarray:
        """kwargs에 segment, overlay가 있으면 render_segment_overlay를 호출하고, 없으면 검정 프레임을 반환한다."""
        segment = kwargs.get("segment")
        overlay = kwargs.get("overlay")
        if segment is not None and overlay is not None:
            return self.render_segment_overlay(
                segment, overlay, timestamp_sec, width, height
            )
        # segment/overlay 없으면 검정 프레임 반환 (의존성 없이 core만으로 처리)
        return np.zeros((height, width, 3), dtype=np.uint8)

    @abstractmethod
    def render_segment_overlay(
        self,
        segment: Any,
        overlay: Any,
        timestamp_sec: float,
        width: int,
        height: int,
    ) -> np.ndarray:
        """세그먼트 영상과 오버레이를 결합한 한 프레임을 반환한다. 하위 클래스에서 구현.

        Args:
            segment: 영상 구간 정보(VideoSegment 등). core는 data를 import하지 않으므로 Any.
            overlay: 오버레이 정보(OverlayItem 등). Any.
            timestamp_sec: 추출할 시점(초).
            width: 프레임 너비(픽셀).
            height: 프레임 높이(픽셀).

        Returns:
            RGB numpy 배열 (height, width, 3), dtype uint8.
        """
        ...


class IAudioMixer(ABC):
    """오디오 믹싱을 담당하는 추상 인터페이스."""

    @abstractmethod
    def mix(
        self,
        sound_paths: list[str],
        start_time_sec: float,
        end_time_sec: float,
        **kwargs: Any,
    ) -> bytes | str:
        """여러 사운드 소스를 지정 구간으로 믹싱한다.

        Args:
            sound_paths: 사운드 파일 경로 목록.
            start_time_sec: 출력 구간 시작 시점(초).
            end_time_sec: 출력 구간 종료 시점(초).
            **kwargs: 구현체별 추가 옵션(샘플레이트, 채널 등).

        Returns:
            믹싱된 오디오 데이터(bytes) 또는 출력 파일 경로(str).
        """
        ...
