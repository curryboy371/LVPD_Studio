"""Windows file drag-and-drop onto tk widgets (optional windnd)."""
from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

if sys.platform == "win32":
    import tkinter as tk


def bind_file_drop(
    widget: tk.Misc,
    on_files: Callable[[list[Path]], None],
) -> None:
    """Drop files onto widget → on_files(paths). No-op off Windows or without windnd."""
    if sys.platform != "win32":
        return

    def _register() -> None:
        try:
            import windnd
        except ImportError:
            return
        if not widget.winfo_exists():
            return

        def _handler(files: list) -> None:
            paths: list[Path] = []
            for item in files:
                raw = item.decode("utf-8") if isinstance(item, bytes) else str(item)
                raw = raw.strip().strip('"').strip("'")
                if raw:
                    paths.append(Path(raw))
            if paths:
                on_files(paths)

        try:
            windnd.hook_dropfiles(widget, func=_handler)
        except OSError:
            pass

    if widget.winfo_ismapped():
        _register()
    else:
        widget.bind("<Map>", lambda _e: _register(), add="+")
