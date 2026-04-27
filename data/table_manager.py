"""
테이블 CSV 로더 및 인메모리 저장소. 재생용 테이블 행·LoadedContent 제공.
CSV → 구조체 리스트 로드, set/get 로 테이블 보관.
get_table / get_loaded_content 로 재생·스튜디오에서 사용.
"""
from __future__ import annotations

import csv
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
    SubSentence,
    VideoRange,
    VideoSegment,
    VocabularyWordRow,
    Word,
)

logger = logging.getLogger(__name__)

# 인메모리 저장소
_base_sentences: list[BaseSentence] | None = None
_words_table: list[Word] | None = None
_sub_sentences: list[SubSentence] | None = None
_vocabulary_word_rows: list[VocabularyWordRow] | None = None
# 재생용 테이블 행 (get_table_rows() 결과 저장, get_loaded_content()에서 사용)
_table: list[dict[str, Any]] | None = None


def _build_stem_index(base_dir: Path, pattern: str) -> dict[str, str]:
    """디렉터리 하위를 재귀 순회해 stem(확장자 제외 파일명) -> 상대경로 인덱스를 만든다."""
    if not base_dir.exists():
        return {}

    repo_root = base_dir.parents[1]
    index: dict[str, str] = {}
    for fp in base_dir.rglob(pattern):
        if not fp.is_file():
            continue
        key = fp.stem.strip()
        if not key or key in index:
            continue
        try:
            index[key] = str(fp.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue
    return index


def _resolve_media_path_from_name(
    raw_value: str,
    stem_index: dict[str, str],
) -> str:
    """CSV 값이 파일명이면 인덱스로 실제 경로를 찾아 반환한다."""
    value = (raw_value or "").strip()
    if not value:
        return ""
    if "/" in value or "\\" in value:
        return value.replace("\\", "/")

    as_path = Path(value)
    if as_path.suffix:
        return value.replace("\\", "/")

    hit = stem_index.get(value)
    if hit:
        return hit

    return value


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


def _normalize_pipe_list(val: Any) -> str:
    """'a| b | |c' -> 'a|b|c' 형태로 정규화한다."""
    raw = _str(val)
    if not raw:
        return ""
    items = [x.strip() for x in raw.split("|") if x.strip()]
    return "|".join(items)


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
                        base_words=_str(row.get("base_words")),
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
    from core.paths import get_repo_root

    path = Path(csv_path)
    if not path.exists():
        logger.warning("words CSV 없음: %s", path)
        set_words([])
        return []

    repo_root = get_repo_root()
    image_index = _build_stem_index(repo_root / "resource" / "image", "*")
    sound_index = _build_stem_index(repo_root / "resource" / "sound", "*.mp3")

    out: list[Word] = []
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                img_raw = _str(row.get("img_path"))
                sound_raw = _str(row.get("sound_path"))
                out.append(
                    Word(
                        id=_to_int(row.get("id"), 0),
                        word=_str(row.get("word")),
                        pinyin=_str(row.get("pinyin")),
                        pos=_normalize_pipe_list(row.get("pos")),
                        meaning=_normalize_pipe_list(row.get("meaning")),
                        img_path=_resolve_media_path_from_name(img_raw, image_index),
                        sound_path=_resolve_media_path_from_name(sound_raw, sound_index),
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
# Vocabulary word rows (단어장 행 → words.id 참조)
# ---------------------------------------------------------------------------


def load_vocabulary_word_rows_from_csv(
    csv_path: str | Path,
    encoding: str = "utf-8-sig",
) -> list[VocabularyWordRow]:
    """단어장 전용 CSV를 읽는다. 컬럼: id, topic, word_id, pronunciation_mask, desc(선택·엑셀 메모용)."""
    path = Path(csv_path)
    if not path.exists():
        logger.warning("vocabulary word rows CSV 없음: %s", path)
        set_vocabulary_word_rows([])
        return []

    out: list[VocabularyWordRow] = []
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                wid = _to_int(row.get("word_id"), 0)
                if wid < 1:
                    continue
                out.append(
                    VocabularyWordRow(
                        id=_to_int(row.get("id"), 0),
                        topic=_str(row.get("topic")),
                        word_id=wid,
                        pronunciation_mask=_str(row.get("pronunciation_mask")),
                        desc=_str(row.get("desc")),
                    )
                )
            except Exception as e:
                logger.debug("vocabulary_word_rows 행 스킵 (id=%s): %s", row.get("id"), e)

    out.sort(key=lambda r: (r.id if r.id else 10**9, r.topic, r.word_id))
    set_vocabulary_word_rows(out)
    logger.info("vocabulary_word_rows CSV 로드 완료: %s (%d개)", path, len(out))
    return out


def set_vocabulary_word_rows(rows: list[VocabularyWordRow]) -> None:
    """단어장 행 테이블을 저장한다."""
    global _vocabulary_word_rows
    _vocabulary_word_rows = list(rows) if rows else []


def get_vocabulary_word_rows() -> list[VocabularyWordRow] | None:
    """저장된 단어장 행을 반환한다. 없으면 None."""
    return _vocabulary_word_rows


def ensure_vocabulary_word_rows_loaded(
    csv_path: str | Path | None = None,
    encoding: str = "utf-8-sig",
) -> None:
    """단어장 CSV가 아직 로드되지 않았을 때만 기본 경로로 로드한다."""
    global _vocabulary_word_rows
    if _vocabulary_word_rows is not None:
        return
    from core.paths import DEFAULT_VOCABULARY_WORD_ROWS_CSV

    load_vocabulary_word_rows_from_csv(csv_path or DEFAULT_VOCABULARY_WORD_ROWS_CSV, encoding=encoding)


def select_all_vocabulary_word_rows() -> list[VocabularyWordRow]:
    """로드된 단어장 행 전체(정렬본). `--studio vocabulary` 등."""
    ensure_vocabulary_word_rows_loaded()
    table = get_vocabulary_word_rows() or []
    return sorted(
        table,
        key=lambda row: (row.id if row.id else 10**9, row.topic, row.word_id),
    )


def select_vocabulary_word_rows_for_session_topics(topics: list[str]) -> list[VocabularyWordRow]:
    """`vocabulary_word_rows`에서 CSV `topic` 컬럼이 세션 topic과 **정확히 일치**하는 행만 반환한다.

    - `topics`가 비어 있으면: 매칭할 topic이 없으므로 **빈 목록**을 반환한다.
      (단독 단어장 전체는 `select_all_vocabulary_word_rows()`를 사용한다.)
    - 빈 topic(`""`) 행은 와일드카드로 넣지 않는다.
    """
    ensure_vocabulary_word_rows_loaded()
    table = get_vocabulary_word_rows() or []
    if not table:
        return []
    topic_set = {str(t).strip() for t in topics if str(t).strip()}
    if not topic_set:
        return []
    out = [r for r in table if (r.topic or "").strip() in topic_set]
    out.sort(key=lambda row: (row.id if row.id else 10**9, row.topic, row.word_id))
    return out


# ---------------------------------------------------------------------------
# Base sentence (단일 조회)
# ---------------------------------------------------------------------------


def get_base_sentence(sentence_id: int) -> BaseSentence | None:
    """sentence_id로 기본 문장을 조회한다."""
    base_list = _base_sentences
    if not base_list:
        return None
    for b in base_list:
        if b.id == sentence_id:
            return b
    return None


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


def clear_new_tables() -> None:
    """base_sentences / words / sub_sentences / vocabulary_word_rows 저장소를 모두 비운다."""
    global _base_sentences, _words_table, _sub_sentences, _vocabulary_word_rows
    _base_sentences = None
    _words_table = None
    _sub_sentences = None
    _vocabulary_word_rows = None


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
    encoding: str = "utf-8-sig",
) -> None:
    """base_sentences / words / sub_sentences CSV를 기본 경로(또는 지정 경로)로 로드한다."""
    from core.paths import (
        DEFAULT_BASE_SENTENCES_CSV,
        DEFAULT_SUB_SENTENCES_CSV,
        DEFAULT_WORDS_TABLE_CSV,
    )
    base_sentences_path = base_sentences_path or DEFAULT_BASE_SENTENCES_CSV
    words_path = words_path or DEFAULT_WORDS_TABLE_CSV
    sub_sentences_path = sub_sentences_path or DEFAULT_SUB_SENTENCES_CSV
    load_base_sentences_from_csv(base_sentences_path, encoding=encoding)
    load_words_table_from_csv(words_path, encoding=encoding)
    load_sub_sentences_from_csv(sub_sentences_path, encoding=encoding)


# ---------------------------------------------------------------------------
# 테이블 행 변환
# ---------------------------------------------------------------------------


def _raw_sentence_to_display(raw: str) -> str:
    """'{苹果}{多少}{钱}' → '苹果多少钱' (중괄호 제거)."""
    if not raw:
        return ""
    return re.sub(r"\{([^}]*)\}", r"\1", raw)


def _raw_sentence_slot_words(raw: str) -> list[str]:
    """'{苹果}{多少}{钱}'에서 중괄호 슬롯 단어만 순서대로 추출."""
    if not raw:
        return []
    return [str(x).strip() for x in re.findall(r"\{([^}]*)\}", raw) if str(x).strip()]


def get_table_rows() -> list[dict[str, Any]]:
    """저장된 base_sentences를 재생용 행 형식으로 반환. get_loaded_content()가 기대하는 키 포함."""
    base = get_base_sentences()
    if not base:
        return []

    rows: list[dict[str, Any]] = []
    for b in base:
        words_str = (b.base_words or "").strip()
        if not words_str:
            words_str = "|".join(_raw_sentence_slot_words(b.raw_sentence))
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


