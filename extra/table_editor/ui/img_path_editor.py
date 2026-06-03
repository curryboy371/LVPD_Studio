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
    copy_pil_image_to_system_clipboard,
    discard_staged_image,
    get_clipboard_image,
    prepare_word_image_for_clipboard,
    stage_image_file_to_tmp,
    stage_prepared_image_to_tmp,
)
from extra.table_editor.ui.file_drop import bind_file_drop
from extra.table_editor.services.image_paths import (
    _IMAGE_SUFFIXES,
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

        clip_row = ttk.Frame(entry_frame)
        clip_row.pack(fill=tk.X, pady=(4, 0))
        self._copy_bg_x_btn = ttk.Button(
            clip_row,
            text="클립보드(배경x)",
            command=lambda: self._copy_image_to_clipboard(remove_background=True),
        )
        self._copy_bg_x_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        self._copy_bg_o_btn = ttk.Button(
            clip_row,
            text="클립보드(배경o)",
            command=lambda: self._copy_image_to_clipboard(remove_background=False),
        )
        self._copy_bg_o_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

        preview_outer = ttk.LabelFrame(
            self,
            text="이미지 미리보기 (파일 드래그 앤 드롭 가능)",
        )
        preview_outer.pack(fill=tk.X, pady=4)
        self._preview_outer = preview_outer
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
        bind_file_drop(self._preview_outer, self._on_files_dropped)
        bind_file_drop(self._preview_label, self._on_files_dropped)

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
        self._copy_bg_x_btn.configure(state=state)
        self._copy_bg_o_btn.configure(state=state)
        if not enabled:
            self._photo = None
            self._preview_label.configure(image="", text="(이미지 미사용)")
            if not initial or self._pending_tmp is None:
                self._status_var.set(f"img_path = {IMG_PATH_NONE}")
            return
        self._status_var.set("")
        self._refresh_preview()

    def _widget_text(self, widget: tk.Widget) -> str:
        if isinstance(widget, ttk.Combobox):
            return (widget.get() or "").strip()
        if isinstance(widget, tk.Text):
            return widget.get("1.0", tk.END).strip()
        return (widget.get() or "").strip()

    def _row_context(self) -> tuple[str, str, str]:
        """행 편집 창 id·word·sound_path (부모 체인에서 _widgets 탐색)."""
        word_id = ""
        word = ""
        sound_path = ""
        w: tk.Misc | None = self
        while w is not None:
            widgets = getattr(w, "_widgets", None)
            if isinstance(widgets, dict):
                id_w = widgets.get("id")
                if id_w is not None:
                    word_id = self._widget_text(id_w)
                word_w = widgets.get("word")
                if word_w is not None:
                    word = self._widget_text(word_w)
                sound_w = widgets.get("sound_path")
                if sound_w is not None:
                    sound_path = self._widget_text(sound_w)
                break
            w = w.master
        return word_id, word, sound_path

    def _word_context(self) -> tuple[str, str]:
        word_id, word, _sound = self._row_context()
        return word_id, word

    def _refresh_preview(self) -> None:
        if not self.is_image_enabled():
            return
        word_id, word, sound_path = self._row_context()
        path = preview_image_path(
            self._repo_root,
            self._path_var.get(),
            word_id=word_id,
            word=word,
            sound_path=sound_path,
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

    def _apply_staged_tmp(self, tmp: Path, *, source_label: str) -> None:
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
            f"{source_label}가 임시 저장되었습니다.\n"
            f"「저장」을 누르면 아래 경로의 파일이 교체됩니다:\n{target}"
        )
        self._refresh_preview()

    def _load_image_for_clipboard_buttons(self):
        """클립보드 버튼용 소스 — OS 클립보드 우선, 없을 때만 저장 파일·임시본."""
        from PIL import Image

        clip = get_clipboard_image()
        if clip is not None:
            return clip

        word_id, word, sound_path = self._row_context()
        path = preview_image_path(
            self._repo_root,
            self._path_var.get(),
            word_id=word_id,
            word=word,
            sound_path=sound_path,
            pending_tmp=self._pending_tmp,
        )
        if path is None:
            return None
        with Image.open(path) as loaded:
            return loaded.copy()

    def _copy_image_to_clipboard(self, *, remove_background: bool) -> None:
        if not self.is_image_enabled():
            return
        tag = "배경x" if remove_background else "배경o"
        try:
            source = self._load_image_for_clipboard_buttons()
            if source is None:
                messagebox.showinfo(
                    "클립보드 복사",
                    "복사할 이미지가 없습니다.\n\n"
                    "• resource/image/word/ 에 단어 이미지가 있거나\n"
                    "• 미리보기에 이미지를 드래그해 둔 뒤, 또는\n"
                    "• Windows 클립보드에 이미지를 넣은 다음 다시 시도하세요.",
                    parent=self,
                )
                return
            prepared = prepare_word_image_for_clipboard(
                source, remove_background=remove_background
            )
            tmp = stage_prepared_image_to_tmp(prepared, prefix="clip")
            self._apply_staged_tmp(tmp, source_label=f"클립보드({tag})")
            copy_pil_image_to_system_clipboard(prepared)
            self._status_var.set(
                f"클립보드({tag})로 복사했습니다. 미리보기에 반영되었습니다.\n"
                f"「저장」을 누르면 아래 경로의 파일이 교체됩니다:\n"
                f"{self._commit_target}"
            )
        except ImportError as ex:
            messagebox.showerror("클립보드 복사", str(ex), parent=self)
        except ValueError as ex:
            messagebox.showinfo("클립보드 복사", str(ex), parent=self)
        except OSError as ex:
            messagebox.showerror(
                "클립보드 복사",
                f"클립보드에 넣지 못했습니다:\n{ex}",
                parent=self,
            )

    def _on_files_dropped(self, paths: list[Path]) -> None:
        if not self.is_image_enabled():
            return
        image_path: Path | None = None
        for path in paths:
            if path.suffix.lower() in _IMAGE_SUFFIXES:
                image_path = path
                break
        if image_path is None:
            messagebox.showinfo(
                "드래그 앤 드롭",
                "이미지 파일(.png, .jpg, .webp 등)을 놓아 주세요.",
                parent=self,
            )
            return
        try:
            tmp = stage_image_file_to_tmp(image_path)
        except ImportError as ex:
            messagebox.showerror("드래그 앤 드롭", str(ex), parent=self)
            return
        except ValueError as ex:
            messagebox.showinfo("드래그 앤 드롭", str(ex), parent=self)
            return
        except OSError as ex:
            messagebox.showerror(
                "드래그 앤 드롭",
                f"임시 저장 실패:\n{ex}",
                parent=self,
            )
            return
        self._apply_staged_tmp(tmp, source_label="드롭한 이미지")

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
