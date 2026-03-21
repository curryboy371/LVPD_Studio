"""
테이블 CSV 로더 및 인메모리 저장소. 재생용 테이블 행·LoadedContent 제공.
CSV → 구조체 리스트 로드, set/get 로 테이블 보관.
get_table / get_loaded_content 로 재생·스튜디오에서 사용.
"""
from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

from data.models import (
    AudioTrack,
    BaseSentence,
    BaseSentenceMedia,
    BaseSentenceSound,
    LoadedContent,
    OverlayItem,
    SentenceWordMap,
    SubSentence,
    VideoRange,
    VideoSegment,
    Word,
)

logger = logging.getLogger(__name__)

# 인메모리 저장소
_base_sentences: list[BaseSentence] | None = None
_words_table: list[Word] | None = None
_sub_sentences: list[SubSentence] | None = None
_sentence_word_map: list[SentenceWordMap] | None = None
# 재생용 테이블 행 (get_table_rows() 결과 저장, get_loaded_content()에서 사용)
_table: list[dict[str, Any]] | None = None


def _str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _to_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _to_float(val: Any, default: float = 0.0) -> float:
    try:
        x = float(val)
    except (TypeError, ValueError):
        return default
    return max(0.0, x)


def _parse_syllable_times_l1(val: Any) -> list[int]:
    """'[1200,1500,2000]' 또는 '1200,1500,2000' → list[int]."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return []
    s = _str(val)
    if not s:
        return []
    s = s.strip()
    if s.startswith("["):
        try:
            return [int(x) for x in json.loads(s)]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return [_to_int(x, 0) for x in s.split(",") if _str(x)]


# ---------------------------------------------------------------------------
# Base sentences
# ---------------------------------------------------------------------------


def load_base_sentences_from_csv(
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> list[BaseSentence]:
    """base_sentences.csv를 읽어 BaseSentence 리스트로 반환하고 저장소에 저장."""
    path = Path(csv_path)
    if not path.exists():
        logger.warning("base_sentences CSV 없음: %s", path)
        set_base_sentences([])
        return []

    out: list[BaseSentence] = []
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                media = BaseSentenceMedia(
                    video_path=_str(row.get("video_path")),
                    video_range=VideoRange(
                        start_ms=_to_int(row.get("video_start_ms"), 0),
                        end_ms=_to_int(row.get("video_end_ms"), 0),
                    ),
                    sound=BaseSentenceSound(
                        lv1_path=_str(row.get("sound_lv1_path")),
                        lv2_path=_str(row.get("sound_lv2_path")),
                        syllable_times_l1=_parse_syllable_times_l1(
                            row.get("syllable_times_l1")
                        ),
                    ),
                )
                out.append(
                    BaseSentence(
                        id=_to_int(row.get("id"), 0),
                        topic=_str(row.get("topic")),
                        level=_to_int(row.get("level"), 1),
                        raw_sentence=_str(row.get("raw_sentence")),
                        translation=_str(row.get("translation")),
                        life_tip=_str(row.get("life_tip")),
                        media=media,
                    )
                )
            except Exception as e:
                logger.debug("base_sentences 행 스킵 (id=%s): %s", row.get("id"), e)

    set_base_sentences(out)
    logger.info("base_sentences CSV 로드 완료: %s (%d개)", path, len(out))
    return out


def set_base_sentences(rows: list[BaseSentence]) -> None:
    """base_sentences 테이블을 저장한다."""
    global _base_sentences
    _base_sentences = list(rows) if rows else []


def get_base_sentences() -> list[BaseSentence] | None:
    """저장된 base_sentences를 반환한다. 없으면 None."""
    return _base_sentences


# ---------------------------------------------------------------------------
# Words (단어 마스터)
# ---------------------------------------------------------------------------


def load_words_table_from_csv(
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> list[Word]:
    """words.csv를 읽어 Word 리스트로 반환하고 저장소에 저장."""
    path = Path(csv_path)
    if not path.exists():
        logger.warning("words CSV 없음: %s", path)
        set_words([])
        return []

    out: list[Word] = []
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                out.append(
                    Word(
                        id=_to_int(row.get("id"), 0),
                        word=_str(row.get("word")),
                        pinyin=_str(row.get("pinyin")),
                        pos=_str(row.get("pos")),
                        meaning=_str(row.get("meaning")),
                        img_path=_str(row.get("img_path")),
                        sound_path=_str(row.get("sound_path")),
                    )
                )
            except Exception as e:
                logger.debug("words 행 스킵 (id=%s): %s", row.get("id"), e)

    set_words(out)
    logger.info("words CSV 로드 완료: %s (%d개)", path, len(out))
    return out


def set_words(rows: list[Word]) -> None:
    """words 테이블을 저장한다."""
    global _words_table
    _words_table = list(rows) if rows else []


def get_words() -> list[Word] | None:
    """저장된 words를 반환한다. 없으면 None."""
    return _words_table


def get_word(word_id: int) -> Word | None:
    """word_id로 단어를 조회한다. 없으면 None."""
    table = _words_table
    if not table:
        return None
    for w in table:
        if w.id == word_id:
            return w
    return None


def get_word_by_hanzi(hanzi: str) -> Word | None:
    """한자(단어)로 단어를 조회한다. 없으면 None."""
    if not hanzi or not isinstance(hanzi, str):
        return None
    key = hanzi.strip()
    table = _words_table
    if not table:
        return None
    for w in table:
        if (w.word or "").strip() == key:
            return w
    return None


def get_word_info_for_display(hanzi: str) -> dict[str, list[str]] | None:
    """한자로 단어 정보를 조회. 표시용 dict 반환. pos/meaning은 | 구분 문자열을 리스트로 변환.

    Returns:
        {"pos": [...], "meaning": [...]} 또는 None
    """
    w = get_word_by_hanzi(hanzi)
    if not w:
        return None
    def _pipe_list(s: str) -> list[str]:
        return [x.strip() for x in (s or "").split("|") if x.strip()]
    return {
        "pos": _pipe_list(w.pos),
        "meaning": _pipe_list(w.meaning),
    }


# ---------------------------------------------------------------------------
# Sub sentences
# ---------------------------------------------------------------------------


def load_sub_sentences_from_csv(
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> list[SubSentence]:
    """sub_sentences.csv를 읽어 SubSentence 리스트로 반환하고 저장소에 저장."""
    path = Path(csv_path)
    if not path.exists():
        logger.warning("sub_sentences CSV 없음: %s", path)
        set_sub_sentences([])
        return []

    out: list[SubSentence] = []
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                out.append(
                    SubSentence(
                        id=_to_int(row.get("id"), 0),
                        base_id=_to_int(row.get("base_id"), 0),
                        target_slot_order=_to_int(row.get("target_slot_order"), 0),
                        alt_word_id=_to_int(row.get("alt_word_id"), 0),
                        alt_translation=_str(row.get("alt_translation")),
                        alt_sound_path=_str(row.get("alt_sound_path")),
                    )
                )
            except Exception as e:
                logger.debug("sub_sentences 행 스킵 (id=%s): %s", row.get("id"), e)

    set_sub_sentences(out)
    logger.info("sub_sentences CSV 로드 완료: %s (%d개)", path, len(out))
    return out


def set_sub_sentences(rows: list[SubSentence]) -> None:
    """sub_sentences 테이블을 저장한다."""
    global _sub_sentences
    _sub_sentences = list(rows) if rows else []


def get_sub_sentences() -> list[SubSentence] | None:
    """저장된 sub_sentences를 반환한다. 없으면 None."""
    return _sub_sentences


def get_sub_sentences_for_base(base_id: int) -> list[SubSentence]:
    """base_id에 해당하는 서브 문장(슬롯 변형) 목록을 반환한다. slot_order 순 정렬."""
    table = _sub_sentences
    if not table:
        return []
    out = [s for s in table if s.base_id == base_id]
    out.sort(key=lambda s: (s.target_slot_order, s.id))
    return out


# ---------------------------------------------------------------------------
# Sentence word map
# ---------------------------------------------------------------------------


def load_sentence_word_map_from_csv(
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> list[SentenceWordMap]:
    """sentence_word_map.csv를 읽어 SentenceWordMap 리스트로 반환하고 저장소에 저장."""
    path = Path(csv_path)
    if not path.exists():
        logger.warning("sentence_word_map CSV 없음: %s", path)
        set_sentence_word_map([])
        return []

    out: list[SentenceWordMap] = []
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                out.append(
                    SentenceWordMap(
                        sentence_id=_to_int(row.get("sentence_id"), 0),
                        word_id=_to_int(row.get("word_id"), 0),
                        slot_order=_to_int(row.get("slot_order"), 0),
                        is_clickable=row.get("is_clickable", "true"),
                        is_slot_target=row.get("is_slot_target", "false"),
                    )
                )
            except Exception as e:
                logger.debug(
                    "sentence_word_map 행 스킵 (sentence_id=%s): %s",
                    row.get("sentence_id"),
                    e,
                )

    set_sentence_word_map(out)
    _fill_base_sentence_word_maps()
    logger.info("sentence_word_map CSV 로드 완료: %s (%d개)", path, len(out))
    return out


def _fill_base_sentence_word_maps() -> None:
    """저장된 base_sentences 각 항목의 word_maps를 sentence_word_map에서 채운다."""
    base = _base_sentences
    map_list = _sentence_word_map
    if not base or not map_list:
        return
    map_by_sentence: dict[int, list[SentenceWordMap]] = {}
    for m in map_list:
        map_by_sentence.setdefault(m.sentence_id, []).append(m)
    for sid in map_by_sentence:
        map_by_sentence[sid].sort(key=lambda x: x.slot_order)
    for b in base:
        b.word_maps.clear()
        b.word_maps.extend(map_by_sentence.get(b.id, []))


def set_sentence_word_map(rows: list[SentenceWordMap]) -> None:
    """sentence_word_map 테이블을 저장한다."""
    global _sentence_word_map
    _sentence_word_map = list(rows) if rows else []


def get_sentence_word_map() -> list[SentenceWordMap] | None:
    """저장된 sentence_word_map을 반환한다. 없으면 None."""
    return _sentence_word_map


def get_sentence_word_maps(sentence_id: int) -> list[SentenceWordMap]:
    """sentence_id에 해당하는 단어 배치 목록을 slot_order 순으로 반환한다."""
    table = _sentence_word_map
    if not table:
        return []
    out = [m for m in table if m.sentence_id == sentence_id]
    out.sort(key=lambda m: m.slot_order)
    return out


def get_base_sentence_word_list(base_id: int) -> list[str]:
    """base_id 문장의 단어 배열을 slot_order 순으로 반환한다.
    sentence_word_map에서 sentence_id == base_id인 행을 slot_order 순으로 가져와
    각 word_id에 해당하는 words.word를 배열로 만든다.
    예: ["苹果", "多少", "钱"]
    """
    maps = get_sentence_word_maps(base_id)
    if not maps:
        return []
    result: list[str] = []
    for m in maps:
        w = get_word(m.word_id)
        result.append((w.word or "").strip() if w else "")
    return result


def build_sub_sentence_word_list(
    base_id: int,
    target_slot_order: int,
    alt_word_id: int,
) -> list[str]:
    """Base 문장 단어 배열에서 target_slot_order 위치만 alt_word로 교체한 배열을 반환한다.
    Step 1: get_base_sentence_word_list(base_id)
    Step 2: result[target_slot_order] = get_word(alt_word_id).word
    """
    base_list = get_base_sentence_word_list(base_id)
    if not base_list or not (0 <= target_slot_order < len(base_list)):
        return list(base_list)
    alt_word = get_word(alt_word_id)
    alt_str = (alt_word.word or "").strip() if alt_word else ""
    result = list(base_list)
    result[target_slot_order] = alt_str
    return result


# ---------------------------------------------------------------------------
# Base sentence (단일 조회, word_maps 채움)
# ---------------------------------------------------------------------------


def get_base_sentence(sentence_id: int) -> BaseSentence | None:
    """sentence_id로 기본 문장을 조회한다. word_maps가 비어 있으면 채워서 반환."""
    base_list = _base_sentences
    if not base_list:
        return None
    for b in base_list:
        if b.id == sentence_id:
            if not b.word_maps and _sentence_word_map:
                maps = get_sentence_word_maps(sentence_id)
                if maps:
                    return b.model_copy(update={"word_maps": maps})
            return b
    return None


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


def clear_new_tables() -> None:
    """4개 테이블 저장소를 모두 비운다."""
    global _base_sentences, _words_table, _sub_sentences, _sentence_word_map
    _base_sentences = None
    _words_table = None
    _sub_sentences = None
    _sentence_word_map = None


# ---------------------------------------------------------------------------
# 재생용 테이블 API (set_table / get_table / get_loaded_content)
# ---------------------------------------------------------------------------


def set_table(rows: list[dict[str, Any]] | Any) -> None:
    """재생용 테이블 행을 저장한다. get_table_rows() 결과 또는 동일 형식의 리스트."""
    global _table
    try:
        import pandas as pd
        if isinstance(rows, pd.DataFrame):
            _table = rows.to_dict("records")
        else:
            _table = list(rows) if rows else None
    except ImportError:
        _table = list(rows) if rows else None


def get_table() -> list[dict[str, Any]] | None:
    """저장된 재생용 테이블 행을 반환한다. 없으면 None."""
    return _table if _table is not None else None


def clear_table() -> None:
    """재생용 테이블을 비운다."""
    global _table
    _table = None


def get_loaded_content() -> LoadedContent:
    """저장된 테이블 행에서 LoadedContent를 만들어 반환한다. 테이블이 없으면 빈 LoadedContent."""
    from core.paths import get_repo_root
    rows = get_table()
    if not rows:
        return LoadedContent()
    repo = get_repo_root()
    video_segments: list[VideoSegment] = []
    overlay_items: list[OverlayItem] = []
    audio_tracks: list[AudioTrack] = []

    for row in rows:
        topic = str(row.get("topic") or "").strip()
        row_id = str(row.get("id") or "").strip()
        if not topic and not row_id:
            continue
        vpath = str(row.get("video_path") or "").strip()
        if not vpath:
            vpath = str(Path("resource", "video", topic, f"{row_id}.mp4"))
        if not Path(vpath).is_absolute():
            vpath = str(repo / vpath)
        start_sec = _to_float(row.get("start_ms"), 0.0)
        if start_sec > 1000:
            start_sec /= 1000.0
        raw_end = row.get("end_ms")
        end_sec = _to_float(raw_end, 0.0)
        if end_sec == -1:
            end_sec = -1.0
        elif end_sec > 1000:
            end_sec /= 1000.0
        video_segments.append(
            VideoSegment(
                file_path=vpath,
                start_time=start_sec,
                end_time=end_sec,
                volume=_to_float(row.get("volume", 1.0), 1.0),
            )
        )
        sentence = str(row.get("sentence") or "").strip() or None
        translation = str(row.get("translation") or "").strip() or None
        pinyin = str(row.get("pinyin_marks") or "").strip() or None
        pinyin_phonetic = str(row.get("pinyin_phonetic") or "").strip() or None
        pinyin_lexical = str(row.get("pinyin_lexical") or "").strip() or None
        words = str(row.get("words") or "").strip() or None
        life_tips = str(row.get("life_tips") or "").strip() or None
        overlay_items.append(
            OverlayItem(
                sentence=sentence,
                translation=translation,
                pinyin=pinyin,
                pinyin_phonetic=pinyin_phonetic,
                pinyin_lexical=pinyin_lexical,
                words=words,
                life_tips=life_tips,
            )
        )
        sound_l1 = str(row.get("sound_l1") or "").strip()
        sound_l2 = str(row.get("sound_l2") or "").strip()
        if sound_l1:
            if not Path(sound_l1).is_absolute():
                sound_l1 = str(repo / sound_l1)
            audio_tracks.append(AudioTrack(sound_path=sound_l1, fade_in_sec=0.0, fade_out_sec=0.0))
        if sound_l2:
            if not Path(sound_l2).is_absolute():
                sound_l2 = str(repo / sound_l2)
            audio_tracks.append(AudioTrack(sound_path=sound_l2, fade_in_sec=0.0, fade_out_sec=0.0))

    return LoadedContent(
        video_segments=video_segments,
        overlay_items=overlay_items,
        audio_tracks=audio_tracks,
    )


def load_all_from_csv(
    base_sentences_path: str | Path | None = None,
    words_path: str | Path | None = None,
    sub_sentences_path: str | Path | None = None,
    sentence_word_map_path: str | Path | None = None,
    encoding: str = "utf-8-sig",
) -> None:
    """4개 CSV를 기본 경로(또는 지정 경로)로 로드하고, BaseSentence.word_maps를 채운다."""
    from core.paths import (
        DEFAULT_BASE_SENTENCES_CSV,
        DEFAULT_SENTENCE_WORD_MAP_CSV,
        DEFAULT_SUB_SENTENCES_CSV,
        DEFAULT_WORDS_TABLE_CSV,
    )
    base_sentences_path = base_sentences_path or DEFAULT_BASE_SENTENCES_CSV
    words_path = words_path or DEFAULT_WORDS_TABLE_CSV
    sub_sentences_path = sub_sentences_path or DEFAULT_SUB_SENTENCES_CSV
    sentence_word_map_path = sentence_word_map_path or DEFAULT_SENTENCE_WORD_MAP_CSV
    load_base_sentences_from_csv(base_sentences_path, encoding=encoding)
    load_words_table_from_csv(words_path, encoding=encoding)
    load_sub_sentences_from_csv(sub_sentences_path, encoding=encoding)
    load_sentence_word_map_from_csv(sentence_word_map_path, encoding=encoding)


# ---------------------------------------------------------------------------
# 테이블 행 변환
# ---------------------------------------------------------------------------


def _raw_sentence_to_display(raw: str) -> str:
    """'{苹果}{多少}{钱}' → '苹果多少钱' (중괄호 제거)."""
    if not raw:
        return ""
    return re.sub(r"\{([^}]*)\}", r"\1", raw)


def get_table_rows() -> list[dict[str, Any]]:
    """저장된 base_sentences를 재생용 행 형식으로 반환. get_loaded_content()가 기대하는 키 포함."""
    base = get_base_sentences()
    words_list = get_words()
    map_list = get_sentence_word_map()
    if not base:
        return []

    word_by_id: dict[int, str] = {}
    if words_list:
        word_by_id = {w.id: w.word for w in words_list}

    map_by_sentence: dict[int, list[SentenceWordMap]] = {}
    if map_list:
        for m in map_list:
            map_by_sentence.setdefault(m.sentence_id, []).append(m)
        for k in map_by_sentence:
            map_by_sentence[k].sort(key=lambda x: x.slot_order)

    rows: list[dict[str, Any]] = []
    for b in base:
        words_str = ""
        if b.id in map_by_sentence:
            words_str = "|".join(
                word_by_id.get(m.word_id, "") for m in map_by_sentence[b.id]
            )
        rows.append({
            "topic": b.topic,
            "id": b.id,
            "sentence": _raw_sentence_to_display(b.raw_sentence),
            "translation": b.translation,
            "words": words_str,
            "life_tips": b.life_tip,
            "video_path": b.media.video_path,
            "start_ms": b.media.video_range.start_ms,
            "end_ms": b.media.video_range.end_ms,
            "sound_l1": b.media.sound.lv1_path,
            "sound_l2": b.media.sound.lv2_path,
            "pinyin_marks": "",
            "pinyin_phonetic": "",
            "pinyin_lexical": "",
        })
    return rows


