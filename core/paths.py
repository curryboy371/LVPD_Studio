"""
기본 경로: env 없이 통일된 기본 경로 사용.
"""
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# CSV·출력 기본 경로 (env 미사용). 비디오/사운드는 테이블에 resource/... 경로로 저장됨 → get_repo_root() 기준 해석
_RESOURCE_CSV_DIR = _REPO_ROOT / "resource" / "csv"
_RESOURCE_TABLE_DIR = _REPO_ROOT / "resource" / "table"  # 엑셀 원본

# 신규 테이블 (base_sentences / words / sub_sentences)
DEFAULT_BASE_SENTENCES_EXCEL = _RESOURCE_TABLE_DIR / "base_sentences.xlsx"
DEFAULT_BASE_SENTENCES_CSV = _RESOURCE_CSV_DIR / "base_sentences.csv"
DEFAULT_WORDS_TABLE_EXCEL = _RESOURCE_TABLE_DIR / "words.xlsx"
DEFAULT_WORDS_TABLE_CSV = _RESOURCE_CSV_DIR / "words.csv"
DEFAULT_SUB_SENTENCES_EXCEL = _RESOURCE_TABLE_DIR / "sub_sentences.xlsx"
DEFAULT_SUB_SENTENCES_CSV = _RESOURCE_CSV_DIR / "sub_sentences.csv"
DEFAULT_VOCABULARY_WORD_ROWS_EXCEL = _RESOURCE_TABLE_DIR / "vocabulary_word_rows.xlsx"
DEFAULT_VOCABULARY_WORD_ROWS_CSV = _RESOURCE_CSV_DIR / "vocabulary_word_rows.csv"

DEFAULT_OUTPUT_DIR = _REPO_ROOT / "output"

# 폰트: resource/font 하위 (중국어·한국어 각각)
DEFAULT_FONT_DIR = _REPO_ROOT / "resource" / "font"

# 성조 비교 아이콘 PNG (병음 줄 위)
DEFAULT_TONE_ICON_DIR = _REPO_ROOT / "resource" / "image" / "icon"
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

# pygame mixer·비디오 장면 사이드카 MP3→WAV·녹화 mux 무음 베이스와 동일(48k)으로 맞춰 이중 리샘플을 줄인다.
STUDIO_AUDIO_SAMPLE_RATE = 48000

# 녹화본에 붙는 최종 AAC(이중 인코딩 시 여유를 두려면 256k 권장)
STUDIO_MUX_AUDIO_BITRATE = "256k"

# 녹화 mux: MP4 등 내장 오디오만 선형 게인(1.0=유지). 동명 MP3·삽입음은 게인 없음(디버그 재생 레벨과 맞춤).
STUDIO_MUX_EMBEDDED_AUDIO_LINEAR_GAIN = 0.5

# utils/video_audio_extract: 비디오→동명 MP3 시 libmp3lame -q:a (0=최고 VBR)
STUDIO_VIDEO_EXTRACT_MP3_LAME_Q = 0


def get_repo_root() -> Path:
    return _REPO_ROOT
