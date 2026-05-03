"""회화 스튜디오 데이터 로딩.

요구사항에 따라 기본 경로는 CSV 기반으로 재생용 `data_list`를 만든다.
`data.table_manager` 등 테이블/모델 의존성은 사용하지 않는다(CSV-only).
"""
import csv
import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional, Tuple, List, Union

from utils.pinyin_processor import get_pinyin_processor

from .constants import _REPO_ROOT

_SLOT_APPEND = "__append__"


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

    sound_lv = (
        row.get("sound_lv")
        or row.get("sound_lv_path")
        or row.get("sound_level_path")
        or row.get("sound_l1")
        or row.get("sound_level1_path")
        or row.get("sound_lv1_path")
        or row.get("sound_l2")
        or row.get("sound_level2_path")
        or row.get("sound_lv2_path")
        or ""
    ).strip()
    if sound_lv and not os.path.isabs(sound_lv):
        sound_lv = str(repo / sound_lv.replace("\\", "/"))

    pinyin_marks = (row.get("pinyin_marks") or row.get("pinyin") or "").strip()
    pinyin_phonetic = (row.get("pinyin_phonetic") or "").strip()
    pinyin_lexical = (row.get("pinyin_lexical") or "").strip()
    tip_text = str(row.get("tip") or "").strip()
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
        "sound_lv": sound_lv,
        "words": words_list,
        "id": vid,
        "topic": topic,
        "index": index,
        "type": "base",
        "slot_index": 0,
        "sub_variants": _copy_sub_variants_list(row.get("sub_variants")),
        "tip": tip_text,
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
                sound_lv = (
                    row.get("sound_lv")
                    or row.get("sound_lv_path")
                    or row.get("sound_level_path")
                    or row.get("sound_l1")
                    or row.get("sound_level1_path")
                    or row.get("sound_l2")
                    or row.get("sound_level2_path")
                    or ""
                ).strip()
                tip_text = str(row.get("tip") or "").strip()
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
                    "sound_lv": sound_lv,
                    "tip": tip_text,
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
                    "words": "",
                    "video_path": (row.get("video_path") or "").strip(),
                    "start_ms": row.get("video_start_ms") or 0,
                    "end_ms": row.get("video_end_ms") or -1,
                    "sound_lv": (
                        row.get("sound_lv_path")
                        or row.get("sound_lv1_path")
                        or row.get("sound_lv2_path")
                        or ""
                    ).strip(),
                    "tip": (row.get("tip") or "").strip(),
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
                
                target_slot_orders = _parse_target_slot_orders(row.get("target_slot_order"))
                alt_word_ids = _parse_alt_word_ids(row.get("alt_word_id"))
                if not target_slot_orders or not alt_word_ids:
                    continue

                item = {
                    "id": int(float(str(row.get("id") or 0).strip())),
                    # 하위 호환: 단일 슬롯/단어를 쓰는 기존 코드도 동작하게 첫 값을 유지한다.
                    "target_slot_order": target_slot_orders[0],
                    "alt_word_id": alt_word_ids[0],
                    # 신규: 다중 치환 지원.
                    "target_slot_orders": target_slot_orders,
                    "alt_word_ids": alt_word_ids,
                    "alt_translation": str(row.get("alt_translation") or "").strip(),
                    "alt_sound_path": str(row.get("alt_sound_path") or "").strip(),
                }
                
                grouped.setdefault(base_id, []).append(item)
                
            except (ValueError, TypeError) as e:
                print(f"CSV {i+1}행 데이터 오류 (base_id: {row.get('base_id')}): {e}")
                continue

    # PRACTICE 순서는 sub_sentences.id 오름차순으로 고정한다.
    for base_id in grouped:
        grouped[base_id].sort(key=lambda x: x["id"])
        
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


def _split_csv_multi_value(raw: Any) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    # 다중 값 표준 구분자는 파이프(|)로 통일한다.
    chunks = text.split("|")
    return [c.strip() for c in chunks if c is not None and c.strip()]


def _parse_target_slot_orders(raw: Any) -> list[Union[int, str, float]]:
    """슬롯 순서. 한 슬롯을 여러 단어로 쪼갤 때 `0|0.1|0.2`처럼 소수로 순서만 구분한다."""
    out: list[Union[int, str, float]] = []
    for token in _split_csv_multi_value(raw):
        t = token.strip().lower()
        if t in ("-1", "front", "start", "prefix", "맨앞", "앞"):
            out.append(-1)
            continue
        if t in ("end", "last", "suffix", "맨끝", "끝"):
            out.append(_SLOT_APPEND)
            continue
        try:
            v = float(token)
        except (TypeError, ValueError):
            continue
        # 정수 슬롯은 int 유지(기존 비교·모델 호환). 소수만 float로 유지.
        if v.is_integer():
            out.append(int(v))
        else:
            out.append(v)
    return out


def _parse_alt_word_ids(raw: Any) -> list[int]:
    out: list[int] = []
    for token in _split_csv_multi_value(raw):
        try:
            out.append(int(float(token)))
        except (TypeError, ValueError):
            continue
    return out


def _zip_slot_orders_and_alt_word_ids(
    *,
    target_slot_orders: list[Union[int, str, float]],
    alt_word_ids: list[int],
) -> list[tuple[Union[int, str, float], int]]:
    if not target_slot_orders or not alt_word_ids:
        return []
    if len(target_slot_orders) == len(alt_word_ids):
        return list(zip(target_slot_orders, alt_word_ids))
    if len(target_slot_orders) == 1:
        return [(target_slot_orders[0], wid) for wid in alt_word_ids]
    if len(alt_word_ids) == 1:
        return [(slot, alt_word_ids[0]) for slot in target_slot_orders]
    n = min(len(target_slot_orders), len(alt_word_ids))
    return list(zip(target_slot_orders[:n], alt_word_ids[:n]))


def _sort_key_slot_order(slot_order: Any) -> tuple[int, float]:
    """다중 치환 적용·표시 순서: 맨앞(-1) → 본문 슬롯(소수 포함 정렬) → 맨끝(append)."""
    if slot_order == _SLOT_APPEND:
        return (2, 1e12)
    if slot_order == -1:
        return (0, -1.0)
    try:
        return (1, float(slot_order))
    except (TypeError, ValueError):
        return (3, 0.0)


def _sort_resolved_replacements(
    resolved: list[tuple[Union[int, str, float], int, str]],
) -> list[tuple[Union[int, str, float], int, str]]:
    return sorted(resolved, key=lambda x: _sort_key_slot_order(x[0]))


def _replace_multiple_slots_in_raw_sentence(
    raw_sentence: str,
    *,
    replacements: list[tuple[Union[int, str, float], str]],
) -> str:
    """원문 슬롯 여러 개를 바꾸고, 필요 시 문장 앞/뒤에 단어를 붙여 display 문장을 만든다."""
    if not raw_sentence:
        return ""

    slot_words = _raw_sentence_to_words(raw_sentence)
    if not slot_words:
        return ""

    # 슬롯 밖 텍스트(문장부호 포함)를 보존한다.
    literals: list[str] = []
    cursor = 0
    for m in re.finditer(r"\{([^}]*)\}", raw_sentence):
        literals.append(raw_sentence[cursor : m.start()])
        cursor = m.end()
    literals.append(raw_sentence[cursor:])
    if len(literals) != len(slot_words) + 1:
        return _raw_sentence_to_display(raw_sentence)

    merged_slots = list(slot_words)
    prefix_words: list[str] = []
    suffix_words: list[str] = []

    # 동일한 정수 슬롯(예: 0, 0.1, 0.2)은 순서대로 이어 붙여 한 칸을 여러 음절로 확장한다.
    by_base: defaultdict[int, list[tuple[float, str]]] = defaultdict(list)

    for slot_order, new_word in replacements:
        w = str(new_word or "").strip()
        if not w:
            continue
        if slot_order == _SLOT_APPEND:
            suffix_words.append(w)
            continue
        if slot_order == -1:
            prefix_words.append(w)
            continue
        try:
            order_f = float(slot_order)
        except (TypeError, ValueError):
            continue
        if order_f < 0:
            continue
        base_i = int(order_f)
        by_base[base_i].append((order_f, w))

    for base_i, pairs in by_base.items():
        if not pairs:
            continue
        pairs.sort(key=lambda x: x[0])
        merged = "".join(p for _, p in pairs)
        if 0 <= base_i < len(merged_slots):
            merged_slots[base_i] = merged
        else:
            suffix_words.append(merged)

    parts: list[str] = []
    parts.extend(prefix_words)
    for i, slot_word in enumerate(merged_slots):
        parts.append(literals[i])
        parts.append(slot_word)
    parts.append(literals[-1])
    parts.extend(suffix_words)
    return "".join(parts).strip()


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


def _find_word_span_in_display_sentence(display_sentence: str, word: str) -> Optional[Tuple[int, int]]:
    target = str(word or "").strip()
    text = str(display_sentence or "")
    if not text or not target:
        return None
    pos = text.find(target)
    if pos < 0:
        return None
    return pos, len(target)


def _find_word_span_in_display_sentence_from(
    display_sentence: str,
    word: str,
    *,
    start_pos: int = 0,
) -> Optional[Tuple[int, int]]:
    target = str(word or "").strip()
    text = str(display_sentence or "")
    if not text or not target:
        return None
    pos = text.find(target, max(0, int(start_pos)))
    if pos < 0:
        return None
    return pos, len(target)


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
            raw_slot_orders = v.get("target_slot_orders")
            if isinstance(raw_slot_orders, list) and raw_slot_orders:
                slot_orders = list(raw_slot_orders)
            else:
                slot_orders = [v.get("target_slot_order", 0)]
            raw_alt_word_ids = v.get("alt_word_ids")
            if isinstance(raw_alt_word_ids, list) and raw_alt_word_ids:
                alt_word_ids = [int(x) for x in raw_alt_word_ids]
            else:
                alt_word_ids = [int(v.get("alt_word_id", 0))]
            replacement_specs = _zip_slot_orders_and_alt_word_ids(
                target_slot_orders=slot_orders,
                alt_word_ids=alt_word_ids,
            )
            if not replacement_specs:
                continue

            resolved_replacements: list[tuple[Union[int, str, float], int, str]] = []
            for slot_order, alt_word_id in replacement_specs:
                alt_word = words_by_id.get(int(alt_word_id), "").strip()
                if not alt_word:
                    continue
                resolved_replacements.append((slot_order, int(alt_word_id), alt_word))
            if not resolved_replacements:
                continue
            # 요청한 다중 치환은 "전부 성공"해야 한다.
            # 일부만 해석되면 원문 슬롯이 남아 보이므로 해당 변형을 스킵한다.
            if len(resolved_replacements) != len(replacement_specs):
                continue

            resolved_replacements = _sort_resolved_replacements(resolved_replacements)

            alt_sound_path = str(v.get("alt_sound_path") or "").strip()
            if alt_sound_path and not os.path.isabs(alt_sound_path):
                alt_sound_path = str(_REPO_ROOT / alt_sound_path.replace("\\", "/"))

            replaced_sentence = _replace_multiple_slots_in_raw_sentence(
                raw_sentence,
                replacements=[(slot_order, alt_word) for slot_order, _wid, alt_word in resolved_replacements],
            )
            if not replaced_sentence:
                continue

            primary_slot_order, primary_alt_word_id, primary_alt_word = resolved_replacements[0]
            primary_f: Optional[float] = None
            try:
                primary_f = float(primary_slot_order)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                primary_f = None
            if (
                primary_f is not None
                and primary_f >= 0
                and primary_f == int(primary_f)
                and primary_slot_order != -1
            ):
                span = _display_alt_hanzi_span(
                    raw_sentence,
                    target_slot_order=int(primary_f),
                    alt_word=primary_alt_word,
                )
            else:
                span = _find_word_span_in_display_sentence(replaced_sentence, primary_alt_word)

            variant_dict: dict[str, Any] = {
                "target_slot_order": primary_slot_order,
                "alt_word_id": primary_alt_word_id,
                "alt_word": primary_alt_word,
                "target_slot_orders": [slot for slot, _wid, _w in resolved_replacements],
                "alt_word_ids": [wid for _slot, wid, _w in resolved_replacements],
                "alt_words": [w for _slot, _wid, w in resolved_replacements],
                "replaced_sentence": replaced_sentence,
                "alt_translation": str(v.get("alt_translation") or "").strip(),
                "alt_sound_path": alt_sound_path,
            }
            # 추가/치환된 단어를 모두 하이라이트할 수 있도록 span 목록을 저장한다.
            spans: list[dict[str, int]] = []
            search_pos = 0
            for slot_order, _wid, alt_word in resolved_replacements:
                cur_span: Optional[Tuple[int, int]] = None
                try:
                    so_f = float(slot_order)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    so_f = None
                if so_f is not None and so_f >= 0 and so_f == int(so_f):
                    cur_span = _display_alt_hanzi_span(
                        raw_sentence,
                        target_slot_order=int(so_f),
                        alt_word=alt_word,
                    )
                if cur_span is None:
                    cur_span = _find_word_span_in_display_sentence_from(
                        replaced_sentence,
                        alt_word,
                        start_pos=search_pos,
                    )
                if cur_span is None:
                    continue
                start_i, len_i = int(cur_span[0]), int(cur_span[1])
                if len_i <= 0:
                    continue
                spans.append({"start": start_i, "len": len_i})
                search_pos = max(search_pos, start_i + len_i)
            if span is not None:
                variant_dict["alt_hanzi_start"] = int(span[0])
                variant_dict["alt_hanzi_len"] = int(span[1])
            if spans:
                variant_dict["alt_hanzi_spans"] = spans
            sub_variants.append(variant_dict)
        if sub_variants:
            # LearningScene의 전용 Stage에서 바로 사용할 공통 키.
            row["sub_variants"] = sub_variants
    return base_rows


def _attach_words_from_raw_sentence(base_rows: list[dict]) -> list[dict]:
    """raw_sentence 슬롯 추출로 words를 채운다."""
    if not base_rows:
        return base_rows
    for row in base_rows:
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
                    words_by_id_map[sid] = str(base_row.get("words") or "").strip()

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
        base_rows = _attach_words_from_raw_sentence(base_rows)
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
