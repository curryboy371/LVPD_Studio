"""숏츠 회화 클립 전용 행 편집 창 (한글 라벨·필드 구역)."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from extra.table_editor.data.fields import SHORTS_CONVERSATION_CLIPS_FIELDNAMES
from extra.table_editor.services.search import ids_equal
from extra.table_editor.services.shorts_editor_choices import (
    BG_PATH_RANDOM_LABEL,
    bg_path_for_combo,
    bg_path_from_combo,
    ko_narration_id_for_combo,
    ko_narration_id_from_combo,
    ko_narration_label_maps,
    list_bg_path_choices,
    list_ko_narration_set_choices,
)
from extra.table_editor.services.shorts_moment_data import (
    id_from_combo_label,
    label_for_id,
    list_base_options,
    option_maps,
)
from extra.table_editor.services.topic_sources import topics_for_conversation_preview
from extra.table_editor.ui.multiline_lines_editor import normalize_multiline_input
from extra.table_editor.ui.shorts_bg_path_preview import attach_bg_path_preview
from extra.table_editor.ui.shorts_moment_pairs_editor import ShortsMomentPairsEditor
from extra.table_editor.ui.window_placement import center_toplevel_on_parent

# (field, 라벨, kind, 힌트)
_FIELD_SPECS: list[tuple[str, str, str, str]] = [
    ("id", "클립 ID", "entry", ""),
    ("topic", "topic (주제)", "topic", ""),
    ("base_id", "base_id", "base_id", "base_sentences.id — sub 슬롯 조합"),
    (
        "hook_title",
        "hook_title (후킹 타이틀)",
        "multiline",
        "상단 후킹 문구. 줄바꿈 가능",
    ),
    (
        "ko_narration_id",
        "ko_narration_id",
        "ko_narration",
        "ko_narration_sets.id (= ko_narration_lines.set_id)",
    ),
    (
        "last_hold_sec",
        "last_hold_sec",
        "entry",
        "CTA_HOLD 대기(초). 비우면 2.5",
    ),
    ("bg_path", "bg_path", "bg_path", "배경음. 비우면 resource/sound/bg_short 랜덤"),
]

_SITUATION_SUBTITLE_SPEC = (
    "situation_subtitle",
    "situation_subtitle (상황·CTA)",
    "하단 상황 설명·CTA_HOLD 마무리. 비우면 base translation",
)


class ShortsConversationClipEditorDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        row: dict[str, str],
        *,
        title: str = "숏츠 회화 클립 편집",
        is_new: bool = False,
        existing_ids: set[str] | None = None,
        original_id: str | None = None,
        topic_choices: list[str] | None = None,
        on_save: Callable[[dict[str, str], bool], bool | None],
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.geometry("760x920")
        self.minsize(600, 740)

        self._is_new = is_new
        self._existing_ids = existing_ids or set()
        self._original_id = (original_id or row.get("id", "")).strip()
        self._on_save = on_save
        self._save_in_progress = False
        self._widgets: dict[str, Any] = {}
        self._bg_path_choices = list_bg_path_choices()
        ko_choices = list_ko_narration_set_choices()
        self._ko_label_to_id, self._ko_id_to_label = ko_narration_label_maps(ko_choices)
        self._ko_combo_labels = [label for _sid, label in ko_choices]
        (
            self._base_combo_labels,
            self._base_label_to_id,
            self._base_id_to_label,
            _base_id_to_preview,
        ) = option_maps(list_base_options())
        merged_topics = list(topic_choices or []) + topics_for_conversation_preview()
        seen_topics: set[str] = set()
        self._topic_choices = []
        for t in merged_topics:
            if t and t not in seen_topics:
                seen_topics.add(t)
                self._topic_choices.append(t)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        canvas = tk.Canvas(body, borderwidth=0, highlightthickness=0)
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

        basic = ttk.LabelFrame(inner, text="기본")
        basic.pack(fill=tk.X, padx=10, pady=6)
        screen = ttk.LabelFrame(inner, text="화면 문구")
        screen.pack(fill=tk.X, padx=10, pady=6)
        narr = ttk.LabelFrame(inner, text="한국어 나레이션")
        narr.pack(fill=tk.X, padx=10, pady=6)
        pairs_section = ttk.LabelFrame(inner, text="멘트 · sub 매칭")
        pairs_section.pack(fill=tk.X, padx=10, pady=6)
        play = ttk.LabelFrame(inner, text="재생")
        play.pack(fill=tk.X, padx=10, pady=6)

        section_for: dict[str, ttk.LabelFrame] = {
            "id": basic,
            "topic": basic,
            "base_id": basic,
            "hook_title": screen,
            "ko_narration_id": narr,
            "last_hold_sec": play,
            "bg_path": play,
        }
        self._moment_pairs: ShortsMomentPairsEditor | None = None

        for field, label, kind, hint in _FIELD_SPECS:
            parent_frame = section_for[field]
            block = ttk.Frame(parent_frame)
            block.pack(fill=tk.X, padx=8, pady=5)
            ttk.Label(block, text=label, width=28).pack(side=tk.LEFT, anchor="n")

            right = ttk.Frame(block)
            right.pack(side=tk.LEFT, fill=tk.X, expand=True)

            value = row.get(field, "")
            if kind == "multiline":
                text = tk.Text(right, height=4, width=48, wrap=tk.WORD)
                text.insert("1.0", normalize_multiline_input(value))
                text.pack(fill=tk.X, expand=True)
                self._widgets[field] = text
            elif kind == "topic":
                current = (value or "").strip()
                values = list(self._topic_choices)
                if current and current not in values:
                    values = [current, *values]
                combo = ttk.Combobox(right, values=values, width=46)
                combo.set(current)
                combo.pack(fill=tk.X, expand=True)
                self._widgets[field] = combo
            elif kind == "bg_path":
                values = [BG_PATH_RANDOM_LABEL, *self._bg_path_choices]
                current = bg_path_for_combo(value)
                if current not in values:
                    values = [current, *values]
                combo_row = ttk.Frame(right)
                combo_row.pack(fill=tk.X, expand=True)
                combo = ttk.Combobox(
                    combo_row, values=values, width=38, state="readonly"
                )
                combo.set(current)
                combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
                attach_bg_path_preview(combo_row, combo).pack(side=tk.RIGHT, padx=(6, 0))
                self._widgets[field] = combo
            elif kind == "ko_narration":
                values = list(self._ko_combo_labels)
                current = ko_narration_id_for_combo(
                    value, id_to_label=self._ko_id_to_label
                )
                if current and current not in values:
                    values = [current, *values]
                combo = ttk.Combobox(
                    right, values=values, width=46, state="readonly"
                )
                combo.set(current or (values[0] if values else ""))
                combo.pack(fill=tk.X, expand=True)
                self._widgets[field] = combo
            elif kind == "base_id":
                values = list(self._base_combo_labels)
                current = label_for_id(
                    value,
                    id_to_label=self._base_id_to_label,
                    labels=values,
                )
                if current and current not in values:
                    values = [current, *values]
                combo = ttk.Combobox(
                    right, values=values, width=46, state="readonly"
                )
                combo.set(current or (values[0] if values else ""))
                combo.pack(fill=tk.X, expand=True)
                self._widgets[field] = combo
            else:
                entry = ttk.Entry(right, width=48)
                entry.insert(0, value)
                entry.pack(fill=tk.X, expand=True)
                self._widgets[field] = entry
                if field == "id" and not is_new:
                    entry.configure(state="readonly")

            if hint:
                ttk.Label(
                    right,
                    text=hint,
                    foreground="#666666",
                    wraplength=420,
                    font=("", 8),
                ).pack(anchor="w", pady=(2, 0))

        self._moment_pairs = ShortsMomentPairsEditor(
            pairs_section,
            initial_ko_line_id=row.get("ko_narration_line_id", ""),
            initial_sub_id=row.get("sub_sentence_id", ""),
        )
        self._moment_pairs.pack(fill=tk.X, padx=8, pady=6)

        sub_field, sub_label, sub_hint = _SITUATION_SUBTITLE_SPEC
        sub_block = ttk.Frame(pairs_section)
        sub_block.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(sub_block, text=sub_label, width=28).pack(side=tk.LEFT, anchor="n")
        sub_right = ttk.Frame(sub_block)
        sub_right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sub_text = tk.Text(sub_right, height=4, width=48, wrap=tk.WORD)
        sub_text.insert(
            "1.0", normalize_multiline_input(row.get(sub_field, ""))
        )
        sub_text.pack(fill=tk.X, expand=True)
        self._widgets[sub_field] = sub_text
        if sub_hint:
            ttk.Label(
                sub_right,
                text=sub_hint,
                foreground="#666666",
                wraplength=420,
                font=("", 8),
            ).pack(anchor="w", pady=(2, 0))

        def _refresh_moment_sources(_event: tk.Event | None = None) -> None:
            if self._moment_pairs is None:
                return
            base_w = self._widgets.get("base_id")
            ko_w = self._widgets.get("ko_narration_id")
            base_id = ""
            if isinstance(base_w, ttk.Combobox):
                base_id = id_from_combo_label(
                    base_w.get(), label_to_id=self._base_label_to_id
                )
            elif base_w is not None:
                base_id = base_w.get().strip()
            ko_set = ""
            if isinstance(ko_w, ttk.Combobox):
                ko_set = ko_narration_id_from_combo(
                    ko_w.get(), label_to_id=self._ko_label_to_id
                )
            self._moment_pairs.refresh_sources(base_id, ko_set)

        base_w = self._widgets.get("base_id")
        if isinstance(base_w, ttk.Combobox):
            base_w.bind("<<ComboboxSelected>>", _refresh_moment_sources)
        ko_w = self._widgets.get("ko_narration_id")
        if isinstance(ko_w, ttk.Combobox):
            ko_w.bind("<<ComboboxSelected>>", _refresh_moment_sources)
        self.after_idle(_refresh_moment_sources)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=8, pady=12, side=tk.BOTTOM)
        ttk.Button(btn_frame, text="저장", command=self._save).pack(side=tk.RIGHT, padx=(4, 12))
        ttk.Button(btn_frame, text="취소", command=self._destroy).pack(side=tk.RIGHT, padx=4)

        self._scroll_canvas = canvas
        self._bind_mousewheel()
        self.protocol("WM_DELETE_WINDOW", self._destroy)
        self.bind("<Escape>", lambda _e: self._destroy())
        self.bind("<Control-Return>", lambda _e: self._save())
        self.after_idle(_on_inner_configure)
        self.after_idle(lambda: center_toplevel_on_parent(self, parent))

    def _bind_mousewheel(self) -> None:
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

    def _read_values(self) -> dict[str, str]:
        out: dict[str, str] = {c: "" for c in SHORTS_CONVERSATION_CLIPS_FIELDNAMES}
        for field, _label, kind, _hint in _FIELD_SPECS:
            w = self._widgets[field]
            if isinstance(w, tk.Text):
                out[field] = w.get("1.0", tk.END).strip()
            elif isinstance(w, ttk.Combobox):
                selected = (w.get() or "").strip()
                if field == "bg_path":
                    out[field] = bg_path_from_combo(selected)
                elif field == "ko_narration_id":
                    out[field] = ko_narration_id_from_combo(
                        selected, label_to_id=self._ko_label_to_id
                    )
                elif field == "base_id":
                    out[field] = id_from_combo_label(
                        selected, label_to_id=self._base_label_to_id
                    )
                else:
                    out[field] = selected
            else:
                out[field] = w.get().strip()
        sub_w = self._widgets.get("situation_subtitle")
        if isinstance(sub_w, tk.Text):
            out["situation_subtitle"] = sub_w.get("1.0", tk.END).strip()
        if self._moment_pairs is not None:
            ko_pipe, sub_pipe = self._moment_pairs.get_pipe_values()
            out["ko_narration_line_id"] = ko_pipe
            out["sub_sentence_id"] = sub_pipe
        return out

    def _id_exists(self, row_id: str) -> bool:
        target = (row_id or "").strip()
        if not target:
            return False
        for existing in self._existing_ids:
            if ids_equal(existing, target):
                return True
        return False

    def _save(self) -> None:
        if self._save_in_progress:
            return
        values = self._read_values()
        rid = values.get("id", "").strip()
        if not rid:
            messagebox.showwarning("검증", "클립 ID를 입력하세요.", parent=self)
            return
        if not ids_equal(rid, self._original_id) and self._id_exists(rid):
            messagebox.showwarning(
                "검증",
                f"클립 ID {rid} 가 이미 존재합니다.",
                parent=self,
            )
            return
        self._save_in_progress = True
        if self._on_save(values, self._is_new) is False:
            self._save_in_progress = False
            return
        self.destroy()

    def _destroy(self) -> None:
        self.destroy()
