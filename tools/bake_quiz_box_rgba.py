"""quiz_box.png → 매트 제거 RGBA 복사본(quiz_box_rgba.png) 생성."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from extra.table_editor.services.word_memorize_layout import (  # noqa: E402
    WORD_MEMORIZE_GAME_DIR,
)
from studio.studios.word_memorize_quiz import _defringe_quiz_box_image  # noqa: E402


def bake_quiz_box_rgba(
    *,
    src: Path | None = None,
    dst: Path | None = None,
) -> Path:
    """검정 매트가 있는 원본을 투명 RGBA로 베이크한다.

    Args:
        src: 원본 PNG. 기본 resource/image/game/quiz_box.png
        dst: 출력 PNG. 기본 resource/image/game/quiz_box_rgba.png

    Returns:
        저장된 출력 경로.
    """
    from PIL import Image

    source = src or (WORD_MEMORIZE_GAME_DIR / "quiz_box.png")
    output = dst or (WORD_MEMORIZE_GAME_DIR / "quiz_box_rgba.png")
    if not source.is_file():
        raise FileNotFoundError(f"원본 없음: {source}")
    im = Image.open(source)
    clean = _defringe_quiz_box_image(im)
    output.parent.mkdir(parents=True, exist_ok=True)
    clean.save(output, format="PNG", optimize=True)
    return output


def main() -> None:
    out = bake_quiz_box_rgba()
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
