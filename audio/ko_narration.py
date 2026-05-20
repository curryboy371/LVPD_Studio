"""
한국어 내레이션: SRT/텍스트 파싱 → TTS → 실제 음성 길이 기준 타임라인 재조정 → 합성 오디오.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from core.paths import (
    DEFAULT_KO_NARRATION_SOUND_DIR,
    LEGACY_KO_NARRATION_SOUND_DIR,
    get_repo_root,
)

logger = logging.getLogger(__name__)

_REPO = get_repo_root()
# TTS mp3·타임라인·SRT — resource/sound/shorts (batch_ko_tts)
KO_SOUND_DIR = DEFAULT_KO_NARRATION_SOUND_DIR
_LEGACY_KO_SOUND_DIR = LEGACY_KO_NARRATION_SOUND_DIR

DEFAULT_KO_CUE_GAP_SEC = 0.15


@dataclass(frozen=True)
class KoCue:
    """재조정된 한국어 내레이션 큐."""

    index: int
    text: str
    start_sec: float
    end_sec: float
    audio_path: str


@dataclass(frozen=True)
class KoNarrationPlan:
    """내레이션 세트 단위 재생·합성 계획 (숏츠 클립은 ko_narration_id로 참조)."""

    set_id: int
    clip_type: str
    clip_id: int
    cues: list[KoCue]
    composite_audio_path: str
    adjusted_srt_path: str
    timeline_json_path: str
    total_duration_sec: float


class ITtsProvider(Protocol):
    """텍스트 → 음성 파일 합성."""

    def synthesize(self, text: str, *, lang: str = "ko", out_path: Path) -> Path:
        ...


def srt_time_to_seconds(srt_time: Any) -> float:
    """pysrt SubRipTime → 초."""
    return (
        int(srt_time.hours) * 3600
        + int(srt_time.minutes) * 60
        + int(srt_time.seconds)
        + float(srt_time.milliseconds) / 1000.0
    )


def _seconds_to_srt_time(sec: float) -> Any:
    import pysrt

    ms = int(round(max(0.0, float(sec)) * 1000.0))
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1000
    ms %= 1000
    return pysrt.SubRipTime(hours=h, minutes=m, seconds=s, milliseconds=ms)


def measure_audio_duration_sec(path: str | Path) -> float:
    """오디오 파일 재생 길이(초)."""
    p = Path(path)
    if not p.is_file():
        return 0.0
    if p.suffix.lower() == ".wav":
        try:
            import wave

            with wave.open(str(p), "rb") as wf:
                rate = float(wf.getframerate() or 1)
                return float(wf.getnframes()) / rate
        except Exception:
            pass
    try:
        from mutagen.mp3 import MP3

        if p.suffix.lower() == ".mp3":
            return float(MP3(str(p)).info.length or 0.0)
    except Exception:
        pass
    try:
        from moviepy.editor import AudioFileClip

        with AudioFileClip(str(p)) as clip:
            return float(clip.duration or 0.0)
    except Exception as ex:
        logger.debug("오디오 길이 측정 실패 %s: %s", p, ex)
    return 0.0


class GttsProvider:
    """Google TTS (온라인)."""

    def synthesize(self, text: str, *, lang: str = "ko", out_path: Path) -> Path:
        from gtts import gTTS

        out_path.parent.mkdir(parents=True, exist_ok=True)
        tts = gTTS(text=text, lang=lang)
        tts.save(str(out_path))
        return out_path


class EdgeTtsProvider:
    """Microsoft Edge TTS (온라인, 품질 우수)."""

    def __init__(self, voice: str = "ko-KR-SunHiNeural") -> None:
        self._voice = voice

    def synthesize(self, text: str, *, lang: str = "ko", out_path: Path) -> Path:
        import asyncio

        import edge_tts

        out_path.parent.mkdir(parents=True, exist_ok=True)

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self._voice)
            await communicate.save(str(out_path))

        asyncio.run(_run())
        return out_path


def resolve_tts_provider(name: str = "gtts", *, voice: str = "") -> ITtsProvider:
    key = (name or "gtts").strip().lower()
    if key in ("edge", "edge-tts", "edge_tts"):
        v = (voice or "ko-KR-SunHiNeural").strip()
        return EdgeTtsProvider(voice=v)
    return GttsProvider()


def resolve_tts_config_for_set(
    set_id: int,
    *,
    tts_cli: str = "gtts",
    tts_voice_cli: str = "",
) -> tuple[str, str]:
    """세트 테이블(tts, tts_voice) 우선, 비어 있으면 CLI 기본값."""
    from data.ko_narration_loader import get_ko_narration_set

    engine = (tts_cli or "gtts").strip().lower()
    voice = (tts_voice_cli or "").strip()
    ko_set = get_ko_narration_set(int(set_id))
    if ko_set is not None:
        if ko_set.tts:
            engine = ko_set.tts.strip().lower()
        if ko_set.tts_voice:
            voice = ko_set.tts_voice.strip()
    if not voice and engine in ("edge", "edge-tts", "edge_tts"):
        voice = "ko-KR-SunHiNeural"
    return engine, voice


def format_tts_log_label(engine: str, voice: str = "") -> str:
    """로그용 음성 타입 문자열 (engine + edge 목소리 ID)."""
    key = (engine or "gtts").strip().lower()
    if key in ("edge", "edge-tts", "edge_tts"):
        return f"edge / {(voice or 'ko-KR-SunHiNeural').strip()}"
    return "gtts"


def _resolve_repo_path(raw: str) -> Path:
    p = Path((raw or "").strip())
    if not p.is_absolute():
        p = _REPO / p
    return p


def parse_ko_cue_texts(
    *,
    ko_narration: str = "",
    ko_narration_srt: str = "",
) -> list[str]:
    """SRT 경로 우선, 없으면 ko_narration(줄 단위)에서 큐 텍스트 목록."""
    srt_raw = (ko_narration_srt or "").strip()
    if srt_raw:
        srt_path = _resolve_repo_path(srt_raw)
        if not srt_path.is_file():
            logger.warning("ko_narration_srt 없음: %s", srt_path)
            return []
        import pysrt

        subs = pysrt.open(str(srt_path), encoding="utf-8")
        texts = [re.sub(r"\s+", " ", (sub.text or "").replace("\n", " ")).strip() for sub in subs]
        return [t for t in texts if t]

    raw = (ko_narration or "").strip()
    if not raw:
        return []
    if "\n" in raw:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return [raw]


def _cache_stem_for_set(set_id: int) -> str:
    return f"set_{int(set_id)}"


def _cache_stem(clip_type: str, clip_id: int) -> str:
    """하위 호환(clip 키). 신규는 set_id 기준 _cache_stem_for_set 사용."""
    safe_type = re.sub(r"[^\w\-]+", "_", (clip_type or "clip").strip()) or "clip"
    return f"{safe_type}_{int(clip_id)}"


def _ko_sound_basename(set_id: int, index: int) -> str:
    return f"ko_{_cache_stem_for_set(set_id)}_{index}"


def _cue_audio_path_for_set(set_id: int, index: int) -> Path:
    return KO_SOUND_DIR / f"{_ko_sound_basename(set_id, index)}.mp3"


def cached_cue_audio_usable(path: Path | str) -> bool:
    """TTS mp3 캐시가 재생 가능한지."""
    return _cached_cue_audio_usable(Path(path))


def _cached_cue_audio_usable(path: Path) -> bool:
    """0바이트·길이 0 mp3는 실패 캐시로 보고 재생성."""
    if not path.is_file():
        return False
    try:
        if path.stat().st_size < 64:
            return False
    except OSError:
        return False
    return measure_audio_duration_sec(path) > 1e-3


def _cue_audio_path(clip_type: str, clip_id: int, index: int) -> Path:
    stem = _cache_stem(clip_type, clip_id)
    return KO_SOUND_DIR / f"ko_{stem}_{index}.mp3"


def synthesize_cue_audios(
    texts: list[str],
    *,
    set_id: int,
    provider: ITtsProvider,
    lang: str = "ko",
    force: bool = False,
    clip_type: str = "",
    clip_id: int = 0,
) -> list[Path]:
    """큐별 MP3 캐시 생성 (set_id 기준 경로, 동일 세트는 클립 간 공유)."""
    paths: list[Path] = []
    for i, text in enumerate(texts):
        out = _cue_audio_path_for_set(set_id, i) if set_id > 0 else _cue_audio_path(clip_type, clip_id, i)
        if not force and _cached_cue_audio_usable(out):
            paths.append(out)
            continue
        if out.is_file() and not _cached_cue_audio_usable(out):
            logger.warning("손상된 TTS 캐시 삭제 후 재생성: %s", out)
            try:
                out.unlink()
            except OSError as ex:
                logger.debug("캐시 삭제 실패 %s: %s", out, ex)
        try:
            provider.synthesize(text, lang=lang, out_path=out)
            if not _cached_cue_audio_usable(out):
                logger.warning("TTS 산출물이 비어 있음: %s", out)
                try:
                    out.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            paths.append(out)
        except Exception as ex:
            logger.exception("TTS 실패 set_id=%s idx=%s: %s", set_id, i, ex)
    return paths


def build_timeline(
    texts: list[str],
    audio_paths: list[Path],
    *,
    start_offset_sec: float = 0.0,
    gap_sec: float = DEFAULT_KO_CUE_GAP_SEC,
) -> list[KoCue]:
    """TTS 실제 길이로 start/end 재계산."""
    cues: list[KoCue] = []
    t = max(0.0, float(start_offset_sec))
    gap = max(0.0, float(gap_sec))
    n = min(len(texts), len(audio_paths))
    for i in range(n):
        text = texts[i]
        ap = audio_paths[i]
        dur = measure_audio_duration_sec(ap)
        if dur <= 1e-6:
            logger.warning("TTS 길이 0, 큐 스킵: %s", ap)
            continue
        start = t
        end = start + dur
        cues.append(
            KoCue(
                index=len(cues),
                text=text,
                start_sec=start,
                end_sec=end,
                audio_path=str(ap.resolve()),
            )
        )
        t = end + gap
    return cues


def write_adjusted_srt(cues: list[KoCue], out_path: Path) -> str:
    """재조정 타임라인을 SRT로 저장."""
    import pysrt

    out_path.parent.mkdir(parents=True, exist_ok=True)
    items = pysrt.SubRipFile()
    for i, cue in enumerate(cues, start=1):
        items.append(
            pysrt.SubRipItem(
                index=i,
                start=_seconds_to_srt_time(cue.start_sec),
                end=_seconds_to_srt_time(cue.end_sec),
                text=cue.text,
            )
        )
    items.save(str(out_path), encoding="utf-8")
    return str(out_path.resolve())


def write_timeline_json(plan: KoNarrationPlan) -> str:
    """pygame/MoviePy 공용 JSON."""
    p = Path(plan.timeline_json_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "set_id": plan.set_id,
        "clip_type": plan.clip_type,
        "clip_id": plan.clip_id,
        "composite_audio_path": plan.composite_audio_path,
        "adjusted_srt_path": plan.adjusted_srt_path,
        "total_duration_sec": plan.total_duration_sec,
        "cues": [asdict(c) for c in plan.cues],
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p.resolve())


def build_composite_audio(cues: list[KoCue], out_path: Path) -> str:
    """moviepy CompositeAudioClip으로 큐 오디오 합성."""
    if not cues:
        return ""
    from moviepy.editor import AudioFileClip, CompositeAudioClip

    out_path.parent.mkdir(parents=True, exist_ok=True)
    clips = []
    opened: list[Any] = []
    try:
        for cue in cues:
            ac = AudioFileClip(cue.audio_path).set_start(cue.start_sec)
            opened.append(ac)
            clips.append(ac)
        composite = CompositeAudioClip(clips)
        composite.write_audiofile(str(out_path), logger=None)
        composite.close()
    finally:
        for ac in opened:
            try:
                ac.close()
            except Exception:
                pass
    return str(out_path.resolve()) if out_path.is_file() else ""


def active_ko_text_for_elapsed(plan: KoNarrationPlan, elapsed_sec: float) -> str:
    """현재 시각에 해당하는 큐 텍스트."""
    t = float(elapsed_sec)
    for cue in plan.cues:
        if cue.start_sec <= t < cue.end_sec + 1e-3:
            return cue.text
    if plan.cues and t >= plan.cues[-1].end_sec - 1e-3:
        return plan.cues[-1].text
    return ""


def load_ko_narration_plan_from_json(path: str | Path) -> Optional[KoNarrationPlan]:
    """저장된 timeline JSON 로드."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        cues = [
            KoCue(
                index=int(c.get("index", 0)),
                text=str(c.get("text", "")),
                start_sec=float(c.get("start_sec", 0)),
                end_sec=float(c.get("end_sec", 0)),
                audio_path=str(c.get("audio_path", "")),
            )
            for c in data.get("cues", [])
        ]
        return KoNarrationPlan(
            set_id=int(data.get("set_id", 0)),
            clip_type=str(data.get("clip_type", "")),
            clip_id=int(data.get("clip_id", 0)),
            cues=cues,
            composite_audio_path=str(data.get("composite_audio_path", "")),
            adjusted_srt_path=str(data.get("adjusted_srt_path", "")),
            timeline_json_path=str(p.resolve()),
            total_duration_sec=float(data.get("total_duration_sec", 0)),
        )
    except Exception as ex:
        logger.warning("ko timeline JSON 로드 실패 %s: %s", p, ex)
        return None


def ko_narration_id_from_clip(clip: dict[str, Any]) -> int:
    try:
        return int(clip.get("ko_narration_id") or 0)
    except (TypeError, ValueError):
        return 0


def clip_has_ko_narration(clip: dict[str, Any]) -> bool:
    return ko_narration_id_from_clip(clip) > 0


def adjusted_srt_path_for_set(set_id: int) -> Path:
    """배치 산출 자막: resource/sound/shorts/ko_set_{id}_adjusted.srt"""
    stem = _cache_stem_for_set(set_id)
    return KO_SOUND_DIR / f"ko_{stem}_adjusted.srt"


def _ko_set_output_glob_patterns(set_id: int) -> list[str]:
    stem = _cache_stem_for_set(set_id)
    return [f"ko_{stem}_*"]


def clear_ko_set_sound_output(set_id: int) -> int:
    """지정 ko_narration set_id 산출물만 삭제 (ko_set_{id}_*.mp3/json/srt 등)."""
    sid = int(set_id)
    if sid < 1:
        return 0
    removed = 0
    dirs = [KO_SOUND_DIR]
    if _LEGACY_KO_SOUND_DIR != KO_SOUND_DIR:
        dirs.append(_LEGACY_KO_SOUND_DIR)
    for directory in dirs:
        if not directory.is_dir():
            continue
        for pattern in _ko_set_output_glob_patterns(sid):
            for entry in directory.glob(pattern):
                try:
                    if entry.is_file():
                        entry.unlink()
                        removed += 1
                    elif entry.is_dir():
                        shutil.rmtree(entry)
                        removed += 1
                except OSError as ex:
                    logger.warning("set_id=%s 삭제 실패 %s: %s", sid, entry, ex)
    logger.info(
        "set_id=%s TTS 산출물 삭제: %d개 (ko_set_%s_*)",
        sid,
        removed,
        sid,
    )
    return removed


def clear_ko_shorts_sound_output() -> None:
    """전체 shorts 출력 비우기 (--set-id 없이 전체 배치할 때만)."""
    KO_SOUND_DIR.mkdir(parents=True, exist_ok=True)
    removed = 0
    for entry in KO_SOUND_DIR.iterdir():
        try:
            if entry.is_file():
                entry.unlink()
                removed += 1
            elif entry.is_dir():
                shutil.rmtree(entry)
                removed += 1
        except OSError as ex:
            logger.warning("shorts 출력 삭제 실패 %s: %s", entry, ex)
    logger.info("shorts TTS 출력 폴더 비움: %s (%d개)", KO_SOUND_DIR, removed)


def cached_timeline_json_path_for_set(set_id: int) -> Path:
    return KO_SOUND_DIR / f"ko_{_cache_stem_for_set(set_id)}_timeline.json"


def _timeline_json_candidates_for_set(set_id: int) -> list[Path]:
    """신규 shorts 경로 우선, 이전 resource/sound 캐시 폴백."""
    name = f"ko_{_cache_stem_for_set(set_id)}_timeline.json"
    paths = [KO_SOUND_DIR / name]
    legacy = _LEGACY_KO_SOUND_DIR / name
    if legacy != paths[0]:
        paths.append(legacy)
    return paths


def cached_timeline_json_path(clip_type: str, clip_id: int) -> Path:
    """하위 호환."""
    return KO_SOUND_DIR / f"ko_{_cache_stem(clip_type, clip_id)}_timeline.json"


def resolve_ko_cue_audio_path(raw: str) -> str:
    """timeline JSON의 audio_path → 재생 가능한 절대 경로 (절대/상대/파일명 폴백)."""
    s = (raw or "").strip()
    if not s:
        return ""
    p = Path(s)
    if p.is_file():
        return str(p.resolve())
    if not p.is_absolute():
        under_repo = (_REPO / p).resolve()
        if under_repo.is_file():
            return str(under_repo)
    name = p.name
    if name:
        for base in (KO_SOUND_DIR, _LEGACY_KO_SOUND_DIR):
            cand = (base / name).resolve()
            if cand.is_file():
                return str(cand)
    return str(p.resolve()) if s else ""


def normalize_plan_cue_audio_paths(plan: KoNarrationPlan) -> KoNarrationPlan:
    """로드 후 cue mp3 경로를 repo 기준으로 정규화."""
    cues = [
        KoCue(
            index=c.index,
            text=c.text,
            start_sec=c.start_sec,
            end_sec=c.end_sec,
            audio_path=resolve_ko_cue_audio_path(c.audio_path),
        )
        for c in plan.cues
    ]
    return KoNarrationPlan(
        set_id=plan.set_id,
        clip_type=plan.clip_type,
        clip_id=plan.clip_id,
        cues=cues,
        composite_audio_path=plan.composite_audio_path,
        adjusted_srt_path=plan.adjusted_srt_path,
        timeline_json_path=plan.timeline_json_path,
        total_duration_sec=plan.total_duration_sec,
    )


def plan_cue_audios_ready(plan: KoNarrationPlan) -> bool:
    """문장별 TTS mp3가 모두 있으면 True (재생·자막 동기용)."""
    if not plan.cues:
        return False
    return all(Path(resolve_ko_cue_audio_path(c.audio_path)).is_file() for c in plan.cues)


def try_load_cached_ko_plan(clip: dict[str, Any]) -> Optional[KoNarrationPlan]:
    """배치로 생성된 timeline JSON + 문장별 mp3가 있으면 로드."""
    set_id = ko_narration_id_from_clip(clip)
    if set_id < 1:
        return None
    for json_path in _timeline_json_candidates_for_set(set_id):
        plan = load_ko_narration_plan_from_json(json_path)
        if plan is not None and plan_cue_audios_ready(plan):
            return plan
    return None


def batch_build_ko_narration_set(
    set_id: int,
    *,
    tts: str = "gtts",
    tts_voice: str = "",
    force_tts: bool = False,
    with_composite: bool = False,
    clip_type: str = "",
    clip_id: int = 0,
) -> Optional[KoNarrationPlan]:
    """ko_narration_id(세트) 단위 TTS·타임라인 생성."""
    from data.ko_narration_loader import load_ko_narration_tables

    load_ko_narration_tables()
    fake_clip = {
        "ko_narration_id": int(set_id),
        "clip_type": clip_type,
        "clip_id": clip_id,
    }
    return build_ko_narration_plan(
        fake_clip,
        tts=tts,
        tts_voice=tts_voice,
        force_tts=force_tts,
        skip_composite=not with_composite,
    )


def collect_ko_narration_set_ids_from_shorts_csv(
    *,
    shorts_mode: str = "conversation",
    csv_path: str | Path | None = None,
    session_topics: Optional[list[str]] = None,
    clip_id: int = 0,
    set_id: int = 0,
) -> list[int]:
    """숏츠 CSV에서 ko_narration_id만 읽는다(base_sentences 조인 불필요)."""
    from studio.shorts.clip_types import CLIP_TYPE_CONVERSATION, CLIP_TYPE_VOCABULARY, normalize_clip_type
    from studio.shorts.data_loading import _parse_ko_narration_id, _read_shorts_csv, _topic_matches
    from core.paths import (
        DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV,
        DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV,
    )

    if set_id > 0:
        return [int(set_id)]

    mode = normalize_clip_type(shorts_mode)
    default_path = (
        DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV
        if mode == CLIP_TYPE_VOCABULARY
        else DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV
    )
    path = Path(csv_path) if csv_path else default_path
    topic_set: Optional[set[str]] = None
    if session_topics:
        topic_set = {t.strip().lower() for t in session_topics if t.strip()}

    found: set[int] = set()
    label = "shorts_vocabulary_clips" if mode == CLIP_TYPE_VOCABULARY else "shorts_conversation_clips"
    for row in _read_shorts_csv(path, label=label):
        try:
            cid = int(float(row.get("id") or "0"))
        except (TypeError, ValueError):
            continue
        if clip_id and cid != clip_id:
            continue
        topic = (row.get("topic") or "").strip()
        if not _topic_matches(topic, topic_set):
            continue
        sid = _parse_ko_narration_id(row)
        if sid > 0:
            found.add(sid)
    return sorted(found)


def batch_build_shorts_ko_narration(
    *,
    shorts_mode: str = "conversation",
    csv_path: str | Path | None = None,
    session_topics: Optional[list[str]] = None,
    tts: str = "gtts",
    tts_voice: str = "",
    force_tts: bool = False,
    clip_id: int = 0,
    set_id: int = 0,
    with_composite: bool = False,
) -> tuple[int, int, int]:
    """숏츠 CSV의 ko_narration_id → 세트별 TTS 배치(동일 set_id는 한 번만 생성).

    Returns:
        (생성 성공 세트 수, 내레이션 없음 스킵 클립 수, 실패 수)
    """
    from data.ko_narration_loader import load_ko_narration_tables

    load_ko_narration_tables()
    if int(set_id) > 0:
        clear_ko_set_sound_output(int(set_id))
    else:
        clear_ko_shorts_sound_output()
    target_ids = collect_ko_narration_set_ids_from_shorts_csv(
        shorts_mode=shorts_mode,
        csv_path=csv_path,
        session_topics=session_topics,
        clip_id=clip_id,
        set_id=set_id,
    )
    ok = skip = fail = 0
    if not target_ids:
        logger.warning(
            "ko_narration_id 대상 없음 (shorts CSV·topic·clip-id 확인). "
            "세트만 만들려면 --set-id N"
        )
        return 0, 0, 1

    for sid in target_ids:
        engine, voice = resolve_tts_config_for_set(sid, tts_cli=tts, tts_voice_cli=tts_voice)
        tts_label = format_tts_log_label(engine, voice)
        logger.info("배치 시작 set_id=%s 음성=%s", sid, tts_label)
        plan = batch_build_ko_narration_set(
            sid,
            tts=tts,
            tts_voice=tts_voice,
            force_tts=force_tts,
            with_composite=with_composite,
        )
        if plan is None or not plan_cue_audios_ready(plan):
            fail += 1
            logger.warning("배치 TTS 실패 set_id=%s 음성=%s", sid, tts_label)
            continue
        ok += 1
        srt_out = adjusted_srt_path_for_set(plan.set_id)
        logger.info(
            "set_id=%s 문장 %d개 음성=%s → %s / %s",
            plan.set_id,
            len(plan.cues),
            tts_label,
            plan.timeline_json_path,
            srt_out,
        )
    return ok, skip, fail


def build_ko_narration_plan(
    clip: dict[str, Any],
    *,
    tts: str = "gtts",
    tts_voice: str = "",
    lang: str = "ko",
    gap_sec: float = DEFAULT_KO_CUE_GAP_SEC,
    start_offset_sec: float = 0.0,
    force_tts: bool = False,
    skip_composite: bool = False,
) -> Optional[KoNarrationPlan]:
    """클립의 ko_narration_id → ko_narration_* 테이블 조인 후 계획 생성."""
    set_id = ko_narration_id_from_clip(clip)
    if set_id < 1:
        return None

    from data.ko_narration_loader import get_cue_texts_for_set, load_ko_narration_tables

    load_ko_narration_tables()
    texts = get_cue_texts_for_set(set_id)
    if not texts:
        logger.warning("ko_narration set_id=%s: 문장 없음", set_id)
        return None

    clip_type = str(clip.get("clip_type") or "clip").strip()
    clip_id = int(clip.get("clip_id") or 0)

    engine, voice = resolve_tts_config_for_set(set_id, tts_cli=tts, tts_voice_cli=tts_voice)
    provider = resolve_tts_provider(engine, voice=voice)
    logger.info("TTS set_id=%s 음성=%s", set_id, format_tts_log_label(engine, voice))
    audio_paths = synthesize_cue_audios(
        texts,
        set_id=set_id,
        provider=provider,
        lang=lang,
        force=force_tts,
        clip_type=clip_type,
        clip_id=clip_id,
    )
    if len(audio_paths) != len(texts):
        logger.warning("TTS 일부 실패 set_id=%s (%d/%d)", set_id, len(audio_paths), len(texts))
        texts = texts[: len(audio_paths)]

    cues = build_timeline(
        texts,
        audio_paths,
        start_offset_sec=start_offset_sec,
        gap_sec=gap_sec,
    )
    if not cues:
        return None

    KO_SOUND_DIR.mkdir(parents=True, exist_ok=True)
    adjusted_srt = adjusted_srt_path_for_set(set_id)
    stem = _cache_stem_for_set(set_id)
    timeline_json = KO_SOUND_DIR / f"ko_{stem}_timeline.json"
    composite_path = KO_SOUND_DIR / f"ko_{stem}_composite.mp3"

    write_adjusted_srt(cues, adjusted_srt)

    composite_str = ""
    if not skip_composite:
        composite_str = build_composite_audio(cues, composite_path)

    total = cues[-1].end_sec if cues else 0.0
    plan = KoNarrationPlan(
        set_id=set_id,
        clip_type=clip_type,
        clip_id=clip_id,
        cues=cues,
        composite_audio_path=composite_str,
        adjusted_srt_path=str(adjusted_srt.resolve()),
        timeline_json_path=str(timeline_json.resolve()),
        total_duration_sec=total,
    )
    write_timeline_json(plan)

    cached = load_ko_narration_plan_from_json(timeline_json)
    return cached if cached is not None else plan
