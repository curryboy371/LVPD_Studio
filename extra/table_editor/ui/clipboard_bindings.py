"""Global copy/paste/cut/select-all for Entry and Text widgets."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Tcl widget class names (ttk.Entry -> TEntry)
_CLIPBOARD_CLASSES = ("Entry", "TEntry", "Text")


def _copy(widget: tk.Widget) -> str:
    try:
        text = widget.selection_get()  # type: ignore[attr-defined]
    except tk.TclError:
        return "break"
    widget.clipboard_clear()
    widget.clipboard_append(text)
    return "break"


def _cut(widget: tk.Widget) -> str:
    try:
        text = widget.selection_get()  # type: ignore[attr-defined]
    except tk.TclError:
        return "break"
    widget.clipboard_clear()
    widget.clipboard_append(text)
    if isinstance(widget, tk.Text):
        widget.delete("sel.first", "sel.last")
    elif isinstance(widget, (tk.Entry, ttk.Entry)):
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
    return "break"


def _paste(widget: tk.Widget) -> str:
    try:
        text = widget.clipboard_get()
    except tk.TclError:
        return "break"
    if isinstance(widget, tk.Text):
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        widget.insert(tk.INSERT, text)
    elif isinstance(widget, (tk.Entry, ttk.Entry)):
        try:
            widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        widget.insert(tk.INSERT, text)
    return "break"


def _select_all(widget: tk.Widget) -> str:
    if isinstance(widget, tk.Text):
        widget.tag_add(tk.SEL, "1.0", tk.END)
        widget.mark_set(tk.INSERT, "1.0")
        widget.see(tk.INSERT)
    elif isinstance(widget, (tk.Entry, ttk.Entry)):
        widget.selection_range(0, tk.END)
        widget.icursor(tk.END)
    return "break"


_HANDLERS = {
    "copy": _copy,
    "cut": _cut,
    "paste": _paste,
    "select_all": _select_all,
}

_SEQUENCES = (
    ("<Control-c>", "copy"),
    ("<Control-C>", "copy"),
    ("<Control-x>", "cut"),
    ("<Control-X>", "cut"),
    ("<Control-v>", "paste"),
    ("<Control-V>", "paste"),
    ("<Control-a>", "select_all"),
    ("<Control-A>", "select_all"),
)


def bind_clipboard_on_class(root: tk.Misc) -> None:
    """Bind Ctrl+C/V/X/A on all Entry/Text widgets under *root*."""
    for class_name in _CLIPBOARD_CLASSES:
        for sequence, action in _SEQUENCES:
            handler = _HANDLERS[action]

            def _callback(event: tk.Event, h=handler) -> str:
                return h(event.widget)

            root.bind_class(class_name, sequence, _callback, add="+")
