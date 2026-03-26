"""회화 스튜디오 데이터 로딩.

요구사항에 따라 기본 경로는 CSV 기반으로 재생용 `data_list`를 만든다.
`data.table_manager` 등 테이블/모델 의존성은 사용하지 않는다(CSV-only).
"""
import csv
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from utils.syllable_timing import parse_syllable_times_ms
from utils.pinyin_processor import get_pinyin_processor

from .constants import _REPO_ROOT


def _parse_time_sec(val: Any, default: float = 0.0) -> float:
    """숫자 또는 문자열을 초 단위로 변환. 1000 초과면 ms로 간주."""
    try:
        x = float(val)
    except (TypeError, ValueError):
        return default
    if x > 1000:
        x = x / 1000.0
    return max(-1.0, x)


def _raw_sentence_to_display(raw: str) -> str:
    """'{苹果}{多少}{钱}？' → '苹果多少钱？'."""
    if not raw:
        return ""
    return re.sub(r"\{([^}]*)\}", r"\1", raw)


def _row_to_base_item(row: dict, index: int, repo: Path) -> dict:
    """테이블 행 하나를 재생용 base 항목 딕셔너리로 변환."""
    topic = (row.get("topic") or "").strip()
    vid = str(row.get("id") or "0").strip()
    video_path = (row.get("video_path") or "").strip()
    if not video_path and topic:
        video_path = str(repo / "resource" / "video" / topic / f"{vid}.mp4")
    elif video_path and not os.path.isabs(video_path):
        video_path = str(repo / video_path.replace("\\", "/"))
    if not os.path.exists(video_path):
        video_path = ""

    sen = row.get("sentence", "")
    if isinstance(sen, str):
        sen = _raw_sentence_to_display(sen)
    trans = row.get("translation", "")
    if isinstance(sen, str):
        sen = [sen] if sen else []
    if isinstance(trans, str):
        trans = [trans] if trans else []
    words_raw = (row.get("words") or "").strip()
    words_list = [w.strip() for w in words_raw.split("|") if w.strip()] if words_raw else []

    start_sec = _parse_time_sec(row.get("start_time") or row.get("start_ms", 0) or row.get("video_start_ms", 0))
    end_raw = row.get("end_time") or row.get("end_ms") or row.get("split_ms")
    if end_raw in (None, ""):
        end_raw = row.get("video_end_ms")
    end_sec = _parse_time_sec(end_raw, -1.0) if end_raw not in (None, "") else -1.0

    sound_l1 = (row.get("sound_l1") or row.get("sound_level1_path") or row.get("sound_lv1_path") or "").strip()
    sound_l2 = (row.get("sound_l2") or row.get("sound_level2_path") or row.get("sound_lv2_path") or "").strip()
    if sound_l1 and not os.path.isabs(sound_l1):
        sound_l1 = str(repo / sound_l1.replace("\\", "/"))
    if sound_l2 and not os.path.isabs(sound_l2):
        sound_l2 = str(repo / sound_l2.replace("\\", "/"))

    syllable_times_l1_raw = row.get("syllable_times_l1_ms")
    if syllable_times_l1_raw in (None, ""):
        syllable_times_l1_raw = row.get("syllable_times_l1")
    syllable_times_l2_raw = row.get("syllable_times_l2_ms")
    if syllable_times_l2_raw in (None, ""):
        syllable_times_l2_raw = row.get("syllable_times_l2")
    syllable_times_l1 = parse_syllable_times_ms(str(syllable_times_l1_raw or "").strip())
    syllable_times_l2 = parse_syllable_times_ms(str(syllable_times_l2_raw or "").strip())

    pinyin_marks = (row.get("pinyin_marks") or row.get("pinyin") or "").strip()
    pinyin_phonetic = (row.get("pinyin_phonetic") or "").strip()
    pinyin_lexical = (row.get("pinyin_lexical") or "").strip()
    raw_sentence = "".join(str(x) for x in sen if str(x).strip()).strip()
    if raw_sentence:
        try:
            pp = get_pinyin_processor()
            if pp.available:
                if not pinyin_marks:
                    pinyin_marks = pp.full_convert(raw_sentence)
                if not pinyin_lexical:
                    lexical_list = pp.get_lexical_pinyin(raw_sentence)
                    pinyin_lexical = " ".join(lexical_list).strip()
                if not pinyin_phonetic:
                    phonetic_list = pp.get_phonetic_pinyin(raw_sentence)
                    pinyin_phonetic = " ".join(phonetic_list).strip()
        except Exception:
            pass

    return {
        "video_path": video_path,
        "start_time": start_sec,
        "end_time": end_sec,
        "sentence": sen,
        "translation": trans,
        "pinyin": pinyin_marks,
        "pinyin_phonetic": pinyin_phonetic,
        "pinyin_lexical": pinyin_lexical,
        "sound_l1": sound_l1,
        "sound_l2": sound_l2,
        "syllable_times_l1": syllable_times_l1,
        "syllable_times_l2": syllable_times_l2,
        "words": words_list,
        "id": vid,
        "topic": topic,
        "index": index,
        "type": "base",
        "slot_index": 0,
    }


def _data_list_from_csv_rows(rows: list[dict], *, repo: Path) -> list[dict]:
    """CSV row(= base 단위)만으로 재생용 data_list 생성.

    render_only 범위에서는 util(활용 슬롯)까지 필요 없으므로,
    sub_sentences 테이블 의존성을 피하기 위해 base만 생성한다.
    """
    if not rows:
        return []
    out: list[dict] = []
    for i, row in enumerate(rows):
        row = dict(row)
        # csv loader가 id/topic/video_path/start_time/end_time을 제공한다고 가정
        out.append(_row_to_base_item(row, i, repo))
    return out


def _normalize_table_rows_one_per_base(rows: list[dict]) -> list[dict]:
    """CSV 등에서 base당 여러 행(id_0, id_1)이 올 수 있을 때, base당 1행만 남긴다. id는 base_id(int)로 통일."""
    if not rows:
        return []
    order: list[str] = []
    by_base: dict[str, dict] = {}
    for row in rows:
        row = dict(row)
        rid = str(row.get("id") or "").strip()
        if "_" in rid:
            base_id_str = rid.rsplit("_", 1)[0]
        else:
            base_id_str = rid
        if base_id_str not in by_base:
            order.append(base_id_str)
            by_base[base_id_str] = row
    out = []
    for base_id_str in order:
        row = dict(by_base[base_id_str])
        try:
            row["id"] = int(base_id_str)
        except (TypeError, ValueError):
            row["id"] = base_id_str
        out.append(row)
    return out


def _load_conversation_csv(csv_path: str) -> list[dict]:
    """CSV에서 회화 항목 리스트 로드. video_path는 resource/... 형태면 repo 기준으로 해석."""
    path = Path(csv_path)
    if not path.exists():
        return []
    repo = _REPO_ROOT

    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                topic = (row.get("topic") or "").strip()
                vid = str(row.get("id") or "0").strip()
                video_path = (row.get("video_path") or "").strip()
                if not video_path and topic:
                    video_path = str(repo / "resource" / "video" / topic / f"{vid}.mp4")
                elif video_path and not os.path.isabs(video_path):
                    video_path = str(repo / video_path.replace("\\", "/"))
                if not os.path.exists(video_path):
                    video_path = ""
                sen = row.get("sentence", "[]")
                trans = row.get("translation", "[]")
                if isinstance(sen, str) and sen.startswith("["):
                    try:
                        sen = json.loads(sen)
                    except json.JSONDecodeError:
                        sen = [sen]
                if isinstance(trans, str) and trans.startswith("["):
                    try:
                        trans = json.loads(trans)
                    except json.JSONDecodeError:
                        trans = [trans]
                if not isinstance(sen, list):
                    sen = [str(sen)]
                if not isinstance(trans, list):
                    trans = [str(trans)]
                start_sec = _parse_time_sec(row.get("start_time") or row.get("start_ms", 0))
                end_raw = row.get("end_time") or row.get("end_ms") or row.get("split_ms")
                end_sec = _parse_time_sec(end_raw, default=-1.0) if end_raw not in (None, "") else -1.0
                if end_sec > 1000:
                    end_sec = end_sec / 1000.0
                words_raw = (row.get("words") or "").strip()
                words_list = [w.strip() for w in words_raw.split("|") if w.strip()] if words_raw else []

                pinyin_marks = (row.get("pinyin_marks") or row.get("pinyin") or "").strip()
                pinyin_phonetic = (row.get("pinyin_phonetic") or "").strip()
                pinyin_lexical = (row.get("pinyin_lexical") or "").strip()
                sound_l1 = (row.get("sound_l1") or row.get("sound_level1_path") or "").strip()
                sound_l2 = (row.get("sound_l2") or row.get("sound_level2_path") or "").strip()
                syllable_times_l1_ms = (row.get("syllable_times_l1_ms") or "").strip()
                syllable_times_l2_ms = (row.get("syllable_times_l2_ms") or "").strip()

                rows.append({
                    "id": vid,
                    "topic": topic,
                    "video_path": video_path,
                    "start_time": start_sec,
                    "end_time": end_sec,
                    "start_ms": start_sec * 1000 if start_sec >= 0 else 0,
                    "end_ms": end_sec * 1000 if end_sec >= 0 else -1,
                    "sentence": sen,
                    "translation": trans,
                    "words": words_list,
                    "index": len(rows),
                    "pinyin_marks": pinyin_marks,
                    "pinyin_phonetic": pinyin_phonetic,
                    "pinyin_lexical": pinyin_lexical,
                    "sound_l1": sound_l1,
                    "sound_l2": sound_l2,
                    "syllable_times_l1_ms": syllable_times_l1_ms,
                    "syllable_times_l2_ms": syllable_times_l2_ms,
                })
            except Exception:
                continue
    return rows


def _load_base_sentences_csv(csv_path: str) -> list[dict]:
    """신규 테이블의 base_sentences.csv를 직접 읽어 재생용 row(list[dict])로 변환."""
    path = Path(csv_path)
    if not path.exists():
        return []
    rows: list[dict] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pinyin_marks = (
                    row.get("pinyin_marks")
                    or row.get("pinyin")
                    or row.get("pinyin_text")
                    or ""
                ).strip()
                pinyin_phonetic = (row.get("pinyin_phonetic") or row.get("pinyin_ipa") or "").strip()
                pinyin_lexical = (row.get("pinyin_lexical") or "").strip()
                text = _raw_sentence_to_display((row.get("raw_sentence") or "").strip())
                if text:
                    try:
                        pp = get_pinyin_processor()
                        if pp.available:
                            if not pinyin_marks:
                                pinyin_marks = pp.full_convert(text)
                            if not pinyin_lexical:
                                lexical_list = pp.get_lexical_pinyin(text)
                                pinyin_lexical = " ".join(lexical_list).strip()
                            if not pinyin_phonetic:
                                phonetic_list = pp.get_phonetic_pinyin(text)
                                pinyin_phonetic = " ".join(phonetic_list).strip()
                    except Exception:
                        pass
                rows.append({
                    "id": (row.get("id") or "").strip(),
                    "topic": (row.get("topic") or "").strip(),
                    # get_table_rows() 포맷에 맞춰서 넣어둔다.
                    "sentence": _raw_sentence_to_display((row.get("raw_sentence") or "").strip()),
                    "translation": (row.get("translation") or "").strip(),
                    "words": "",
                    "video_path": (row.get("video_path") or "").strip(),
                    "start_ms": row.get("video_start_ms") or 0,
                    "end_ms": row.get("video_end_ms") or -1,
                    "sound_l1": (row.get("sound_lv1_path") or "").strip(),
                    "sound_l2": (row.get("sound_lv2_path") or "").strip(),
                    "pinyin_marks": pinyin_marks,
                    "pinyin_phonetic": pinyin_phonetic,
                    "pinyin_lexical": pinyin_lexical,
                    "syllable_times_l1": (row.get("syllable_times_l1") or "").strip(),
                })
            except Exception:
                continue
    return rows


def _load_words_csv(csv_path: str) -> dict[int, str]:
    """words.csv를 읽어 word_id -> hanzi(word) 매핑을 만든다."""
    path = Path(csv_path)
    if not path.exists():
        return {}
    out: dict[int, str] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                wid = int(float(row.get("id") or 0))
                w = str(row.get("word") or "").strip()
                if wid and w:
                    out[wid] = w
            except Exception:
                continue
    return out


def _load_sentence_word_map_csv(csv_path: str) -> dict[int, list[int]]:
    """sentence_word_map.csv를 읽어 sentence_id -> word_id list(slot_order 순) 매핑."""
    path = Path(csv_path)
    if not path.exists():
        return {}
    tmp: dict[int, list[tuple[int, int]]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                sid = int(float(row.get("sentence_id") or 0))
                wid = int(float(row.get("word_id") or 0))
                slot = int(float(row.get("slot_order") or 0))
                if sid and wid:
                    tmp.setdefault(sid, []).append((slot, wid))
            except Exception:
                continue
    out: dict[int, list[int]] = {}
    for sid, pairs in tmp.items():
        pairs.sort(key=lambda x: x[0])
        out[sid] = [wid for _, wid in pairs]
    return out


def _attach_words_to_base_rows(
    base_rows: list[dict],
    *,
    words_by_id: dict[int, str],
    word_ids_by_sentence_id: dict[int, list[int]],
) -> list[dict]:
    """base_rows에 words 문자열(apple|...)을 채운다."""
    if not base_rows:
        return base_rows
    for row in base_rows:
        try:
            sid = int(float(row.get("id") or 0))
        except Exception:
            sid = 0
        if not sid:
            continue
        word_ids = word_ids_by_sentence_id.get(sid) or []
        if not word_ids:
            continue
        words = [words_by_id.get(wid, "").strip() for wid in word_ids]
        words = [w for w in words if w]
        if words:
            row["words"] = "|".join(words)
    return base_rows


def build_data_list(csv_path: str, content: Any = None) -> list[dict]:
    """CSV 기반으로 재생용 data_list 생성.

    Args:
        csv_path: conversation CSV 경로(기본 경로).
        content: 기존 호환용(이번 리팩터링에서는 사용하지 않음).

    Returns:
        render에 필요한 최소 키를 포함한 dict 리스트.
    """
    _ = content

    # 1) CSV 우선: 명시 경로가 있으면 conversation 전용 CSV로 처리
    csv_path = (csv_path or "").strip()
    repo = _REPO_ROOT
    if csv_path:
        rows = _load_conversation_csv(csv_path)
        rows = _normalize_table_rows_one_per_base(rows)
        return _data_list_from_csv_rows(rows, repo=repo)

    # 2) 기본 CSV: resource/csv/base_sentences.csv 직접 로드
    try:
        from core.paths import DEFAULT_BASE_SENTENCES_CSV, DEFAULT_WORDS_TABLE_CSV, DEFAULT_SENTENCE_WORD_MAP_CSV

        base_rows = _load_base_sentences_csv(str(DEFAULT_BASE_SENTENCES_CSV))
        words_by_id = _load_words_csv(str(DEFAULT_WORDS_TABLE_CSV))
        word_ids_by_sentence_id = _load_sentence_word_map_csv(str(DEFAULT_SENTENCE_WORD_MAP_CSV))
        base_rows = _attach_words_to_base_rows(
            base_rows,
            words_by_id=words_by_id,
            word_ids_by_sentence_id=word_ids_by_sentence_id,
        )
        base_rows = _normalize_table_rows_one_per_base(base_rows)
        return _data_list_from_csv_rows(base_rows, repo=repo)
    except Exception as e:
        logging.getLogger(__name__).debug("base_sentences CSV direct load failed: %s", e, exc_info=True)
    return []
