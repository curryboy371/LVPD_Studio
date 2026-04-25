"""
CSV 행 데이터 및 영상 소스를 담는 Pydantic 모델.
텍스트, 이미지/사운드 경로, 시작·종료 시간, 영상 세그먼트·오버레이·오디오 트랙 정의.
"""
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# 영상 소스 모델 (렌더링/편집용)
# ---------------------------------------------------------------------------


class VideoSegment(BaseModel):
    """영상 소스 한 구간: 파일 경로, 시작/종료 시간, 볼륨 설정."""

    file_path: str = Field(..., description="영상 파일 경로")
    start_time: float = Field(default=0.0, ge=0, description="시작 시간(초)")
    end_time: float = Field(default=0.0, ge=-1, description="종료 시간(초). -1이면 영상 끝까지 재생")
    volume: float = Field(default=1.0, ge=0, le=2.0, description="재생 볼륨 (0.0~2.0, 기본 1.0)")

    @field_validator("file_path", mode="before")
    @classmethod
    def strip_path(cls, v: Optional[str]) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return ""
        return v.strip()


class OverlayItem(BaseModel):
    """오버레이 요소: 문장/번역/병음/단어/팁 등 전부 저장. text는 하위 호환용."""

    sentence: Optional[str] = Field(default=None, description="중국어 문장")
    translation: Optional[str] = Field(default=None, description="번역")
    pinyin: Optional[str] = Field(default=None, description="병음(성조 기호) = pinyin_marks")
    pinyin_phonetic: Optional[str] = Field(default=None, description="발음 병음(숫자)")
    pinyin_lexical: Optional[str] = Field(default=None, description="표기 병음(숫자)")
    words: Optional[str] = Field(default=None, description="단어 목록(| 구분)")
    life_tips: Optional[str] = Field(default=None, description="팁 목록(| 구분)")
    font_name: Optional[str] = Field(default=None, description="폰트 이름(선택)")
    font_size: int = Field(default=24, ge=1, le=500, description="폰트 크기(선택)")
    position_x: float = Field(default=0.0, description="x 위치(선택)")
    position_y: float = Field(default=0.0, description="y 위치(선택)")
    image_path: Optional[str] = Field(default=None, description="오버레이 이미지 경로(선택)")

    @field_validator(
        "font_name", "image_path", "pinyin", "pinyin_phonetic", "pinyin_lexical",
        "sentence", "translation", "words", "life_tips",
        mode="before",
    )
    @classmethod
    def empty_str_to_none_overlay(cls, v: Optional[str]) -> Optional[str]:
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        return v.strip() if isinstance(v, str) else v


class AudioTrack(BaseModel):
    """오디오 트랙: 사운드 파일 경로, 페이드 인/아웃 설정."""

    sound_path: str = Field(..., description="사운드 파일 경로")
    fade_in_sec: float = Field(default=0.0, ge=0, description="페이드 인 길이(초)")
    fade_out_sec: float = Field(default=0.0, ge=0, description="페이드 아웃 길이(초)")

    @field_validator("sound_path", mode="before")
    @classmethod
    def strip_sound_path(cls, v: Optional[str]) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return ""
        return v.strip()


# ---------------------------------------------------------------------------
# CSV 행 (ContentRow)
# ---------------------------------------------------------------------------


class ContentRow(BaseModel):
    """CSV 한 행에 해당하는 콘텐츠 데이터. 자막·이미지·사운드·타임라인 정보를 담는다."""

    text: str = Field(default="", description="자막/문장 텍스트")
    image_path: Optional[str] = Field(default=None, description="이미지 파일 경로")
    sound_path: Optional[str] = Field(default=None, description="사운드 파일 경로")
    start_time: float = Field(default=0.0, ge=0, description="시작 시간(초)")
    end_time: float = Field(default=0.0, ge=0, description="종료 시간(초)")
    video_path: Optional[str] = Field(default=None, description="영상 파일 경로(선택)")

    @field_validator("image_path", "sound_path", "video_path", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Optional[str]) -> Optional[str]:
        """빈 문자열을 None으로 정규화한다."""
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        return v.strip() if isinstance(v, str) else v

    class Config:
        str_strip_whitespace = True


class LoadedContent(BaseModel):
    """CSV 로더가 반환하는 영상 소스 묶음: 세그먼트·오버레이·오디오 트랙 리스트."""

    video_segments: list[VideoSegment] = Field(default_factory=list, description="영상 구간 목록")
    overlay_items: list[OverlayItem] = Field(default_factory=list, description="오버레이 요소 목록")
    audio_tracks: list[AudioTrack] = Field(default_factory=list, description="오디오 트랙 목록")


# ---------------------------------------------------------------------------
# 테이블 구조 (base_sentence / word / sub_sentence / sentence_word_map)
# ---------------------------------------------------------------------------


class VideoRange(BaseModel):
    """영상 구간: ms 단위."""

    start_ms: int = Field(default=0, ge=0, description="시작 시각(ms)")
    end_ms: int = Field(default=0, ge=-1, description="종료 시각(ms). -1이면 끝까지")


class BaseSentenceSound(BaseModel):
    """문장 음성: L1/L2 경로."""

    lv1_path: str = Field(default="", description="L1 음성 경로")
    lv2_path: str = Field(default="", description="L2 음성 경로")


class BaseSentenceMedia(BaseModel):
    """문장 미디어: 영상 경로·구간, 음성."""

    video_path: str = Field(default="", description="영상 파일 경로")
    video_range: VideoRange = Field(default_factory=VideoRange, description="재생 구간(ms)")
    sound: BaseSentenceSound = Field(default_factory=BaseSentenceSound, description="음성 정보")


class SentenceWordMap(BaseModel):
    """문장의 slot_order 위치에 올 단어 및 클릭/슬롯 여부."""

    sentence_id: int = Field(..., description="base_sentence.id")
    word_id: int = Field(..., description="word.id")
    slot_order: int = Field(default=0, ge=0, description="슬롯 순서")
    is_clickable: bool = Field(default=True, description="클릭 가능 여부")
    is_slot_target: bool = Field(default=False, description="슬롯 교체 대상 여부")

    @field_validator("is_clickable", "is_slot_target", mode="before")
    @classmethod
    def to_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "1", "yes", "y"):
                return True
            if s in ("false", "0", "no", "n", ""):
                return False
        return False


class BaseSentence(BaseModel):
    """학습 원본 문장 + 미디어 리소스."""

    id: int = Field(..., description="기본키")
    topic: str = Field(default="", description="주제 (예: 쇼핑)")
    level: int = Field(default=1, ge=1, description="난이도")
    raw_sentence: str = Field(default="", description="원문 (예: {苹果}{多少}{钱})")
    translation: str = Field(default="", description="번역")
    life_tip: str = Field(default="", description="생활 팁")
    media: BaseSentenceMedia = Field(default_factory=BaseSentenceMedia, description="미디어 정보")
    word_maps: list[SentenceWordMap] = Field(
        default_factory=list,
        description="이 문장(id)에 대한 단어 배치 목록. 로드 후 매니저에서 채움.",
    )


class Word(BaseModel):
    """문장 공통 단어 마스터."""

    id: int = Field(..., description="기본키")
    word: str = Field(default="", description="한자 단어")
    pinyin: str = Field(default="", description="성조 병음 (예: píngguǒ)")
    pos: str = Field(default="", description="품사 (예: 명사, 동사). 복수 시 | 구분")
    meaning: str = Field(default="", description="뜻")
    img_path: str = Field(default="", description="이미지 경로")
    sound_path: str = Field(default="", description="단어 단독 발음 음원 (선택)")


class SubSentence(BaseModel):
    """슬롯 교체 시 사용할 대체 단어·번역·음성."""

    id: int = Field(..., description="기본키")
    base_id: int = Field(..., description="base_sentence.id")
    target_slot_order: int = Field(default=0, ge=0, description="대상 슬롯 순서")
    alt_word_id: int = Field(..., description="대체 단어 word.id")
    alt_translation: str = Field(default="", description="대체 번역")
    alt_sound_path: str = Field(default="", description="대체 음성 경로")
