"""메인 모드 — CSV/TTS/에셋/미리보기/녹화 빠른 실행."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Callable

from core.paths import get_repo_root
from extra.table_editor.services.task_runner import TaskRunner
from extra.table_editor.services.topic_sources import (
    topics_for_conversation_preview,
    topics_for_shorts_conversation_preview,
    topics_for_shorts_vocabulary_preview,
    topics_for_vocabulary_preview,
)
from extra.table_editor.services.word_memorize_layouts import (
    list_layout_files,
    normalize_layout_filename,
)
from extra.table_editor.ui.studio_run_dialog import StudioRunDialog
from extra.table_editor.services.tts_voice_options import (
    TtsLangOptions,
    WordMemorizeTtsOptions,
)
from extra.table_editor.ui.tts_generate_dialog import TtsGenerateDialog
from extra.table_editor.ui.word_memorize_run_dialog import WordMemorizeRunDialog

_RECORD_MAX_SEC: dict[tuple[str, str], int] = {
    ("conversation", ""): 900,
    ("vocabulary", ""): 1800,
    ("shorts", "conversation"): 900,
    ("shorts", "vocabulary"): 900,
    ("word_memorize", ""): 600,
}


class MainPanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_status: Callable[[str], None],
    ) -> None:
        super().__init__(master)
        self._on_status = on_status
        self._runner = TaskRunner(get_repo_root())
        self._build_ui()

    @property
    def is_dirty(self) -> bool:
        return False

    @property
    def file_path(self) -> None:
        return None

    def path_summary(self) -> str:
        return "(메인 — 빠른 작업)"

    def open_file_dialog(self) -> None:
        pass

    def save(self) -> bool:
        return True

    def save_as(self) -> bool:
        return True

    def export_current_csv(self) -> None:
        self._run_task(["-m", "tools.csv_gen"], title="CSV 전체 생성")

    def export_all_csv(self) -> None:
        self.export_current_csv()

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=8)

        ttk.Label(top, text="입력 (topic / set_id / word_id):").pack(side=tk.LEFT)
        self._arg_var = tk.StringVar()
        ttk.Entry(top, textvariable=self._arg_var, width=36).pack(
            side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True
        )
        ttk.Label(
            top,
            text="TTS·스튜디오 실행에 사용",
            foreground="#666",
        ).pack(side=tk.LEFT, padx=(8, 0))

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        self._btn_widgets: list[ttk.Button] = []

        self._section(left, "데이터", [
            ("CSV 전체 생성", self._run_csv),
        ])
        self._section(left, "TTS", [
            ("TTS 생성", self._run_tts),
        ])
        self._section(left, "에셋", [
            ("비디오 → MP3 추출", self._run_video_to_mp3),
            ("한자 프레임 생성", self._run_hanzi_frames),
        ])
        self._section(left, "스튜디오 (미리보기 / 녹화)", [
            ("회화", lambda: self._run_studio_menu("conversation")),
            ("단어장", lambda: self._run_studio_menu("vocabulary")),
            ("숏츠 회화", lambda: self._run_studio_menu("shorts", "conversation")),
            ("숏츠 단어", lambda: self._run_studio_menu("shorts", "vocabulary")),
            ("단어 외우기", self._run_word_memorize_menu),
            ("녹화 파일 경로 열기", self._open_release_folder),
        ])

        log_frame = ttk.LabelFrame(body, text="실행 로그")
        log_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._log = scrolledtext.ScrolledText(
            log_frame,
            height=30,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
        )
        self._log.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        hint = ttk.Label(
            self,
            text="lvpd.bat 메뉴 1·2·3·4·5·6~9 와 동일한 작업을 GUI에서 실행합니다. "
            "녹화 mp4는 release\\ 폴더에 저장됩니다. 긴 작업은 로그 창에서 진행을 확인하세요.",
            foreground="#555",
            wraplength=960,
        )
        hint.pack(fill=tk.X, padx=12, pady=(0, 8))

    def _section(
        self,
        parent: ttk.Frame,
        title: str,
        buttons: list[tuple[str, Callable[[], None]]],
    ) -> None:
        frame = ttk.LabelFrame(parent, text=title)
        frame.pack(fill=tk.X, pady=(0, 8))
        inner = ttk.Frame(frame)
        inner.pack(fill=tk.X, padx=8, pady=8)
        for label, command in buttons:
            btn = ttk.Button(inner, text=label, command=command, width=22)
            btn.pack(fill=tk.X, pady=2)
            self._btn_widgets.append(btn)

    def _arg(self) -> str:
        return (self._arg_var.get() or "").strip()

    def _set_buttons_state(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in self._btn_widgets:
            btn.configure(state=state)

    def _append_log(self, line: str) -> None:
        def _do() -> None:
            self._log.configure(state=tk.NORMAL)
            self._log.insert(tk.END, line + "\n")
            self._log.see(tk.END)
            self._log.configure(state=tk.DISABLED)

        self.after(0, _do)

    def _on_task_done(self, code: int, title: str) -> None:
        def _do() -> None:
            self._set_buttons_state(True)
            if code == 0:
                msg = f"완료: {title}"
                self._append_log(f"[OK] {msg}")
            else:
                msg = f"실패 (코드 {code}): {title}"
                self._append_log(f"[FAIL] {msg}")
            self._on_status(msg)

        self.after(0, _do)

    def _run_task(self, argv: list[str], *, title: str) -> None:
        if self._runner.is_running:
            messagebox.showinfo(
                "실행 중",
                "다른 작업이 진행 중입니다. 로그 창에서 완료를 기다려 주세요.",
                parent=self.winfo_toplevel(),
            )
            return
        self._set_buttons_state(False)
        self._on_status(f"실행 중: {title}")
        started = self._runner.run(
            argv,
            title=title,
            on_line=self._append_log,
            on_done=self._on_task_done,
        )
        if not started:
            self._set_buttons_state(True)

    def _run_csv(self) -> None:
        self._run_task(["-m", "tools.csv_gen"], title="CSV 전체 생성")

    def _run_video_to_mp3(self) -> None:
        self._run_task(["run_extract_audio.py"], title="비디오 → MP3 추출")

    def _run_hanzi_frames(self) -> None:
        self._run_task(
            ["tools/hanzi/render_svg_frames.py", "--skip-existing"],
            title="한자 프레임 생성",
        )

    def _run_tts(self) -> None:
        result = TtsGenerateDialog.ask(
            self.winfo_toplevel(),
            initial=self._arg(),
        )
        if not result:
            return
        self._arg_var.set(result.value)
        if result.kind == "word_memorize":
            self._dispatch_word_memorize_tts(
                WordMemorizeTtsOptions.from_generate_result(result)
            )
            return
        self._dispatch_tts(result.kind, result.value, result.lang)

    def _ko_voice_argv(self, lang: TtsLangOptions) -> list[str]:
        if not lang.gen_ko or not lang.voice_ko:
            return []
        return ["--tts-voice", lang.voice_ko]

    def _dispatch_tts(self, kind: str, raw: str, lang: TtsLangOptions) -> None:
        voice = self._ko_voice_argv(lang)
        lang_tag = "KO" if lang.gen_ko else ""
        if kind == "conv":
            self._run_task(
                [
                    "-m",
                    "tools.tts_gen.build_conversation_sub_ko",
                    "--topic",
                    raw,
                    *voice,
                ],
                title=f"회화 TTS ({raw}) [{lang_tag}]",
            )
            return
        if kind == "vocab":
            self._run_task(
                [
                    "-m",
                    "tools.tts_gen.build_vocab_meaning_ko",
                    "--studio-topic",
                    raw,
                    *voice,
                ],
                title=f"단어장 TTS ({raw}) [{lang_tag}]",
            )
            return
        if kind == "shorts_conv":
            self._run_task(
                [
                    "-m",
                    "tools.tts_gen.build_shorts_ko_narration",
                    "--topic",
                    raw,
                    *voice,
                ],
                title=f"숏츠 회화 TTS ({raw}) [{lang_tag}]",
            )
            return
        if kind == "shorts_vocab":
            self._run_task(
                [
                    "-m",
                    "tools.tts_gen.build_vocab_meaning_ko",
                    "--topic",
                    raw,
                    *voice,
                ],
                title=f"숏츠 단어 TTS ({raw}) [{lang_tag}]",
            )
            return
    def _dispatch_word_memorize_tts(self, opts: WordMemorizeTtsOptions) -> None:
        argv = [
            "-m",
            "tools.tts_gen.build_word_memorize_tts",
            "--layout",
            opts.layout_path,
            "--tts-voice",
            opts.voice_ko,
            "--tts-voice-zh",
            opts.voice_zh,
            "--tts-voice-en",
            opts.voice_en,
        ]
        if not opts.gen_ko:
            argv.append("--skip-ko")
        if not opts.gen_zh:
            argv.append("--skip-zh")
        if not opts.gen_en:
            argv.append("--skip-en")
        parts = []
        if opts.gen_ko:
            parts.append("KO")
        if opts.gen_zh:
            parts.append("ZH")
        if opts.gen_en:
            parts.append("EN")
        title = f"단어 외우기 TTS ({opts.layout_name}) [{'+'.join(parts)}]"
        self._run_task(argv, title=title)

    def _run_studio_menu(self, studio: str, shorts_type: str = "") -> None:
        meta = self._studio_run_meta(studio, shorts_type)
        if meta is None:
            return
        label, prompt, topics = meta
        if not topics:
            messagebox.showwarning(
                label,
                "topic 목록이 없습니다.\n"
                "resource/csv 의 CSV를 확인하거나 CSV 전체 생성을 실행하세요.",
                parent=self.winfo_toplevel(),
            )
            return
        picked = StudioRunDialog.ask(
            self.winfo_toplevel(),
            title=label,
            prompt=prompt,
            topics=topics,
            initial=self._arg(),
        )
        if not picked:
            return
        mode, topic = picked
        self._arg_var.set(topic)
        self._dispatch_studio(mode, studio, shorts_type, topic)

    def _run_word_memorize_menu(self) -> None:
        layouts = list_layout_files()
        if not layouts:
            messagebox.showwarning(
                "단어 외우기",
                "저장된 배치가 없습니다.\n"
                "단어 외우기 배치 편집기에서 JSON을 저장한 뒤\n"
                "resource/table/word_memorize_layouts/ 를 확인하세요.",
                parent=self.winfo_toplevel(),
            )
            return
        initial = normalize_layout_filename(self._arg())
        names = [name for name, _ in layouts]
        if initial and initial not in names:
            initial = ""
        picked = WordMemorizeRunDialog.ask(
            self.winfo_toplevel(),
            layouts=layouts,
            initial_layout=initial,
        )
        if not picked:
            return
        mode, layout_path, meaning_lang = picked
        stem = Path(layout_path).stem
        self._arg_var.set(stem)
        self._dispatch_word_memorize(mode, layout_path, meaning_lang)

    def _dispatch_word_memorize(
        self,
        mode: str,
        layout_path: str,
        meaning_lang: str = "ko",
    ) -> None:
        stem = Path(layout_path).stem
        lang = (meaning_lang or "ko").strip().lower()
        if lang not in ("ko", "en", "zh"):
            lang = "ko"
        argv = [
            "-u",
            "-m",
            "studio.runner",
            "--mode",
            mode,
            "--studio",
            "word_memorize",
            "--layout",
            layout_path,
            "--meaning-lang",
            lang,
        ]
        if mode == "record":
            max_sec = _RECORD_MAX_SEC.get(("word_memorize", ""), 600)
            argv.extend(
                [
                    "--record-until-content-done",
                    "--record-max-sec",
                    str(max_sec),
                ]
            )
        lang_label = "한국어" if lang == "ko" else "영어"
        prefix = "녹화" if mode == "record" else "F5"
        self._run_task(
            argv, title=f"{prefix} 단어 외우기 ({stem}, {lang_label})"
        )

    def _studio_run_meta(
        self,
        studio: str,
        shorts_type: str = "",
    ) -> tuple[str, str, list[str]] | None:
        if studio == "conversation":
            return (
                "회화",
                "base_sentences.topic 을 선택한 뒤 미리보기 또는 녹화를 고르세요.",
                topics_for_conversation_preview(),
            )
        if studio == "vocabulary":
            return (
                "단어장",
                "vocabulary_word_rows.topic 을 선택한 뒤 미리보기 또는 녹화를 고르세요.",
                topics_for_vocabulary_preview(),
            )
        if studio == "shorts" and shorts_type == "conversation":
            return (
                "숏츠 회화",
                "shorts_conversation_clips.topic 을 선택한 뒤 미리보기 또는 녹화를 고르세요.",
                topics_for_shorts_conversation_preview(),
            )
        if studio == "shorts" and shorts_type == "vocabulary":
            return (
                "숏츠 단어",
                "shorts_vocabulary_clips.topic 을 선택한 뒤 미리보기 또는 녹화를 고르세요.",
                topics_for_shorts_vocabulary_preview(),
            )
        return None

    def _dispatch_studio(
        self,
        mode: str,
        studio: str,
        shorts_type: str,
        topic: str,
    ) -> None:
        argv = ["-u", "-m", "studio.runner", "--mode", mode]
        if mode == "record":
            max_sec = _RECORD_MAX_SEC.get((studio, shorts_type), 900)
            argv.extend(
                [
                    "--record-until-content-done",
                    "--record-max-sec",
                    str(max_sec),
                ]
            )
        if studio == "shorts":
            argv.extend(["--studio", "shorts", "--shorts-type", shorts_type])
            label = f"숏츠 {'회화' if shorts_type == 'conversation' else '단어'}"
        else:
            argv.extend(["--studio", studio])
            label = "회화" if studio == "conversation" else "단어장"
        argv.extend(["--topic", topic])
        prefix = "녹화" if mode == "record" else "F5"
        title = f"{prefix} {label} ({topic})"
        self._run_task(argv, title=title)

    def _open_release_folder(self) -> None:
        release = get_repo_root() / "release"
        release.mkdir(exist_ok=True)
        try:
            os.startfile(str(release))
        except OSError as ex:
            messagebox.showerror(
                "녹화 파일 경로",
                f"폴더를 열 수 없습니다:\n{release}\n\n{ex}",
                parent=self.winfo_toplevel(),
            )
            return
        self._on_status(f"녹화 폴더: {release}")
