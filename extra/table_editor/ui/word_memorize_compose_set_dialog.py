"""단어 외우기 조합형 — 조합 세트 파일(결과 단어 + 부품 2개 + 문장)을 만들고
목록으로 보면서 추가·수정·삭제한다.

조합 세트 파일을 고르면 그 안에 이미 들어있는 결과 단어들을 목록으로 보여주고,
[+ 추가]/[수정]/[- 삭제]로 관리한다. 부품·결과 단어 자체는 words.xlsx에 이미
있어야 한다(없으면 먼저 단어장에 추가).
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from extra.table_editor.services.shorts_editor_choices import (
    BG_PATH_RANDOM_LABEL,
    bg_path_for_combo,
    bg_path_from_combo,
    list_bg_path_choices,
)
from extra.table_editor.services.word_lookup import lookup_word_details
from extra.table_editor.services.word_memorize_compose_builder import (
    ComposeEntry,
    add_result_to_layout,
    link_compose_component_ids,
    list_combo_layout_files,
    list_compose_entries,
    remove_compose_entry_from_layout,
    set_compose_entry_desc,
)
from extra.table_editor.services.word_memorize_layout import (
    DEFAULT_LAYOUTS_DIR,
    load_layout,
    save_layout,
)
from extra.table_editor.ui.shorts_bg_path_preview import attach_bg_path_preview
from extra.table_editor.ui.window_placement import schedule_center_toplevel_on_parent
from extra.table_editor.ui.word_memorize_word_pick_dialog import WordMemorizeWordPickDialog

_NEW_SET_LABEL = "+ 새 조합 세트로 만들기…"

# 라벨은 studio.studios.word_memorize_compose.COMPOSE_THEMES와 맞춰 동기화 —
# table_editor는 pygame 의존 렌더러 모듈을 끌어들이지 않도록 여기서 직접 나열한다.
_COMPOSE_THEME_CHOICES: list[tuple[str, str]] = [
    ("보라_주황", "ivory"),
    ("보라_파랑", "bright"),
    ("화이트_녹색", "white"),
    ("화이트_레드", "white_red"),
]


def _find_main_window(widget: tk.Misc):
    """widget 조상 중 MainWindow(단어장 등 모드를 가진 루트 창)를 찾는다."""
    from extra.table_editor.ui.main_window import MainWindow

    w: tk.Misc | None = widget
    while w is not None:
        if isinstance(w, MainWindow):
            return w
        w = getattr(w, "master", None)
    return None


def _describe_word(word_id: str) -> str:
    details = lookup_word_details(word_id)
    hanzi = details.get("word", "?")
    meaning = (details.get("meaning") or "").strip()
    label = f"{word_id}  {hanzi}"
    if meaning:
        label += f"  ({meaning})"
    return label


def _run_tts(
    result_id: int, c1_id: int, c2_id: int, c3_id: int | None, *, sentence_zh: str
) -> str:
    from audio.word_memorize_tts import batch_build_word_memorize_tts_for_word_ids
    from audio.word_memorize_compose_sentence import (
        batch_build_compose_sentence_tts_for_word_ids,
    )

    word_ids = [c1_id, c2_id, result_id]
    if c3_id:
        word_ids.insert(2, c3_id)
    word_ok, word_skip, word_fail = batch_build_word_memorize_tts_for_word_ids(
        word_ids, layout_label="조합 세트 만들기"
    )
    summary = f"단어 TTS: 생성 {word_ok} / 스킵 {word_skip} / 실패 {word_fail}"
    if sentence_zh:
        s_ok, s_skip, s_fail = batch_build_compose_sentence_tts_for_word_ids([result_id])
        summary += f"\n문장 TTS: 생성 {s_ok} / 스킵 {s_skip} / 실패 {s_fail}"
    return summary


class _ComposeEntryDialog(tk.Toplevel):
    """조합 세트 1건(결과 단어+부품1+부품2+문장) 추가/수정 입력창."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        mode: str,
        entry: ComposeEntry | None = None,
        exclude_result_ids: set[str] | None = None,
        on_submit: Callable[[str, str, str, str, str, str, str, bool], bool],
    ) -> None:
        super().__init__(parent)
        self.title("조합 세트 추가" if mode == "add" else "조합 세트 수정")
        self.transient(parent)
        self.grab_set()
        self._mode = mode
        self._on_submit = on_submit
        self._exclude_result_ids = exclude_result_ids or set()

        self._result_id = str(entry.word_id) if entry else ""
        self._c1_id = str(entry.component1_id) if entry and entry.component1_id else ""
        self._c2_id = str(entry.component2_id) if entry and entry.component2_id else ""
        self._c3_id = str(entry.component3_id) if entry and entry.component3_id else ""

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        self._result_var = tk.StringVar(
            value=_describe_word(self._result_id) if self._result_id else "(선택 안 됨)"
        )
        self._c1_var = tk.StringVar(
            value=_describe_word(self._c1_id) if self._c1_id else "(선택 안 됨)"
        )
        self._c2_var = tk.StringVar(
            value=_describe_word(self._c2_id) if self._c2_id else "(선택 안 됨)"
        )
        self._c3_var = tk.StringVar(
            value=_describe_word(self._c3_id) if self._c3_id else "(사용 안 함)"
        )

        result_row = ttk.Frame(frame)
        result_row.pack(fill=tk.X, pady=3)
        ttk.Label(result_row, text="결과 단어(합성어)", width=14).pack(side=tk.LEFT)
        ttk.Label(result_row, textvariable=self._result_var, foreground="#222").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8)
        )
        if mode == "add":
            ttk.Button(
                result_row, text="찾기…", command=self._pick_result, width=8
            ).pack(side=tk.RIGHT)

        self._add_pick_row(frame, "부품1", self._c1_var, self._pick_c1)
        self._add_pick_row(frame, "부품2", self._c2_var, self._pick_c2)
        self._add_pick_row(
            frame, "부품3(선택)", self._c3_var, self._pick_c3, on_clear=self._clear_c3
        )

        sentence_box = ttk.LabelFrame(frame, text="활용 문장(선택 — 4단 문장 카드용)")
        sentence_box.pack(fill=tk.X, pady=(6, 10))
        s_in = ttk.Frame(sentence_box)
        s_in.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(s_in, text="중국어 문장:", width=12).grid(row=0, column=0, sticky="w", pady=2)
        self._sentence_zh_var = tk.StringVar(value=entry.sentence_zh if entry else "")
        ttk.Entry(s_in, textvariable=self._sentence_zh_var, width=40).grid(
            row=0, column=1, sticky="we", pady=2
        )
        ttk.Label(s_in, text="한국어 뜻:", width=12).grid(row=1, column=0, sticky="w", pady=2)
        self._sentence_ko_var = tk.StringVar(value=entry.sentence_ko if entry else "")
        ttk.Entry(s_in, textvariable=self._sentence_ko_var, width=40).grid(
            row=1, column=1, sticky="we", pady=2
        )
        s_in.columnconfigure(1, weight=1)

        desc_box = ttk.LabelFrame(frame, text='설명(선택 — "왜 이 조합인지" 화면에 표시)')
        desc_box.pack(fill=tk.X, pady=(0, 10))
        d_in = ttk.Frame(desc_box)
        d_in.pack(fill=tk.X, padx=8, pady=8)
        self._word_desc_var = tk.StringVar(value=entry.word_desc if entry else "")
        ttk.Entry(d_in, textvariable=self._word_desc_var).pack(fill=tk.X)

        self._tts_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame, text="지금 TTS도 생성(네트워크 필요, 몇 초~수십 초 소요)", variable=self._tts_var
        ).pack(anchor="w", pady=(0, 8))

        self._status_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self._status_var, foreground="#0a6").pack(
            anchor="w", pady=(0, 8)
        )

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X)
        self._submit_btn = ttk.Button(
            btn_row, text="저장", command=self._on_submit_clicked
        )
        self._submit_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="취소", command=self.destroy).pack(side=tk.LEFT)

        self.bind("<Escape>", lambda _e: self.destroy())
        schedule_center_toplevel_on_parent(self, parent, width=520, height=530)

    def _add_pick_row(
        self,
        parent: tk.Misc,
        label: str,
        var: tk.StringVar,
        command,
        *,
        on_clear: Callable[[], None] | None = None,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label, width=14).pack(side=tk.LEFT)
        ttk.Label(row, textvariable=var, foreground="#222").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8)
        )
        if on_clear is not None:
            ttk.Button(row, text="지우기", command=on_clear, width=8).pack(
                side=tk.RIGHT, padx=(4, 0)
            )
        ttk.Button(row, text="찾기…", command=command, width=8).pack(side=tk.RIGHT)

    def _pick_result(self) -> None:
        dlg = WordMemorizeWordPickDialog(
            self,
            self._set_result,
            exclude_ids=self._exclude_result_ids,
            title="결과 단어(합성어) 찾기",
        )
        self.wait_window(dlg)

    def _pick_c1(self) -> None:
        dlg = WordMemorizeWordPickDialog(self, self._set_c1, title="부품1 찾기")
        self.wait_window(dlg)

    def _pick_c2(self) -> None:
        dlg = WordMemorizeWordPickDialog(self, self._set_c2, title="부품2 찾기")
        self.wait_window(dlg)

    def _pick_c3(self) -> None:
        dlg = WordMemorizeWordPickDialog(self, self._set_c3, title="부품3 찾기(선택)")
        self.wait_window(dlg)

    def _set_result(self, word_id: str) -> None:
        self._result_id = word_id
        self._result_var.set(_describe_word(word_id))

    def _set_c1(self, word_id: str) -> None:
        self._c1_id = word_id
        self._c1_var.set(_describe_word(word_id))

    def _set_c2(self, word_id: str) -> None:
        self._c2_id = word_id
        self._c2_var.set(_describe_word(word_id))

    def _set_c3(self, word_id: str) -> None:
        self._c3_id = word_id
        self._c3_var.set(_describe_word(word_id))

    def _clear_c3(self) -> None:
        self._c3_id = ""
        self._c3_var.set("(사용 안 함)")

    def _on_submit_clicked(self) -> None:
        if not (self._result_id and self._c1_id and self._c2_id):
            messagebox.showwarning(
                "선택 필요", "결과 단어·부품1·부품2를 모두 골라주세요.", parent=self
            )
            return
        chosen_ids = [self._result_id, self._c1_id, self._c2_id]
        if self._c3_id:
            chosen_ids.append(self._c3_id)
        if len(set(chosen_ids)) < len(chosen_ids):
            messagebox.showwarning(
                "중복 선택", "결과 단어·부품들은 서로 달라야 합니다.", parent=self
            )
            return

        self._submit_btn.state(["disabled"])
        self._status_var.set("저장 중…")
        self.update_idletasks()
        ok = self._on_submit(
            self._result_id,
            self._c1_id,
            self._c2_id,
            self._c3_id,
            (self._sentence_zh_var.get() or "").strip(),
            (self._sentence_ko_var.get() or "").strip(),
            (self._word_desc_var.get() or "").strip(),
            self._tts_var.get(),
        )
        if ok:
            self.destroy()
        else:
            self._submit_btn.state(["!disabled"])
            self._status_var.set("")


class WordMemorizeComposeSetDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("조합 세트 만들기")
        self.transient(parent)
        self.grab_set()

        self._combo_files = list_combo_layout_files()
        self._current_target_path: Path | None = None
        self._entries: list[ComposeEntry] = []

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=(
                "조합 세트 파일을 고르면 안에 들어있는 결과 단어 목록이 보입니다. "
                "결과 단어·부품 한자는 words.xlsx에 이미 있어야 합니다."
            ),
            foreground="#555",
            wraplength=560,
        ).pack(anchor="w", pady=(0, 10))

        target_box = ttk.LabelFrame(frame, text="조합 세트 파일")
        target_box.pack(fill=tk.X, pady=(0, 10))
        t_in = ttk.Frame(target_box)
        t_in.pack(fill=tk.X, padx=8, pady=8)
        combo_values = [name for name, _ in self._combo_files] + [_NEW_SET_LABEL]
        self._target_var = tk.StringVar(value=combo_values[0] if combo_values else _NEW_SET_LABEL)
        self._target_combo = ttk.Combobox(
            t_in, textvariable=self._target_var, values=combo_values, state="readonly", width=40
        )
        self._target_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._target_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_target_changed())

        self._new_name_row = ttk.Frame(target_box)
        ttk.Label(self._new_name_row, text="새 파일 이름:", width=12).pack(side=tk.LEFT)
        self._new_name_var = tk.StringVar()
        ttk.Entry(self._new_name_row, textvariable=self._new_name_var, width=26).pack(
            side=tk.LEFT, padx=(4, 12)
        )
        ttk.Label(self._new_name_row, text="스타일 참고:", width=10).pack(side=tk.LEFT)
        template_values = [name for name, _ in self._combo_files]
        self._template_var = tk.StringVar(value=template_values[0] if template_values else "")
        ttk.Combobox(
            self._new_name_row,
            textvariable=self._template_var,
            values=template_values,
            state="readonly",
            width=20,
        ).pack(side=tk.LEFT)

        bgm_row = ttk.Frame(target_box)
        bgm_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(bgm_row, text="배경음(BGM):", width=12).pack(side=tk.LEFT)
        self._bgm_var = tk.StringVar(value=BG_PATH_RANDOM_LABEL)
        bgm_choices = [BG_PATH_RANDOM_LABEL] + list_bg_path_choices()
        self._bgm_combo = ttk.Combobox(
            bgm_row, textvariable=self._bgm_var, values=bgm_choices, state="readonly", width=26
        )
        self._bgm_combo.pack(side=tk.LEFT, padx=(4, 8))
        self._bgm_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_bgm_changed())
        attach_bg_path_preview(bgm_row, self._bgm_combo).pack(side=tk.LEFT)

        topic_row = ttk.Frame(target_box)
        topic_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(topic_row, text="주제:", width=12).pack(side=tk.LEFT)
        self._topic_var = tk.StringVar()
        topic_entry = ttk.Entry(topic_row, textvariable=self._topic_var)
        topic_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        topic_entry.bind("<KeyRelease>", lambda _e: self._on_topic_changed())

        theme_row = ttk.Frame(target_box)
        theme_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(theme_row, text="색 테마:", width=12).pack(side=tk.LEFT)
        self._theme_label_to_key = dict(_COMPOSE_THEME_CHOICES)
        self._theme_key_to_label = {key: label for label, key in _COMPOSE_THEME_CHOICES}
        self._theme_var = tk.StringVar(value=_COMPOSE_THEME_CHOICES[0][0])
        theme_combo = ttk.Combobox(
            theme_row,
            textvariable=self._theme_var,
            values=[label for label, _ in _COMPOSE_THEME_CHOICES],
            state="readonly",
            width=26,
        )
        theme_combo.pack(side=tk.LEFT)
        theme_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_theme_changed())

        desc_row = ttk.Frame(target_box)
        desc_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(desc_row, text="설명:", width=12).pack(side=tk.LEFT)
        self._desc_var = tk.StringVar()
        desc_entry = ttk.Entry(desc_row, textvariable=self._desc_var)
        desc_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        desc_entry.bind("<KeyRelease>", lambda _e: self._on_desc_changed())

        entries_box = ttk.LabelFrame(frame, text="포함된 단어")
        entries_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        tree_wrap = ttk.Frame(entries_box)
        tree_wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        columns = ("order", "result", "c1", "c2", "c3", "sentence", "word_desc")
        self._tree = ttk.Treeview(
            tree_wrap, columns=columns, show="headings", height=8, selectmode="browse"
        )
        headings = {
            "order": ("#", 32),
            "result": ("결과 단어", 130),
            "c1": ("부품1", 90),
            "c2": ("부품2", 90),
            "c3": ("부품3", 90),
            "sentence": ("문장", 160),
            "word_desc": ("설명", 160),
        }
        for col, (text, width) in headings.items():
            self._tree.heading(col, text=text)
            self._tree.column(col, width=width, anchor="w")
        scroll = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.LEFT, fill=tk.Y)
        self._tree.bind("<Double-1>", lambda _e: self._on_edit())

        entry_btn_row = ttk.Frame(entries_box)
        entry_btn_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        ttk.Button(entry_btn_row, text="+ 추가", command=self._on_add).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(entry_btn_row, text="수정", command=self._on_edit).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(entry_btn_row, text="- 삭제", command=self._on_delete).pack(
            side=tk.LEFT, padx=6
        )

        nav_row = ttk.Frame(entries_box)
        nav_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(nav_row, text="이미지 경로 넣기:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            nav_row, text="결과 단어 편집", command=lambda: self._go_to_word_editor("result")
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(
            nav_row, text="부품1 편집", command=lambda: self._go_to_word_editor("c1")
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(
            nav_row, text="부품2 편집", command=lambda: self._go_to_word_editor("c2")
        ).pack(side=tk.LEFT, padx=3)
        ttk.Button(
            nav_row, text="부품3 편집", command=lambda: self._go_to_word_editor("c3")
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(frame, text="닫기", command=self.destroy).pack(anchor="e")

        self._on_target_changed()
        self.bind("<Escape>", lambda _e: self.destroy())
        schedule_center_toplevel_on_parent(self, parent, width=700, height=700)

    # -- 대상 파일 -----------------------------------------------------------
    def _on_target_changed(self) -> None:
        if self._target_var.get() == _NEW_SET_LABEL:
            self._new_name_row.pack(fill=tk.X, padx=8, pady=(0, 8))
            self._current_target_path = None
            self._entries = []
            self._refresh_tree()
        else:
            self._new_name_row.pack_forget()
            path = self._path_for_choice(self._target_var.get())
            self._current_target_path = path
            self._reload_entries()
        self._sync_bgm_from_target()
        self._sync_topic_theme_from_target()

    def _sync_bgm_from_target(self) -> None:
        if self._current_target_path is not None and self._current_target_path.is_file():
            try:
                layout = load_layout(self._current_target_path)
                self._bgm_var.set(bg_path_for_combo(layout.bg_music_path))
                return
            except (ValueError, OSError):
                pass
        self._bgm_var.set(BG_PATH_RANDOM_LABEL)

    def _on_bgm_changed(self) -> None:
        if self._current_target_path is None or not self._current_target_path.is_file():
            return  # 새 세트는 파일이 만들어진 뒤(첫 + 추가 시) 적용된다.
        try:
            layout = load_layout(self._current_target_path)
            layout.bg_music_path = bg_path_from_combo(self._bgm_var.get())
            save_layout(self._current_target_path, layout)
        except (ValueError, OSError) as ex:
            messagebox.showerror("배경음 저장 실패", str(ex), parent=self)

    def _sync_topic_theme_from_target(self) -> None:
        if self._current_target_path is not None and self._current_target_path.is_file():
            try:
                layout = load_layout(self._current_target_path)
                self._topic_var.set(str(getattr(layout, "compose_topic", "") or ""))
                theme_key = str(getattr(layout, "compose_theme", "") or "ivory")
                self._theme_var.set(
                    self._theme_key_to_label.get(theme_key, _COMPOSE_THEME_CHOICES[0][0])
                )
                self._desc_var.set(str(getattr(layout, "compose_desc", "") or ""))
                return
            except (ValueError, OSError):
                pass
        self._topic_var.set("")
        self._theme_var.set(_COMPOSE_THEME_CHOICES[0][0])
        self._desc_var.set("")

    def _on_topic_changed(self) -> None:
        if self._current_target_path is None or not self._current_target_path.is_file():
            return  # 새 세트는 파일이 만들어진 뒤(첫 + 추가 시) 적용된다.
        try:
            layout = load_layout(self._current_target_path)
            layout.compose_topic = self._topic_var.get().strip()
            save_layout(self._current_target_path, layout)
        except (ValueError, OSError) as ex:
            messagebox.showerror("주제 저장 실패", str(ex), parent=self)

    def _on_theme_changed(self) -> None:
        if self._current_target_path is None or not self._current_target_path.is_file():
            return  # 새 세트는 파일이 만들어진 뒤(첫 + 추가 시) 적용된다.
        key = self._theme_label_to_key.get(self._theme_var.get())
        if not key:
            return
        try:
            layout = load_layout(self._current_target_path)
            layout.compose_theme = key
            save_layout(self._current_target_path, layout)
        except (ValueError, OSError) as ex:
            messagebox.showerror("색 테마 저장 실패", str(ex), parent=self)

    def _on_desc_changed(self) -> None:
        if self._current_target_path is None or not self._current_target_path.is_file():
            return  # 새 세트는 파일이 만들어진 뒤(첫 + 추가 시) 적용된다.
        try:
            layout = load_layout(self._current_target_path)
            layout.compose_desc = self._desc_var.get().strip()
            save_layout(self._current_target_path, layout)
        except (ValueError, OSError) as ex:
            messagebox.showerror("설명 저장 실패", str(ex), parent=self)

    def _path_for_choice(self, choice: str) -> Path | None:
        for fname, fpath in self._combo_files:
            if fname == choice:
                return fpath
        return None

    def _resolve_target_for_add(self) -> tuple[Path, Path | None] | None:
        """(저장할 layout 경로, 새로 만들 때만 쓰는 템플릿 경로) — 검증 실패 시 None."""
        if self._target_var.get() != _NEW_SET_LABEL:
            if self._current_target_path is None:
                return None
            return self._current_target_path, None

        name = (self._new_name_var.get() or "").strip()
        if not name:
            messagebox.showwarning("이름 필요", "새 조합 세트 파일 이름을 입력하세요.", parent=self)
            return None
        template_name = self._template_var.get()
        template_path = self._path_for_choice(template_name) if template_name else None
        if template_path is None:
            messagebox.showwarning(
                "템플릿 필요",
                "스타일을 참고할 기존 조합 세트 파일이 없습니다. 먼저 조합형 배치를 1개 만들어두세요.",
                parent=self,
            )
            return None
        return DEFAULT_LAYOUTS_DIR / f"{name}.json", template_path

    def _reload_entries(self) -> None:
        if self._current_target_path is None or not self._current_target_path.is_file():
            self._entries = []
        else:
            try:
                self._entries = list_compose_entries(self._current_target_path)
            except (ValueError, OSError) as ex:
                messagebox.showerror("불러오기 실패", str(ex), parent=self)
                self._entries = []
        self._refresh_tree()

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for entry in self._entries:
            sentence = entry.sentence_zh
            if len(sentence) > 24:
                sentence = sentence[:24] + "…"
            word_desc = entry.word_desc
            if len(word_desc) > 24:
                word_desc = word_desc[:24] + "…"
            self._tree.insert(
                "",
                tk.END,
                iid=str(entry.word_id),
                values=(
                    entry.order,
                    f"{entry.hanzi} ({entry.meaning})" if entry.meaning else entry.hanzi,
                    entry.component1_hanzi or "?",
                    entry.component2_hanzi or "?",
                    entry.component3_hanzi or "-",
                    sentence,
                    word_desc,
                ),
            )

    def _selected_entry(self) -> ComposeEntry | None:
        sel = self._tree.selection()
        if not sel:
            return None
        wid = int(sel[0])
        return next((e for e in self._entries if e.word_id == wid), None)

    def _go_to_word_editor(self, which: str) -> None:
        entry = self._selected_entry()
        if entry is None:
            messagebox.showinfo("선택 필요", "이미지를 넣을 단어를 목록에서 선택하세요.", parent=self)
            return
        word_id = {
            "result": entry.word_id,
            "c1": entry.component1_id,
            "c2": entry.component2_id,
            "c3": entry.component3_id,
        }[which]
        if not word_id:
            messagebox.showinfo(
                "이동 불가", "해당 부품의 word_id가 없습니다(연결 안 됨).", parent=self
            )
            return
        main_window = _find_main_window(self)
        if main_window is None:
            messagebox.showerror("이동 실패", "메인 창을 찾을 수 없습니다.", parent=self)
            return
        main_window.open_vocabulary_word_editor(str(word_id))

    # -- 추가/수정/삭제 -------------------------------------------------------
    def _on_add(self) -> None:
        target = self._resolve_target_for_add()
        if target is None:
            if self._target_var.get() != _NEW_SET_LABEL:
                messagebox.showwarning(
                    "파일 선택 필요", "먼저 조합 세트 파일을 고르거나 새로 만들어주세요.", parent=self
                )
            return
        target_path, template_path = target
        exclude_ids = {str(e.word_id) for e in self._entries}

        def _submit(
            result_id: str, c1_id: str, c2_id: str, c3_id: str,
            sentence_zh: str, sentence_ko: str, word_desc: str, do_tts: bool,
        ) -> bool:
            c3_int = int(c3_id) if c3_id else None
            try:
                link_compose_component_ids(
                    int(result_id), int(c1_id), int(c2_id), c3_int,
                    sentence_zh=sentence_zh, sentence_ko=sentence_ko,
                )
                add_result_to_layout(
                    int(result_id), target_path=target_path, template_path=template_path
                )
                set_compose_entry_desc(int(result_id), word_desc, target_path=target_path)
                new_layout = load_layout(target_path)
                new_layout.bg_music_path = bg_path_from_combo(self._bgm_var.get())
                new_layout.compose_topic = self._topic_var.get().strip()
                theme_key = self._theme_label_to_key.get(self._theme_var.get())
                if theme_key:
                    new_layout.compose_theme = theme_key
                new_layout.compose_desc = self._desc_var.get().strip()
                save_layout(target_path, new_layout)
            except (ValueError, OSError) as ex:
                messagebox.showerror("추가 실패", str(ex), parent=self)
                return False

            tts_summary = ""
            if do_tts:
                tts_summary = _run_tts(
                    int(result_id), int(c1_id), int(c2_id), c3_int, sentence_zh=sentence_zh
                )

            if self._target_var.get() == _NEW_SET_LABEL:
                self._combo_files = list_combo_layout_files()
                values = [name for name, _ in self._combo_files] + [_NEW_SET_LABEL]
                self._target_combo.configure(values=values)
                self._target_var.set(target_path.name)
                self._new_name_row.pack_forget()
            self._current_target_path = target_path
            self._reload_entries()
            if tts_summary:
                messagebox.showinfo("TTS 생성 결과", tts_summary, parent=self)
            return True

        _ComposeEntryDialog(
            self, mode="add", exclude_result_ids=exclude_ids, on_submit=_submit
        )

    def _on_edit(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            messagebox.showinfo("선택 필요", "수정할 단어를 목록에서 선택하세요.", parent=self)
            return
        target_path = self._current_target_path
        if target_path is None:
            return

        def _submit(
            result_id: str, c1_id: str, c2_id: str, c3_id: str,
            sentence_zh: str, sentence_ko: str, word_desc: str, do_tts: bool,
        ) -> bool:
            c3_int = int(c3_id) if c3_id else None
            try:
                link_compose_component_ids(
                    int(result_id), int(c1_id), int(c2_id), c3_int,
                    sentence_zh=sentence_zh, sentence_ko=sentence_ko,
                )
                set_compose_entry_desc(int(result_id), word_desc, target_path=target_path)
            except (ValueError, OSError) as ex:
                messagebox.showerror("수정 실패", str(ex), parent=self)
                return False

            tts_summary = ""
            if do_tts:
                tts_summary = _run_tts(
                    int(result_id), int(c1_id), int(c2_id), c3_int, sentence_zh=sentence_zh
                )
            self._reload_entries()
            if tts_summary:
                messagebox.showinfo("TTS 생성 결과", tts_summary, parent=self)
            return True

        _ComposeEntryDialog(self, mode="edit", entry=entry, on_submit=_submit)

    def _on_delete(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            messagebox.showinfo("선택 필요", "삭제할 단어를 목록에서 선택하세요.", parent=self)
            return
        target_path = self._current_target_path
        if target_path is None:
            return
        if not messagebox.askyesno(
            "삭제 확인",
            f"'{entry.hanzi}'를 이 조합 세트에서 제거할까요?\n"
            "(words.xlsx의 부품·문장 정보는 그대로 남습니다.)",
            parent=self,
        ):
            return
        try:
            remove_compose_entry_from_layout(entry.word_id, target_path=target_path)
        except (ValueError, OSError) as ex:
            messagebox.showerror("삭제 실패", str(ex), parent=self)
            return
        self._reload_entries()


def open_word_memorize_compose_set_dialog(parent: tk.Misc) -> None:
    WordMemorizeComposeSetDialog(parent)
