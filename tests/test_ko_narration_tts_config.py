"""ko_narration_sets 테이블 TTS·목소리 설정 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.ko_narration import format_tts_log_label, resolve_tts_config_for_set
from data.ko_narration_loader import load_ko_narration_tables


def test_resolve_tts_config_from_set_table(tmp_path: Path) -> None:
    sets_csv = tmp_path / "sets.csv"
    lines_csv = tmp_path / "lines.csv"
    sets_csv.write_text(
        "id,title,tts,tts_voice\n"
        "1,테스트,,edge,ko-KR-InJoonNeural\n",
        encoding="utf-8-sig",
    )
    lines_csv.write_text("id,set_id,seq,text\n", encoding="utf-8-sig")
    load_ko_narration_tables(sets_csv=sets_csv, lines_csv=lines_csv)

    engine, voice = resolve_tts_config_for_set(1, tts_cli="gtts", tts_voice_cli="")
    assert engine == "edge"
    assert voice == "ko-KR-InJoonNeural"

    engine2, voice2 = resolve_tts_config_for_set(1, tts_cli="gtts", tts_voice_cli="ko-KR-SunHiNeural")
    assert engine2 == "edge"
    assert voice2 == "ko-KR-InJoonNeural"
    assert format_tts_log_label(engine, voice) == "edge / ko-KR-InJoonNeural"
    assert format_tts_log_label("gtts", "") == "gtts"


def test_resolve_tts_config_cli_fallback(tmp_path: Path) -> None:
    sets_csv = tmp_path / "sets.csv"
    lines_csv = tmp_path / "lines.csv"
    sets_csv.write_text("id,title,tts,tts_voice\n2,빈설정,,\n", encoding="utf-8-sig")
    lines_csv.write_text("id,set_id,seq,text\n", encoding="utf-8-sig")
    load_ko_narration_tables(sets_csv=sets_csv, lines_csv=lines_csv)

    engine, voice = resolve_tts_config_for_set(2, tts_cli="edge", tts_voice_cli="ko-KR-SunHiNeural")
    assert engine == "edge"
    assert voice == "ko-KR-SunHiNeural"
