"""숏츠 회화/단어 CSV 로드 및 base_sentences·words 조인."""

from __future__ import annotations

import csv
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from core.paths import (
    DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV,
    DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV,
    get_repo_root,
)
from data.table_manager import get_base_sentences, get_word
from studio.shorts.clip_types import CLIP_TYPE_CONVERSATION, CLIP_TYPE_VOCABULARY, normalize_clip_type
from studio.shorts.constants import SHORTS_PANDA_DIR
from utils.pinyin_processor import get_pinyin_processor
from utils.syllable_timing import parse_syllable_times_ms

logger = logging.getLogger(__name__)

_REPO_ROOT = get_repo_root()


def _raw_sentence_to_display(raw: str) -> str:
    """'{苹果}{多少}{钱}？' → '苹果多少钱？'."""
    if not raw:
        return ""
    return re.sub(r"\{([^}]*)\}", r"\1", raw)


def _resolve_path(repo: Path, raw: str) -> str:
    p = (raw or "").strip()
    if not p:
        return ""
    if os.path.isabs(p):
        return p
    return str(repo / p.replace("\\", "/"))


def _resolve_conversation_video_path(
    row: dict[str, str],
    *,
    clip_id: int,
    topic: str,
    base: Any,
    repo: Path,
) -> str:
    """회화 클립 비디오 경로. CSV → topic/id.mp4 → base.media 순."""
    video_path = _resolve_path(repo, row.get("video_path") or "")
    if not video_path or not os.path.exists(video_path):
        if topic:
            cand = repo / "resource" / "video" / topic / f"{clip_id}.mp4"
            if cand.is_file():
                video_path = str(cand)
            else:
                video_path = ""
        else:
            video_path = ""
    if not video_path and base is not None:
        vp = (getattr(getattr(base, "media", None), "video_path", None) or "").strip()
        if vp:
            video_path = _resolve_path(repo, vp)
    if video_path and not os.path.exists(video_path):
        return ""
    return video_path


def _resolve_vocabulary_video_path(
    row: dict[str, str],
    *,
    clip_id: int,
    topic: str,
    repo: Path,
) -> str:
    """단어 클립 인트로 비디오. CSV video_path → resource/video/{topic}/vocab_{id}.mp4 등."""
    video_path = _resolve_path(repo, row.get("video_path") or "")
    if video_path and os.path.exists(video_path):
        return video_path
    if topic:
        for name in (f"vocab_{clip_id}.mp4", f"{clip_id}.mp4"):
            cand = repo / "resource" / "video" / topic / name
            if cand.is_file():
                return str(cand)
    return ""


def _default_hook_image(clip_id: int, *, subdir: str = "") -> str:
    if subdir:
        return str(SHORTS_PANDA_DIR / subdir / f"{clip_id}.png")
    return str(SHORTS_PANDA_DIR / f"{clip_id}.png")


def _enrich_pinyin(sentence: str, row: dict[str, Any]) -> None:
    """병음 필드가 비어 있으면 pinyin_processor로 채운다."""
    pinyin_marks = (row.get("pinyin") or row.get("pinyin_marks") or "").strip()
    pinyin_phonetic = (row.get("pinyin_phonetic") or "").strip()
    pinyin_lexical = (row.get("pinyin_lexical") or "").strip()
    if not sentence:
        return
    try:
        pp = get_pinyin_processor()
        if not pp.available:
            return
        if not pinyin_marks:
            pinyin_marks = pp.full_convert(sentence)
        if not pinyin_lexical:
            pinyin_lexical = " ".join(pp.get_lexical_pinyin(sentence)).strip()
        if not pinyin_phonetic:
            pinyin_phonetic = " ".join(pp.get_phonetic_pinyin(sentence)).strip()
    except Exception:
        return
    row["pinyin"] = pinyin_marks
    row["pinyin_phonetic"] = pinyin_phonetic
    row["pinyin_lexical"] = pinyin_lexical


def _base_by_id() -> dict[int, Any]:
    base = get_base_sentences()
    if not base:
        return {}
    return {int(b.id): b for b in base if int(b.id) > 0}


def _merge_base_into_clip(clip: dict[str, Any], base: Any, repo: Path) -> None:
    """BaseSentence를 클립 렌더 필드에 병합."""
    sentence = _raw_sentence_to_display(base.raw_sentence)
    translation = (base.translation or "").strip()
    clip["sentence"] = [sentence] if sentence else []
    clip["translation"] = [translation] if translation else []
    clip.setdefault("topic", (base.topic or "").strip())

    sound = (clip.get("sound_path") or "").strip()
    if not sound:
        sound = (base.media.sound.lv_path or "").strip()
    clip["sound_path"] = _resolve_path(repo, sound)

    if not (clip.get("situation_subtitle") or "").strip():
        clip["situation_subtitle"] = (base.translation or "").strip()

    _enrich_pinyin(sentence, clip)


def _merge_word_into_clip(clip: dict[str, Any], word: Any, repo: Path) -> None:
    """Word 마스터를 클립 렌더 필드에 병합."""
    hanzi = (word.word or "").strip()
    clip["word_id"] = int(word.id)
    clip["sentence"] = [hanzi] if hanzi else []
    meaning_raw = (word.meaning or "").strip()
    first_meaning = meaning_raw.split("|")[0].strip() if meaning_raw else ""
    pos = (word.pos or "").strip()
    clip["translation"] = [first_meaning] if first_meaning else []
    clip["pinyin"] = (word.pinyin or "").strip()
    clip["word_img_path"] = _resolve_path(repo, (word.img_path or "").strip())
    clip["word_video_path"] = _resolve_path(repo, (getattr(word, "video_path", None) or "").strip())
    clip["word_pos"] = pos
    clip["word_tip"] = (getattr(word, "tip", None) or "").strip().replace("\\n", "\n")

    sound = (clip.get("sound_path") or "").strip()
    if not sound:
        sound = (word.sound_path or "").strip()
    clip["sound_path"] = _resolve_path(repo, sound)
    clip["situation_subtitle"] = ""

    if hanzi and not clip["pinyin"]:
        _enrich_pinyin(hanzi, clip)


def _read_shorts_csv(path: Path, *, label: str) -> list[dict[str, str]]:
    if not path.exists():
        logger.warning("%s CSV 없음: %s", label, path)
        return []
    rows: list[dict[str, str]] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    (k or "").strip(): (v or "").strip() if isinstance(v, str) else str(v or "").strip()
                    for k, v in row.items()
                }
            )
    return rows


def resolve_hook_title(data: dict[str, Any] | Any) -> str:
    """클립/CSV 행에서 hook_title 필드를 찾는다."""
    if data is None:
        return ""
    get = getattr(data, "get", None)
    if get is None:
        return ""
    text = str(get("hook_title") or "").strip()
    if text:
        return text
    for key, raw in (getattr(data, "items", lambda: [])() or []):
        if str(key or "").strip().lower().replace(" ", "_") == "hook_title":
            text = str(raw or "").strip()
            if text:
                return text
    return ""


def _parse_ko_narration_id(row: dict[str, str]) -> int:
    try:
        return int(float(row.get("ko_narration_id") or "0"))
    except (TypeError, ValueError):
        return 0


def _topic_matches(topic: str, topic_set: Optional[set[str]]) -> bool:
    if topic_set is None:
        return True
    return topic.lower() in topic_set


def _common_clip_fields(
    row: dict[str, str],
    *,
    clip_id: int,
    topic: str,
    hook_image: str,
    repo: Path,
    index: int,
    clip_type: str,
    sound_from_row: bool = True,
    use_syllable_times_ms: bool = True,
) -> dict[str, Any]:
    sound_path = (
        _resolve_path(repo, row.get("sound_path") or "") if sound_from_row else ""
    )
    times_raw = row.get("syllable_times_ms") or row.get("syllable_times") or ""
    syllable_times = (
        parse_syllable_times_ms(times_raw) if use_syllable_times_ms else []
    )
    return {
        "clip_id": clip_id,
        "clip_type": clip_type,
        "base_id": 0,
        "word_id": 0,
        "topic": topic,
        "hook_title": resolve_hook_title(row),
        "hook_image_path": hook_image,
        "situation_subtitle": (row.get("situation_subtitle") or "").strip(),
        "ko_narration_id": _parse_ko_narration_id(row),
        "sound_path": sound_path,
        "syllable_times": syllable_times,
        "sentence": [],
        "translation": [],
        "pinyin": "",
        "word_img_path": "",
        "word_pos": "",
        "word_tip": "",
        "sound_repeat_count": 1,
        "after_sound_delay_sec": 0.0,
        "video_path": _resolve_path(repo, row.get("video_path") or ""),
        "index": index,
    }


def build_shorts_conversation_clip_list(
    csv_path: str | Path | None = None,
    *,
    session_topics: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """shorts_conversation_clips.csv + base_sentences 조인."""
    path = Path(csv_path) if csv_path else DEFAULT_SHORTS_CONVERSATION_CLIPS_CSV
    repo = _REPO_ROOT
    bases = _base_by_id()
    topic_set: Optional[set[str]] = None
    if session_topics:
        topic_set = {t.strip().lower() for t in session_topics if t.strip()}

    out: list[dict[str, Any]] = []
    for i, row in enumerate(_read_shorts_csv(path, label="shorts_conversation_clips")):
        try:
            clip_id = int(float(row.get("id") or "0"))
        except (TypeError, ValueError):
            continue
        if clip_id < 1:
            continue
        topic = (row.get("topic") or "").strip()
        if not _topic_matches(topic, topic_set):
            continue
        hook_title = resolve_hook_title(row)
        if not hook_title:
            logger.warning("shorts conversation clip id=%s: hook_title 없음, 스킵", clip_id)
            continue
        try:
            base_id = int(float(row.get("base_id") or "0"))
        except (TypeError, ValueError):
            logger.warning("shorts conversation clip id=%s: base_id 없음", clip_id)
            continue

        hook_image = _resolve_path(repo, row.get("hook_image_path") or "")
        if not hook_image or not os.path.exists(hook_image):
            hook_image = _default_hook_image(clip_id, subdir="conversation")
            if not os.path.exists(hook_image):
                hook_image = _default_hook_image(clip_id)
            if not os.path.exists(hook_image):
                hook_image = ""

        clip = _common_clip_fields(
            row,
            clip_id=clip_id,
            topic=topic,
            hook_image=hook_image,
            repo=repo,
            index=i,
            clip_type=CLIP_TYPE_CONVERSATION,
        )
        clip["base_id"] = base_id
        base = bases.get(base_id)
        if base is None:
            logger.warning("shorts conversation clip id=%s: base_id=%s 없음", clip_id, base_id)
            continue
        _merge_base_into_clip(clip, base, repo)
        clip["video_path"] = _resolve_conversation_video_path(
            row, clip_id=clip_id, topic=topic, base=base, repo=repo
        )
        if not clip["sentence"]:
            continue
        out.append(clip)

    logger.info("shorts 회화 클립 로드: %d개 (%s)", len(out), path)
    return out


def _split_pipe_field(raw: str) -> list[str]:
    """CSV `|` 구분 (쉼표 대체 `，` 허용)."""
    return [p.strip() for p in str(raw or "").replace("，", "|").split("|") if p.strip()]


def parse_vocab_word_ids_field(raw: str) -> list[int]:
    """word_id 셀: `20501` 또는 `20501|20504|20505`."""
    ids: list[int] = []
    seen: set[int] = set()
    for part in _split_pipe_field(raw):
        try:
            wid = int(float(part))
        except (TypeError, ValueError):
            continue
        if wid < 1 or wid in seen:
            continue
        seen.add(wid)
        ids.append(wid)
    return ids


def parse_vocab_int_list_field(
    raw: str,
    word_count: int,
    *,
    default: int = 1,
    minimum: int = 1,
) -> list[int]:
    """`| ` 구분 정수. 1개면 모든 단어 동일."""
    if word_count < 1:
        return []
    parts = _split_pipe_field(raw)
    if not parts:
        return [max(minimum, int(default))] * word_count

    vals: list[int] = []
    for part in parts:
        try:
            vals.append(max(minimum, int(float(part))))
        except (TypeError, ValueError):
            vals.append(max(minimum, int(default)))
    if len(vals) == 1:
        return vals * word_count
    if len(vals) < word_count:
        vals.extend([vals[-1]] * (word_count - len(vals)))
    return vals[:word_count]


def _parse_bool_token(part: str, *, default: bool) -> bool:
    s = str(part or "").strip().lower()
    if not s:
        return default
    if s in ("1", "true", "yes", "y", "on", "t"):
        return True
    if s in ("0", "false", "no", "n", "off", "f"):
        return False
    return default


def parse_vocab_bool_list_field(
    raw: str,
    word_count: int,
    *,
    default: bool = True,
) -> list[bool]:
    """`| ` 구분 bool. 1개면 모든 단어 동일. true/1/yes → 뜻 TTS 재생."""
    if word_count < 1:
        return []
    parts = _split_pipe_field(raw)
    if not parts:
        return [default] * word_count

    vals: list[bool] = [_parse_bool_token(p, default=default) for p in parts]
    if len(vals) == 1:
        return vals * word_count
    if len(vals) < word_count:
        vals.extend([vals[-1]] * (word_count - len(vals)))
    return vals[:word_count]


def parse_vocab_float_list_field(
    raw: str,
    word_count: int,
    *,
    default: float = 0.0,
) -> list[float]:
    """`| ` 구분 실수(초). 1개면 모든 단어 동일."""
    if word_count < 1:
        return []
    parts = _split_pipe_field(raw)
    if not parts:
        return [max(0.0, float(default))] * word_count

    vals: list[float] = []
    for part in parts:
        try:
            vals.append(max(0.0, float(part)))
        except (TypeError, ValueError):
            vals.append(max(0.0, float(default)))
    if len(vals) == 1:
        return vals * word_count
    if len(vals) < word_count:
        vals.extend([vals[-1]] * (word_count - len(vals)))
    return vals[:word_count]


def parse_vocab_hook_titles_field(raw: str, word_count: int) -> list[str]:
    """hook_title 셀: 1개면 모든 단어 동일, 여러 개면 word_id 순서와 짝."""
    if word_count < 1:
        return []
    parts = [p.replace("\\n", "\n") for p in _split_pipe_field(raw)]
    if not parts:
        return [""] * word_count
    if len(parts) == 1:
        return parts * word_count
    if len(parts) < word_count:
        parts.extend([parts[-1]] * (word_count - len(parts)))
    return parts[:word_count]


def _vocab_word_clip_id(topic_row_id: int, word_index: int) -> int:
    """topic CSV id 하나 → 단어 클립별 내부 id (판다 이미지 등)."""
    if word_index < 1:
        return int(topic_row_id)
    return int(topic_row_id) * 1000 + int(word_index)


def _topic_intro_from_row(
    row: dict[str, str],
    *,
    clip_id: int,
    topic: str,
    repo: Path,
) -> dict[str, Any]:
    """topic 인트로 1회용 (행의 video_path·ko_narration_id)."""
    intro_titles = parse_vocab_hook_titles_field(row.get("hook_title") or "", 1)
    hook = intro_titles[0] if intro_titles else resolve_hook_title(row)
    return {
        "topic": topic,
        "clip_id": int(clip_id),
        "clip_type": CLIP_TYPE_VOCABULARY,
        "hook_title": hook,
        "ko_narration_id": _parse_ko_narration_id(row),
        "video_path": _resolve_vocabulary_video_path(
            row, clip_id=max(1, int(clip_id)), topic=topic, repo=repo
        ),
    }


def extract_vocab_topic_intro(clips: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """단어 클립 목록에 붙은 topic_intro (첫 클립 기준)."""
    if not clips:
        return None
    intro = clips[0].get("topic_intro")
    if isinstance(intro, dict) and (
        (intro.get("video_path") or "").strip()
        or int(intro.get("ko_narration_id") or 0) > 0
    ):
        return intro
    return None


def topic_intro_configured(intro: Optional[dict[str, Any]]) -> bool:
    if not intro:
        return False
    if int(intro.get("ko_narration_id") or 0) > 0:
        return True
    return bool((intro.get("video_path") or "").strip())


def build_shorts_vocabulary_clip_list(
    csv_path: str | Path | None = None,
    *,
    session_topics: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """shorts_vocabulary_clips.csv + words 조인.

  topic당 CSV 행 1개(id). word_id·hook_title는 `|` 로 복수 지정.
  hook_title 1개만 있으면 모든 단어에 동일 적용.
    """
    path = Path(csv_path) if csv_path else DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV
    repo = _REPO_ROOT
    topic_set: Optional[set[str]] = None
    if session_topics:
        topic_set = {t.strip().lower() for t in session_topics if t.strip()}

    topic_intros: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    clip_index = 0
    for row in _read_shorts_csv(path, label="shorts_vocabulary_clips"):
        try:
            topic_row_id = int(float(row.get("id") or "0"))
        except (TypeError, ValueError):
            continue
        if topic_row_id < 1:
            continue
        topic = (row.get("topic") or "").strip()
        if not _topic_matches(topic, topic_set):
            continue

        word_ids = parse_vocab_word_ids_field(row.get("word_id") or "")
        if not word_ids:
            logger.warning(
                "shorts vocabulary topic id=%s: word_id 없음 (| 구분)",
                topic_row_id,
            )
            continue

        hook_titles = parse_vocab_hook_titles_field(
            row.get("hook_title") or "", len(word_ids)
        )
        if not any(hook_titles):
            logger.warning(
                "shorts vocabulary topic id=%s: hook_title 없음, 스킵",
                topic_row_id,
            )
            continue

        topic_key = topic.lower()
        topic_intros[topic_key] = _topic_intro_from_row(
            row, clip_id=topic_row_id, topic=topic, repo=repo
        )
        sound_repeat_counts = parse_vocab_int_list_field(
            row.get("sound_repeat_count") or "",
            len(word_ids),
            default=1,
            minimum=1,
        )
        after_sound_delays = parse_vocab_float_list_field(
            row.get("after_sound_delay_sec") or "",
            len(word_ids),
            default=0.0,
        )
        read_meaning_ko_flags = parse_vocab_bool_list_field(
            row.get("read_meaning_ko") or "",
            len(word_ids),
            default=True,
        )

        for wi, word_id in enumerate(word_ids, start=1):
            word_clip_id = _vocab_word_clip_id(topic_row_id, wi)
            hook_image = _default_hook_image(word_clip_id, subdir="vocabulary")
            if not os.path.exists(hook_image):
                hook_image = _default_hook_image(topic_row_id, subdir="vocabulary")
            if not os.path.exists(hook_image):
                hook_image = ""

            word_row = {
                "id": str(topic_row_id),
                "topic": topic,
                "word_id": str(word_id),
                "hook_title": hook_titles[wi - 1],
                "ko_narration_id": "0",
                "video_path": "",
            }
            clip = _common_clip_fields(
                word_row,
                clip_id=word_clip_id,
                topic=topic,
                hook_image=hook_image,
                repo=repo,
                index=clip_index,
                clip_type=CLIP_TYPE_VOCABULARY,
                sound_from_row=False,
                use_syllable_times_ms=False,
            )
            clip["video_path"] = ""
            clip["ko_narration_id"] = 0
            clip["topic_row_id"] = topic_row_id
            clip["hook_title"] = hook_titles[wi - 1]
            clip["sound_repeat_count"] = sound_repeat_counts[wi - 1]
            clip["after_sound_delay_sec"] = after_sound_delays[wi - 1]
            clip["read_meaning_ko"] = read_meaning_ko_flags[wi - 1]
            word = get_word(word_id)
            if word is None:
                logger.warning(
                    "shorts vocabulary topic id=%s: word_id=%s 없음",
                    topic_row_id,
                    word_id,
                )
                continue
            _merge_word_into_clip(clip, word, repo)
            if not clip["sentence"]:
                continue
            out.append(clip)
            clip_index += 1

    for clip in out:
        key = (clip.get("topic") or "").strip().lower()
        clip["topic_intro"] = topic_intros.get(key, {})

    if not out and session_topics:
        out = _build_vocab_clips_from_vocabulary_word_rows(session_topics, repo)
        if out:
            logger.info(
                "shorts_vocabulary_clips에 해당 topic 없음 → vocabulary_word_rows %d개 클립",
                len(out),
            )

    n_intro = sum(1 for t in topic_intros.values() if topic_intro_configured(t))
    logger.info(
        "shorts 단어 클립 로드: %d개, topic 인트로 %d개 (%s)",
        len(out),
        n_intro,
        path,
    )
    return out


def _build_vocab_clips_from_vocabulary_word_rows(
    session_topics: list[str],
    repo: Path,
) -> list[dict[str, Any]]:
    """shorts_vocabulary_clips 비었을 때 vocabulary_word_rows로 숏츠 단어 클립 합성."""
    from core.paths import DEFAULT_VOCABULARY_WORD_ROWS_CSV
    from data.table_manager import (
        load_vocabulary_word_rows_from_csv,
        select_vocabulary_word_rows_for_session_topics,
    )

    load_vocabulary_word_rows_from_csv(DEFAULT_VOCABULARY_WORD_ROWS_CSV)
    rows = select_vocabulary_word_rows_for_session_topics(list(session_topics))
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        word_id = int(row.word_id)
        if word_id < 1:
            continue
        word = get_word(word_id)
        if word is None:
            logger.warning("vocabulary_word_rows id=%s: word_id=%s 없음", row.id, word_id)
            continue
        clip_id = int(row.id) if int(row.id) > 0 else word_id
        topic = (row.topic or "").strip()
        hanzi = (word.word or "").strip()
        hook_title = (row.desc or "").strip() or (
            f"{hanzi} 뜻을 외워보세요" if hanzi else "단어 뜻을 외워보세요"
        )
        hook_image = _default_hook_image(clip_id, subdir="vocabulary")
        if not os.path.exists(hook_image):
            hook_image = _default_hook_image(clip_id)
        if not os.path.exists(hook_image):
            hook_image = ""
        csv_row = {
            "id": str(clip_id),
            "topic": topic,
            "word_id": str(word_id),
            "hook_title": hook_title,
            "ko_narration_id": "0",
            "video_path": "",
        }
        clip = _common_clip_fields(
            csv_row,
            clip_id=clip_id,
            topic=topic,
            hook_image=hook_image,
            repo=repo,
            index=i,
            clip_type=CLIP_TYPE_VOCABULARY,
            sound_from_row=False,
            use_syllable_times_ms=False,
        )
        _merge_word_into_clip(clip, word, repo)
        if not clip["sentence"]:
            continue
        clip["topic_intro"] = {}
        clip["read_meaning_ko"] = True
        out.append(clip)
    return out


def build_shorts_clip_list(
    *,
    shorts_mode: str,
    csv_path: str | Path | None = None,
    session_topics: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """shorts_mode에 맞는 전용 CSV에서 클립 목록을 만든다."""
    try:
        from data.ko_narration_loader import load_ko_narration_tables

        load_ko_narration_tables()
    except Exception as ex:
        logger.debug("ko_narration 테이블 로드 생략: %s", ex)

    mode = normalize_clip_type(shorts_mode)
    if mode == CLIP_TYPE_VOCABULARY:
        return build_shorts_vocabulary_clip_list(csv_path, session_topics=session_topics)
    return build_shorts_conversation_clip_list(csv_path, session_topics=session_topics)
