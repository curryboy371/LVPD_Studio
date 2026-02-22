"""
기본 경로: env 없이 통일된 기본 경로 사용.
"""
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# CSV·출력 기본 경로 (env 미사용). 비디오/사운드는 테이블에 resource/... 경로로 저장됨 → get_repo_root() 기준 해석
_RESOURCE_CSV_DIR = _REPO_ROOT / "resource" / "csv"
_RESOURCE_TABLE_DIR = _REPO_ROOT / "resource" / "table"  # 엑셀 원본
DEFAULT_CSV_PATH = _RESOURCE_CSV_DIR / "video_data.csv"
DEFAULT_EXCEL_PATH = _RESOURCE_TABLE_DIR / "video_data.xlsx"  # 실행 시 항상 여기서 CSV 생성
DEFAULT_OUTPUT_DIR = _REPO_ROOT / "output"

# 폰트: resource/font 하위 (중국어·한국어 각각)
DEFAULT_FONT_DIR = _REPO_ROOT / "resource" / "font"
FONT_CN_FILENAME = "MaruBuri-Light.otf"   # 중국어(문장·병음)용
FONT_KR_FILENAME = "NotoSansKR-Regular.ttf"    # 한국어(번역·UI)용

# 스튜디오: 해상도·FPS (창/녹화 공통)
STUDIO_WIDTH = 1920
STUDIO_HEIGHT = 1080
STUDIO_FPS = 30
STUDIO_VIDEO_FALLBACK_FPS = 25.0  # 비디오에서 FPS 못 읽을 때 기본값

# 배치 렌더(FFmpeg) 기본 해상도·FPS
RENDER_WIDTH = 1280
RENDER_HEIGHT = 720
RENDER_FPS = 24

# FFmpeg 실행 파일 (env 미사용)
FFMPEG_CMD = "ffmpeg"


def get_repo_root() -> Path:
    return _REPO_ROOT
