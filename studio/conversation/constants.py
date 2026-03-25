"""회화 스튜디오 공통 상수.

이번 리팩터링(render_only) 이후에는 데이터 로딩에서 쓰는 `_REPO_ROOT`만 남긴다.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
