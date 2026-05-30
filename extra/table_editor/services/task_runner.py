"""백그라운드 subprocess 실행 (메인 패널 빠른 작업)."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

OnLine = Callable[[str], None]
OnDone = Callable[[int, str], None]


class TaskRunner:
    """단일 작업만 순차 실행."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen[str] | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def run(
        self,
        argv: list[str],
        *,
        title: str,
        on_line: OnLine,
        on_done: OnDone,
        extra_env: dict[str, str] | None = None,
    ) -> bool:
        if self._running:
            on_line("[실행 중] 다른 작업이 끝날 때까지 기다려 주세요.")
            return False

        env = os.environ.copy()
        env["PYTHONPATH"] = str(self._repo_root)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        if extra_env:
            env.update(extra_env)

        cmd = [sys.executable, *argv]

        def _worker() -> None:
            code = 1
            try:
                on_line(f"\n=== {title} ===")
                on_line("$ " + " ".join(cmd))
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(self._repo_root),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                assert self._proc.stdout is not None
                for line in self._proc.stdout:
                    on_line(line.rstrip("\n\r"))
                code = int(self._proc.wait())
            except OSError as ex:
                on_line(f"[오류] {ex}")
                code = 1
            finally:
                self._proc = None
                self._running = False
                on_done(code, title)

        self._running = True
        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()
        return True
