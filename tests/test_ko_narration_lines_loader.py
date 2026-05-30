"""ko_narration_lines: id 1행 + text \\n segment TTS."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from data.ko_narration_loader import (
    get_cue_texts_for_set,
    ko_cue_index_for_segment,
    load_ko_narration_tables,
    split_ko_line_text,
)


def test_split_ko_line_text_multiline() -> None:
    assert split_ko_line_text("첫 줄\n둘째 줄") == ["첫 줄", "둘째 줄"]
    assert split_ko_line_text("한 줄") == ["한 줄"]


def test_loader_merges_legacy_seq_rows() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        sets_csv = td / "sets.csv"
        lines_csv = td / "lines.csv"
        sets_csv.write_text("id,title,tts,tts_voice\n1,T,edge,\n", encoding="utf-8-sig")
        lines_csv.write_text(
            "id,set_id,seq,text\n"
            "1,1,1,첫 큐\n"
            "1,1,2,둘째 큐\n"
            "2,1,1,멘트2\n",
            encoding="utf-8-sig",
        )
        load_ko_narration_tables(sets_csv=sets_csv, lines_csv=lines_csv)
        texts = get_cue_texts_for_set(1)
        assert texts == ["첫 큐", "둘째 큐", "멘트2"]
        assert ko_cue_index_for_segment(1, ment_id=1, segment=2) == 1
        assert ko_cue_index_for_segment(1, ment_id=2, segment=1) == 2


def test_loader_splits_newline_text_row() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        sets_csv = td / "sets.csv"
        lines_csv = td / "lines.csv"
        sets_csv.write_text("id,title,tts,tts_voice\n1,T,edge,\n", encoding="utf-8-sig")
        lines_csv.write_text(
            'id,set_id,text\n1,1,"첫\n둘"\n',
            encoding="utf-8-sig",
        )
        load_ko_narration_tables(sets_csv=sets_csv, lines_csv=lines_csv)
        assert get_cue_texts_for_set(1) == ["첫", "둘"]


if __name__ == "__main__":
    test_split_ko_line_text_multiline()
    test_loader_merges_legacy_seq_rows()
    test_loader_splits_newline_text_row()
    print("ok")
