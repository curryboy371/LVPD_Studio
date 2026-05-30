"""저장 직후 CSV 생성 — 패널 공통."""
from __future__ import annotations

from collections.abc import Callable
from tkinter import messagebox


def export_csv_paths(
    parent,
    on_status: Callable[[str], None],
    write_csv: Callable[[], str | list[str]],
    *,
    show_dialog: bool,
    dialog_title: str = "CSV",
    status_prefix: str = "CSV",
) -> bool:
    try:
        raw = write_csv()
        paths = [raw] if isinstance(raw, str) else list(raw)
        if not paths:
            on_status(f"{status_prefix} 생성 완료")
            return True
        if len(paths) == 1:
            on_status(f"{status_prefix}: {paths[0]}")
        else:
            on_status(f"{status_prefix} 생성 완료 ({len(paths)}개)")
        if show_dialog:
            messagebox.showinfo(
                dialog_title,
                "생성 완료:\n" + "\n".join(paths),
                parent=parent,
            )
        return True
    except Exception as ex:
        messagebox.showerror("CSV 실패", str(ex), parent=parent)
        return False
