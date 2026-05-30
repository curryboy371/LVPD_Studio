"""Launch table editor GUI."""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_on_path() -> None:
    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))


def main() -> None:
    _ensure_repo_on_path()
    try:
        from extra.table_editor.ui.main_window import MainWindow

        app = MainWindow()
        app.mainloop()
    except Exception as ex:
        import traceback

        traceback.print_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Table Editor", f"시작 실패:\n{ex}")
            root.destroy()
        except Exception:
            input("Press Enter to exit…")
        raise SystemExit(1) from ex


if __name__ == "__main__":
    main()
