"""Treeview 행 우클릭 메뉴 — 클립보드 복사."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable


def copy_text_to_clipboard(widget: tk.Misc, text: str) -> None:
    widget.clipboard_clear()
    widget.clipboard_append(text)


def attach_tree_row_copy_menu(
    tree: ttk.Treeview,
    get_row: Callable[[], dict[str, str] | None],
    get_copy_text: Callable[[dict[str, str]], str],
    *,
    label: str = "완성형 문장 복사",
    parent: tk.Misc,
    on_status: Callable[[str], None] | None = None,
) -> None:
    """*tree* 우클릭 시 *label* 메뉴로 *get_copy_text(row)* 를 클립보드에 복사."""

    menu = tk.Menu(tree, tearoff=0)

    def _copy_row(row: dict[str, str]) -> None:
        text = (get_copy_text(row) or "").strip()
        if not text:
            messagebox.showinfo(
                "복사",
                "복사할 내용이 없습니다.",
                parent=parent,
            )
            return
        copy_text_to_clipboard(tree, text)
        if on_status:
            preview = text if len(text) <= 48 else text[:45] + "…"
            on_status(f"클립보드 복사: {preview}")

    def _show_menu(event: tk.Event) -> None:
        iid = tree.identify_row(event.y)
        if iid:
            tree.selection_set(iid)
            tree.focus(iid)
        row = get_row()
        menu.delete(0, tk.END)
        if row is None:
            menu.add_command(label=label, state=tk.DISABLED)
        else:
            text = (get_copy_text(row) or "").strip()
            state = tk.NORMAL if text else tk.DISABLED

            def _do_copy(r: dict[str, str] = row) -> None:
                _copy_row(r)

            menu.add_command(label=label, state=state, command=_do_copy)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    tree.bind("<Button-3>", _show_menu, add="+")
