"""
녹화 타임라인용 오디오 이벤트 정의.
record 모드에서 스튜디오가 재생/일시정지/seek/삽입 사운드를 이벤트로 기록하고,
녹화 종료 후 이벤트 로그로 오디오 트랙을 생성해 비디오와 mux할 때 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Union


@dataclass(frozen=True)
class VideoSegmentStart:
    """녹화 타임라인 상 이 시점부터 해당 비디오 오디오 재생 시작."""
    timeline_sec: float
    video_path: str
    video_pts_sec: float


@dataclass(frozen=True)
class VideoSegmentEnd:
    """녹화 타임라인 상 이 시점에서 비디오 오디오 재생 중단 (일시정지/구간 전환/seek)."""
    timeline_sec: float


@dataclass(frozen=True)
class InsertSound:
    """녹화 타임라인 상 해당 시점에 삽입 사운드(나레이션·효과음) 재생."""
    timeline_sec: float
    path: str
    duration_sec: float


RecordingEvent = Union[VideoSegmentStart, VideoSegmentEnd, InsertSound]


def recording_log_event(
    log: Optional[Callable[[RecordingEvent], None]],
    event: RecordingEvent,
) -> None:
    """config.recording_log_event가 있으면 이벤트를 기록. 없으면 무시."""
    if log is not None:
        try:
            log(event)
        except Exception:
            pass


def is_recording(config: Any) -> bool:
    """config에 녹화용 콜백이 붙어 있으면 True."""
    return getattr(config, "recording_log_event", None) is not None
