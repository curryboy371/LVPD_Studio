"""sub 치환 슬롯 편집 + base 참고 그리드 + 완성형 문장."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from extra.table_editor.services.raw_sentence_slots import parse_raw_sentence, raw_to_display
from extra.table_editor.services.sub_replacement_slots import (
    ReplacementPair,
    pairs_to_storage,
    parse_replacement_pairs,
)
from extra.table_editor.services.sub_sentence_preview import (
    build_sub_display_sentence,
    combine_slot_and_middle,
    sort_replacement_pairs,
    split_slot_order_display,
)
from extra.table_editor.services.word_lookup import (
    clear_words_index_cache,
    lookup_hanzi_by_word_id,
)
from extra.table_editor.ui.slot_words_grid import render_sentence_slot_grid

_COL_MINWIDTH = 88
_GRID_PAD = 4


class SubReplacementSlotsEditor(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        base_raw_sentence: str = "",
        slot_order_value: str = "",
        alt_word_id_value: str = "",
    ) -> None:
        super().__init__(master)
        clear_words_index_cache()

        self._base_raw_sentence = base_raw_sentence or ""
        self._pairs: list[ReplacementPair] = parse_replacement_pairs(
            slot_order_value, alt_word_id_value
        )
        self._line_rows: list[ttk.Frame] = []
        self._slot_entries: list[ttk.Entry] = []
        self._middle_entries: list[ttk.Entry] = []
        self._id_entries: list[ttk.Entry] = []

        preview = raw_to_display(base_raw_sentence) or "(없음)"
        render_sentence_slot_grid(
            self,
            parse_raw_sentence(base_raw_sentence),
            title=f"base 문장 (참고) — {preview}",
        ).pack(fill=tk.X, pady=(0, 8))

        map_frame = ttk.LabelFrame(self, text="치환 슬롯 (target_slot_order · alt_word_id)")
        map_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            map_frame,
            text="슬롯: 0,1,2… / -1(앞) / end(끝)  ·  아래 중간: .1, .2(삽입)  ·  Enter → 행 순서 정렬",
            foreground="#555",
            wraplength=640,
        ).pack(fill=tk.X, padx=8, pady=(6, 2))

        self._lines_host = ttk.Frame(map_frame)
        self._lines_host.pack(fill=tk.X, padx=6, pady=(0, 6))

        self._sub_grid_host = ttk.LabelFrame(self, text="치환 · words")
        self._sub_grid_host.pack(fill=tk.X)
        self._sub_grid_inner = ttk.Frame(self._sub_grid_host)
        self._sub_grid_inner.pack(fill=tk.X, padx=6, pady=6)

        done_frame = ttk.Frame(self)
        done_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(done_frame, text="완성형 문장:").pack(side=tk.LEFT, anchor="n")
        self._done_var = tk.StringVar(value="")
        ttk.Label(
            done_frame,
            textvariable=self._done_var,
            wraplength=620,
            foreground="#111",
            font=("", 10, "bold"),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        self._rebuild_pair_rows()

    def _rebuild_pair_rows(self) -> None:
        for row in self._line_rows:
            row.destroy()
        self._line_rows.clear()
        self._slot_entries.clear()
        self._middle_entries.clear()
        self._id_entries.clear()
        if not self._pairs:
            self._pairs = [ReplacementPair("", "")]
        for i, pair in enumerate(self._pairs):
            self._build_pair_row(i, pair)
        self._refresh_sub_grid()

    def _build_pair_row(self, index: int, pair: ReplacementPair) -> None:
        block = ttk.Frame(self._lines_host)
        block.pack(fill=tk.X, pady=3)

        row = ttk.Frame(block)
        row.pack(fill=tk.X)

        ttk.Label(row, text="슬롯", width=6).pack(side=tk.LEFT)
        slot_main, slot_mid = split_slot_order_display(pair.slot_order)
        slot_e = ttk.Entry(row, width=8)
        slot_e.pack(side=tk.LEFT, padx=(0, 8))
        if slot_main:
            slot_e.insert(0, slot_main)
        slot_e.bind("<KeyRelease>", lambda _e: self._sync_from_ui())
        slot_e.bind("<Return>", lambda _e: self._on_slot_enter(index))

        ttk.Label(row, text="word id", width=8).pack(side=tk.LEFT)
        id_e = ttk.Entry(row, width=12)
        id_e.pack(side=tk.LEFT, padx=(0, 8))
        if pair.alt_word_id:
            id_e.insert(0, pair.alt_word_id)
        id_e.bind("<KeyRelease>", lambda _e: self._sync_from_ui())

        ttk.Button(
            row, text="+", width=3, command=lambda i=index: self._insert_after(i)
        ).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Button(
            row, text="−", width=3, command=lambda i=index: self._remove_at(i)
        ).pack(side=tk.LEFT)

        mid_row = ttk.Frame(block)
        mid_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(mid_row, text="", width=6).pack(side=tk.LEFT)
        ttk.Label(mid_row, text="중간", width=6).pack(side=tk.LEFT)
        mid_e = ttk.Entry(mid_row, width=8)
        mid_e.pack(side=tk.LEFT, padx=(0, 8))
        if slot_mid:
            mid_e.insert(0, slot_mid)
        mid_e.bind("<KeyRelease>", lambda _e: self._sync_from_ui())
        mid_e.bind("<Return>", lambda _e: self._on_middle_enter(index))
        ttk.Label(
            mid_row,
            text="(예: .1 → 1번 슬롯 뒤 삽입, Enter로 순서 정렬)",
            foreground="#888",
        ).pack(side=tk.LEFT)

        self._line_rows.append(block)
        self._slot_entries.append(slot_e)
        self._middle_entries.append(mid_e)
        self._id_entries.append(id_e)

    def _pair_from_row(self, index: int) -> ReplacementPair:
        slot_e = self._slot_entries[index]
        mid_e = self._middle_entries[index]
        id_e = self._id_entries[index]
        return ReplacementPair(
            slot_order=combine_slot_and_middle(slot_e.get(), mid_e.get()),
            alt_word_id=id_e.get().strip(),
        )

    def _sync_from_ui(self) -> None:
        self._pairs = self._read_pairs_from_ui()
        self._refresh_sub_grid()

    def _read_pairs_from_ui(self) -> list[ReplacementPair]:
        return [self._pair_from_row(i) for i in range(len(self._slot_entries))]

    def _apply_sorted_pairs(self) -> None:
        self._pairs = sort_replacement_pairs(self._read_pairs_from_ui())
        self._rebuild_pair_rows()

    def _on_middle_enter(self, index: int) -> None:
        pair = self._pair_from_row(index)
        self._pairs = self._read_pairs_from_ui()
        if index < len(self._pairs):
            self._pairs[index] = pair
        self._apply_sorted_pairs()
        return "break"

    def _on_slot_enter(self, _index: int) -> None:
        self._apply_sorted_pairs()
        return "break"

    def _insert_after(self, index: int) -> None:
        self._pairs = self._read_pairs_from_ui()
        self._pairs.insert(index + 1, ReplacementPair("", ""))
        self._rebuild_pair_rows()

    def _remove_at(self, index: int) -> None:
        self._pairs = self._read_pairs_from_ui()
        if len(self._pairs) <= 1:
            self._pairs = [ReplacementPair("", "")]
        else:
            del self._pairs[index]
        self._rebuild_pair_rows()

    def _refresh_sub_grid(self) -> None:
        for child in self._sub_grid_inner.winfo_children():
            child.destroy()

        pairs = self._read_pairs_from_ui()
        self._done_var.set(
            build_sub_display_sentence(self._base_raw_sentence, pairs)
        )

        visible = [
            p
            for p in pairs
            if (p.slot_order or "").strip() or (p.alt_word_id or "").strip()
        ]
        if not visible:
            ttk.Label(self._sub_grid_inner, text="(치환 없음)").grid(
                row=0, column=0, sticky="w"
            )
            return

        ttk.Label(self._sub_grid_inner, text="슬롯", width=10, anchor="e").grid(
            row=0, column=0, sticky="e", padx=(0, _GRID_PAD), pady=2
        )
        ttk.Label(self._sub_grid_inner, text="word id", width=10, anchor="e").grid(
            row=1, column=0, sticky="e", padx=(0, _GRID_PAD), pady=2
        )
        ttk.Label(self._sub_grid_inner, text="한자", width=10, anchor="e").grid(
            row=2, column=0, sticky="e", padx=(0, _GRID_PAD), pady=2
        )

        col = 0
        for pair in visible:
            col += 1
            slot_t = (pair.slot_order or "").strip() or "—"
            wid = (pair.alt_word_id or "").strip()
            id_text = wid if wid else "—"
            hanzi = "—"
            id_fg = "#888"
            if wid == "0":
                hanzi = "(제거)"
                id_fg = "#a60"
            elif wid:
                found = lookup_hanzi_by_word_id(wid)
                hanzi = found if found else "—"
                id_fg = "#222" if found else "#c00"

            for row_i, text, fg, bold in (
                (0, slot_t, "#222", True),
                (1, id_text, id_fg, False),
                (2, hanzi, id_fg, False),
            ):
                tk.Label(
                    self._sub_grid_inner,
                    text=text,
                    anchor="center",
                    foreground=fg,
                    relief="groove",
                    bd=1,
                    padx=_GRID_PAD,
                    pady=4,
                    width=10,
                    font=("", 9, "bold") if bold else ("", 9),
                ).grid(row=row_i, column=col, sticky="nsew", padx=1, pady=1)
            self._sub_grid_inner.grid_columnconfigure(
                col, minsize=_COL_MINWIDTH, weight=1
            )

    def get_values(self) -> tuple[str, str]:
        self._pairs = sort_replacement_pairs(self._read_pairs_from_ui())
        return pairs_to_storage(self._pairs)
