"""Edit or create one table row."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from extra.table_editor.config import (
    BASE_EDITOR_FIELDNAMES,
    COMBOBOX_FIELD_CHOICES,
    IMG_PATH_FIELD,
    LONG_TEXT_FIELDS,
    MASKING_FIELD,
    MULTILINE_LINES_FIELDS,
    RAW_SENTENCE_FIELD,
    ROW_EDITOR_GEOMETRY_DEFAULT,
    ROW_EDITOR_GEOMETRY_WORDS,
    ROW_EDITOR_MINSIZE_DEFAULT,
    ROW_EDITOR_MINSIZE_WORDS,
    SUB_ALT_WORD_ID_FIELD,
    SUB_EDITOR_FIELDNAMES,
    SUB_SLOT_ORDER_FIELD,
)
from extra.table_editor.data.fields import BASE_FIELDNAMES
from extra.table_editor.services.masking_format import (
    masking_for_display,
    masking_for_storage,
)
from extra.table_editor.services.word_autofill import apply_hanzi_autofill
from extra.table_editor.ui.img_path_editor import ImgPathEditor
from extra.table_editor.ui.multiline_lines_editor import MultilineLinesEditor
from extra.table_editor.ui.raw_sentence_slots_editor import RawSentenceSlotsEditor
from extra.table_editor.ui.sub_replacement_slots_editor import SubReplacementSlotsEditor


class RowEditorDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        fieldnames: list[str],
        row: dict[str, str],
        *,
        title: str = "행 편집",
        is_new: bool = False,
        existing_ids: set[str] | None = None,
        original_id: str | None = None,
        on_save: Callable[[dict[str, str], bool], None],
        base_raw_sentence: str = "",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self._is_new = is_new
        self._existing_ids = existing_ids or set()
        self._original_id = (original_id or row.get("id", "")).strip()
        self._on_save = on_save
        self._widgets: dict[
            str,
            tk.Entry | tk.Text | ttk.Combobox | MultilineLinesEditor | RawSentenceSlotsEditor,
        ] = {}
        self._img_editor: ImgPathEditor | None = None
        self._raw_sentence_editor: RawSentenceSlotsEditor | None = None
        self._sub_slots_editor: SubReplacementSlotsEditor | None = None
        self._scroll_canvas: tk.Canvas | None = None
        self._is_words_editor = IMG_PATH_FIELD in fieldnames
        self._is_base_editor = (
            RAW_SENTENCE_FIELD in fieldnames and "base_id" not in fieldnames
        )
        self._is_sub_editor = (
            "base_id" in fieldnames and SUB_SLOT_ORDER_FIELD not in fieldnames
        )
        self._original_row = dict(row)
        if self._is_base_editor:
            self._fieldnames = list(BASE_EDITOR_FIELDNAMES)
        elif self._is_sub_editor:
            self._fieldnames = list(SUB_EDITOR_FIELDNAMES)
        else:
            self._fieldnames = list(fieldnames)

        is_words = self._is_words_editor
        if is_words:
            self.geometry(ROW_EDITOR_GEOMETRY_WORDS)
            self.minsize(*ROW_EDITOR_MINSIZE_WORDS)
        elif self._is_base_editor or self._is_sub_editor:
            self.geometry("820x720")
            self.minsize(560, 480)
        else:
            self.geometry(ROW_EDITOR_GEOMETRY_DEFAULT)
            self.minsize(*ROW_EDITOR_MINSIZE_DEFAULT)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        canvas = tk.Canvas(body, borderwidth=0, highlightthickness=0)
        self._scroll_canvas = canvas
        scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        def _on_inner_configure(_event: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event: tk.Event) -> None:
            canvas.itemconfigure(canvas_window, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        self._bind_dialog_mousewheel()

        if self._is_base_editor:
            slot_block = ttk.LabelFrame(inner, text="슬롯 (raw_sentence)")
            slot_block.pack(fill=tk.X, padx=12, pady=4)
            slot_editor = RawSentenceSlotsEditor(
                slot_block,
                show_field_label=False,
                initial_value=row.get(RAW_SENTENCE_FIELD, ""),
            )
            slot_editor.pack(fill=tk.X, padx=4, pady=4)
            self._raw_sentence_editor = slot_editor

        if self._is_sub_editor:
            slot_block = ttk.Frame(inner)
            slot_block.pack(fill=tk.X, padx=12, pady=4)
            sub_editor = SubReplacementSlotsEditor(
                slot_block,
                base_raw_sentence=base_raw_sentence,
                slot_order_value=row.get(SUB_SLOT_ORDER_FIELD, ""),
                alt_word_id_value=row.get(SUB_ALT_WORD_ID_FIELD, ""),
            )
            sub_editor.pack(fill=tk.X)
            self._sub_slots_editor = sub_editor

        for col in self._fieldnames:
            value = row.get(col, "")
            if col == RAW_SENTENCE_FIELD:
                continue
            if col == IMG_PATH_FIELD:
                block = ttk.Frame(inner)
                block.pack(fill=tk.X, padx=12, pady=4)
                self._img_editor = ImgPathEditor(block, initial_path=value)
                self._img_editor.pack(fill=tk.X)
                continue

            if col in MULTILINE_LINES_FIELDS or (self._is_base_editor and col == "tip"):
                editor = MultilineLinesEditor(inner, label=col, initial_value=value)
                editor.pack(fill=tk.X, padx=12, pady=4)
                self._widgets[col] = editor
                continue

            row_frame = ttk.Frame(inner)
            row_frame.pack(fill=tk.X, padx=12, pady=4)
            ttk.Label(row_frame, text=col, width=18).pack(side=tk.LEFT, anchor="n")
            if col in COMBOBOX_FIELD_CHOICES:
                self._widgets[col] = self._make_combobox(row_frame, col, value)
            elif col in LONG_TEXT_FIELDS:
                text = tk.Text(row_frame, height=4, width=52, wrap=tk.WORD)
                text.insert("1.0", value)
                text.pack(side=tk.LEFT, fill=tk.X, expand=True)
                self._widgets[col] = text
            else:
                display_value = (
                    masking_for_display(value) if col == MASKING_FIELD else value
                )
                entry = ttk.Entry(row_frame, width=54)
                entry.insert(0, display_value)
                entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
                self._widgets[col] = entry

        if "tts_type" in self._widgets and "tts_voice" in self._widgets:
            tts_combo = self._widgets["tts_type"]
            tts_combo.bind("<<ComboboxSelected>>", self._sync_tts_voice_state)
            self._sync_tts_voice_state()
        elif "tts" in self._widgets and "tts_voice" in self._widgets:
            self._widgets["tts"].bind("<<ComboboxSelected>>", self._sync_tts_voice_state)
            self._sync_tts_voice_state()

        if self._img_editor is not None:
            for key in ("id", "word"):
                w = self._widgets.get(key)
                if w is not None:
                    w.bind("<KeyRelease>", lambda _e: self._img_editor._refresh_preview())

        if self._is_new and self._is_words_editor:
            word_w = self._widgets.get("word")
            if isinstance(word_w, ttk.Entry):
                word_w.bind("<Return>", self._on_word_enter_autofill)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=8, pady=12, side=tk.BOTTOM)
        ttk.Button(btn_frame, text="저장", command=self._save).pack(side=tk.RIGHT, padx=(4, 12))
        ttk.Button(btn_frame, text="취소", command=self._cancel).pack(side=tk.RIGHT, padx=4)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Control-Return>", lambda _e: self._save())
        self.after_idle(_on_inner_configure)

    def _bind_dialog_mousewheel(self) -> None:
        def _on_wheel(event: tk.Event) -> None:
            canvas = self._scroll_canvas
            if canvas is None:
                return
            if event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(3, "units")

        self.bind("<MouseWheel>", _on_wheel)
        self.bind("<Button-4>", _on_wheel)
        self.bind("<Button-5>", _on_wheel)

    def _set_field_value(self, col: str, value: str) -> None:
        if col == IMG_PATH_FIELD:
            if self._img_editor is not None:
                self._img_editor.set_path_value(value)
            return
        w = self._widgets.get(col)
        if w is None:
            return
        if isinstance(w, MultilineLinesEditor):
            w.set_value(value)
            return
        if isinstance(w, tk.Text):
            w.delete("1.0", tk.END)
            w.insert("1.0", value)
        elif isinstance(w, ttk.Combobox):
            text = (value or "").strip()
            values = list(w.cget("values"))
            if text and text not in values:
                w.configure(values=[text, *values])
            w.set(text)
            if col in ("tts_type", "tts") and text.lower() == "gtts":
                self._sync_tts_voice_state()
            elif col == "tts_voice":
                self._sync_tts_voice_state()
        elif isinstance(w, ttk.Entry):
            show = masking_for_display(value) if col == MASKING_FIELD else value
            w.delete(0, tk.END)
            w.insert(0, show)

    def _on_word_enter_autofill(self, _event: tk.Event | None = None) -> str:
        if not self._is_new or not self._is_words_editor:
            return "break"
        word_w = self._widgets.get("word")
        if not isinstance(word_w, ttk.Entry):
            return "break"
        hanzi = word_w.get().strip()
        if not hanzi:
            return "break"
        image_on = True
        if self._img_editor is not None:
            image_on = self._img_editor.is_image_enabled()
        filled = apply_hanzi_autofill(
            self._read_values(), hanzi, image_enabled=image_on
        )
        if self._img_editor is not None and image_on:
            self._img_editor.set_image_enabled(True, word=hanzi)
        for col, val in filled.items():
            if col in self._fieldnames:
                self._set_field_value(col, val)
        return "break"

    def _make_combobox(self, parent: ttk.Frame, col: str, value: str) -> ttk.Combobox:
        choices = list(COMBOBOX_FIELD_CHOICES[col])
        current = (value or "").strip()
        if current and current not in choices:
            choices = [current, *choices]
        combo = ttk.Combobox(
            parent,
            values=choices,
            state="readonly",
            width=52,
        )
        combo.set(current if current in choices else (choices[0] if choices else ""))
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return combo

    def _tts_engine_value(self) -> str:
        for key in ("tts_type", "tts"):
            w = self._widgets.get(key)
            if isinstance(w, ttk.Combobox):
                return (w.get() or "").strip().lower()
        return ""

    def _sync_tts_voice_state(self, _event: tk.Event | None = None) -> None:
        voice_combo = self._widgets.get("tts_voice")
        if not isinstance(voice_combo, ttk.Combobox):
            return
        if self._tts_engine_value() == "gtts":
            voice_combo.set("")
            voice_combo.configure(state="disabled")
        else:
            voice_combo.configure(state="readonly")

    def _read_values(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self._raw_sentence_editor is not None:
            out[RAW_SENTENCE_FIELD] = self._raw_sentence_editor.get_value()
        if self._sub_slots_editor is not None:
            order, alt_id = self._sub_slots_editor.get_values()
            out[SUB_SLOT_ORDER_FIELD] = order
            out[SUB_ALT_WORD_ID_FIELD] = alt_id
        for col in self._fieldnames:
            if col == IMG_PATH_FIELD:
                if self._img_editor is not None:
                    out[col] = self._img_editor.get_path_value()
                else:
                    out[col] = ""
                continue
            w = self._widgets[col]
            if isinstance(w, MultilineLinesEditor):
                out[col] = w.get_value()
            elif isinstance(w, tk.Text):
                out[col] = w.get("1.0", tk.END).strip()
            elif isinstance(w, ttk.Combobox):
                out[col] = (w.get() or "").strip()
            else:
                raw = w.get().strip()
                out[col] = masking_for_storage(raw) if col == MASKING_FIELD else raw
        if out.get("tts_type", "").strip().lower() == "gtts" or out.get("tts", "").strip().lower() == "gtts":
            out["tts_voice"] = ""
        if self._is_base_editor:
            for col in BASE_FIELDNAMES:
                if col not in out:
                    out[col] = ""
        return out

    def _save(self) -> None:
        values = self._read_values()
        rid = values.get("id", "").strip()
        if not rid:
            messagebox.showwarning("검증", "id를 입력하세요.", parent=self)
            return
        if rid != self._original_id and rid in self._existing_ids:
            messagebox.showwarning(
                "검증",
                f"id {rid} 가 이미 존재합니다.",
                parent=self,
            )
            return
        if self._img_editor is not None:
            try:
                values = self._img_editor.commit_on_save(values)
            except OSError:
                return
        self._on_save(values, self._is_new)
        self._cleanup_img()
        self.destroy()

    def _cancel(self) -> None:
        self._cleanup_img()
        self.destroy()

    def _cleanup_img(self) -> None:
        if self._img_editor is not None:
            self._img_editor.cleanup()
