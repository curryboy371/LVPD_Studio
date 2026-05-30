"""Toplevel 창을 부모(또는 화면) 중앙에 배치."""
from __future__ import annotations

import tkinter as tk


def center_toplevel_on_parent(window: tk.Misc, parent: tk.Misc) -> None:
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    if width <= 1 or height <= 1:
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()

    x: int
    y: int
    try:
        if parent.winfo_ismapped() and parent.winfo_width() > 1:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + max(0, (pw - width) // 2)
            y = py + max(0, (ph - height) // 2)
        else:
            raise tk.TclError("parent not mapped")
    except tk.TclError:
        sw = window.winfo_screenwidth()
        sh = window.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2)

    window.geometry(f"+{x}+{y}")
