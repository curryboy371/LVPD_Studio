"""raw_sentence 슬롯 편집 (+ / − / ↓, 미리보기, words id 그리드)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from extra.table_editor.services.raw_sentence_slots import (
    COMMA_PUNCT,
    PUNCT_CHOICES,
    SentenceSlot,
    parse_raw_sentence,
    raw_to_display,
    slot_column_header,
    slots_to_raw,
)
from extra.table_editor.services.word_lookup import (
    clear_words_index_cache,
    format_word_ids,
    lookup_word_ids,
)

_SLOT_TYPES: tuple[str, ...] = ("단어", ", ", "?", "？")
_COL_MINWIDTH = 88
_GRID_PAD = 4


def _combo_kind_label(combo: ttk.Combobox) -> str:
    """콤보 값 (`, ` 는 strip 하면 `,`만 남아 단어로 오인됨)."""
    return combo.get() or "단어"


def _normalize_punct_kind(label: str) -> str | None:
    if label in PUNCT_CHOICES:
        return label
    if label == ",":
        return COMMA_PUNCT
    return None


class RawSentenceSlotsEditor(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        label: str = "raw_sentence",
        show_field_label: bool = True,
        initial_value: str = "",
    ) -> None:
        super().__init__(master)
        clear_words_index_cache()

        self._label = label
        self._slots: list[SentenceSlot] = parse_raw_sentence(initial_value)
        self._line_rows: list[ttk.Frame] = []
        self._type_combos: list[ttk.Combobox] = []
        self._entries: list[ttk.Entry] = []

        if show_field_label:
            ttk.Label(self, text=label, width=18).pack(side=tk.LEFT, anchor=tk.N)
            right = ttk.Frame(self)
            right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        else:
            right = self

        self._lines_host = ttk.Frame(right)
        self._lines_host.pack(fill=tk.X)

        preview_frame = ttk.Frame(right)
        preview_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(preview_frame, text="미리보기:").pack(side=tk.LEFT)
        self._preview_var = tk.StringVar()
        ttk.Label(
            preview_frame,
            textvariable=self._preview_var,
            wraplength=520,
            foreground="#333",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        self._grid_host = ttk.LabelFrame(right, text="슬롯 · words (한자 / word id)")
        self._grid_host.pack(fill=tk.X, pady=(8, 0))
        self._grid_inner = ttk.Frame(self._grid_host)
        self._grid_inner.pack(fill=tk.X, padx=6, pady=6)

        self._rebuild_all_rows()

    def _rebuild_all_rows(self) -> None:
        for row in self._line_rows:
            row.destroy()
        self._line_rows.clear()
        self._type_combos.clear()
        self._entries.clear()
        if not self._slots:
            self._slots = [SentenceSlot("word", "")]
        for i, slot in enumerate(self._slots):
            self._build_row_ui(i, slot)
        self._refresh_preview()

    def _slot_type_label(self, slot: SentenceSlot) -> str:
        if slot.kind == "punct":
            if slot.text in ("?", "？"):
                return slot.text
            if slot.text in (",", "，", ", "):
                return ", "
            return slot.text if slot.text in PUNCT_CHOICES else ", "
        return "단어"

    def _build_row_ui(self, index: int, slot: SentenceSlot) -> None:
        row = ttk.Frame(self._lines_host)
        row.pack(fill=tk.X, pady=2)

        type_label = self._slot_type_label(slot)
        type_combo = ttk.Combobox(
            row,
            values=list(_SLOT_TYPES),
            state="readonly",
            width=7,
        )
        type_combo.set(type_label)
        type_combo.pack(side=tk.LEFT, padx=(0, 4))
        type_combo.bind("<<ComboboxSelected>>", lambda _e, i=index: self._on_type_changed(i))

        entry = ttk.Entry(row, width=40)
        if slot.kind == "word":
            if slot.text:
                entry.insert(0, slot.text)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind("<KeyRelease>", lambda _e: self._sync_from_ui())
        if slot.kind == "punct":
            entry.configure(state="disabled")

        ttk.Button(
            row, text="+", width=3, command=lambda i=index: self._insert_after(i)
        ).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Button(
            row, text="−", width=3, command=lambda i=index: self._remove_at(i)
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            row, text="↓", width=3, command=lambda i=index: self._move_down(i)
        ).pack(side=tk.LEFT, padx=2)

        self._line_rows.append(row)
        self._type_combos.append(type_combo)
        self._entries.append(entry)

    def _sync_from_ui(self) -> None:
        self._slots = self._read_slots_from_ui()
        self._refresh_preview()

    def _read_slots_from_ui(self) -> list[SentenceSlot]:
        out: list[SentenceSlot] = []
        for combo, entry in zip(self._type_combos, self._entries):
            kind_label = _combo_kind_label(combo)
            punct = _normalize_punct_kind(kind_label)
            if punct is not None:
                out.append(SentenceSlot("punct", punct))
            else:
                out.append(SentenceSlot("word", entry.get().strip()))
        return out

    def _on_type_changed(self, index: int) -> None:
        self._slots = self._read_slots_from_ui()
        label = _combo_kind_label(self._type_combos[index])
        punct = _normalize_punct_kind(label)
        if punct is not None:
            self._slots[index] = SentenceSlot("punct", punct)
            self._entries[index].configure(state="disabled")
            self._entries[index].delete(0, tk.END)
        else:
            self._slots[index] = SentenceSlot("word", "")
            self._entries[index].configure(state="normal")
        self._rebuild_all_rows()

    def _insert_after(self, index: int) -> None:
        self._slots = self._read_slots_from_ui()
        self._slots.insert(index + 1, SentenceSlot("word", ""))
        self._rebuild_all_rows()
        if index + 1 < len(self._entries):
            self._entries[index + 1].focus_set()

    def _remove_at(self, index: int) -> None:
        self._slots = self._read_slots_from_ui()
        if len(self._slots) <= 1:
            self._slots = [SentenceSlot("word", "")]
        else:
            del self._slots[index]
        self._rebuild_all_rows()

    def _move_down(self, index: int) -> None:
        self._slots = self._read_slots_from_ui()
        if index >= len(self._slots) - 1:
            return
        self._slots[index], self._slots[index + 1] = (
            self._slots[index + 1],
            self._slots[index],
        )
        self._rebuild_all_rows()

    def _refresh_preview(self) -> None:
        self._slots = self._read_slots_from_ui() if self._type_combos else self._slots
        raw = slots_to_raw(self._slots)
        self._preview_var.set(raw_to_display(raw))
        self._refresh_word_grid()

    def _refresh_word_grid(self) -> None:
        for child in self._grid_inner.winfo_children():
            child.destroy()

        slots = self._slots
        if not slots:
            ttk.Label(self._grid_inner, text="(슬롯 없음)").grid(row=0, column=0, sticky="w")
            return

        ttk.Label(self._grid_inner, text="구분", width=10, anchor="e").grid(
            row=0, column=0, sticky="e", padx=(0, _GRID_PAD), pady=2
        )
        ttk.Label(self._grid_inner, text="한자", width=10, anchor="e").grid(
            row=1, column=0, sticky="e", padx=(0, _GRID_PAD), pady=2
        )
        ttk.Label(self._grid_inner, text="word id", width=10, anchor="e").grid(
            row=2, column=0, sticky="e", padx=(0, _GRID_PAD), pady=2
        )

        word_idx = 0
        for col, slot in enumerate(slots, start=1):
            s = slot.normalized()
            header = slot_column_header(s, word_idx)
            if s.kind == "word":
                word_idx += 1
                hanzi = s.text or "—"
                ids = lookup_word_ids(s.text)
                id_text = format_word_ids(ids)
                if not ids:
                    id_fg = "#c00"
                elif len(ids) > 1:
                    id_fg = "#a60"
                else:
                    id_fg = "#222"
                hanzi_fg = "#222"
            else:
                hanzi = "—"
                id_text = "—"
                id_fg = "#888"
                hanzi_fg = "#888"

            tk.Label(
                self._grid_inner,
                text=header,
                anchor="center",
                font=("", 9, "bold"),
                relief="groove",
                bd=1,
                padx=_GRID_PAD,
                pady=4,
                width=10,
            ).grid(row=0, column=col, sticky="nsew", padx=1, pady=1)

            tk.Label(
                self._grid_inner,
                text=hanzi,
                anchor="center",
                foreground=hanzi_fg,
                relief="groove",
                bd=1,
                padx=_GRID_PAD,
                pady=6,
                width=10,
            ).grid(row=1, column=col, sticky="nsew", padx=1, pady=1)

            tk.Label(
                self._grid_inner,
                text=id_text,
                anchor="center",
                foreground=id_fg,
                relief="groove",
                bd=1,
                padx=_GRID_PAD,
                pady=6,
                width=10,
                font=("", 9),
            ).grid(row=2, column=col, sticky="nsew", padx=1, pady=1)

            self._grid_inner.grid_columnconfigure(col, minsize=_COL_MINWIDTH, weight=1)

    def get_value(self) -> str:
        self._slots = self._read_slots_from_ui()
        return slots_to_raw(self._slots)

