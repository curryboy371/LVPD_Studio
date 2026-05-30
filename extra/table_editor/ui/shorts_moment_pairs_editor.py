"""ko_narration_line_id · sub_sentence_id 쌍 (+/−, 콤보, 미리보기)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from extra.table_editor.services.shorts_moment_data import (
    SelectOption,
    id_from_combo_label,
    label_for_id,
    list_ko_line_options,
    list_sub_options,
    option_maps,
    parse_pipe_ids,
)


class _PairRowWidgets:
    __slots__ = (
        "frame",
        "ko_combo",
        "sub_combo",
        "ko_preview",
        "sub_preview",
    )

    def __init__(
        self,
        frame: ttk.Frame,
        ko_combo: ttk.Combobox,
        sub_combo: ttk.Combobox,
        ko_preview: ttk.Label,
        sub_preview: ttk.Label,
    ) -> None:
        self.frame = frame
        self.ko_combo = ko_combo
        self.sub_combo = sub_combo
        self.ko_preview = ko_preview
        self.sub_preview = sub_preview


class ShortsMomentPairsEditor(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        initial_ko_line_id: str = "",
        initial_sub_id: str = "",
        on_sources_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._on_sources_changed = on_sources_changed
        self._pair_rows: list[_PairRowWidgets] = []
        self._lines_host = ttk.Frame(self)
        self._lines_host.pack(fill=tk.X, expand=True)

        self._ko_labels: list[str] = []
        self._sub_labels: list[str] = []
        self._ko_label_to_id: dict[str, str] = {}
        self._sub_label_to_id: dict[str, str] = {}
        self._ko_id_to_label: dict[str, str] = {}
        self._sub_id_to_label: dict[str, str] = {}
        self._ko_id_to_preview: dict[str, str] = {}
        self._sub_id_to_preview: dict[str, str] = {}

        self._hint_var = tk.StringVar(
            value="base_id · ko_narration_id 를 선택하면 목록이 채워집니다."
        )
        ttk.Label(
            self,
            textvariable=self._hint_var,
            foreground="#666666",
            wraplength=520,
            font=("", 8),
        ).pack(anchor="w", pady=(0, 4))

        header = ttk.Frame(self._lines_host)
        header.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(header, text="", width=6).pack(side=tk.LEFT)
        ttk.Label(header, text="ko line", width=22).pack(side=tk.LEFT, padx=2)
        ttk.Label(header, text="sub", width=22).pack(side=tk.LEFT, padx=2)

        ko_ids = parse_pipe_ids(initial_ko_line_id)
        sub_ids = parse_pipe_ids(initial_sub_id)
        n = max(len(ko_ids), len(sub_ids), 1)
        for i in range(n):
            self._add_pair_row(
                ko_ids[i] if i < len(ko_ids) else "",
                sub_ids[i] if i < len(sub_ids) else "",
                focus=False,
            )

    def refresh_sources(self, base_id: str, ko_set_id: str) -> None:
        ko_opts = list_ko_line_options(ko_set_id)
        sub_opts = list_sub_options(base_id)
        (
            self._ko_labels,
            self._ko_label_to_id,
            self._ko_id_to_label,
            self._ko_id_to_preview,
        ) = _maps_from_options(ko_opts)
        (
            self._sub_labels,
            self._sub_label_to_id,
            self._sub_id_to_label,
            self._sub_id_to_preview,
        ) = _maps_from_options(sub_opts)

        parts: list[str] = []
        if not (base_id or "").strip():
            parts.append("base_id")
        if not (ko_set_id or "").strip():
            parts.append("ko_narration_id")
        if parts:
            self._hint_var.set(
                f"{', '.join(parts)} 입력 후 멘트·sub 를 매칭하세요. (+ 로 행 추가)"
            )
        elif not ko_opts and not sub_opts:
            self._hint_var.set("해당 base / set 에 줄이 없습니다.")
        else:
            self._hint_var.set(
                f"ko line {len(ko_opts)}개 · sub {len(sub_opts)}개. 순서대로 재생됩니다."
            )

        for row in self._pair_rows:
            self._apply_combo_sources(row)
            self._update_row_previews(row)

        if self._on_sources_changed:
            self._on_sources_changed()

    def get_pipe_values(self) -> tuple[str, str]:
        ko_ids: list[str] = []
        sub_ids: list[str] = []
        for row in self._pair_rows:
            ko_id = id_from_combo_label(
                row.ko_combo.get(), label_to_id=self._ko_label_to_id
            )
            sub_id = id_from_combo_label(
                row.sub_combo.get(), label_to_id=self._sub_label_to_id
            )
            if ko_id or sub_id:
                ko_ids.append(ko_id)
                sub_ids.append(sub_id)
        return "|".join(ko_ids), "|".join(sub_ids)

    def _add_pair_row(
        self,
        ko_id: str = "",
        sub_id: str = "",
        *,
        after: _PairRowWidgets | None = None,
        focus: bool = True,
    ) -> _PairRowWidgets:
        index = len(self._pair_rows) + 1
        block = ttk.Frame(self._lines_host)
        if after is not None and after.frame.winfo_exists():
            block.pack(fill=tk.X, pady=4, after=after.frame)
        else:
            block.pack(fill=tk.X, pady=4)

        top = ttk.Frame(block)
        top.pack(fill=tk.X)
        ttk.Label(top, text=f"#{index}", width=6).pack(side=tk.LEFT, anchor="n")

        ko_combo = ttk.Combobox(top, width=24, state="readonly")
        ko_combo.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        sub_combo = ttk.Combobox(top, width=24, state="readonly")
        sub_combo.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        ttk.Button(
            top,
            text="+",
            width=3,
            command=lambda r=None: self._insert_after(block),
        ).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Button(
            top,
            text="-",
            width=3,
            command=lambda b=block: self._remove_block(b),
        ).pack(side=tk.LEFT)

        preview = ttk.Frame(block)
        preview.pack(fill=tk.X, padx=(6, 0), pady=(2, 0))
        ko_preview = ttk.Label(
            preview,
            text="KO: —",
            wraplength=500,
            foreground="#333333",
            font=("", 9),
        )
        ko_preview.pack(anchor="w")
        sub_preview = ttk.Label(
            preview,
            text="CN: —",
            wraplength=500,
            foreground="#333333",
            font=("", 9),
        )
        sub_preview.pack(anchor="w")

        row = _PairRowWidgets(block, ko_combo, sub_combo, ko_preview, sub_preview)
        insert_at = (
            self._pair_rows.index(after) + 1
            if after is not None and after in self._pair_rows
            else len(self._pair_rows)
        )
        self._pair_rows.insert(insert_at, row)
        self._renumber_labels()

        self._apply_combo_sources(row)
        ko_combo.set(
            label_for_id(
                ko_id, id_to_label=self._ko_id_to_label, labels=self._ko_labels
            )
        )
        sub_combo.set(
            label_for_id(
                sub_id, id_to_label=self._sub_id_to_label, labels=self._sub_labels
            )
        )
        ko_combo.bind("<<ComboboxSelected>>", lambda _e, r=row: self._update_row_previews(r))
        sub_combo.bind("<<ComboboxSelected>>", lambda _e, r=row: self._update_row_previews(r))
        self._update_row_previews(row)

        if focus:
            ko_combo.focus_set()
        return row

    def _insert_after(self, block: ttk.Frame) -> None:
        after: _PairRowWidgets | None = None
        for row in self._pair_rows:
            if row.frame is block:
                after = row
                break
        self._add_pair_row(after=after, focus=True)

    def _remove_block(self, block: ttk.Frame) -> None:
        target: _PairRowWidgets | None = None
        for row in self._pair_rows:
            if row.frame is block:
                target = row
                break
        if target is None:
            return
        if len(self._pair_rows) <= 1:
            target.ko_combo.set("")
            target.sub_combo.set("")
            self._update_row_previews(target)
            return
        self._pair_rows.remove(target)
        target.frame.destroy()
        self._renumber_labels()

    def _renumber_labels(self) -> None:
        for i, row in enumerate(self._pair_rows, start=1):
            for child in row.frame.winfo_children():
                if isinstance(child, ttk.Frame):
                    for label in child.winfo_children():
                        if isinstance(label, ttk.Label) and label.cget("width") == 6:
                            label.configure(text=f"#{i}")
                            break
                    break

    def _apply_combo_sources(self, row: _PairRowWidgets) -> None:
        ko_id = id_from_combo_label(
            row.ko_combo.get(), label_to_id=self._ko_label_to_id
        )
        sub_id = id_from_combo_label(
            row.sub_combo.get(), label_to_id=self._sub_label_to_id
        )
        ko_values = [""] + self._ko_labels if self._ko_labels else [""]
        sub_values = [""] + self._sub_labels if self._sub_labels else [""]
        ko_label = label_for_id(
            ko_id, id_to_label=self._ko_id_to_label, labels=self._ko_labels
        )
        sub_label = label_for_id(
            sub_id, id_to_label=self._sub_id_to_label, labels=self._sub_labels
        )
        if ko_label and ko_label not in ko_values:
            ko_values = [ko_label, *ko_values]
        if sub_label and sub_label not in sub_values:
            sub_values = [sub_label, *sub_values]
        row.ko_combo["values"] = ko_values
        row.sub_combo["values"] = sub_values
        row.ko_combo.set(ko_label)
        row.sub_combo.set(sub_label)

    def _update_row_previews(self, row: _PairRowWidgets) -> None:
        ko_id = id_from_combo_label(
            row.ko_combo.get(), label_to_id=self._ko_label_to_id
        )
        sub_id = id_from_combo_label(
            row.sub_combo.get(), label_to_id=self._sub_label_to_id
        )
        if ko_id:
            ko_text = self._ko_id_to_preview.get(ko_id, "")
            row.ko_preview.configure(text=f"KO: {ko_text or '(미리보기 없음)'}")
        else:
            row.ko_preview.configure(text="KO: —")
        if sub_id:
            cn_text = self._sub_id_to_preview.get(sub_id, "")
            row.sub_preview.configure(text=f"CN: {cn_text or '(미리보기 없음)'}")
        else:
            row.sub_preview.configure(text="CN: —")


def _maps_from_options(
    options: list[SelectOption],
) -> tuple[list[str], dict[str, str], dict[str, str], dict[str, str]]:
    labels, label_to_id, id_to_label, id_to_preview = option_maps(options)
    return labels, label_to_id, id_to_label, id_to_preview
