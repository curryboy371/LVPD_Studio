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
DEFAULT_SHORTS_CONVERSATION_CLIPS_EXCEL = _RESOURCE_TABLE_DIR / "shorts_conversation_clips.xlsx"
DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV = _RESOURCE_CSV_DIR / "shorts_conversation_clips.csv"
DEFAULT_SHORTS_VOCABULARY_CLIPS_EXCEL = _RESOURCE_TABLE_DIR / "shorts_vocabulary_clips.xlsx"
DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV = _RESOURCE_CSV_DIR / "shorts_vocabulary_clips.csv"
DEFAULT_KO_NARRATION_SETS_EXCEL = _RESOURCE_TABLE_DIR / "ko_narration_sets.xlsx"
DEFAULT_KO_NARRATION_SETS_CSV = _RESOURCE_CSV_DIR / "ko_narration_sets.csv"
DEFAULT_KO_NARRATION_LINES_EXCEL = _RESOURCE_TABLE_DIR / "ko_narration_lines.xlsx"
DEFAULT_KO_NARRATION_LINES_CSV = _RESOURCE_CSV_DIR / "ko_narration_lines.csv"
# 숏츠 한국어 TTS 배치(batch_ko_tts) 산출 mp3·timeline JSON
DEFAULT_KO_NARRATION_SOUND_DIR = _REPO_ROOT / "resource" / "sound" / "shorts"
LEGACY_KO_NARRATION_SOUND_DIR = _REPO_ROOT / "resource" / "sound"
# 회화 PRACTICE sub_sentences.alt_translation TTS (batch_tts 모드 1)
CONVERSATION_SUB_KO_SOUND_DIR = _REPO_ROOT / "resource" / "sound" / "sentense"

DEFAULT_OUTPUT_DIR = _REPO_ROOT / "output"

# 폰트: resource/font 하위 (중국어·한국어 각각)
DEFAULT_FONT_DIR = _REPO_ROOT / "resource" / "font"

# 성조 비교 아이콘 PNG (병음 줄 위)
DEFAULT_TONE_ICON_DIR = _REPO_ROOT / "resource" / "image" / "icon"
FONT_CN_FILENAME = "MaruBuri-Light.otf"   # 중국어(문장·병음)용
FONT_KR_FILENAME = "NotoSansKR-Regular.ttf"    # 한국어(번역·UI)용
# situation_subtitle 등 한글+한자 혼합 (Noto Sans CJK KR 권장)
FONT_SITUATION_FILENAMES = (
    "NotoSansCJKkr-Regular.otf",
    "NotoSansCJKkr-Regular.ttf",
    "NotoSansCJK-Regular.otf",
    "SourceHanSansKR-Regular.otf",
    "SourceHanSansK-Regular.otf",
    # repo에 실제 있는 한·중 혼합 대체 (위 CJK KR 없을 때)
    "SourceHanSansSC-Regular.otf",
    "NotoSerifSC-Regular.ttf",
)
# 숏츠 단어 tip: 한자 커버 우선 (간체 SC)
FONT_TIP_CN_FILENAMES = (
    "SourceHanSansSC-Regular.otf",
    "SourceHanSansSC-Normal.otf",
    "NotoSerifSC-Regular.ttf",
    "NotoSerifSC-Medium.ttf",
)

# 스튜디오 CLI / record_output_select_mode.bat combo에서 topic 생략·엔터 시 기본값과 동일하게 유지
DEFAULT_STUDIO_TOPIC = "fruit_store"

# 스튜디오: 해상도·FPS (창/녹화 공통)
STUDIO_WIDTH = 1920
STUDIO_HEIGHT = 1080
# 숏츠 스튜디오: 세로 9:16
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
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

# 회화 연습 주황 게이지 배경음 선형 볼륨(1.0=원본). pygame 재생과 녹화 mux에 동일 적용.
STUDIO_PRACTICE_BG_AUDIO_LINEAR_GAIN = 0.2

# utils/video_audio_extract: 비디오→동명 MP3 시 libmp3lame -q:a (0=최고 VBR)
STUDIO_VIDEO_EXTRACT_MP3_LAME_Q = 0


def get_repo_root() -> Path:
    return _REPO_ROOT


def conversation_sub_ko_mp3_path(sub_sentence_id: int) -> Path:
    """회화 sub 문장 한국어 번역 TTS: ko_sub_{id}.mp3"""
    return CONVERSATION_SUB_KO_SOUND_DIR / f"ko_sub_{int(sub_sentence_id)}.mp3"
