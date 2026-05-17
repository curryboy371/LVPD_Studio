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
    trans_parts = [p for p in (first_meaning, pos) if p]
    clip["translation"] = [" · ".join(trans_parts)] if trans_parts else []
    clip["pinyin"] = (word.pinyin or "").strip()
    clip["word_img_path"] = _resolve_path(repo, (word.img_path or "").strip())
    clip["word_pos"] = pos

    sound = (clip.get("sound_path") or "").strip()
    if not sound:
        sound = (word.sound_path or "").strip()
    clip["sound_path"] = _resolve_path(repo, sound)

    if not (clip.get("situation_subtitle") or "").strip() and first_meaning:
        clip["situation_subtitle"] = first_meaning

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
) -> dict[str, Any]:
    sound_path = _resolve_path(repo, row.get("sound_path") or "")
    times_raw = row.get("syllable_times_ms") or row.get("syllable_times") or ""
    return {
        "clip_id": clip_id,
        "clip_type": clip_type,
        "base_id": 0,
        "word_id": 0,
        "topic": topic,
        "hook_title": resolve_hook_title(row),
        "hook_image_path": hook_image,
        "situation_subtitle": (row.get("situation_subtitle") or "").strip(),
        "cta_text": (row.get("cta_text") or "더 많은 내용은 본편에서!").strip(),
        "sound_path": sound_path,
        "syllable_times": parse_syllable_times_ms(times_raw),
        "sentence": [],
        "translation": [],
        "pinyin": "",
        "word_img_path": "",
        "word_pos": "",
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


def build_shorts_vocabulary_clip_list(
    csv_path: str | Path | None = None,
    *,
    session_topics: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """shorts_vocabulary_clips.csv + words 조인."""
    path = Path(csv_path) if csv_path else DEFAULT_SHORTS_VOCABULARY_CLIPS_CSV
    repo = _REPO_ROOT
    topic_set: Optional[set[str]] = None
    if session_topics:
        topic_set = {t.strip().lower() for t in session_topics if t.strip()}

    out: list[dict[str, Any]] = []
    for i, row in enumerate(_read_shorts_csv(path, label="shorts_vocabulary_clips")):
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
            logger.warning("shorts vocabulary clip id=%s: hook_title 없음, 스킵", clip_id)
            continue
        try:
            word_id = int(float(row.get("word_id") or "0"))
        except (TypeError, ValueError):
            logger.warning("shorts vocabulary clip id=%s: word_id 없음", clip_id)
            continue

        hook_image = _resolve_path(repo, row.get("hook_image_path") or "")
        if not hook_image or not os.path.exists(hook_image):
            hook_image = _default_hook_image(clip_id, subdir="vocabulary")
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
            clip_type=CLIP_TYPE_VOCABULARY,
        )
        word = get_word(word_id)
        if word is None:
            logger.warning("shorts vocabulary clip id=%s: word_id=%s 없음", clip_id, word_id)
            continue
        _merge_word_into_clip(clip, word, repo)
        if not clip["sentence"]:
            continue
        out.append(clip)

    logger.info("shorts 단어 클립 로드: %d개 (%s)", len(out), path)
    return out


def build_shorts_clip_list(
    *,
    shorts_mode: str,
    csv_path: str | Path | None = None,
    session_topics: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """shorts_mode에 맞는 전용 CSV에서 클립 목록을 만든다."""
    mode = normalize_clip_type(shorts_mode)
    if mode == CLIP_TYPE_VOCABULARY:
        return build_shorts_vocabulary_clip_list(csv_path, session_topics=session_topics)
    return build_shorts_conversation_clip_list(csv_path, session_topics=session_topics)
