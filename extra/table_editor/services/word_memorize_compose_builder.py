"""조합형(단어 조합) 세트 생성 — UI(WordMemorizeComposeSetDialog)의 핵심 로직.

words.xlsx의 결과 단어(합성어) row에 component1_id/component2_id(+선택:
example_sentence/example_translation)를 채우고, 조합형 layout JSON
(combo_layout: true)에 결과 단어를 새 box로 추가하거나 새 레이아웃을 만든다.

tools/words_batch/build_compose_layout.py(CLI, .words_compose 파일 기반)와는
별도 경로지만 같은 저장 방식(MultiSheetWorkbookStore + words.csv 재생성 +
save_layout)을 쓴다.
"""
from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
from pathlib import Path

from core.paths import DEFAULT_WORDS_TABLE_CSV, DEFAULT_WORDS_TABLE_EXCEL
from extra.table_editor.data.fields import WORDS_FIELDNAMES
from extra.table_editor.data.workbook import MultiSheetWorkbookStore
from extra.table_editor.services.word_lookup import lookup_word_details
from extra.table_editor.services.word_memorize_layout import (
    DEFAULT_LAYOUTS_DIR,
    WordMemorizeBox,
    layout_uses_compose,
    load_layout,
    save_layout,
)
from tools.csv_gen.words_table_excel_to_csv import words_table_excel_to_csv


def _load_word_components_by_id(csv_path: Path) -> dict[int, tuple[int, ...]]:
    """words.csv component1_id/component2_id(+선택: component3_id) — 조합형 결과
    단어 → 부품 word_id 2개 또는 3개(长颈鹿=长+颈+鹿 같은 3부품 조합).

    studio.studios.word_memorize_renderer.load_word_components_by_id와 같은
    로직이지만, table_editor가 pygame 의존 렌더러 모듈을 끌어들이지 않도록
    여기서 직접 CSV를 읽는다.
    """
    out: dict[int, tuple[int, ...]] = {}
    if not csv_path.is_file():
        return out
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                wid = int(float(row.get("id", 0)))
            except (TypeError, ValueError):
                continue
            try:
                c1 = int(float(row.get("component1_id") or ""))
                c2 = int(float(row.get("component2_id") or ""))
            except (TypeError, ValueError):
                continue
            ids = [c1, c2]
            try:
                c3 = int(float(row.get("component3_id") or ""))
            except (TypeError, ValueError):
                c3 = 0
            if c3:
                ids.append(c3)
            out[wid] = tuple(ids)
    return out


def _load_word_example_sentences_by_id(csv_path: Path) -> dict[int, tuple[str, str]]:
    """words.csv example_sentence/example_translation — 결과 단어 활용 문장·번역."""
    out: dict[int, tuple[str, str]] = {}
    if not csv_path.is_file():
        return out
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            try:
                wid = int(float(row.get("id", 0)))
            except (TypeError, ValueError):
                continue
            sentence = (row.get("example_sentence") or "").strip()
            if not sentence:
                continue
            translation = (row.get("example_translation") or "").strip()
            out[wid] = (sentence, translation)
    return out


@dataclass
class ComposeSetResult:
    layout_path: Path
    result_id: int
    added_new_box: bool


@dataclass
class ComposeEntry:
    """조합 세트 layout에 이미 들어있는 결과 단어 1개 — UI 목록 표시용."""

    word_id: int
    order: int
    hanzi: str
    meaning: str
    component1_id: int | None
    component1_hanzi: str
    component2_id: int | None
    component2_hanzi: str
    component3_id: int | None
    component3_hanzi: str
    sentence_zh: str
    sentence_ko: str
    word_desc: str = ""


def _find_row_by_id(
    store: MultiSheetWorkbookStore, word_id: int
) -> tuple[str, int] | None:
    wid = str(int(word_id))
    for sheet in store.sheet_names:
        rows = store.get_sheet_rows(sheet)
        for i, row in enumerate(rows):
            if (row.get("id") or "").strip() == wid:
                return sheet, i
    return None


def link_compose_component_ids(
    result_id: int,
    component1_id: int,
    component2_id: int,
    component3_id: int | None = None,
    *,
    sentence_zh: str = "",
    sentence_ko: str = "",
    excel_path: Path = DEFAULT_WORDS_TABLE_EXCEL,
) -> None:
    """words.xlsx 결과 단어 row에 component1_id/2_id(+선택: component3_id, +예문)
    기록 후 CSV 갱신. component3_id=None이면 부품 2개짜리(빈 문자열로 저장)."""
    store = MultiSheetWorkbookStore(WORDS_FIELDNAMES)
    store.load(excel_path)
    found = _find_row_by_id(store, result_id)
    if found is None:
        raise ValueError(f"결과 단어(id={result_id})를 words.xlsx에서 찾을 수 없습니다.")
    sheet, idx = found
    rows = store.get_sheet_rows(sheet)
    updated = {
        **rows[idx],
        "component1_id": str(int(component1_id)),
        "component2_id": str(int(component2_id)),
        "component3_id": str(int(component3_id)) if component3_id else "",
    }
    if sentence_zh.strip():
        updated["example_sentence"] = sentence_zh.strip()
        updated["example_translation"] = sentence_ko.strip()
    rows[idx] = updated
    store.set_sheet_rows(sheet, rows)
    store.save(excel_path)
    words_table_excel_to_csv(excel_path, DEFAULT_WORDS_TABLE_CSV, merge_all_sheets=True)


def add_result_to_layout(
    result_id: int,
    *,
    target_path: Path,
    template_path: Path | None = None,
) -> ComposeSetResult:
    """기존 조합형 layout에 결과 단어를 새 box로 추가(이미 있으면 스킵)하거나,
    target_path가 아직 없으면 template_path를 복제해 새 layout을 만든다."""
    if target_path.is_file():
        layout = load_layout(target_path)
        if not layout_uses_compose(layout):
            raise ValueError(
                f"{target_path.name}은(는) 조합형(combo_layout) 레이아웃이 아닙니다."
            )
        existing_ids = {str(b.word_id) for b in layout.boxes}
        if str(int(result_id)) in existing_ids:
            return ComposeSetResult(
                layout_path=target_path, result_id=result_id, added_new_box=False
            )
        ref = layout.boxes[-1] if layout.boxes else None
        order = len(layout.boxes) + 1
        layout.boxes.append(
            WordMemorizeBox(
                word_id=str(int(result_id)),
                order=order,
                x=ref.x if ref else 400,
                y=ref.y if ref else 724,
                w=ref.w if ref else 280,
                h=ref.h if ref else 383,
                box_key=f"box_{order}",
            )
        )
        save_layout(target_path, layout)
        return ComposeSetResult(
            layout_path=target_path, result_id=result_id, added_new_box=True
        )

    if template_path is None or not template_path.is_file():
        raise ValueError("새 조합 세트를 만들려면 참고할 템플릿 레이아웃이 필요합니다.")
    template = load_layout(template_path)
    layout = copy.deepcopy(template)
    layout.combo_layout = True
    layout.boxes = [
        WordMemorizeBox(
            word_id=str(int(result_id)), order=1, x=400, y=724, w=280, h=383, box_key="box_1"
        )
    ]
    layout.holding_word_ids = []
    save_layout(target_path, layout)
    return ComposeSetResult(layout_path=target_path, result_id=result_id, added_new_box=True)


def list_compose_entries(layout_path: Path) -> list[ComposeEntry]:
    """layout에 들어있는 결과 단어들을 순서대로 — 부품·문장 정보(words.csv)까지 채워서."""
    layout = load_layout(layout_path)
    components_by_id = _load_word_components_by_id(DEFAULT_WORDS_TABLE_CSV)
    sentences_by_id = _load_word_example_sentences_by_id(DEFAULT_WORDS_TABLE_CSV)

    entries: list[ComposeEntry] = []
    for box in layout.boxes:
        wid_str = (box.word_id or "").strip()
        if not wid_str:
            continue
        try:
            wid = int(wid_str)
        except ValueError:
            continue
        details = lookup_word_details(wid_str)
        comp_ids = components_by_id.get(wid, ())
        c1_id = comp_ids[0] if len(comp_ids) > 0 else None
        c2_id = comp_ids[1] if len(comp_ids) > 1 else None
        c3_id = comp_ids[2] if len(comp_ids) > 2 else None
        c1_hanzi = lookup_word_details(str(c1_id)).get("word", "") if c1_id else ""
        c2_hanzi = lookup_word_details(str(c2_id)).get("word", "") if c2_id else ""
        c3_hanzi = lookup_word_details(str(c3_id)).get("word", "") if c3_id else ""
        sentence_zh, sentence_ko = sentences_by_id.get(wid, ("", ""))
        entries.append(
            ComposeEntry(
                word_id=wid,
                order=box.order,
                hanzi=details.get("word", ""),
                meaning=details.get("meaning", ""),
                component1_id=c1_id,
                component1_hanzi=c1_hanzi,
                component2_id=c2_id,
                component2_hanzi=c2_hanzi,
                component3_id=c3_id,
                component3_hanzi=c3_hanzi,
                sentence_zh=sentence_zh,
                sentence_ko=sentence_ko,
                word_desc=(box.compose_desc or "").strip(),
            )
        )
    entries.sort(key=lambda e: e.order)
    return entries


def set_compose_entry_desc(result_id: int, desc: str, *, target_path: Path) -> bool:
    """layout 내 결과 단어 box의 compose_desc(왜 이 조합인지 설명)를 갱신.

    Returns 실제로 해당 word_id의 box를 찾아 갱신했으면 True.
    """
    layout = load_layout(target_path)
    wid = str(int(result_id))
    for box in layout.boxes:
        if box.word_id == wid:
            box.compose_desc = (desc or "").strip()
            save_layout(target_path, layout)
            return True
    return False


def remove_compose_entry_from_layout(result_id: int, *, target_path: Path) -> bool:
    """layout에서 결과 단어 box 제거(words.xlsx의 부품/문장 데이터는 그대로 둔다).

    Returns 실제로 제거됐으면 True, 원래 없었으면 False.
    """
    layout = load_layout(target_path)
    wid = str(int(result_id))
    before = len(layout.boxes)
    layout.boxes = [b for b in layout.boxes if b.word_id != wid]
    if len(layout.boxes) == before:
        return False
    for i, box in enumerate(layout.boxes, start=1):
        box.order = i
    save_layout(target_path, layout)
    return True


def list_combo_layout_files() -> list[tuple[str, Path]]:
    """조합형(combo_layout=true) layout JSON만 (파일명, 경로) 목록."""
    root = DEFAULT_LAYOUTS_DIR
    if not root.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for path in sorted(root.glob("*.json"), key=lambda p: p.name.lower()):
        if not path.is_file():
            continue
        try:
            if layout_uses_compose(load_layout(path)):
                out.append((path.name, path.resolve()))
        except Exception:
            continue
    return out
