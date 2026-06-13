"""readonly ttk.Combobox — 마우스 휠로 선택값이 바뀌지 않도록 보호."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

_ATTR = "_combobox_scroll_guard"


def find_scroll_canvas(widget: tk.Misc) -> tk.Canvas | None:
    """스크롤 패널 inner에 붙인 ``_scroll_canvas`` 를 상위에서 탐색."""
    w: tk.Misc | None = widget
    while w is not None:
        canvas = getattr(w, "_scroll_canvas", None)
        if isinstance(canvas, tk.Canvas):
            return canvas
        w = w.master if hasattr(w, "master") else None
    return None


def _scroll_canvas(canvas: tk.Canvas, event: tk.Event) -> None:
    if event.delta:
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    elif getattr(event, "num", None) == 4:
        canvas.yview_scroll(-3, "units")
    elif getattr(event, "num", None) == 5:
        canvas.yview_scroll(3, "units")


def block_combobox_mousewheel(
    combo: ttk.Combobox,
    *,
    scroll_canvas: tk.Canvas | None = None,
) -> None:
    """Combobox 위 휠 — 값 변경 대신 패널 스크롤(있을 때)만 수행."""
    if getattr(combo, _ATTR, False):
        return
    setattr(combo, _ATTR, True)

    def _on_wheel(event: tk.Event) -> str:
        if scroll_canvas is not None:
            _scroll_canvas(scroll_canvas, event)
        return "break"

    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        combo.bind(seq, _on_wheel)


def apply_combobox_scroll_guards(
    root: tk.Misc,
    *,
    scroll_canvas: tk.Canvas | None = None,
) -> None:
    """위젯 트리의 모든 Combobox에 휠 보호 바인딩."""
    if scroll_canvas is None:
        scroll_canvas = find_scroll_canvas(root)
    for child in root.winfo_children():
        if isinstance(child, ttk.Combobox):
            block_combobox_mousewheel(child, scroll_canvas=scroll_canvas)
        apply_combobox_scroll_guards(child, scroll_canvas=scroll_canvas)
