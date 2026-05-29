"""raw_sentence 슬롯 칸 그리드 (한자 / word id)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from extra.table_editor.services.raw_sentence_slots import SentenceSlot, slot_column_header
from extra.table_editor.services.word_lookup import format_word_ids, lookup_word_ids

_COL_MINWIDTH = 88
_GRID_PAD = 4


def render_sentence_slot_grid(
    master: tk.Misc,
    slots: list[SentenceSlot],
    *,
    title: str,
) -> ttk.LabelFrame:
    host = ttk.LabelFrame(master, text=title)
    inner = ttk.Frame(host)
    inner.pack(fill=tk.X, padx=6, pady=6)

    if not slots:
        ttk.Label(inner, text="(슬롯 없음)").pack(anchor="w")
        return host

    ttk.Label(inner, text="구분", width=10, anchor="e").grid(
        row=0, column=0, sticky="e", padx=(0, _GRID_PAD), pady=2
    )
    ttk.Label(inner, text="한자", width=10, anchor="e").grid(
        row=1, column=0, sticky="e", padx=(0, _GRID_PAD), pady=2
    )
    ttk.Label(inner, text="word id", width=10, anchor="e").grid(
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
            inner,
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
            inner,
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
            inner,
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

        inner.grid_columnconfigure(col, minsize=_COL_MINWIDTH, weight=1)

    return host
