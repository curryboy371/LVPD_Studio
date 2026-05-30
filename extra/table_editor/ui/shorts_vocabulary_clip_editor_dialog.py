"""숏츠 단어 클립 전용 행 편집 창."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from extra.table_editor.data.fields import SHORTS_VOCABULARY_CLIPS_FIELDNAMES
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
from extra.table_editor.services.topic_sources import topics_for_vocabulary_preview
from extra.table_editor.ui.multiline_lines_editor import normalize_multiline_input
from extra.table_editor.ui.shorts_bg_path_preview import attach_bg_path_preview
from extra.table_editor.ui.shorts_vocabulary_word_rows_editor import (
    ShortsVocabularyWordRowsEditor,
)
from extra.table_editor.ui.window_placement import center_toplevel_on_parent

_FIELD_SPECS: list[tuple[str, str, str, str]] = [
    ("id", "topic 행 ID", "entry", "topic당 1행"),
    ("topic", "topic (주제)", "topic", ""),
    (
        "ko_narration_id",
        "ko_narration_id",
        "ko_narration",
        "topic 인트로 TTS (선택). ko_narration_sets.id",
    ),
    ("video_path", "video_path", "entry", "topic 인트로 mp4 (repo 상대 경로)"),
    (
        "last_hold_text",
        "last_hold_text (CTA)",
        "multiline",
        "마지막 단어 후 CTA_HOLD 문구",
    ),
    (
        "last_hold_sec",
        "last_hold_sec",
        "entry",
        "CTA 대기(초). 비우면 2.5",
    ),
    ("bg_path", "bg_path", "bg_path", "따라해보세요 구간 배경음. 비우면 bg_short 랜덤"),
]


class ShortsVocabularyClipEditorDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        row: dict[str, str],
        *,
        title: str = "숏츠 단어 클립 편집",
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
        self.geometry("780x960")
        self.minsize(640, 780)

        self._is_new = is_new
        self._existing_ids = existing_ids or set()
        self._original_id = (original_id or row.get("id", "")).strip()
        self._on_save = on_save
        self._save_in_progress = False
        self._widgets: dict[str, Any] = {}
        self._ko_label_to_id, self._ko_id_to_label = ko_narration_label_maps(
            list_ko_narration_set_choices()
        )
        self._ko_combo_labels = [
            label for _sid, label in list_ko_narration_set_choices()
        ]
        merged = list(topic_choices or []) + topics_for_vocabulary_preview()
        seen: set[str] = set()
        self._topic_choices = []
        for t in merged:
            if t and t not in seen:
                seen.add(t)
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

        basic = ttk.LabelFrame(inner, text="기본 · topic 인트로")
        basic.pack(fill=tk.X, padx=10, pady=6)
        words_section = ttk.LabelFrame(inner, text="단어 · hook · 단어별 옵션")
        words_section.pack(fill=tk.X, padx=10, pady=6)
        tail = ttk.LabelFrame(inner, text="마무리 · 배경음")
        tail.pack(fill=tk.X, padx=10, pady=6)

        section_for: dict[str, ttk.LabelFrame] = {
            "id": basic,
            "topic": basic,
            "ko_narration_id": basic,
            "video_path": basic,
            "last_hold_text": tail,
            "last_hold_sec": tail,
            "bg_path": tail,
        }

        for field, label, kind, hint in _FIELD_SPECS:
            parent_frame = section_for[field]
            block = ttk.Frame(parent_frame)
            block.pack(fill=tk.X, padx=8, pady=5)
            ttk.Label(block, text=label, width=28).pack(side=tk.LEFT, anchor="n")
            right = ttk.Frame(block)
            right.pack(side=tk.LEFT, fill=tk.X, expand=True)
            value = row.get(field, "")
            if kind == "multiline":
                text = tk.Text(right, height=3, width=48, wrap=tk.WORD)
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
            elif kind == "ko_narration":
                values = list(self._ko_combo_labels)
                empty_label = "(없음)"
                values = [empty_label, *values]
                current = ko_narration_id_for_combo(
                    value, id_to_label=self._ko_id_to_label
                )
                if not current:
                    combo_set = empty_label
                else:
                    combo_set = current
                    if combo_set not in values:
                        values = [combo_set, *values]
                combo = ttk.Combobox(right, values=values, width=46, state="readonly")
                combo.set(combo_set)
                combo.pack(fill=tk.X, expand=True)
                self._widgets[field] = combo
                self._ko_empty_label = empty_label
            elif kind == "bg_path":
                values = [BG_PATH_RANDOM_LABEL, *list_bg_path_choices()]
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

        self._word_rows = ShortsVocabularyWordRowsEditor(
            words_section,
            word_ids=row.get("word_id", ""),
            hook_titles=row.get("hook_title", ""),
            sound_repeat=row.get("sound_repeat_count", ""),
            after_delay=row.get("after_sound_delay_sec", ""),
            read_meaning_ko=row.get("read_meaning_ko", ""),
            use_word_video_audio=row.get("use_word_video_audio", ""),
        )
        self._word_rows.pack(fill=tk.X, padx=8, pady=6)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=8, pady=12, side=tk.BOTTOM)
        ttk.Button(btn_frame, text="저장", command=self._save).pack(side=tk.RIGHT, padx=(4, 12))
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side=tk.RIGHT, padx=4)

        self._scroll_canvas = canvas
        self._bind_mousewheel()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-Return>", lambda _e: self._save())
        self.after_idle(_on_inner_configure)
        self.after_idle(lambda: center_toplevel_on_parent(self, parent))

    def _bind_mousewheel(self) -> None:
        def _on_wheel(event: tk.Event) -> None:
            canvas = self._scroll_canvas
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
        out: dict[str, str] = {c: "" for c in SHORTS_VOCABULARY_CLIPS_FIELDNAMES}
        for field, _label, kind, _hint in _FIELD_SPECS:
            w = self._widgets[field]
            if isinstance(w, tk.Text):
                out[field] = w.get("1.0", tk.END).strip()
            elif isinstance(w, ttk.Combobox):
                selected = (w.get() or "").strip()
                if field == "bg_path":
                    out[field] = bg_path_from_combo(selected)
                elif field == "ko_narration_id":
                    if selected == getattr(self, "_ko_empty_label", "(없음)"):
                        out[field] = ""
                    else:
                        out[field] = ko_narration_id_from_combo(
                            selected, label_to_id=self._ko_label_to_id
                        )
                else:
                    out[field] = selected
            else:
                out[field] = w.get().strip()
        out.update(self._word_rows.get_pipe_values())
        return out

    def _save(self) -> None:
        if self._save_in_progress:
            return
        values = self._read_values()
        rid = values.get("id", "").strip()
        if not rid:
            messagebox.showwarning("검증", "topic 행 ID를 입력하세요.", parent=self)
            return
        if not ids_equal(rid, self._original_id) and self._id_exists(rid):
            messagebox.showwarning(
                "검증",
                f"ID {rid} 가 이미 존재합니다.",
                parent=self,
            )
            return
        self._save_in_progress = True
        if self._on_save(values, self._is_new) is False:
            self._save_in_progress = False
            return
        self.destroy()

    def _id_exists(self, row_id: str) -> bool:
        target = (row_id or "").strip()
        for existing in self._existing_ids:
            if ids_equal(existing, target):
                return True
        return False
