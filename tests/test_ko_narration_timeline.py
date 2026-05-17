"""ko_narration 타임라인 재조정 단위 테스트 (TTS/네트워크 불필요)."""
from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audio.ko_narration import DEFAULT_KO_CUE_GAP_SEC, build_timeline, parse_ko_cue_texts


def _write_silent_wav(path: Path, duration_sec: float, rate: int = 22050) -> None:
    nframes = int(rate * duration_sec)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * nframes)


def test_build_timeline_stacks_with_gap() -> None:
    gap = DEFAULT_KO_CUE_GAP_SEC
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        durs = [0.5, 1.0, 0.25]
        texts = ["a", "b", "c"]
        paths = []
        for i, d in enumerate(durs):
            p = td / f"{i}.wav"
            _write_silent_wav(p, d)
            paths.append(p)
        cues = build_timeline(texts, paths, start_offset_sec=0.0, gap_sec=gap)
        assert len(cues) == 3
        assert cues[0].start_sec == 0.0
        assert abs(cues[0].end_sec - 0.5) < 0.05
        assert abs(cues[1].start_sec - (0.5 + gap)) < 0.05
        assert abs(cues[2].start_sec - cues[1].end_sec - gap) < 0.05


def test_parse_ko_cue_texts_multiline() -> None:
    lines = parse_ko_cue_texts(ko_narration="첫 줄\n둘째 줄")
    assert lines == ["첫 줄", "둘째 줄"]


if __name__ == "__main__":
    test_build_timeline_stacks_with_gap()
    test_parse_ko_cue_texts_multiline()
    print("ok")
