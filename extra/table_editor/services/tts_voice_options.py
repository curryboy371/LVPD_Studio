"""TTS 목소리 목록·미리듣기 샘플 문장·실행 옵션."""
from __future__ import annotations

from dataclasses import dataclass

GENERATE_LABEL = "생성"
SKIP_LABEL = "건너뛰기"
TYPE_CHOICES = (GENERATE_LABEL, SKIP_LABEL)

KO_EDGE_VOICES = (
    "ko-KR-SunHiNeural",
    "ko-KR-InJoonNeural",
    "ko-KR-HyunsuNeural",
)
ZH_EDGE_VOICES = (
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-YunyangNeural",
)
DEFAULT_EN_TTS_VOICE = "en-US-GuyNeural"
EN_EDGE_VOICES = (
    DEFAULT_EN_TTS_VOICE,
    "en-US-JennyNeural",
    "en-US-AriaNeural",
)

PREVIEW_SAMPLE_KO = "월요일"
PREVIEW_SAMPLE_ZH = "星期一"
PREVIEW_SAMPLE_EN = "Monday"

# kind → (한국어 행 라벨, 중국어, 영어) / zh·en 생성 지원 여부
KIND_LANG_META: dict[str, tuple[tuple[str, str, str], bool]] = {
    "conv": (("한국어 (번역)", "중국어", "영어"), False),
    "vocab": (("한국어 (뜻)", "중국어", "영어"), False),
    "shorts_conv": (("한국어 (내레이션)", "중국어", "영어"), False),
    "shorts_vocab": (("한국어 (뜻)", "중국어", "영어"), False),
    "word_memorize": (("한국어 (뜻)", "중국어 (한자)", "영어 (뜻)"), True),
}


@dataclass(frozen=True)
class TtsLangOptions:
    gen_ko: bool
    gen_zh: bool
    gen_en: bool
    voice_ko: str
    voice_zh: str
    voice_en: str
    tts_engine: str = "edge"


@dataclass(frozen=True)
class TtsGenerateResult:
    kind: str
    value: str
    lang: TtsLangOptions
    layout_path: str = ""


@dataclass(frozen=True)
class WordMemorizeTtsOptions:
    """하위 호환 — word_memorize 전용."""

    layout_name: str
    layout_path: str
    gen_ko: bool
    gen_zh: bool
    gen_en: bool
    tts_engine: str
    voice_ko: str
    voice_zh: str
    voice_en: str

    @classmethod
    def from_generate_result(cls, result: TtsGenerateResult) -> WordMemorizeTtsOptions:
        return cls(
            layout_name=result.value,
            layout_path=result.layout_path,
            gen_ko=result.lang.gen_ko,
            gen_zh=result.lang.gen_zh,
            gen_en=result.lang.gen_en,
            tts_engine=result.lang.tts_engine,
            voice_ko=result.lang.voice_ko,
            voice_zh=result.lang.voice_zh,
            voice_en=result.lang.voice_en,
        )
