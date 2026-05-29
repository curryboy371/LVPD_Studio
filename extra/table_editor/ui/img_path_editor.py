"""img_path field with preview and clipboard paste (commit on dialog save)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from extra.table_editor.config import (
    IMG_PATH_FIELD,
    IMG_PATH_NONE,
    IMG_PREVIEW_MAX_SIZE,
    get_repo_root,
)
from extra.table_editor.services.image_clipboard import (
    commit_staged_image,
    discard_staged_image,
    stage_clipboard_image_to_tmp,
)
from extra.table_editor.services.image_paths import (
    img_path_value_for_table,
    preview_image_path,
    resolve_image_absolute,
)


class ImgPathEditor(ttk.Frame):
    def __init__(self, master: tk.Misc, *, initial_path: str = "") -> None:
        super().__init__(master)
        self._repo_root = get_repo_root()
        self._pending_tmp: Path | None = None
        self._photo: tk.PhotoImage | None = None
        self._commit_target: Path | None = None

        raw = (initial_path or "").strip()
        use_image = raw.lower() != IMG_PATH_NONE
        self._use_image = tk.BooleanVar(value=use_image)

        path_row = ttk.Frame(self)
        path_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(path_row, text=IMG_PATH_FIELD, width=18).pack(side=tk.LEFT, anchor="n")

        toggle_frame = ttk.Frame(path_row)
        toggle_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Radiobutton(
            toggle_frame,
            text="이미지 사용",
            variable=self._use_image,
            value=True,
            command=self._on_use_toggle,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(
            toggle_frame,
            text="이미지 미사용",
            variable=self._use_image,
            value=False,
            command=self._on_use_toggle,
        ).pack(side=tk.LEFT)

        entry_frame = ttk.Frame(self)
        entry_frame.pack(fill=tk.X, padx=(18, 0), pady=(0, 6))
        self._path_var = tk.StringVar(
            value=raw if use_image else IMG_PATH_NONE,
        )
        self._entry = ttk.Entry(entry_frame, textvariable=self._path_var, width=48)
        self._entry.pack(fill=tk.X, expand=True)
        self._entry.bind("<KeyRelease>", lambda _e: self._refresh_preview())
        self._clipboard_btn = ttk.Button(
            entry_frame,
            text="클립보드 사용",
            command=self._use_clipboard,
        )
        self._clipboard_btn.pack(fill=tk.X, pady=(4, 0))

        preview_outer = ttk.LabelFrame(self, text="이미지 미리보기")
        preview_outer.pack(fill=tk.X, pady=4)
        self._preview_label = ttk.Label(
            preview_outer,
            text="(이미지 없음)",
            anchor=tk.CENTER,
            width=36,
        )
        self._preview_label.pack(padx=8, pady=8, ipady=40)

        self._status_var = tk.StringVar(value="")
        ttk.Label(
            preview_outer,
            textvariable=self._status_var,
            wraplength=480,
            foreground="#555",
        ).pack(fill=tk.X, padx=8, pady=(0, 8))

        self._apply_use_state(initial=True)

    def is_image_enabled(self) -> bool:
        return bool(self._use_image.get())

    def set_image_enabled(self, enabled: bool, *, word: str = "") -> None:
        self._use_image.set(enabled)
        if enabled:
            stem = (word or "").strip()
            if not stem or stem.lower() == IMG_PATH_NONE:
                _, w = self._word_context()
                stem = w
            self._path_var.set(stem or "")
        else:
            if self._pending_tmp is not None:
                discard_staged_image(self._pending_tmp)
                self._pending_tmp = None
                self._commit_target = None
            self._path_var.set(IMG_PATH_NONE)
        self._apply_use_state()

    def set_path_value(self, value: str) -> None:
        raw = (value or "").strip()
        if raw.lower() == IMG_PATH_NONE:
            self.set_image_enabled(False)
        else:
            self.set_image_enabled(True, word=raw)

    def get_path_value(self) -> str:
        if not self.is_image_enabled():
            return IMG_PATH_NONE
        return self._path_var.get().strip()

    def _on_use_toggle(self) -> None:
        if self._use_image.get():
            _, word = self._word_context()
            current = self._path_var.get().strip()
            if not current or current.lower() == IMG_PATH_NONE:
                self._path_var.set(word)
        else:
            if self._pending_tmp is not None:
                discard_staged_image(self._pending_tmp)
                self._pending_tmp = None
                self._commit_target = None
            self._path_var.set(IMG_PATH_NONE)
        self._apply_use_state()

    def _apply_use_state(self, *, initial: bool = False) -> None:
        enabled = self.is_image_enabled()
        state = "normal" if enabled else "disabled"
        self._entry.configure(state=state)
        self._clipboard_btn.configure(state=state)
        if not enabled:
            self._photo = None
            self._preview_label.configure(image="", text="(이미지 미사용)")
            if not initial or self._pending_tmp is None:
                self._status_var.set(f"img_path = {IMG_PATH_NONE}")
            return
        self._status_var.set("")
        self._refresh_preview()

    def _word_context(self) -> tuple[str, str]:
        root = self.winfo_toplevel()
        word_id = ""
        word = ""
        if hasattr(root, "_widgets"):
            widgets = getattr(root, "_widgets", {})
            for key in ("id", "word"):
                w = widgets.get(key)
                if w is None:
                    continue
                if isinstance(w, ttk.Combobox):
                    val = (w.get() or "").strip()
                elif isinstance(w, tk.Text):
                    val = w.get("1.0", tk.END).strip()
                else:
                    val = w.get().strip()
                if key == "id":
                    word_id = val
                else:
                    word = val
        return word_id, word

    def _refresh_preview(self) -> None:
        if not self.is_image_enabled():
            return
        word_id, word = self._word_context()
        path = preview_image_path(
            self._repo_root,
            self._path_var.get(),
            word_id=word_id,
            word=word,
            pending_tmp=self._pending_tmp,
        )
        if path is None:
            self._photo = None
            self._preview_label.configure(image="", text="(이미지 없음)")
            if self._pending_tmp is None:
                self._status_var.set("")
            return
        try:
            from PIL import Image, ImageTk

            img = Image.open(path)
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            img.thumbnail(IMG_PREVIEW_MAX_SIZE, resample)
            self._photo = ImageTk.PhotoImage(img)
            self._preview_label.configure(image=self._photo, text="")
        except Exception as ex:
            self._photo = None
            self._preview_label.configure(image="", text=f"(미리보기 실패)\n{ex}")

    def _use_clipboard(self) -> None:
        if not self.is_image_enabled():
            return
        try:
            tmp = stage_clipboard_image_to_tmp()
        except ImportError as ex:
            messagebox.showerror("클립보드", str(ex), parent=self)
            return
        except ValueError as ex:
            messagebox.showinfo("클립보드", str(ex), parent=self)
            return
        except OSError as ex:
            messagebox.showerror("클립보드", f"임시 저장 실패:\n{ex}", parent=self)
            return

        if self._pending_tmp is not None:
            discard_staged_image(self._pending_tmp)

        word_id, word = self._word_context()
        target = resolve_image_absolute(
            self._repo_root,
            self._path_var.get(),
            word_id=word_id,
            word=word,
        )
        self._pending_tmp = tmp
        self._commit_target = target
        self._status_var.set(
            "클립보드 이미지가 임시 저장되었습니다.\n"
            f"「저장」을 누르면 아래 경로의 파일이 교체됩니다:\n{target}"
        )
        self._refresh_preview()

    def commit_on_save(self, values: dict[str, str]) -> dict[str, str]:
        out = dict(values)
        if not self.is_image_enabled():
            out[IMG_PATH_FIELD] = IMG_PATH_NONE
            discard_staged_image(self._pending_tmp)
            self._pending_tmp = None
            self._commit_target = None
            return out

        out[IMG_PATH_FIELD] = self.get_path_value()
        if self._pending_tmp is None or self._commit_target is None:
            return out
        try:
            commit_staged_image(self._pending_tmp, self._commit_target)
        except OSError as ex:
            messagebox.showerror(
                "이미지 저장",
                f"이미지 파일 교체 실패:\n{ex}",
                parent=self,
            )
            raise
        out[IMG_PATH_FIELD] = img_path_value_for_table(
            self._repo_root, self._commit_target
        )
        discard_staged_image(self._pending_tmp)
        self._pending_tmp = None
        self._commit_target = None
        return out

    def cleanup(self) -> None:
        discard_staged_image(self._pending_tmp)
        self._pending_tmp = None
        self._commit_target = None
