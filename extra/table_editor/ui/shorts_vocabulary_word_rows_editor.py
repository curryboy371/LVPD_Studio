"""shorts_vocabulary word_id · hook_title · 단어별 옵션 (+/−, 콤보, 미리보기)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from extra.table_editor.services.shorts_vocab_data import (
    id_from_combo_label,
    join_pipe_tokens,
    label_for_id,
    list_word_options,
    option_maps,
    parse_pipe_ids,
    parse_pipe_tokens,
)

_BOOL_CHOICES = ("", "true", "false")


class _WordRowWidgets:
    __slots__ = (
        "frame",
        "word_combo",
        "hook_entry",
        "repeat_entry",
        "delay_entry",
        "meaning_combo",
        "video_audio_combo",
        "preview",
    )

    def __init__(
        self,
        frame: ttk.Frame,
        word_combo: ttk.Combobox,
        hook_entry: ttk.Entry,
        repeat_entry: ttk.Entry,
        delay_entry: ttk.Entry,
        meaning_combo: ttk.Combobox,
        video_audio_combo: ttk.Combobox,
        preview: ttk.Label,
    ) -> None:
        self.frame = frame
        self.word_combo = word_combo
        self.hook_entry = hook_entry
        self.repeat_entry = repeat_entry
        self.delay_entry = delay_entry
        self.meaning_combo = meaning_combo
        self.video_audio_combo = video_audio_combo
        self.preview = preview


class ShortsVocabularyWordRowsEditor(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        word_ids: str = "",
        hook_titles: str = "",
        sound_repeat: str = "",
        after_delay: str = "",
        read_meaning_ko: str = "",
        use_word_video_audio: str = "",
    ) -> None:
        super().__init__(master)
        self._rows: list[_WordRowWidgets] = []
        self._host = ttk.Frame(self)
        self._host.pack(fill=tk.X, expand=True)

        self._refresh_word_sources()

        ttk.Label(
            self,
            text="word_id · hook_title · repeat · delay · 뜻TTS · word비디오음성 (| 순서 동일)",
            foreground="#666666",
            wraplength=560,
            font=("", 8),
        ).pack(anchor="w", pady=(0, 4))

        header = ttk.Frame(self._host)
        header.pack(fill=tk.X, pady=(0, 2))
        for text, width in (
            ("#", 3),
            ("word", 14),
            ("hook", 12),
            ("repeat", 5),
            ("delay", 5),
            ("뜻KO", 6),
            ("vidAud", 6),
        ):
            ttk.Label(header, text=text, width=width).pack(side=tk.LEFT, padx=1)

        wids = parse_pipe_ids(word_ids)
        hooks = parse_pipe_tokens(hook_titles)
        repeats = parse_pipe_tokens(sound_repeat)
        delays = parse_pipe_tokens(after_delay)
        meanings = parse_pipe_tokens(read_meaning_ko)
        videos = parse_pipe_tokens(use_word_video_audio)
        n = max(len(wids), len(hooks), 1)
        for i in range(n):
            self._add_row(
                wids[i] if i < len(wids) else "",
                hooks[i] if i < len(hooks) else "",
                repeats[i] if i < len(repeats) else "1",
                delays[i] if i < len(delays) else "",
                meanings[i] if i < len(meanings) else "true",
                videos[i] if i < len(videos) else "false",
                focus=False,
            )

    def refresh_word_sources(self) -> None:
        self._refresh_word_sources()
        for row in self._rows:
            self._apply_combo_sources(row)
            self._update_preview(row)

    def _refresh_word_sources(self) -> None:
        opts = list_word_options()
        (
            self._word_labels,
            self._word_label_to_id,
            self._word_id_to_label,
            self._word_id_to_preview,
        ) = option_maps(opts)

    def get_pipe_values(self) -> dict[str, str]:
        wids: list[str] = []
        hooks: list[str] = []
        repeats: list[str] = []
        delays: list[str] = []
        meanings: list[str] = []
        videos: list[str] = []
        for row in self._rows:
            wid = id_from_combo_label(
                row.word_combo.get(), label_to_id=self._word_label_to_id
            )
            hook = row.hook_entry.get().strip()
            if not wid and not hook:
                continue
            wids.append(wid)
            hooks.append(hook)
            repeats.append(row.repeat_entry.get().strip() or "1")
            delays.append(row.delay_entry.get().strip())
            meanings.append((row.meaning_combo.get() or "true").strip().lower())
            videos.append((row.video_audio_combo.get() or "false").strip().lower())
        return {
            "word_id": join_pipe_tokens(wids),
            "hook_title": join_pipe_tokens(hooks),
            "sound_repeat_count": join_pipe_tokens(repeats),
            "after_sound_delay_sec": join_pipe_tokens(delays),
            "read_meaning_ko": join_pipe_tokens(meanings),
            "use_word_video_audio": join_pipe_tokens(videos),
        }

    def _add_row(
        self,
        word_id: str = "",
        hook: str = "",
        repeat: str = "1",
        delay: str = "",
        meaning: str = "true",
        video_audio: str = "false",
        *,
        after: _WordRowWidgets | None = None,
        focus: bool = True,
    ) -> _WordRowWidgets:
        block = ttk.Frame(self._host)
        if after is not None and after.frame.winfo_exists():
            block.pack(fill=tk.X, pady=3, after=after.frame)
        else:
            block.pack(fill=tk.X, pady=3)

        top = ttk.Frame(block)
        top.pack(fill=tk.X)
        idx_label = ttk.Label(top, text=f"#{len(self._rows) + 1}", width=3)
        idx_label.pack(side=tk.LEFT, anchor="n")

        word_combo = ttk.Combobox(top, width=12, state="readonly")
        word_combo.pack(side=tk.LEFT, padx=1)
        hook_entry = ttk.Entry(top, width=11)
        hook_entry.pack(side=tk.LEFT, padx=1)
        repeat_entry = ttk.Entry(top, width=4)
        repeat_entry.pack(side=tk.LEFT, padx=1)
        delay_entry = ttk.Entry(top, width=4)
        delay_entry.pack(side=tk.LEFT, padx=1)
        meaning_combo = ttk.Combobox(
            top, values=_BOOL_CHOICES, width=5, state="readonly"
        )
        meaning_combo.pack(side=tk.LEFT, padx=1)
        video_audio_combo = ttk.Combobox(
            top, values=_BOOL_CHOICES, width=5, state="readonly"
        )
        video_audio_combo.pack(side=tk.LEFT, padx=1)

        ttk.Button(
            top, text="+", width=2, command=lambda b=block: self._insert_after(b)
        ).pack(side=tk.LEFT, padx=(2, 1))
        ttk.Button(
            top, text="-", width=2, command=lambda b=block: self._remove_block(b)
        ).pack(side=tk.LEFT)

        preview = ttk.Label(
            block,
            text="—",
            wraplength=540,
            foreground="#333333",
            font=("", 9),
        )
        preview.pack(anchor="w", padx=(4, 0), pady=(1, 0))

        row = _WordRowWidgets(
            block,
            word_combo,
            hook_entry,
            repeat_entry,
            delay_entry,
            meaning_combo,
            video_audio_combo,
            preview,
        )
        row.frame._idx_label = idx_label  # type: ignore[attr-defined]
        insert_at = (
            self._rows.index(after) + 1
            if after is not None and after in self._rows
            else len(self._rows)
        )
        self._rows.insert(insert_at, row)

        self._apply_combo_sources(row)
        word_combo.set(label_for_id(word_id, id_to_label=self._word_id_to_label))
        hook_entry.insert(0, hook)
        repeat_entry.insert(0, repeat)
        delay_entry.insert(0, delay)
        m = (meaning or "true").strip().lower()
        meaning_combo.set(m if m in _BOOL_CHOICES else "true")
        v = (video_audio or "false").strip().lower()
        video_audio_combo.set(v if v in _BOOL_CHOICES else "false")

        word_combo.bind("<<ComboboxSelected>>", lambda _e, r=row: self._update_preview(r))
        self._update_preview(row)
        self._renumber()
        if focus:
            word_combo.focus_set()
        return row

    def _apply_combo_sources(self, row: _WordRowWidgets) -> None:
        wid = id_from_combo_label(
            row.word_combo.get(), label_to_id=self._word_label_to_id
        )
        values = [""] + self._word_labels
        label = label_for_id(wid, id_to_label=self._word_id_to_label)
        if label and label not in values:
            values = [label, *values]
        row.word_combo["values"] = values
        row.word_combo.set(label)

    def _update_preview(self, row: _WordRowWidgets) -> None:
        wid = id_from_combo_label(
            row.word_combo.get(), label_to_id=self._word_label_to_id
        )
        if wid:
            text = self._word_id_to_preview.get(wid, "")
            row.preview.configure(text=text or "(미리보기 없음)")
        else:
            row.preview.configure(text="—")

    def _insert_after(self, block: ttk.Frame) -> None:
        after: _WordRowWidgets | None = None
        for row in self._rows:
            if row.frame is block:
                after = row
                break
        self._add_row(after=after)

    def _remove_block(self, block: ttk.Frame) -> None:
        target: _WordRowWidgets | None = None
        for row in self._rows:
            if row.frame is block:
                target = row
                break
        if target is None:
            return
        if len(self._rows) <= 1:
            target.word_combo.set("")
            target.hook_entry.delete(0, tk.END)
            target.repeat_entry.delete(0, tk.END)
            target.repeat_entry.insert(0, "1")
            target.delay_entry.delete(0, tk.END)
            target.meaning_combo.set("true")
            target.video_audio_combo.set("false")
            self._update_preview(target)
            return
        self._rows.remove(target)
        target.frame.destroy()
        self._renumber()

    def _renumber(self) -> None:
        for i, row in enumerate(self._rows, start=1):
            lbl = getattr(row.frame, "_idx_label", None)
            if isinstance(lbl, ttk.Label):
                lbl.configure(text=f"#{i}")
