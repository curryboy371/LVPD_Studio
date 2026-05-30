"""sub 치환 슬롯 편집 + base 참고 그리드 + 완성형 문장."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from extra.table_editor.services.raw_sentence_slots import parse_raw_sentence, raw_to_display
from extra.table_editor.services.sub_replacement_slots import (
    ReplacementPair,
    index_for_main_slot,
    main_slot_for_pair_index,
    pairs_to_storage,
    parse_replacement_pairs,
)
from extra.table_editor.services.sub_sentence_preview import (
    build_sub_display_sentence,
    sort_replacement_pairs,
)
from extra.table_editor.services.word_lookup import (
    clear_words_index_cache,
    lookup_hanzi_by_word_id,
)
from extra.table_editor.ui.slot_words_grid import render_sentence_slot_grid

_COL_MINWIDTH = 88
_GRID_PAD = 4
_DISPLAY_REFRESH_MS = 250


class SubReplacementSlotsEditor(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        base_raw_sentence: str = "",
        slot_order_value: str = "",
        alt_word_id_value: str = "",
        main_slot_value: str = "",
        initial_display_sentence: str = "",
    ) -> None:
        super().__init__(master)
        clear_words_index_cache()

        self._base_raw_sentence = base_raw_sentence or ""
        self._pairs: list[ReplacementPair] = parse_replacement_pairs(
            slot_order_value, alt_word_id_value
        )
        self._initial_main_slot = (main_slot_value or "").strip()
        self._line_rows: list[ttk.Frame] = []
        self._slot_entries: list[ttk.Entry] = []
        self._id_entries: list[ttk.Entry] = []
        self._main_radios: list[ttk.Radiobutton] = []
        self._focused_id_index = 0
        self._main_pair_index_var = tk.IntVar(
            value=index_for_main_slot(self._pairs, self._initial_main_slot)
        )
        self._applying_sort = False
        self._display_refresh_job: str | None = None

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
            text="슬롯: 0, 1.1, 2.2, -1(앞), end(끝)  ·  main: 회화 재생 시 우측 하단 이미지로 쓸 word",
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
        self._done_var = tk.StringVar(value=initial_display_sentence)
        ttk.Label(
            done_frame,
            textvariable=self._done_var,
            wraplength=620,
            foreground="#111",
            font=("", 10, "bold"),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        self._rebuild_pair_rows(refresh_display=not initial_display_sentence)

    def _rebuild_pair_rows(self, *, refresh_display: bool = True) -> None:
        saved_main_slot = ""
        if self._slot_entries:
            saved_main_slot = main_slot_for_pair_index(
                self._read_pairs_from_ui(),
                self._main_pair_index_var.get(),
            )
        elif self._initial_main_slot:
            saved_main_slot = self._initial_main_slot

        for row in self._line_rows:
            row.destroy()
        self._line_rows.clear()
        self._slot_entries.clear()
        self._id_entries.clear()
        self._main_radios.clear()
        if not self._pairs:
            self._pairs = [ReplacementPair("", "")]
        self._main_pair_index_var.set(
            index_for_main_slot(self._pairs, saved_main_slot)
        )
        for i, pair in enumerate(self._pairs):
            self._build_pair_row(i, pair)
        self._refresh_sub_grid(refresh_display=refresh_display)

    def _build_pair_row(self, index: int, pair: ReplacementPair) -> None:
        block = ttk.Frame(self._lines_host)
        block.pack(fill=tk.X, pady=3)

        row = ttk.Frame(block)
        row.pack(fill=tk.X)

        ttk.Label(row, text="슬롯", width=6).pack(side=tk.LEFT)
        slot_e = ttk.Entry(row, width=10)
        slot_e.pack(side=tk.LEFT, padx=(0, 8))
        if pair.slot_order:
            slot_e.insert(0, pair.slot_order)
        slot_e.bind("<KeyRelease>", lambda _e: self._sync_from_ui())
        slot_e.bind("<Return>", lambda _e: self._on_slot_commit())
        slot_e.bind("<FocusOut>", lambda _e: self._on_slot_commit())

        ttk.Label(row, text="word id", width=8).pack(side=tk.LEFT)
        id_e = ttk.Entry(row, width=12)
        id_e.pack(side=tk.LEFT, padx=(0, 8))
        if pair.alt_word_id:
            id_e.insert(0, pair.alt_word_id)
        id_e.bind("<KeyRelease>", lambda _e: self._sync_from_ui())
        id_e.bind("<FocusIn>", lambda _e, i=index: self._set_focused_id_index(i))

        main_rb = ttk.Radiobutton(
            row,
            text="main",
            variable=self._main_pair_index_var,
            value=index,
            command=self._sync_from_ui,
        )
        main_rb.pack(side=tk.LEFT, padx=(0, 8))
        self._update_main_radio_state(main_rb, slot_e, id_e)

        ttk.Button(
            row, text="+", width=3, command=lambda i=index: self._insert_after(i)
        ).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Button(
            row, text="−", width=3, command=lambda i=index: self._remove_at(i)
        ).pack(side=tk.LEFT)

        self._line_rows.append(block)
        self._slot_entries.append(slot_e)
        self._id_entries.append(id_e)
        self._main_radios.append(main_rb)

    @staticmethod
    def _update_main_radio_state(
        radio: ttk.Radiobutton,
        slot_e: ttk.Entry,
        id_e: ttk.Entry,
    ) -> None:
        slot = slot_e.get().strip()
        wid = id_e.get().strip()
        enabled = bool(slot and wid and wid != "0")
        radio.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def _refresh_main_radio_states(self) -> None:
        for radio, slot_e, id_e in zip(
            self._main_radios, self._slot_entries, self._id_entries
        ):
            self._update_main_radio_state(radio, slot_e, id_e)
        idx = self._main_pair_index_var.get()
        if idx < 0 or idx >= len(self._slot_entries):
            return
        slot = self._slot_entries[idx].get().strip()
        wid = self._id_entries[idx].get().strip()
        if not slot or not wid or wid == "0":
            fallback = index_for_main_slot(self._read_pairs_from_ui(), "")
            self._main_pair_index_var.set(fallback)

    def _set_focused_id_index(self, index: int) -> None:
        if 0 <= index < len(self._id_entries):
            self._focused_id_index = index

    def apply_word_id(self, word_id: str) -> bool:
        """현재 포커스된 word id 입력란에 id를 넣는다."""
        if not self._id_entries:
            return False
        idx = self._focused_id_index
        if idx < 0 or idx >= len(self._id_entries):
            idx = 0
        entry = self._id_entries[idx]
        entry.delete(0, tk.END)
        entry.insert(0, (word_id or "").strip())
        entry.focus_set()
        self._sync_from_ui()
        return True

    def _pair_from_row(self, index: int) -> ReplacementPair:
        slot_e = self._slot_entries[index]
        id_e = self._id_entries[index]
        return ReplacementPair(
            slot_order=slot_e.get().strip(),
            alt_word_id=id_e.get().strip(),
        )

    def _sync_from_ui(self) -> None:
        self._pairs = self._read_pairs_from_ui()
        self._refresh_main_radio_states()
        self._refresh_sub_grid()

    def _schedule_display_refresh(self) -> None:
        if self._display_refresh_job is not None:
            self.after_cancel(self._display_refresh_job)
        self._display_refresh_job = self.after(
            _DISPLAY_REFRESH_MS,
            self._refresh_display_sentence,
        )

    def _refresh_display_sentence(self) -> None:
        self._display_refresh_job = None
        pairs = self._read_pairs_from_ui()
        self._done_var.set(
            build_sub_display_sentence(self._base_raw_sentence, pairs)
        )

    def _read_pairs_from_ui(self) -> list[ReplacementPair]:
        return [self._pair_from_row(i) for i in range(len(self._slot_entries))]

    def _apply_sorted_pairs(self) -> None:
        pairs = sort_replacement_pairs(self._read_pairs_from_ui())
        old_main_slot = main_slot_for_pair_index(
            pairs, self._main_pair_index_var.get()
        )
        self._pairs = pairs
        self._initial_main_slot = old_main_slot
        self._rebuild_pair_rows()

    def _on_slot_commit(self, _event=None) -> str | None:
        if self._applying_sort:
            return None
        self._applying_sort = True
        try:
            self._apply_sorted_pairs()
        finally:
            self._applying_sort = False
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

    def _refresh_sub_grid(self, *, refresh_display: bool = True) -> None:
        for child in self._sub_grid_inner.winfo_children():
            child.destroy()

        pairs = self._read_pairs_from_ui()
        if refresh_display:
            self._schedule_display_refresh()

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

    def get_values(self) -> tuple[str, str, str]:
        self._pairs = sort_replacement_pairs(self._read_pairs_from_ui())
        order, alt_id = pairs_to_storage(self._pairs)
        main_slot = main_slot_for_pair_index(
            self._pairs, self._main_pair_index_var.get()
        )
        return order, alt_id, main_slot

    def get_display_sentence(self) -> str:
        return build_sub_display_sentence(
            self._base_raw_sentence,
            self._read_pairs_from_ui(),
        )
