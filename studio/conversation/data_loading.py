"""회화 스튜디오 데이터 로딩: CSV/테이블/LoadedContent → 재생용 data_list."""
import csv
import json
import logging
import os
from pathlib import Path
from typing import Any

from utils.pinyin_processor import get_pinyin_processor
from utils.syllable_timing import parse_syllable_times_ms

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
    trans = row.get("translation", "")
    if isinstance(sen, str):
        sen = [sen] if sen else []
    if isinstance(trans, str):
        trans = [trans] if trans else []
    words_raw = (row.get("words") or "").strip()
    words_list = [w.strip() for w in words_raw.split("|") if w.strip()] if words_raw else []

    start_sec = _parse_time_sec(row.get("start_time") or row.get("start_ms", 0))
    end_raw = row.get("end_time") or row.get("end_ms") or row.get("split_ms")
    end_sec = _parse_time_sec(end_raw, -1.0) if end_raw not in (None, "") else -1.0

    sound_l1 = (row.get("sound_l1") or row.get("sound_level1_path") or "").strip()
    sound_l2 = (row.get("sound_l2") or row.get("sound_level2_path") or "").strip()
    if sound_l1 and not os.path.isabs(sound_l1):
        sound_l1 = str(repo / sound_l1.replace("\\", "/"))
    if sound_l2 and not os.path.isabs(sound_l2):
        sound_l2 = str(repo / sound_l2.replace("\\", "/"))

    syllable_times_l1 = parse_syllable_times_ms(str(row.get("syllable_times_l1_ms") or "").strip())
    syllable_times_l2 = parse_syllable_times_ms(str(row.get("syllable_times_l2_ms") or "").strip())

    pinyin_marks = (row.get("pinyin_marks") or row.get("pinyin") or "").strip()
    pinyin_phonetic = (row.get("pinyin_phonetic") or "").strip()
    pinyin_lexical = (row.get("pinyin_lexical") or "").strip()

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


def _data_list_from_loaded_content(content: Any) -> list[dict]:
    """LoadedContent에서 재생용 _data_list 생성. segment/overlay 쌍당 한 항목."""
    try:
        from data.models import LoadedContent
        content = content if isinstance(content, LoadedContent) else LoadedContent.model_validate(content)
    except Exception:
        return []
    segments = content.video_segments
    overlays = content.overlay_items
    audio_tracks = getattr(content, "audio_tracks", []) or []
    n = min(len(segments), len(overlays))
    processor = get_pinyin_processor()
    table_rows = []
    try:
        from data.table_manager import get_table
        table_rows = get_table() or []
    except Exception:
        pass
    out = []
    for i in range(n):
        seg = segments[i]
        ov = overlays[i]
        sen_raw = ov.sentence or ov.text
        if isinstance(sen_raw, list):
            sen_str = str(sen_raw[0]) if sen_raw else ""
        else:
            sen_str = str(sen_raw or "")
        pinyin_sandhi_types = processor.get_sandhi_types(sen_str) if sen_str and processor.available else []
        sound_l1 = audio_tracks[2 * i].sound_path if len(audio_tracks) > 2 * i else ""
        sound_l2 = audio_tracks[2 * i + 1].sound_path if len(audio_tracks) > 2 * i + 1 else ""
        row = table_rows[i] if i < len(table_rows) else {}
        syllable_times_l1 = parse_syllable_times_ms(str(row.get("syllable_times_l1_ms") or "").strip())
        syllable_times_l2 = parse_syllable_times_ms(str(row.get("syllable_times_l2_ms") or "").strip())
        words_raw = (row.get("words") or "").strip()
        words_list = [w.strip() for w in words_raw.split("|") if w.strip()] if words_raw else []
        out.append({
            "video_path": seg.file_path or "",
            "start_time": seg.start_time,
            "end_time": seg.end_time,
            "sentence": [ov.sentence or ov.text] if (ov.sentence or ov.text) else [],
            "translation": [ov.translation] if ov.translation else [],
            "pinyin": (ov.pinyin or "").strip(),
            "pinyin_phonetic": (ov.pinyin_phonetic or "").strip(),
            "pinyin_lexical": (ov.pinyin_lexical or "").strip(),
            "pinyin_sandhi_types": pinyin_sandhi_types,
            "sound_l1": sound_l1,
            "sound_l2": sound_l2,
            "syllable_times_l1": syllable_times_l1,
            "syllable_times_l2": syllable_times_l2,
            "words": words_list,
            "id": str(i),
            "topic": "",
            "index": i,
        })
    return out


def _data_list_from_table_rows(rows: list[dict]) -> list[dict]:
    """테이블 행(한 행당 base 한 개)을 재생용 _data_list로 변환. sub_sentences 테이블에서 슬롯(활용) 목록을 가져와 base(0) + 활용(1,2,...) 순으로 구성."""
    if not rows:
        return []
    repo = _REPO_ROOT
    processor = get_pinyin_processor()
    from data.table_manager import get_sub_sentences_for_base, build_sub_sentence_word_list

    out: list[dict] = []
    global_index = 0
    for row in rows:
        row = dict(row)
        base_id_raw = row.get("id")
        try:
            base_id = int(base_id_raw) if base_id_raw is not None else 0
        except (TypeError, ValueError):
            base_id = 0
        base_id_str = str(base_id_raw or "")

        item = _row_to_base_item(row, global_index, repo)
        item["type"] = "base"
        item["slot_index"] = 0
        sen_str = (row.get("sentence") or "")
        if isinstance(sen_str, list):
            sen_str = sen_str[0] if sen_str else ""
        sen_str = str(sen_str).strip()
        item["pinyin_sandhi_types"] = processor.get_sandhi_types(sen_str) if sen_str and processor.available else []
        out.append(item)
        global_index += 1

        base_row = row
        base_item = item
        base_sen = base_row.get("sentence", "")
        base_trans = base_row.get("translation", "")
        if isinstance(base_sen, str):
            base_sen = [base_sen] if base_sen else []
        if isinstance(base_trans, str):
            base_trans = [base_trans] if base_trans else []
        base_pinyin = (base_row.get("pinyin_marks") or base_row.get("pinyin") or "").strip()
        words_raw = (base_row.get("words") or "").strip()
        words_list = [w.strip() for w in words_raw.split("|") if w.strip()] if words_raw else []

        sub_list = get_sub_sentences_for_base(base_id)
        for variant_index, sub in enumerate(sub_list, start=1):
            sentence_words = build_sub_sentence_word_list(base_id, sub.target_slot_order, sub.alt_word_id)
            new_sentence_str = "".join(sentence_words)
            sen = [new_sentence_str]
            trans = [sub.alt_translation or ""]

            util_item = {
                "video_path": base_item["video_path"],
                "start_time": base_item["start_time"],
                "end_time": base_item["end_time"],
                "sentence": sen,
                "translation": trans,
                "pinyin": "",
                "pinyin_phonetic": "",
                "pinyin_lexical": "",
                "sound_l1": "",
                "sound_l2": "",
                "syllable_times_l1": [],
                "syllable_times_l2": [],
                "words": words_list,
                "id": base_id_str,
                "topic": base_item["topic"],
                "index": global_index,
                "type": "util",
                "slot_index": variant_index,
                "base_sentence": base_sen,
                "base_translation": base_trans,
                "base_pinyin": base_pinyin,
                "pinyin_sandhi_types": [],
                "sentence_words": sentence_words,
                "target_slot_order": sub.target_slot_order,
            }
            out.append(util_item)
            global_index += 1

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


def build_data_list(csv_path: str, content: Any) -> list[dict]:
    """CSV 경로 또는 LoadedContent로 재생용 data_list 생성. 로딩 로직 일원화."""
    if content is not None:
        try:
            from data.table_manager import get_table
            table_rows = get_table()
            if table_rows:
                return _data_list_from_table_rows(table_rows)
            return _data_list_from_loaded_content(content)
        except Exception as e:
            logging.getLogger(__name__).debug(
                "table rows unavailable, using loaded content: %s", e, exc_info=True
            )
            return _data_list_from_loaded_content(content)
    rows = _normalize_table_rows_one_per_base(_load_conversation_csv(csv_path))
    return _data_list_from_table_rows(rows) if rows else []
