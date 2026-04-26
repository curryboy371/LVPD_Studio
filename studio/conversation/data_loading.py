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
from typing import Any, Optional, Tuple, List

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


def _raw_sentence_to_words(raw: str) -> list[str]:
    """'{苹果}{多少}{钱}？'에서 중괄호 슬롯 단어만 추출."""
    if not raw:
        return []
    return [str(x).strip() for x in re.findall(r"\{([^}]*)\}", raw) if str(x).strip()]


def _copy_sub_variants_list(raw: Any) -> list[dict]:
    """항목 간 sub_variants 리스트·딕셔너리 공유로 이전 base 변형이 섞이지 않게 복사한다."""
    if not isinstance(raw, list) or not raw:
        return []
    out: list[dict] = []
    for v in raw:
        if isinstance(v, dict):
            out.append(dict(v))
    return out


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
        "words": words_list,
        "id": vid,
        "topic": topic,
        "index": index,
        "type": "base",
        "slot_index": 0,
        "sub_variants": _copy_sub_variants_list(row.get("sub_variants")),
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


def _sort_data_list_for_playback(data_list: list[dict]) -> list[dict]:
    """topic → 숫자 id 순으로 재생 목록을 고정한다.

    CSV 행 순서와 무관하게 id 1 전체(VIDEO→LEARNING→PRACTICE→sub…) 후 id 2가 오도록 한다.
    """
    if len(data_list) <= 1:
        return data_list

    def sort_key(idx_item: tuple[int, dict]) -> tuple[str, int, int]:
        i, row = idx_item
        topic = str(row.get("topic") or "").strip().lower()
        raw_id = row.get("id")
        try:
            idv = int(float(str(raw_id).strip())) if raw_id not in (None, "") else 10**9
        except (TypeError, ValueError):
            idv = 10**9
        return (topic, idv, i)

    order = sorted(range(len(data_list)), key=lambda j: sort_key((j, data_list[j])))
    out = []
    for new_index, j in enumerate(order):
        row = dict(data_list[j])
        row["index"] = new_index
        row["sub_variants"] = _copy_sub_variants_list(row.get("sub_variants"))
        out.append(row)
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
                    "raw_sentence": (row.get("raw_sentence") or "").strip(),
                    # get_table_rows() 포맷에 맞춰서 넣어둔다.
                    "sentence": _raw_sentence_to_display((row.get("raw_sentence") or "").strip()),
                    "translation": (row.get("translation") or "").strip(),
                    "words": (row.get("base_words") or "").strip(),
                    "video_path": (row.get("video_path") or "").strip(),
                    "start_ms": row.get("video_start_ms") or 0,
                    "end_ms": row.get("video_end_ms") or -1,
                    "sound_l1": (row.get("sound_lv1_path") or "").strip(),
                    "sound_l2": (row.get("sound_lv2_path") or "").strip(),
                    "pinyin_marks": pinyin_marks,
                    "pinyin_phonetic": pinyin_phonetic,
                    "pinyin_lexical": pinyin_lexical,
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


def _load_sub_sentences_csv(csv_path: str) -> dict[int, list[dict]]:
    path = Path(csv_path)
    if not path.exists():
        return {}
        
    grouped: dict[int, list[dict]] = {}
    
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            try:
                # 공백 제거 후 안전하게 float -> int 변환
                raw_base_id = str(row.get("base_id") or "").strip()
                if not raw_base_id:
                    continue
                
                base_id = int(float(raw_base_id))
                
                item = {
                    "id": int(float(str(row.get("id") or 0).strip())),
                    "target_slot_order": int(float(str(row.get("target_slot_order") or 0).strip())),
                    "alt_word_id": int(float(str(row.get("alt_word_id") or 0).strip())),
                    "alt_translation": str(row.get("alt_translation") or "").strip(),
                    "alt_sound_path": str(row.get("alt_sound_path") or "").strip(),
                }
                
                grouped.setdefault(base_id, []).append(item)
                
            except (ValueError, TypeError) as e:
                print(f"CSV {i+1}행 데이터 오류 (base_id: {row.get('base_id')}): {e}")
                continue

    # 정렬 로직
    for base_id in grouped:
        grouped[base_id].sort(key=lambda x: (x["target_slot_order"], x["id"]))
        
    return grouped


def _replace_slot_in_raw_sentence(raw_sentence: str, *, target_slot_order: int, new_word: str) -> str:
    """raw_sentence의 슬롯(target_slot_order)만 교체해서 표시 문장을 만든다."""
    if not raw_sentence:
        return ""
    idx = -1

    def _slot_repl(match: re.Match[str]) -> str:
        nonlocal idx
        idx += 1
        if idx == target_slot_order:
            return "{" + str(new_word or "").strip() + "}"
        return match.group(0)

    replaced_raw = re.sub(r"\{([^}]*)\}", _slot_repl, raw_sentence)
    return _raw_sentence_to_display(replaced_raw)


def _display_alt_hanzi_span(
    raw_sentence: str, *, target_slot_order: int, alt_word: str
) -> Optional[Tuple[int, int]]:
    """`raw_sentence` 슬롯 중 `target_slot_order`번을 `alt_word`로 바꾼 display 문장에서 그 한자 구간 [시작, 길이).

    `_replace_slot_in_raw_sentence`가 만든 `replaced_sentence`와 같은 좌표계.
    """
    w = (alt_word or "").strip()
    if not raw_sentence or target_slot_order < 0 or not w:
        return None
    slot_i = -1
    display_pos = 0
    i = 0
    n = len(raw_sentence)
    while i < n:
        if raw_sentence[i] == "{":
            end = raw_sentence.find("}", i + 1)
            if end < 0:
                return None
            slot_i += 1
            inner = raw_sentence[i + 1 : end]
            if slot_i == target_slot_order:
                return display_pos, len(w)
            display_pos += len(inner)
            i = end + 1
        else:
            j = i
            while j < n and raw_sentence[j] != "{":
                j += 1
            display_pos += j - i
            i = j
    return None


def _attach_sub_variants_to_base_rows(
    base_rows: list[dict],
    *,
    words_by_id: dict[int, str],
    sub_rows_by_base_id: dict[int, list[dict]],
) -> list[dict]:
    """base row에 학습 활용용 sub 변형 리스트(`sub_variants`)를 채운다."""
    if not base_rows or not sub_rows_by_base_id:
        return base_rows
    for row in base_rows:
        try:
            sid = int(float(row.get("id") or 0))
        except Exception:
            sid = 0
        variants = sub_rows_by_base_id.get(sid) or []
        if not variants:
            row.pop("sub_variants", None)
            continue
        raw_sentence = str(row.get("raw_sentence") or "").strip()
        sub_variants: list[dict] = []
        for v in variants:
            alt_word_id = int(v.get("alt_word_id", 0))
            slot_order = int(v.get("target_slot_order", 0))
            alt_word = words_by_id.get(alt_word_id, "").strip()
            if not alt_word:
                continue
            alt_sound_path = str(v.get("alt_sound_path") or "").strip()
            if alt_sound_path and not os.path.isabs(alt_sound_path):
                alt_sound_path = str(_REPO_ROOT / alt_sound_path.replace("\\", "/"))
            replaced_sentence = _replace_slot_in_raw_sentence(
                raw_sentence,
                target_slot_order=slot_order,
                new_word=alt_word,
            )
            if not replaced_sentence:
                continue
            span = _display_alt_hanzi_span(
                raw_sentence, target_slot_order=slot_order, alt_word=alt_word
            )
            variant_dict: dict[str, Any] = {
                "target_slot_order": slot_order,
                "alt_word_id": alt_word_id,
                "alt_word": alt_word,
                "replaced_sentence": replaced_sentence,
                "alt_translation": str(v.get("alt_translation") or "").strip(),
                "alt_sound_path": alt_sound_path,
            }
            if span is not None:
                variant_dict["alt_hanzi_start"] = int(span[0])
                variant_dict["alt_hanzi_len"] = int(span[1])
            sub_variants.append(variant_dict)
        if sub_variants:
            # LearningScene의 전용 Stage에서 바로 사용할 공통 키.
            row["sub_variants"] = sub_variants
    return base_rows


def _attach_words_from_base_words(base_rows: list[dict]) -> list[dict]:
    """base_words(예: 苹果|多少|钱) 우선, 없으면 raw_sentence 슬롯 추출로 words를 채운다."""
    if not base_rows:
        return base_rows
    for row in base_rows:
        base_words = str(row.get("words") or row.get("base_words") or "").strip()
        if base_words:
            words = [w.strip() for w in base_words.split("|") if w.strip()]
            if words:
                row["words"] = "|".join(words)
                continue
        raw_sentence = str(row.get("raw_sentence") or "").strip()
        raw_words = _raw_sentence_to_words(raw_sentence)
        if raw_words:
            row["words"] = "|".join(raw_words)
    return base_rows


def _filter_data_list_by_session_topics(
    data: list[dict],
    session_topics: Optional[List[str]],
) -> list[dict]:
    """`session_topics`가 있으면 `item['topic']`이 그 집합에 속하는 항목만 남긴다."""
    if not session_topics:
        return data
    ts = {str(t).strip() for t in session_topics if str(t).strip()}
    if not ts:
        return data
    return [d for d in data if str(d.get("topic") or "").strip() in ts]


def build_data_list(
    csv_path: str,
    content: Any = None,
    *,
    session_topics: Optional[List[str]] = None,
) -> list[dict]:
    """CSV 기반으로 재생용 data_list 생성.

    Args:
        csv_path: conversation CSV 경로(기본 경로).
        content: 기존 호환용(이번 리팩터링에서는 사용하지 않음).
        session_topics: 지정 시 해당 topic 문자열과 일치하는 항목만 재생 목록에 남긴다.

    Returns:
        render에 필요한 최소 키를 포함한 dict 리스트(topic·숫자 id 오름차순, index 재부여).
    """
    _ = content

    # 1) CSV 우선: 명시 경로가 있으면 conversation 전용 CSV로 처리
    csv_path = (csv_path or "").strip()
    repo = _REPO_ROOT
    if csv_path:
        rows = _load_conversation_csv(csv_path)
        # conversation CSV 경로를 쓰더라도, sub_sentences.csv 기반 활용 문장 정보를
        # 붙여야 PRACTICE의 SHOW_SUB_CONTENT 단계로 정상 전환된다.
        words_by_id: dict[int, str] = {}
        sub_rows_by_base_id: dict[int, list[dict]] = {}
        try:
            from core.paths import (
                DEFAULT_BASE_SENTENCES_CSV,
                DEFAULT_WORDS_TABLE_CSV,
                DEFAULT_SUB_SENTENCES_CSV,
            )

            words_by_id = _load_words_csv(str(DEFAULT_WORDS_TABLE_CSV))
            sub_rows_by_base_id = _load_sub_sentences_csv(str(DEFAULT_SUB_SENTENCES_CSV))
            base_rows = _load_base_sentences_csv(str(DEFAULT_BASE_SENTENCES_CSV))
            raw_sentence_by_id: dict[int, str] = {}
            for base_row in base_rows:
                try:
                    sid = int(float(base_row.get("id") or 0))
                except Exception:
                    sid = 0
                if sid:
                    raw_sentence_by_id[sid] = str(base_row.get("raw_sentence") or "").strip()
            words_by_id_map: dict[int, str] = {}
            for base_row in base_rows:
                try:
                    sid = int(float(base_row.get("id") or 0))
                except Exception:
                    sid = 0
                if sid:
                    words_by_id_map[sid] = str(base_row.get("words") or base_row.get("base_words") or "").strip()

            for row in rows:
                try:
                    sid = int(float(row.get("id") or 0))
                except Exception:
                    sid = 0
                if sid and not str(row.get("raw_sentence") or "").strip():
                    row["raw_sentence"] = raw_sentence_by_id.get(sid, "")
                if sid and not str(row.get("words") or "").strip():
                    row["words"] = words_by_id_map.get(sid, "")
        except Exception:
            # 활용 데이터 보강 실패 시에도 base 재생은 유지한다.
            pass
        # base당 1행으로 id를 확정한 뒤에 sub_variants를 붙인다(merge 전 attach 시 sid/행 불일치 방지).
        rows = _normalize_table_rows_one_per_base(rows)
        try:
            if words_by_id and sub_rows_by_base_id:
                rows = _attach_sub_variants_to_base_rows(
                    rows,
                    words_by_id=words_by_id,
                    sub_rows_by_base_id=sub_rows_by_base_id,
                )
        except Exception:
            pass
        out = _sort_data_list_for_playback(_data_list_from_csv_rows(rows, repo=repo))
        return _filter_data_list_by_session_topics(out, session_topics)

    # 2) 기본 CSV: resource/csv/base_sentences.csv 직접 로드
    try:
        from core.paths import (
            DEFAULT_BASE_SENTENCES_CSV,
            DEFAULT_WORDS_TABLE_CSV,
            DEFAULT_SUB_SENTENCES_CSV,
        )

        base_rows = _load_base_sentences_csv(str(DEFAULT_BASE_SENTENCES_CSV))
        words_by_id = _load_words_csv(str(DEFAULT_WORDS_TABLE_CSV))
        sub_rows_by_base_id = _load_sub_sentences_csv(str(DEFAULT_SUB_SENTENCES_CSV))
        base_rows = _attach_words_from_base_words(base_rows)
        base_rows = _attach_sub_variants_to_base_rows(
            base_rows,
            words_by_id=words_by_id,
            sub_rows_by_base_id=sub_rows_by_base_id,
        )
        base_rows = _normalize_table_rows_one_per_base(base_rows)
        out = _sort_data_list_for_playback(_data_list_from_csv_rows(base_rows, repo=repo))
        return _filter_data_list_by_session_topics(out, session_topics)
    except Exception as e:
        logging.getLogger(__name__).debug("base_sentences CSV direct load failed: %s", e, exc_info=True)
    return []
