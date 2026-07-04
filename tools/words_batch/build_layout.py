"""
.words_add 배치를 words.xlsx에 추가한 뒤, 기존 배치 JSON(레이저 타입 dian.json 또는
주제 타입 animal.json 등)을 스타일 템플릿으로 삼아 새 word_memorize_layouts/*.json을 만든다.

실행 (프로젝트 루트):
  # 레이저 타입 (공통 한자) — dian.json 스타일 그대로 복제
  python -m tools.words_batch.build_layout tools/words_batch/hui_compounds.words_add \
      --like resource/table/word_memorize_layouts/dian.json --name 회

  # 주제 타입 — animal.json 스타일 참고, 제목만 교체
  python -m tools.words_batch.build_layout tools/words_batch/food_nouns.words_add \
      --like resource/table/word_memorize_layouts/animal.json --name 음식 \
      --title "음식 이름을 외우자!" --limit 10

옵션:
  --like PATH     스타일 템플릿 배치 JSON (배경·하이라이트·타일·파티클·글꼴·CTA 카드 등 그대로 복제)
  --name STEM     출력 파일 이름 (확장자 제외) — resource/table/word_memorize_layouts/{STEM}.json
  --limit N       배치에서 추가된 단어 중 앞에서 N개만 사용 (기본: 전체)
  --title TEXT    제목 — 줄바꿈은 \n. 비우면 템플릿 제목 유지
  --subtitle TEXT 부제 — 줄바꿈은 \n. 비우면 템플릿 부제 유지
  --no-cta        템플릿의 구독·좋아요 등 CTA 카드는 제외 (기본: 유지)
  --dry-run       words.xlsx 저장·레이아웃 JSON 저장 없이 미리보기만
  --excel / --force / --no-csv  add_words.py 와 동일
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core.paths import DEFAULT_WORDS_TABLE_EXCEL
from extra.table_editor.data.fields import WORDS_FIELDNAMES
from extra.table_editor.data.workbook import MultiSheetWorkbookStore
from extra.table_editor.services.word_memorize_grid import apply_grid_layout
from extra.table_editor.services.word_memorize_layout import (
    CARD_TYPE_NONE,
    DEFAULT_LAYOUTS_DIR,
    SubtitleLineSpec,
    TitleLineSpec,
    WordMemorizeBox,
    box_card_type,
    load_layout,
    save_layout,
)
from tools.words_batch.add_words import import_batch, parse_words_add_file

logger = logging.getLogger(__name__)


def _word_to_id_map_from_rows(rows: list[dict[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        word = (row.get("word") or "").strip()
        wid = (row.get("id") or "").strip()
        if word and wid and word not in out:
            out[word] = wid
    return out


def _collect_word_ids(
    batch,
    added: list[dict[str, str]],
    updated: list[dict[str, str]],
    *,
    excel_path: Path,
    dry_run: bool,
) -> list[str]:
    """배치 순서대로 word_id 목록 — 실제 저장 후에는 시트를 다시 읽어 확정한다."""
    if dry_run:
        word_to_id = _word_to_id_map_from_rows(added + updated)
    else:
        store = MultiSheetWorkbookStore(WORDS_FIELDNAMES)
        store.load(excel_path)
        word_to_id = _word_to_id_map_from_rows(store.get_sheet_rows(batch.sheet))

    ids: list[str] = []
    missing: list[str] = []
    for entry in batch.entries:
        wid = word_to_id.get(entry.word)
        if wid:
            ids.append(wid)
        else:
            missing.append(entry.word)
    if missing:
        logger.warning("word_id를 찾지 못해 배치에서 제외됨: %s", ", ".join(missing))
    return ids


def _word_boxes_and_cta(template) -> tuple[list, list]:
    word_boxes = [b for b in template.sorted_boxes() if box_card_type(b) == CARD_TYPE_NONE]
    cta_boxes = [b for b in template.sorted_boxes() if box_card_type(b) != CARD_TYPE_NONE]
    return word_boxes, cta_boxes


def _build_boxes(
    template,
    word_ids: list[str],
    *,
    keep_cta: bool,
) -> list[WordMemorizeBox]:
    word_boxes_tpl, cta_boxes_tpl = _word_boxes_and_cta(template)
    if not word_boxes_tpl:
        raise ValueError("템플릿에 일반 word box가 없습니다")

    n = len(word_ids)
    boxes: list[WordMemorizeBox] = []

    if n == len(word_boxes_tpl):
        # 개수가 같으면 템플릿 배치를 그대로 재사용 (가장 충실한 참고)
        for i, wid in enumerate(word_ids):
            src = word_boxes_tpl[i]
            boxes.append(
                WordMemorizeBox(
                    word_id=str(wid), order=i + 1,
                    x=src.x, y=src.y, w=src.w, h=src.h,
                    box_key=f"box_{i + 1}",
                )
            )
    else:
        ref = word_boxes_tpl[0]
        cols = max(1, math.ceil(math.sqrt(max(1, n))))
        rows = max(1, math.ceil(n / cols))
        for i, wid in enumerate(word_ids):
            boxes.append(
                WordMemorizeBox(
                    word_id=str(wid), order=i + 1,
                    x=0, y=0, w=ref.w, h=ref.h,
                    box_key=f"box_{i + 1}",
                )
            )
        placeholder = copy.deepcopy(template)
        placeholder.boxes = boxes
        warning = apply_grid_layout(placeholder, rows, cols, uniform=True)
        if warning:
            logger.warning(warning)
        boxes = placeholder.boxes

    if keep_cta and cta_boxes_tpl:
        offset = len(boxes)
        for j, cb in enumerate(cta_boxes_tpl):
            boxes.append(
                WordMemorizeBox(
                    word_id=cb.word_id, order=offset + j + 1,
                    x=cb.x, y=cb.y, w=cb.w, h=cb.h,
                    box_key=f"cta_{j + 1}", card_type=box_card_type(cb),
                )
            )
    return boxes


def _split_lines(text: str) -> list[str]:
    return [ln for ln in text.replace("\r\n", "\n").split("\n")]


def _apply_title(layout, title: str) -> None:
    lines = _split_lines(title)
    base = layout.title_lines[0] if layout.title_lines else TitleLineSpec()
    layout.title_lines = [
        TitleLineSpec(text=ln, color=base.color, font=base.font, font_pt=base.font_pt)
        for ln in lines
    ]


def _apply_subtitle(layout, subtitle: str) -> None:
    lines = _split_lines(subtitle)
    tpl_lines = layout.subtitle_lines or [SubtitleLineSpec()]
    layout.subtitle_lines = [
        SubtitleLineSpec(
            text=ln,
            font=tpl_lines[i % len(tpl_lines)].font,
            text_tile=tpl_lines[i % len(tpl_lines)].text_tile,
        )
        for i, ln in enumerate(lines)
    ]


def build_layout_from_batch(
    batch_file: Path,
    *,
    like: Path,
    name: str,
    excel_path: Path = DEFAULT_WORDS_TABLE_EXCEL,
    dry_run: bool = False,
    force: bool = False,
    export_csv: bool = True,
    limit: int | None = None,
    title: str | None = None,
    subtitle: str | None = None,
    keep_cta: bool = True,
) -> Path:
    batch = parse_words_add_file(batch_file)
    added, updated = import_batch(
        batch,
        excel_path=excel_path,
        dry_run=dry_run,
        skip_duplicates=not force,
        export_csv=export_csv,
    )
    word_ids = _collect_word_ids(batch, added, updated, excel_path=excel_path, dry_run=dry_run)
    if limit is not None:
        word_ids = word_ids[:limit]
    if not word_ids:
        raise ValueError("배치에서 word_id를 하나도 찾지 못했습니다")

    template = load_layout(like)
    layout = copy.deepcopy(template)
    layout.boxes = _build_boxes(template, word_ids, keep_cta=keep_cta)
    layout.holding_word_ids = []
    if title is not None:
        _apply_title(layout, title)
    if subtitle is not None:
        _apply_subtitle(layout, subtitle)

    out_path = DEFAULT_LAYOUTS_DIR / f"{name}.json"
    if dry_run:
        print(json.dumps(layout.to_dict(), ensure_ascii=False, indent=2))
    else:
        save_layout(out_path, layout)
        n_word = sum(1 for b in layout.boxes if box_card_type(b) == CARD_TYPE_NONE)
        n_cta = len(layout.boxes) - n_word
        extra = f", CTA {n_cta}개" if n_cta else ""
        print(f"저장: {out_path} (word box {n_word}개{extra})")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=".words_add 배치 → words.xlsx 추가 + word_memorize_layouts JSON 생성",
    )
    parser.add_argument("batch_file", type=Path, help="단어 배치 파일 (.words_add)")
    parser.add_argument("--like", type=Path, required=True, help="스타일 템플릿 배치 JSON")
    parser.add_argument("--name", required=True, help="출력 파일 이름 (확장자 제외)")
    parser.add_argument("--limit", type=int, default=None, help="앞에서 N개 단어만 사용")
    parser.add_argument("--title", default=None, help="제목 (줄바꿈 \\n)")
    parser.add_argument("--subtitle", default=None, help="부제 (줄바꿈 \\n)")
    parser.add_argument("--no-cta", action="store_true", help="템플릿 CTA 카드 제외")
    parser.add_argument("--excel", type=Path, default=DEFAULT_WORDS_TABLE_EXCEL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-csv", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        build_layout_from_batch(
            args.batch_file,
            like=args.like,
            name=args.name,
            excel_path=args.excel,
            dry_run=args.dry_run,
            force=args.force,
            export_csv=not args.no_csv,
            limit=args.limit,
            title=args.title,
            subtitle=args.subtitle,
            keep_cta=not args.no_cta,
        )
    except (OSError, ValueError) as ex:
        logger.error("%s", ex)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
