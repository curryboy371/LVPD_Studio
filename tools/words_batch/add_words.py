"""
.words_add 파일을 읽어 resource/table/words.xlsx 에 단어 행을 추가한다.

실행 (프로젝트 루트):
  python -m tools.words_batch.add_words tools/words_batch/weekdays.words_add
  python -m tools.words_batch.add_words path/to/batch.words_add --dry-run
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core.paths import DEFAULT_WORDS_TABLE_CSV, DEFAULT_WORDS_TABLE_EXCEL
from extra.table_editor.config import DEFAULT_WORD_TTS_TYPE, DEFAULT_WORD_TTS_VOICE
from extra.table_editor.data.fields import WORDS_FIELDNAMES
from extra.table_editor.data.workbook import MultiSheetWorkbookStore
from extra.table_editor.services.masking_format import masking_for_storage
from extra.table_editor.services.search import allocate_next_word_id
from extra.table_editor.services.word_autofill import (
    apply_hanzi_autofill,
    apply_new_word_defaults,
)
from tools.csv_gen.words_table_excel_to_csv import words_table_excel_to_csv

logger = logging.getLogger(__name__)

_DIRECTIVE_RE = re.compile(r"^@(\w+)\s+(.+)$")
_HEADER_MARKERS = frozenset({"meaning", "한국어", "ko", "뜻"})


@dataclass
class BatchEntry:
    meaning: str
    en_meaning: str
    word: str
    pinyin: str
    pos: str = ""


@dataclass
class ParsedBatch:
    sheet: str
    pos: str
    entries: list[BatchEntry]
    source: Path


def _split_data_line(line: str) -> list[str]:
    if "\t" in line:
        parts = line.split("\t")
    else:
        parts = re.split(r"\s{2,}", line)
    return [p.strip() for p in parts]


def _is_header_row(cells: list[str]) -> bool:
    if not cells:
        return False
    first = (cells[0] or "").strip().lower()
    return first in _HEADER_MARKERS or first.startswith("#")


def parse_words_add_file(path: str | Path) -> ParsedBatch:
    """`.words_add` 텍스트 파일 파싱."""
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"배치 파일 없음: {src}")

    sheet = ""
    pos = ""
    entries: list[BatchEntry] = []

    for raw in src.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _DIRECTIVE_RE.match(line)
        if m:
            key, val = m.group(1).lower(), m.group(2).strip()
            if key == "sheet":
                sheet = val
            elif key == "pos":
                pos = val
            else:
                logger.warning("알 수 없는 지시자 @%s (무시)", key)
            continue

        cells = _split_data_line(line)
        if _is_header_row(cells):
            continue
        if len(cells) < 4:
            raise ValueError(
                f"데이터 행은 meaning·en_meaning·word·pinyin 4열이어야 합니다: {line!r}"
            )
        meaning, en_meaning, word, pinyin = cells[0], cells[1], cells[2], cells[3]
        if not word:
            raise ValueError(f"한자(word)가 비어 있습니다: {line!r}")
        entries.append(
            BatchEntry(
                meaning=meaning,
                en_meaning=en_meaning,
                word=word,
                pinyin=pinyin,
                pos=pos,
            )
        )

    if not sheet:
        raise ValueError(f"@sheet 지시자가 필요합니다: {src}")
    if not pos:
        raise ValueError(f"@pos 지시자가 필요합니다: {src}")
    if not entries:
        raise ValueError(f"추가할 단어 행이 없습니다: {src}")

    return ParsedBatch(sheet=sheet, pos=pos, entries=entries, source=src)


def build_word_row(
    entry: BatchEntry,
    *,
    word_id: str,
    pos: str,
) -> dict[str, str]:
    """편집기 규칙과 동일하게 words 행 dict 생성."""
    row = {col: "" for col in WORDS_FIELDNAMES}
    row["id"] = word_id
    row["meaning"] = entry.meaning
    row["en_meaning"] = entry.en_meaning
    row["pinyin"] = entry.pinyin
    row = apply_new_word_defaults(row, pos=pos)
    row = apply_hanzi_autofill(row, entry.word, image_enabled=True)
    row["masking"] = masking_for_storage(row.get("masking", ""))
    if not (row.get("tts_type") or "").strip():
        row["tts_type"] = DEFAULT_WORD_TTS_TYPE
    if not (row.get("tts_voice") or "").strip():
        row["tts_voice"] = DEFAULT_WORD_TTS_VOICE
    return row


def _all_sheet_rows(store: MultiSheetWorkbookStore) -> dict[str, list[dict[str, str]]]:
    return {name: store.get_sheet_rows(name) for name in store.sheet_names}


def _word_duplicate_in_sheet(
    rows: list[dict[str, str]],
    hanzi: str,
    pos: str,
) -> bool:
    """동일 시트에서 같은 pos·한자(word) 조합이 이미 있는지."""
    target_word = (hanzi or "").strip()
    if not target_word:
        return False
    target_pos = (pos or "").strip()
    for row in rows:
        if (row.get("word") or "").strip() != target_word:
            continue
        if (row.get("pos") or "").strip() == target_pos:
            return True
    return False


def import_batch(
    batch: ParsedBatch,
    *,
    excel_path: Path = DEFAULT_WORDS_TABLE_EXCEL,
    dry_run: bool = False,
    skip_duplicates: bool = True,
    export_csv: bool = True,
) -> list[dict[str, str]]:
    """배치를 words.xlsx 지정 시트에 추가. 추가된 행 dict 리스트 반환."""
    if not excel_path.exists():
        raise FileNotFoundError(f"words.xlsx 없음: {excel_path}")

    store = MultiSheetWorkbookStore(WORDS_FIELDNAMES)
    store.load(excel_path)
    snapshot = _all_sheet_rows(store)

    sheet = batch.sheet
    if sheet not in snapshot:
        snapshot[sheet] = []
        if not dry_run:
            store.set_sheet_rows(sheet, [])
        logger.info("새 시트 생성: %s", sheet)

    rows = list(snapshot[sheet])
    added: list[dict[str, str]] = []

    for entry in batch.entries:
        entry_pos = (entry.pos or batch.pos).strip()
        if skip_duplicates and _word_duplicate_in_sheet(
            rows, entry.word, entry_pos
        ):
            logger.warning(
                "건너뜀 (시트·pos 중복): %s [%s] 시트=%s",
                entry.word,
                entry_pos or "(품사 없음)",
                sheet,
            )
            continue

        word_id = allocate_next_word_id(
            rows, snapshot, sheet_name=sheet
        )
        row = build_word_row(entry, word_id=word_id, pos=entry_pos)
        added.append(row)
        rows.append(row)
        snapshot[sheet] = rows

        logger.info(
            "+%s id=%s %s (%s) / %s",
            sheet,
            word_id,
            entry.word,
            entry.meaning,
            entry.pinyin,
        )

    if not added:
        logger.warning("추가된 행 없음")
        return []

    if dry_run:
        logger.info("dry-run: 저장·CSV 생략 (%d행)", len(added))
        return added

    store.set_sheet_rows(sheet, rows)
    store.save(excel_path)
    logger.info("저장: %s (+%d행, 시트=%s)", excel_path, len(added), sheet)

    if export_csv:
        out = words_table_excel_to_csv(
            excel_path, DEFAULT_WORDS_TABLE_CSV, merge_all_sheets=True
        )
        logger.info("CSV 갱신: %s", out)

    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=".words_add 배치 파일 → words.xlsx 자동 추가",
    )
    parser.add_argument(
        "batch_file",
        type=Path,
        help="단어 배치 파일 (.words_add)",
    )
    parser.add_argument(
        "--excel",
        type=Path,
        default=DEFAULT_WORDS_TABLE_EXCEL,
        help=f"대상 엑셀 (기본: {DEFAULT_WORDS_TABLE_EXCEL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="파싱·id 할당만 하고 저장하지 않음",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="같은 한자가 시트에 있어도 추가",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="저장 후 words.csv 갱신 생략",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        batch = parse_words_add_file(args.batch_file)
    except (OSError, ValueError) as ex:
        logger.error("%s", ex)
        return 1

    logger.info(
        "배치: %s | 시트=%s pos=%s | %d개 단어",
        batch.source.name,
        batch.sheet,
        batch.pos,
        len(batch.entries),
    )

    try:
        added = import_batch(
            batch,
            excel_path=args.excel,
            dry_run=args.dry_run,
            skip_duplicates=not args.force,
            export_csv=not args.no_csv,
        )
    except (OSError, ValueError) as ex:
        logger.error("%s", ex)
        return 1

    print(f"완료: {len(added)}개 추가 (시트={batch.sheet}, pos={batch.pos})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
