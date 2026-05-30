"""Toplevel 창을 부모(또는 화면) 중앙에 배치."""
from __future__ import annotations

import tkinter as tk


def _parse_size_from_geometry(geo: str) -> tuple[int, int]:
    if not geo:
        return 0, 0
    size = geo.split("+", 1)[0]
    if "x" not in size:
        return 0, 0
    w_str, h_str = size.split("x", 1)
    try:
        return max(int(w_str), 1), max(int(h_str), 1)
    except ValueError:
        return 0, 0


def _toplevel_size(
    window: tk.Misc,
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    if width and height and width > 1 and height > 1:
        return width, height
    w, h = _parse_size_from_geometry(window.geometry())
    if w > 1 and h > 1:
        return w, h
    window.update_idletasks()
    w, h = window.winfo_width(), window.winfo_height()
    if w > 1 and h > 1:
        return w, h
    return max(window.winfo_reqwidth(), 1), max(window.winfo_reqheight(), 1)


def _anchor_rect(parent: tk.Misc) -> tuple[int, int, int, int]:
    anchor = parent.winfo_toplevel()
    anchor.update_idletasks()
    try:
        if anchor.winfo_ismapped() and anchor.winfo_width() > 1:
            return (
                anchor.winfo_rootx(),
                anchor.winfo_rooty(),
                anchor.winfo_width(),
                anchor.winfo_height(),
            )
    except tk.TclError:
        pass
    return 0, 0, anchor.winfo_screenwidth(), anchor.winfo_screenheight()


def parse_window_geometry_size(geo: str) -> tuple[int | None, int | None]:
    w, h = _parse_size_from_geometry(geo)
    return (w if w > 1 else None, h if h > 1 else None)


def center_toplevel_on_parent(
    window: tk.Misc,
    parent: tk.Misc,
    *,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """창 중심이 부모(메인) 창 중앙에 오도록 배치."""
    window.update_idletasks()
    w, h = _toplevel_size(window, width, height)
    px, py, pw, ph = _anchor_rect(parent)
    x = px + max(0, (pw - w) // 2)
    y = py + max(0, (ph - h) // 2)
    window.geometry(f"{w}x{h}+{x}+{y}")


def schedule_center_toplevel_on_parent(
    window: tk.Misc,
    parent: tk.Misc,
    *,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """레이아웃·표시 완료 후 중앙 배치."""

    def _place() -> None:
        center_toplevel_on_parent(window, parent, width=width, height=height)

    def _on_map(event: tk.Event) -> None:
        if event.widget is window:
            window.after_idle(_place)

    window.after_idle(_place)
    window.bind("<Map>", _on_map, add="+")
