"""topic별 회화 문장(base + sub variants) / 단어 리스트를 `한자 : 병음` 형식 TXT로 추출.

사용 예:
    python -m tools.export_topic_text --topic fruit_store
    python -m tools.export_topic_text --topic ""        # 전체 topic
    python -m tools.export_topic_text --topic fruit_store --out-dir release/text

회화 문장은 sub_sentences의 슬롯 치환을 적용한 실제 학습 문장을 함께 출력하며,
단어 리스트는 vocabulary_word_rows.csv 의 word_id를 words.csv에서 해석해 한자/병음을 만든다.

슬롯 치환 규칙은 `studio/conversation/data_loading.py`의 동작과 일치하도록 재현한다.
(학습 화면이 사용하는 문장과 동일한 텍스트가 나와야 의미가 있다.)
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from utils.pinyin_processor import get_pinyin_processor

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SLOT_APPEND = "__append__"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _to_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(str(val).strip()))
    except (TypeError, ValueError):
        return default


def _split_csv_multi_value(raw: Any) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    chunks = text.split("|")
    return [c.strip() for c in chunks if c is not None and c.strip()]


def _parse_target_slot_orders(raw: Any) -> list[Union[int, str, float]]:
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
    if slot_order == _SLOT_APPEND:
        return (2, 1e12)
    if slot_order == -1:
        return (0, -1.0)
    try:
        return (1, float(slot_order))
    except (TypeError, ValueError):
        return (3, 0.0)


def _raw_sentence_to_display(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\{([^}]*)\}", r"\1", raw)


def _raw_sentence_to_words(raw: str) -> list[str]:
    if not raw:
        return []
    return [str(x).strip() for x in re.findall(r"\{([^}]*)\}", raw) if str(x).strip()]


def _replace_multiple_slots_in_raw_sentence(
    raw_sentence: str,
    *,
    replacements: list[tuple[Union[int, str, float], Optional[str]]],
) -> str:
    """원문 슬롯 여러 개를 바꾸고, 필요 시 문장 앞/뒤에 단어를 붙여 display 문장을 만든다.

    `studio/conversation/data_loading.py`와 동일: 정수=슬롯 통째 교체·``None``=제거, 소수=해당 슬롯 직후 삽입.
    """
    if not raw_sentence:
        return ""
    slot_words = _raw_sentence_to_words(raw_sentence)
    if not slot_words:
        return ""

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
    slot_replacements: dict[int, str] = {}
    slots_to_remove: set[int] = set()
    insert_after: defaultdict[int, list[tuple[float, str]]] = defaultdict(list)

    for slot_order, new_word in replacements:
        if new_word is None:
            if isinstance(slot_order, int) and not isinstance(slot_order, bool) and slot_order >= 0:
                slots_to_remove.add(slot_order)
            continue
        w = str(new_word or "").strip()
        if not w:
            continue
        if slot_order == _SLOT_APPEND:
            suffix_words.append(w)
            continue
        if slot_order == -1:
            prefix_words.append(w)
            continue
        if isinstance(slot_order, int) and not isinstance(slot_order, bool):
            if slot_order < 0:
                continue
            slot_replacements[slot_order] = w
            continue
        try:
            order_f = float(slot_order)
        except (TypeError, ValueError):
            continue
        if order_f < 0:
            continue
        base_i = int(order_f)
        frac = order_f - base_i
        if frac <= 0:
            continue
        insert_after[base_i].append((order_f, w))

    for si, w in slot_replacements.items():
        if 0 <= si < len(merged_slots):
            merged_slots[si] = w
        else:
            suffix_words.append(w)

    for si in sorted(slots_to_remove, reverse=True):
        if not (0 <= si < len(merged_slots)):
            continue
        merged_slots.pop(si)
        if si + 1 < len(literals):
            literals[si] = literals[si] + literals[si + 1]
            del literals[si + 1]

    if slots_to_remove:
        remapped: defaultdict[int, list[tuple[float, str]]] = defaultdict(list)
        for k, items in insert_after.items():
            if k in slots_to_remove:
                continue
            shift = sum(1 for r in slots_to_remove if r < k)
            nk = k - shift
            if 0 <= nk < len(merged_slots):
                remapped[nk].extend(items)
        insert_after = remapped

    orphan_inserts: list[tuple[float, str]] = []
    for k in list(insert_after.keys()):
        if not (0 <= k < len(merged_slots)):
            orphan_inserts.extend(insert_after.pop(k))
    orphan_inserts.sort(key=lambda x: x[0])
    for _, w in orphan_inserts:
        suffix_words.append(w)

    for k in insert_after:
        insert_after[k].sort(key=lambda x: x[0])

    parts: list[str] = []
    parts.extend(prefix_words)
    for i, slot_word in enumerate(merged_slots):
        parts.append(literals[i])
        parts.append(slot_word)
        for _, w in insert_after.get(i, []):
            parts.append(w)
    parts.append(literals[-1])
    parts.extend(suffix_words)
    return "".join(parts).strip()


def _hanzi_pinyin_line(hanzi: str, pinyin: str) -> str:
    h = (hanzi or "").strip()
    p = (pinyin or "").strip()
    if not h:
        return ""
    if not p:
        return h
    return f"{h} : {p}"


def _make_pinyin(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    pp = get_pinyin_processor()
    if not pp.available:
        return ""
    try:
        return pp.full_convert(text)
    except Exception:
        return ""


def _load_words_index(words_csv: Path) -> dict[int, dict[str, str]]:
    """words.csv 를 id -> {word, pinyin, meaning, pos} 로 매핑."""
    out: dict[int, dict[str, str]] = {}
    for row in _read_csv_rows(words_csv):
        wid = _to_int(row.get("id"), 0)
        if not wid:
            continue
        out[wid] = {
            "word": str(row.get("word") or "").strip(),
            "pinyin": str(row.get("pinyin") or "").strip(),
            "meaning": str(row.get("meaning") or "").strip(),
            "pos": str(row.get("pos") or "").strip(),
        }
    return out


def _build_sentence_lines(
    *,
    base_rows: list[dict[str, str]],
    sub_rows: list[dict[str, str]],
    words_index: dict[int, dict[str, str]],
) -> list[str]:
    """주어진 base 행 목록(이미 topic으로 필터링됨)에 대해 회화 문장 텍스트 라인을 생성한다."""
    sub_by_base_id: dict[int, list[dict[str, Any]]] = {}
    for row in sub_rows:
        base_id = _to_int(row.get("base_id"), -1)
        if base_id < 0:
            continue
        slot_orders = _parse_target_slot_orders(row.get("target_slot_order"))
        alt_ids = _parse_alt_word_ids(row.get("alt_word_id"))
        if not slot_orders or not alt_ids:
            continue
        sub_by_base_id.setdefault(base_id, []).append({
            "id": _to_int(row.get("id"), 0),
            "target_slot_orders": slot_orders,
            "alt_word_ids": alt_ids,
            "alt_translation": str(row.get("alt_translation") or "").strip(),
        })
    for base_id in sub_by_base_id:
        sub_by_base_id[base_id].sort(key=lambda x: x["id"])

    base_rows_sorted = sorted(base_rows, key=lambda r: _to_int(r.get("id"), 0))

    lines: list[str] = []
    for idx, brow in enumerate(base_rows_sorted, start=1):
        base_id = _to_int(brow.get("id"), 0)
        raw_sentence = (brow.get("raw_sentence") or "").strip()
        translation = (brow.get("translation") or "").strip()
        display = _raw_sentence_to_display(raw_sentence)
        if not display:
            continue

        lines.append(f"[{idx}] id={base_id}")
        lines.append(_hanzi_pinyin_line(display, _make_pinyin(display)))
        if translation:
            lines.append(f"    → {translation}")

        variants = sub_by_base_id.get(base_id) or []
        sub_idx = 0
        for v in variants:
            replacement_specs = _zip_slot_orders_and_alt_word_ids(
                target_slot_orders=v["target_slot_orders"],
                alt_word_ids=v["alt_word_ids"],
            )
            if not replacement_specs:
                continue
            resolved: list[tuple[Union[int, str, float], int, Optional[str]]] = []
            spec_ok = True
            for slot_order, alt_word_id in replacement_specs:
                wid = int(alt_word_id)
                if wid == 0:
                    resolved.append((slot_order, wid, None))
                    continue
                w = (words_index.get(wid, {}).get("word") or "").strip()
                if not w:
                    spec_ok = False
                    break
                resolved.append((slot_order, wid, w))
            if not spec_ok or len(resolved) != len(replacement_specs):
                continue
            resolved.sort(key=lambda x: _sort_key_slot_order(x[0]))
            replaced = _replace_multiple_slots_in_raw_sentence(
                raw_sentence,
                replacements=[(slot, w) for slot, _wid, w in resolved],
            )
            replaced = (replaced or "").strip()
            if not replaced:
                continue
            sub_idx += 1
            prefix = f"  ({idx}-{sub_idx})"
            lines.append(f"{prefix} {_hanzi_pinyin_line(replaced, _make_pinyin(replaced))}")
            alt_trans = v.get("alt_translation") or ""
            if alt_trans:
                lines.append(f"        → {alt_trans}")

        lines.append("")
    return lines


def _build_word_lines(
    *,
    topic: str,
    vocab_rows: list[dict[str, str]],
    words_index: dict[int, dict[str, str]],
) -> list[str]:
    """vocabulary_word_rows.csv 에서 topic에 해당하는 단어들을 한자 : 병음 형식으로 출력."""
    selected: list[tuple[int, int]] = []
    for row in vocab_rows:
        row_topic = (row.get("topic") or "").strip()
        if topic and row_topic != topic:
            continue
        rid = _to_int(row.get("id"), 0)
        wid = _to_int(row.get("word_id"), 0)
        if not wid:
            continue
        selected.append((rid, wid))
    selected.sort(key=lambda x: x[0])

    seen_word_ids: set[int] = set()
    lines: list[str] = []
    for seq, (_rid, wid) in enumerate(selected, start=1):
        if wid in seen_word_ids:
            continue
        seen_word_ids.add(wid)
        info = words_index.get(wid)
        if not info:
            lines.append(f"{seq}. (word_id={wid}) — words.csv 에 없음")
            continue
        hanzi = info["word"]
        pinyin = info["pinyin"] or _make_pinyin(hanzi)
        meaning = info["meaning"]
        pos = info["pos"]
        line = f"{seq}. {_hanzi_pinyin_line(hanzi, pinyin)}"
        extras: list[str] = []
        if pos:
            extras.append(pos)
        if meaning:
            extras.append(meaning)
        if extras:
            line = f"{line}    [{' / '.join(extras)}]"
        lines.append(line)
    return lines


def _resolve_topics(base_rows: list[dict[str, str]], requested: str) -> list[str]:
    """topic 인자가 비면 base_sentences.csv 에서 사용된 topic 전체를 출력 대상으로 한다."""
    if requested:
        return [requested]
    seen: list[str] = []
    seen_set: set[str] = set()
    for row in base_rows:
        t = (row.get("topic") or "").strip()
        if not t or t in seen_set:
            continue
        seen.append(t)
        seen_set.add(t)
    return seen


def _write_topic_text(
    *,
    topic: str,
    out_path: Path,
    base_rows_all: list[dict[str, str]],
    sub_rows: list[dict[str, str]],
    vocab_rows: list[dict[str, str]],
    words_index: dict[int, dict[str, str]],
) -> tuple[int, int]:
    """단일 topic 텍스트 파일 작성. (회화 문장 수, 단어 수) 반환."""
    base_rows = [r for r in base_rows_all if (r.get("topic") or "").strip() == topic]
    sentence_lines = _build_sentence_lines(
        base_rows=base_rows,
        sub_rows=sub_rows,
        words_index=words_index,
    )
    word_lines = _build_word_lines(
        topic=topic,
        vocab_rows=vocab_rows,
        words_index=words_index,
    )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = [
        f"# topic: {topic}",
        f"# 생성일: {timestamp}",
        "# 형식: 한자 : 병음 (회화 문장은 base 1줄, sub 변형은 (i-j) 들여쓰기)",
        "",
    ]
    body: list[str] = []
    body.append("=== 회화 문장 (base + sub variants) ===")
    if sentence_lines:
        body.extend(sentence_lines)
    else:
        body.append("(데이터 없음)")
        body.append("")
    body.append("=== 단어 리스트 (vocabulary_word_rows) ===")
    if word_lines:
        body.extend(word_lines)
    else:
        body.append("(데이터 없음)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + body).rstrip() + "\n")

    sentence_count = sum(1 for line in sentence_lines if line.startswith("["))
    word_count = sum(1 for line in word_lines if line and line[0].isdigit())
    return sentence_count, word_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="선택한 topic의 회화 문장(base+sub) 및 단어 리스트를 `한자 : 병음` 형식 TXT로 저장."
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="",
        help="대상 topic. 비우면 base_sentences.csv 에 있는 모든 topic을 각각 출력.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="release/text",
        help="출력 디렉터리 (기본: release/text).",
    )
    args = parser.parse_args()

    csv_dir = _REPO_ROOT / "resource" / "csv"
    base_rows_all = _read_csv_rows(csv_dir / "base_sentences.csv")
    sub_rows = _read_csv_rows(csv_dir / "sub_sentences.csv")
    vocab_rows = _read_csv_rows(csv_dir / "vocabulary_word_rows.csv")
    words_index = _load_words_index(csv_dir / "words.csv")

    if not base_rows_all and not vocab_rows:
        print("[export_text] base_sentences.csv / vocabulary_word_rows.csv 둘 다 비어 있습니다.")
        return 1

    requested = (args.topic or "").strip()
    topics = _resolve_topics(base_rows_all, requested)
    if not topics:
        print(f"[export_text] 대상 topic 없음 (요청: {requested or '(전체)'} )")
        return 1

    timestamp_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = _REPO_ROOT / out_dir

    pp = get_pinyin_processor()
    if not pp.available:
        print("[warn] g2pM 미설치: 병음이 비어 있을 수 있습니다. (pip install g2pM)")

    rc = 0
    for topic in topics:
        out_path = out_dir / f"{topic or 'all'}_{timestamp_tag}.txt"
        try:
            n_sen, n_word = _write_topic_text(
                topic=topic,
                out_path=out_path,
                base_rows_all=base_rows_all,
                sub_rows=sub_rows,
                vocab_rows=vocab_rows,
                words_index=words_index,
            )
        except Exception as e:
            print(f"[export_text][{topic}] 실패: {e}")
            rc = 1
            continue
        print(f"[export_text][{topic}] 회화={n_sen}문장 / 단어={n_word}개 → {out_path}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
