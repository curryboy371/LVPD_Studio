"""Clipboard image capture and tmp staging for table editor."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from extra.table_editor.config import get_table_editor_tmp_dir


def get_clipboard_image():
    """클립보드 이미지 → PIL.Image 또는 None."""
    try:
        from PIL import ImageGrab
    except ImportError as ex:
        raise ImportError(
            "클립보드 이미지를 사용하려면 Pillow가 필요합니다: "
            "py -3 -m pip install Pillow"
        ) from ex

    data = ImageGrab.grabclipboard()
    if data is None:
        return None
    if hasattr(data, "save"):
        return data
    if isinstance(data, list) and data:
        from PIL import Image

        return Image.open(data[0])
    return None


def stage_clipboard_image_to_tmp() -> Path:
    """클립보드 이미지를 .table_editor_tmp 에 저장하고 경로 반환."""
    image = get_clipboard_image()
    if image is None:
        raise ValueError("클립보드에 이미지가 없습니다.")

    tmp_dir = get_table_editor_tmp_dir()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"clip_{uuid.uuid4().hex}.png"
    image.save(tmp_path, format="PNG")
    return tmp_path.resolve()


def commit_staged_image(staged: Path, target: Path) -> None:
    """임시 파일 → 최종 경로 (저장 버튼 시)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(staged, target)


def discard_staged_image(staged: Path | None) -> None:
    if staged is None:
        return
    try:
        if staged.is_file():
            staged.unlink()
    except OSError:
        pass
