"""Clipboard / file image capture and tmp staging for table editor."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from extra.table_editor.config import get_table_editor_tmp_dir
from extra.table_editor.services.image_paths import _IMAGE_SUFFIXES


def _pil_resample_lanczos():
    from PIL import Image

    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def _to_rgba(image):
    """팔레트·LA 등 기존 투명 채널을 보존해 RGBA로 변환."""
    if image.mode == "RGBA":
        return image.copy()
    if image.mode in ("P", "PA", "LA"):
        return image.convert("RGBA")
    return image.convert("RGBA")


def _alpha_has_transparency(image) -> bool:
    if image.mode != "RGBA":
        return False
    lo, _hi = image.getchannel("A").getextrema()
    return lo < 250


def _remove_background_rembg(image):
    """rembg(U²-Net)로 배경 제거 → RGBA. 이미 투명 PNG는 재처리 생략."""
    from PIL import Image

    image = _to_rgba(image)
    if _alpha_has_transparency(image):
        return image

    try:
        from rembg import remove
    except ImportError as ex:
        raise ImportError(
            "배경 제거를 위해 rembg가 필요합니다:\n"
            'py -3 -m pip install "rembg[cpu]" pillow'
        ) from ex

    out = remove(image)
    if isinstance(out, Image.Image):
        return out.convert("RGBA")
    if isinstance(out, (bytes, bytearray)):
        from io import BytesIO

        with Image.open(BytesIO(out)) as loaded:
            return loaded.convert("RGBA")
    raise TypeError(f"rembg 반환 형식을 알 수 없습니다: {type(out)!r}")


def fit_image_center_square(image):
    """1:1 정사각형으로 중앙 기준 cover — 프레임을 최대한 크게 채운다."""
    image = _to_rgba(image)

    w, h = image.size
    if w < 1 or h < 1:
        raise ValueError("유효하지 않은 이미지 크기입니다.")

    side = max(w, h)
    if w == h:
        return image

    scale = side / min(w, h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    scaled = image.resize((new_w, new_h), _pil_resample_lanczos())

    left = max(0, (new_w - side) // 2)
    top = max(0, (new_h - side) // 2)
    return scaled.crop((left, top, left + side, top + side))


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


def _stage_pil_image_to_tmp(image, *, prefix: str = "clip") -> Path:
    tmp_dir = get_table_editor_tmp_dir()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{prefix}_{uuid.uuid4().hex}.png"
    prepared = _remove_background_rembg(image)
    square = fit_image_center_square(prepared)
    square.save(tmp_path, format="PNG")
    return tmp_path.resolve()


def stage_clipboard_image_to_tmp() -> Path:
    """클립보드 이미지를 .table_editor_tmp 에 저장하고 경로 반환."""
    image = get_clipboard_image()
    if image is None:
        raise ValueError("클립보드에 이미지가 없습니다.")
    return _stage_pil_image_to_tmp(image, prefix="clip")


def stage_image_file_to_tmp(source: Path | str) -> Path:
    """이미지 파일을 PNG로 변환해 .table_editor_tmp 에 저장하고 경로 반환."""
    try:
        from PIL import Image
    except ImportError as ex:
        raise ImportError(
            "이미지 파일을 사용하려면 Pillow가 필요합니다: "
            "py -3 -m pip install Pillow"
        ) from ex

    path = Path(source).expanduser()
    if not path.is_file():
        raise ValueError(f"파일을 찾을 수 없습니다: {path}")
    if path.suffix.lower() not in _IMAGE_SUFFIXES:
        supported = ", ".join(_IMAGE_SUFFIXES)
        raise ValueError(
            f"지원하지 않는 이미지 형식입니다: {path.suffix or '(확장자 없음)'}\n"
            f"지원: {supported}"
        )
    with Image.open(path) as image:
        return _stage_pil_image_to_tmp(image.copy(), prefix="drop")


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


def _copy_image_windows_powershell(image) -> None:
    """Windows: PNG 임시 파일 → System.Windows.Forms.Clipboard.SetImage."""
    tmp = Path(tempfile.mktemp(suffix=".png"))
    try:
        image.save(tmp, format="PNG")
        path_ps = str(tmp.resolve()).replace("'", "''")
        cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            f"$img=[System.Drawing.Image]::FromFile('{path_ps}'); "
            "[System.Windows.Forms.Clipboard]::SetImage($img); "
            "$img.Dispose()"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Sta", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise OSError(err or f"PowerShell 종료 코드 {proc.returncode}")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def copy_pil_image_to_system_clipboard(image) -> None:
    """PIL 이미지를 OS 클립보드에 넣는다 (Windows)."""
    try:
        from PIL import Image
    except ImportError as ex:
        raise ImportError(
            "클립보드 복사에 Pillow가 필요합니다: py -3 -m pip install Pillow"
        ) from ex

    if not isinstance(image, Image.Image):
        raise TypeError(f"이미지 형식이 올바르지 않습니다: {type(image)!r}")

    prepared = _to_rgba(image)
    if sys.platform == "win32":
        _copy_image_windows_powershell(prepared)
        return
    raise OSError("클립보드 이미지 복사는 현재 Windows에서만 지원합니다.")


def prepare_word_image_for_clipboard(image, *, remove_background: bool):
    """클립보드 복사용 — 배경x면 rembg, 배경o면 원본 유지, 둘 다 1:1 정사각형."""
    prepared = _to_rgba(image)
    if remove_background:
        prepared = _remove_background_rembg(prepared)
    return fit_image_center_square(prepared)


def stage_prepared_image_to_tmp(image, *, prefix: str = "clip") -> Path:
    """전처리된 PIL 이미지를 편집기 미리보기·저장 대기용 임시 PNG로 저장."""
    tmp_dir = get_table_editor_tmp_dir()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{prefix}_{uuid.uuid4().hex}.png"
    _to_rgba(image).save(tmp_path, format="PNG")
    return tmp_path.resolve()


def copy_pil_image_processed(image, *, remove_background: bool) -> None:
    """PIL 이미지를 전처리한 뒤 OS 클립보드에 넣는다."""
    copy_pil_image_to_system_clipboard(
        prepare_word_image_for_clipboard(image, remove_background=remove_background)
    )


def copy_word_image_from_path(path: Path | str, *, remove_background: bool) -> None:
    """단어 이미지 파일을 클립보드에 복사한다."""
    try:
        from PIL import Image
    except ImportError as ex:
        raise ImportError(
            "클립보드 복사에 Pillow가 필요합니다: py -3 -m pip install Pillow"
        ) from ex

    src = Path(path).expanduser()
    if not src.is_file():
        raise ValueError(f"파일을 찾을 수 없습니다: {src}")

    with Image.open(src) as loaded:
        copy_pil_image_processed(loaded.copy(), remove_background=remove_background)
