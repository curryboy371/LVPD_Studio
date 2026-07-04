"""
.words_compose 파일(결과 합성어 + 부품 한자 2개, 전부 word 텍스트로 참조)을 읽어
words.xlsx의 결과 단어 row에 component1_id/component2_id를 채우고,
조합형 layout JSON(combo_layout: true)을 생성한다.

전제: 결과 합성어·부품 한자 모두 words.xlsx에 이미 있어야 한다. 새 단어(특히
부품 한자)는 이 스크립트가 만들지 않으므로, 없으면 먼저
`python -m tools.words_batch.add_words <배치>.words_add`로 추가한다. 이
스크립트는 이미 있는 단어끼리 "연결"만 하고 layout JSON을 만든다.

실행 (프로젝트 루트):
  python -m tools.words_batch.build_compose_layout tools/words_batch/서점_조합.words_compose \
      --like resource/table/word_memorize_layouts/조합_예시1.json --name 조합_서점세트

--dry-run으로 먼저 확인 권장 (저장 없이 콘솔에 layout JSON 미리보기만 출력).
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core.paths import DEFAULT_WORDS_TABLE_CSV, DEFAULT_WORDS_TABLE_EXCEL
from extra.table_editor.data.fields import WORDS_FIELDNAMES
from extra.table_editor.data.workbook import MultiSheetWorkbookStore
from extra.table_editor.services.word_memorize_layout import (
    DEFAULT_LAYOUTS_DIR,
    WordMemorizeBox,
    load_layout,
    save_layout,
)
from tools.csv_gen.words_table_excel_to_csv import words_table_excel_to_csv

logger = logging.getLogger(__name__)

_DIRECTIVE_RE = re.compile(r"^@(\w+)\s+(.+)$")


@dataclass
class ComposeEntry:
    result_word: str
    component1_word: str
    component2_word: str


@dataclass
class ParsedCompose:
    entries: list[ComposeEntry]
    source: Path


def parse_words_compose_file(path: str | Path) -> ParsedCompose:
    """`.words_compose` 텍스트 파싱 — result/component1/component2 한자 3열(탭 구분)."""
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"배치 파일 없음: {src}")

    entries: list[ComposeEntry] = []
    for raw in src.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _DIRECTIVE_RE.match(line):
            continue  # @sheet 등은 연결 전용 포맷이라 사용 안 함
        cells = line.split("\t") if "\t" in line else re.split(r"\s{2,}", line)
        cells = [c.strip() for c in cells]
        if len(cells) < 3:
            raise ValueError(
                f"데이터 행은 result·component1·component2 3열이어야 합니다: {line!r}"
            )
        result_word, c1, c2 = cells[0], cells[1], cells[2]
        if not (result_word and c1 and c2):
            raise ValueError(f"빈 값이 있습니다: {line!r}")
        entries.append(
            ComposeEntry(result_word=result_word, component1_word=c1, component2_word=c2)
        )

    if not entries:
        raise ValueError(f"연결할 항목이 없습니다: {src}")
    return ParsedCompose(entries=entries, source=src)


def _build_word_index(store: MultiSheetWorkbookStore) -> dict[str, tuple[str, str, int]]:
    """word(한자) → (sheet, id, row_index). 여러 시트에 같은 한자가 있으면 첫 매치 사용."""
    index: dict[str, tuple[str, str, int]] = {}
    for sheet in store.sheet_names:
        rows = store.get_sheet_rows(sheet)
        for i, row in enumerate(rows):
            w = (row.get("word") or "").strip()
            wid = (row.get("id") or "").strip()
            if w and wid and w not in index:
                index[w] = (sheet, wid, i)
    return index


def link_components_and_build_layout(
    compose_file: Path,
    *,
    like: Path,
    name: str,
    excel_path: Path = DEFAULT_WORDS_TABLE_EXCEL,
    dry_run: bool = False,
    export_csv: bool = True,
) -> Path:
    parsed = parse_words_compose_file(compose_file)

    store = MultiSheetWorkbookStore(WORDS_FIELDNAMES)
    store.load(excel_path)
    index = _build_word_index(store)

    missing = sorted(
        {
            w
            for e in parsed.entries
            for w in (e.result_word, e.component1_word, e.component2_word)
            if w not in index
        }
    )
    if missing:
        raise ValueError(
            "words.xlsx에 없는 단어: "
            + ", ".join(missing)
            + " — 먼저 `python -m tools.words_batch.add_words`로 추가하세요."
        )

    result_ids: list[str] = []
    sheet_rows_cache: dict[str, list[dict[str, str]]] = {}
    for e in parsed.entries:
        r_sheet, r_id, r_idx = index[e.result_word]
        _, c1_id, _ = index[e.component1_word]
        _, c2_id, _ = index[e.component2_word]
        rows = sheet_rows_cache.setdefault(r_sheet, store.get_sheet_rows(r_sheet))
        rows[r_idx] = {**rows[r_idx], "component1_id": c1_id, "component2_id": c2_id}
        result_ids.append(r_id)
        logger.info(
            "연결: %s(id=%s) <- %s(id=%s) + %s(id=%s)",
            e.result_word, r_id, e.component1_word, c1_id, e.component2_word, c2_id,
        )

    if dry_run:
        logger.info("dry-run: words.xlsx 저장·CSV 갱신 생략")
    else:
        for sheet, rows in sheet_rows_cache.items():
            store.set_sheet_rows(sheet, rows)
        store.save(excel_path)
        logger.info("저장: %s (%d개 결과 단어에 부품 연결)", excel_path, len(result_ids))
        if export_csv:
            out = words_table_excel_to_csv(
                excel_path, DEFAULT_WORDS_TABLE_CSV, merge_all_sheets=True
            )
            logger.info("CSV 갱신: %s", out)

    template = load_layout(like)
    layout = copy.deepcopy(template)
    layout.combo_layout = True
    layout.boxes = [
        WordMemorizeBox(
            word_id=str(wid), order=i + 1, x=0, y=0, w=280, h=160, box_key=f"box_{i + 1}"
        )
        for i, wid in enumerate(result_ids)
    ]
    layout.holding_word_ids = []

    out_path = DEFAULT_LAYOUTS_DIR / f"{name}.json"
    if dry_run:
        print(json.dumps(layout.to_dict(), ensure_ascii=False, indent=2))
    else:
        save_layout(out_path, layout)
        print(f"저장: {out_path} (조합형, {len(result_ids)}세트: {', '.join(e.result_word for e in parsed.entries)})")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=".words_compose → component1_id/2_id 연결 + 조합형 layout JSON 생성",
    )
    parser.add_argument("compose_file", type=Path, help="연결 배치 파일 (.words_compose)")
    parser.add_argument("--like", type=Path, required=True, help="스타일 템플릿 배치 JSON (예: 조합_예시1.json)")
    parser.add_argument("--name", required=True, help="출력 파일 이름 (확장자 제외)")
    parser.add_argument("--excel", type=Path, default=DEFAULT_WORDS_TABLE_EXCEL)
    parser.add_argument("--dry-run", action="store_true", help="저장 없이 미리보기만")
    parser.add_argument("--no-csv", action="store_true", help="저장 후 words.csv 갱신 생략")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        link_components_and_build_layout(
            args.compose_file,
            like=args.like,
            name=args.name,
            excel_path=args.excel,
            dry_run=args.dry_run,
            export_csv=not args.no_csv,
        )
    except (OSError, ValueError) as ex:
        logger.error("%s", ex)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
