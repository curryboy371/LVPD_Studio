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
    word_type: str = ""


@dataclass
class ParsedBatch:
    sheet: str
    pos: str
    word_type: str
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
    word_type = ""
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
            elif key == "type":
                word_type = val
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
                word_type=word_type,
            )
        )

    if not sheet:
        raise ValueError(f"@sheet 지시자가 필요합니다: {src}")
    if not pos:
        raise ValueError(f"@pos 지시자가 필요합니다: {src}")
    if not entries:
        raise ValueError(f"추가할 단어 행이 없습니다: {src}")

    return ParsedBatch(
        sheet=sheet, pos=pos, word_type=word_type, entries=entries, source=src
    )


def build_word_row(
    entry: BatchEntry,
    *,
    word_id: str,
    pos: str,
    word_type: str = "",
) -> dict[str, str]:
    """편집기 규칙과 동일하게 words 행 dict 생성."""
    row = {col: "" for col in WORDS_FIELDNAMES}
    row["id"] = word_id
    row["meaning"] = entry.meaning
    row["en_meaning"] = entry.en_meaning
    row["pinyin"] = entry.pinyin
    wt = (entry.word_type or word_type or "").strip()
    if wt:
        row["type"] = wt
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


_BATCH_MERGE_FIELDS = ("meaning", "en_meaning", "pinyin")
_AUTOFILL_MERGE_FIELDS = ("img_path", "sound_path", "masking", "tts_type", "tts_voice")


def _find_duplicate_row_index(
    rows: list[dict[str, str]],
    hanzi: str,
    pos: str,
) -> int | None:
    """동일 시트에서 같은 pos·한자(word) 조합 행 인덱스."""
    target_word = (hanzi or "").strip()
    if not target_word:
        return None
    target_pos = (pos or "").strip()
    for idx, row in enumerate(rows):
        if (row.get("word") or "").strip() != target_word:
            continue
        if (row.get("pos") or "").strip() == target_pos:
            return idx
    return None


def _merge_entry_into_row(
    existing: dict[str, str],
    entry: BatchEntry,
    *,
    pos: str,
    word_type: str = "",
) -> tuple[dict[str, str], bool]:
    """기존 행의 빈 필드만 배치 값·자동채움으로 보충. type은 배치 값으로 덮어씀."""
    out = dict(existing)
    changed = False

    for key in _BATCH_MERGE_FIELDS:
        batch_val = (getattr(entry, key, "") or "").strip()
        if batch_val and not (out.get(key) or "").strip():
            out[key] = batch_val
            changed = True

    batch_type = (entry.word_type or word_type or "").strip()
    if batch_type and (out.get("type") or "").strip() != batch_type:
        out["type"] = batch_type
        changed = True

    autofill = apply_hanzi_autofill(dict(out), entry.word, image_enabled=True)
    autofill = apply_new_word_defaults(autofill, pos=pos)
    for key in _AUTOFILL_MERGE_FIELDS:
        if not (out.get(key) or "").strip() and (autofill.get(key) or "").strip():
            out[key] = autofill[key]
            changed = True

    if (out.get("masking") or "").strip():
        stored = masking_for_storage(out["masking"])
        if stored != out.get("masking", ""):
            out["masking"] = stored
            changed = True

    return out, changed


def import_batch(
    batch: ParsedBatch,
    *,
    excel_path: Path = DEFAULT_WORDS_TABLE_EXCEL,
    dry_run: bool = False,
    skip_duplicates: bool = True,
    export_csv: bool = True,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """배치를 words.xlsx 지정 시트에 반영. (추가된 행, 갱신된 행) 반환."""
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
    updated: list[dict[str, str]] = []

    for entry in batch.entries:
        entry_pos = (entry.pos or batch.pos).strip()
        dup_idx = (
            None
            if not skip_duplicates
            else _find_duplicate_row_index(rows, entry.word, entry_pos)
        )
        if dup_idx is not None:
            merged, changed = _merge_entry_into_row(
                rows[dup_idx],
                entry,
                pos=entry_pos,
                word_type=batch.word_type,
            )
            if changed:
                rows[dup_idx] = merged
                updated.append(merged)
                logger.info(
                    "~%s id=%s %s (빈 필드 보충·type 갱신)",
                    sheet,
                    merged.get("id", ""),
                    entry.word,
                )
            else:
                logger.warning(
                    "건너뜀 (시트·pos 중복, 채울 빈 필드 없음): %s [%s] 시트=%s",
                    entry.word,
                    entry_pos or "(품사 없음)",
                    sheet,
                )
            continue

        word_id = allocate_next_word_id(
            rows, snapshot, sheet_name=sheet
        )
        row = build_word_row(
            entry, word_id=word_id, pos=entry_pos, word_type=batch.word_type
        )
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

    if not added and not updated:
        logger.warning("추가·갱신된 행 없음")
        return [], []

    if dry_run:
        logger.info(
            "dry-run: 저장·CSV 생략 (+%d행, ~%d행)",
            len(added),
            len(updated),
        )
        return added, updated

    store.set_sheet_rows(sheet, rows)
    store.save(excel_path)
    logger.info(
        "저장: %s (+%d행, ~%d행, 시트=%s)",
        excel_path,
        len(added),
        len(updated),
        sheet,
    )

    if export_csv:
        out = words_table_excel_to_csv(
            excel_path, DEFAULT_WORDS_TABLE_CSV, merge_all_sheets=True
        )
        logger.info("CSV 갱신: %s", out)

    return added, updated


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
        help="같은 한자가 시트에 있어도 새 행 추가 (기본은 중복 시 빈 필드만 보충)",
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
        "배치: %s | 시트=%s pos=%s type=%s | %d개 단어",
        batch.source.name,
        batch.sheet,
        batch.pos,
        batch.word_type or "(없음)",
        len(batch.entries),
    )

    try:
        added, updated = import_batch(
            batch,
            excel_path=args.excel,
            dry_run=args.dry_run,
            skip_duplicates=not args.force,
            export_csv=not args.no_csv,
        )
    except (OSError, ValueError) as ex:
        logger.error("%s", ex)
        return 1

    parts = [f"{len(added)}개 추가"]
    if updated:
        parts.append(f"{len(updated)}개 갱신(빈 필드 보충)")
    print(f"완료: {', '.join(parts)} (시트={batch.sheet}, pos={batch.pos}, type={batch.word_type or '-'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
