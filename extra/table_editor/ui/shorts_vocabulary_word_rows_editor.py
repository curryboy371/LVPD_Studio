"""shorts_vocabulary word_id · 단어별 옵션 (+/−, id 입력·검색, 미리보기)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from extra.table_editor.services.shorts_vocab_data import (
    join_pipe_tokens,
    normalize_word_id,
    parse_pipe_ids,
    parse_pipe_tokens,
)
from extra.table_editor.services.word_lookup import lookup_word_details
from extra.table_editor.ui.word_search_panel import WordSearchPanel


_BOOL_CHOICES = ("", "true", "false")


def _word_preview_text(word_id: str) -> str:
    wid = normalize_word_id(word_id)
    if not wid:
        return ""
    details = lookup_word_details(wid)
    hanzi = (details.get("word") or "").strip()
    meaning = (details.get("meaning") or "").strip()
    pos = (details.get("pos") or "").strip()
    if not hanzi and not meaning:
        return ""
    text = f"{hanzi} — {meaning}" if hanzi and meaning else hanzi or meaning
    if pos:
        text = f"{text} ({pos})"
    return text


class _WordRowWidgets:
    __slots__ = (
        "frame",
        "word_id_entry",
        "delay_entry",
        "video_audio_combo",
        "preview",
    )

    def __init__(
        self,
        frame: ttk.Frame,
        word_id_entry: ttk.Entry,
        delay_entry: ttk.Entry,
        video_audio_combo: ttk.Combobox,
        preview: ttk.Label,
    ) -> None:
        self.frame = frame
        self.word_id_entry = word_id_entry
        self.delay_entry = delay_entry
        self.video_audio_combo = video_audio_combo
        self.preview = preview


class ShortsVocabularyWordRowsEditor(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        word_ids: str = "",
        after_delay: str = "",
        use_word_video_audio: str = "",
    ) -> None:
        super().__init__(master)
        self._rows: list[_WordRowWidgets] = []
        self._active_row: _WordRowWidgets | None = None

        ttk.Label(
            self,
            text="word_id · delay · word비디오음성 (| 순서 동일)",
            foreground="#666666",
            wraplength=560,
            font=("", 8),
        ).pack(anchor="w", pady=(0, 4))

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        rows_host = ttk.Frame(body)
        body.add(rows_host, weight=3)

        self._host = ttk.Frame(rows_host)
        self._host.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(self._host)
        header.pack(fill=tk.X, pady=(0, 2))
        for text, width in (
            ("#", 3),
            ("word_id", 8),
            ("delay", 5),
            ("vidAud", 6),
        ):
            ttk.Label(header, text=text, width=width).pack(side=tk.LEFT, padx=1)

        self._word_search = WordSearchPanel(
            body,
            on_pick=self.apply_word_id,
            hint="word_id 입력란 클릭 → 검색 (Enter / 더블클릭 / word_id에 넣기)",
            pick_button_text="word_id에 넣기",
        )
        body.add(self._word_search, weight=1)

        wids = parse_pipe_ids(word_ids)
        delays = parse_pipe_tokens(after_delay)
        videos = parse_pipe_tokens(use_word_video_audio)
        n = max(len(wids), 1)
        for i in range(n):
            self._add_row(
                wids[i] if i < len(wids) else "",
                delays[i] if i < len(delays) and delays[i].strip() else "0",
                videos[i] if i < len(videos) else "false",
                focus=False,
            )

    def refresh_word_sources(self) -> None:
        for row in self._rows:
            self._update_preview(row)

    def apply_word_id(self, word_id: str) -> bool:
        wid = normalize_word_id(word_id)
        if not wid or self._active_row is None:
            return False
        entry = self._active_row.word_id_entry
        entry.delete(0, tk.END)
        entry.insert(0, wid)
        self._update_preview(self._active_row)
        entry.focus_set()
        return True

    def get_pipe_values(self) -> dict[str, str]:
        wids: list[str] = []
        delays: list[str] = []
        videos: list[str] = []
        for row in self._rows:
            wid = normalize_word_id(row.word_id_entry.get())
            if not wid:
                continue
            wids.append(wid)
            delays.append(row.delay_entry.get().strip() or "0")
            videos.append((row.video_audio_combo.get() or "false").strip().lower())
        return {
            "word_id": join_pipe_tokens(wids),
            "after_sound_delay_sec": join_pipe_tokens(delays),
            "use_word_video_audio": join_pipe_tokens(videos),
        }

    def _add_row(
        self,
        word_id: str = "",
        delay: str = "0",
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

        word_id_entry = ttk.Entry(top, width=8)
        word_id_entry.pack(side=tk.LEFT, padx=1)
        delay_entry = ttk.Entry(top, width=4)
        delay_entry.pack(side=tk.LEFT, padx=1)
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
            wraplength=380,
            foreground="#333333",
            font=("", 9),
        )
        preview.pack(anchor="w", padx=(4, 0), pady=(1, 0))

        row = _WordRowWidgets(
            block,
            word_id_entry,
            delay_entry,
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

        wid = normalize_word_id(word_id)
        if wid:
            word_id_entry.insert(0, wid)
        delay_entry.insert(0, delay)
        v = (video_audio or "false").strip().lower()
        video_audio_combo.set(v if v in _BOOL_CHOICES else "false")

        word_id_entry.bind(
            "<FocusIn>", lambda _e, r=row: self._set_active_row(r)
        )
        word_id_entry.bind(
            "<KeyRelease>", lambda _e, r=row: self._update_preview(r)
        )
        self._update_preview(row)
        self._renumber()
        if focus:
            self._set_active_row(row)
            word_id_entry.focus_set()
        return row

    def _set_active_row(self, row: _WordRowWidgets) -> None:
        self._active_row = row

    def _update_preview(self, row: _WordRowWidgets) -> None:
        text = _word_preview_text(row.word_id_entry.get())
        if text:
            row.preview.configure(text=text)
        elif normalize_word_id(row.word_id_entry.get()):
            row.preview.configure(text="(words에 없는 id)")
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
        if self._active_row is target:
            self._active_row = None
        if len(self._rows) <= 1:
            target.word_id_entry.delete(0, tk.END)
            target.delay_entry.delete(0, tk.END)
            target.delay_entry.insert(0, "0")
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
