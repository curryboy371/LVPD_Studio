"""
사전 렌더된 PNG 시퀀스를 재생하는 단어장 한자 애니메이션 컴포넌트.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import subprocess
import sys

import pygame

from core.paths import get_repo_root

logger = logging.getLogger(__name__)


@dataclass
class _SequenceClip:
    codepoint: int
    fps: float
    frame_paths: list[Path]


class HanziAnimator:
    """다글자 순차 재생 PNG 시퀀스 애니메이터."""

    _surface_cache: dict[tuple[str, int, int], pygame.Surface] = {}
    _MAX_VISIBLE_CHARS: int = 4

    def __init__(self) -> None:
        self._repo_root = get_repo_root()
        self._frames_root = get_repo_root() / "resource" / "hanzi_frames"
        self._svgs_root = get_repo_root() / "resource" / "svgs"
        self._render_script = get_repo_root() / "tools" / "hanzi" / "render_svg_frames.py"
        self._text: str = ""
        self._clips: list[_SequenceClip] = []
        self._clip_index: int = 0
        self._clip_elapsed: float = 0.0
        self._playing: bool = False
        self._play_speed: float = 1.0
        self._last_missing_report: tuple[str, ...] = ()
        self._auto_render_attempted: set[int] = set()

    def set_text(self, text: str, play_speed: float = 1.0) -> None:
        self._text = (text or "").strip()
        self._play_speed = max(0.1, min(5.0, float(play_speed)))
        self._clips = []
        self._clip_index = 0
        self._clip_elapsed = 0.0
        self._playing = False
        self._last_missing_report = ()
        if not self._text:
            return
        missing: list[str] = []
        for ch in self._text:
            cp = ord(ch)
            clip = self._load_clip(cp)
            if clip is None:
                self._try_auto_render_codepoint(cp)
                clip = self._load_clip(cp)
            if clip is not None:
                self._clips.append(clip)
            else:
                missing.append(f"{ch}(U+{cp:04X})")
        if missing:
            report = tuple(missing)
            if report != self._last_missing_report:
                logger.warning(
                    "한자 프레임 미생성: %s | 생성 스크립트: python tools/hanzi/render_svg_frames.py",
                    ", ".join(missing),
                )
                self._last_missing_report = report
        if self._clips:
            self._playing = True

    def _try_auto_render_codepoint(self, codepoint: int) -> None:
        if codepoint in self._auto_render_attempted:
            return
        self._auto_render_attempted.add(codepoint)
        svg_path = self._svgs_root / f"{codepoint}.svg"
        if not svg_path.exists():
            return
        if not self._render_script.exists():
            return
        try:
            cmd = [
                sys.executable,
                str(self._render_script),
                "--codepoints",
                str(codepoint),
                "--fps",
                "30",
                "--size",
                "768",
            ]
            res = subprocess.run(
                cmd,
                cwd=str(self._repo_root),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if res.returncode != 0:
                output = (res.stderr or res.stdout or "").strip()
                if "No module named 'playwright'" in output:
                    logger.warning(
                        "한자 프레임 자동 생성 실패 U+%04X: playwright 미설치. "
                        "pip install playwright && python -m playwright install chromium",
                        codepoint,
                    )
                    return
                logger.warning(
                    "한자 프레임 자동 생성 실패 U+%04X: %s",
                    codepoint,
                    output,
                )
            else:
                logger.info("한자 프레임 자동 생성 완료 U+%04X", codepoint)
        except Exception as ex:
            logger.warning("한자 프레임 자동 생성 예외 U+%04X: %s", codepoint, ex)

    def reset(self) -> None:
        self.set_text("", play_speed=1.0)

    def has_data(self) -> bool:
        return bool(self._clips)

    def update(self, dt_sec: float) -> None:
        if not self._playing or not self._clips:
            return
        if self._clip_index >= len(self._clips):
            self._playing = False
            return
        self._clip_elapsed += max(0.0, float(dt_sec))
        while self._clip_index < len(self._clips):
            clip = self._clips[self._clip_index]
            duration = self._clip_duration(clip)
            if duration <= 1e-9 or self._clip_elapsed < duration:
                break
            self._clip_elapsed -= duration
            self._clip_index += 1
        if self._clip_index >= len(self._clips):
            self._playing = False

    def draw(self, screen: pygame.Surface, rect: pygame.Rect) -> bool:
        if not self._clips or self._clip_index >= len(self._clips):
            return False
        visible_count = min(self._MAX_VISIBLE_CHARS, len(self._clips))
        if visible_count <= 0:
            return False

        pad_x = max(6, int(rect.width * 0.03))
        gap = max(4, int(rect.width * 0.015))
        inner_w = max(1, rect.width - pad_x * 2 - gap * (visible_count - 1))
        cell_w = max(1, inner_w // visible_count)
        cell_h = max(1, rect.height - 12)
        drawn = False

        for i in range(visible_count):
            clip = self._clips[i]
            if not clip.frame_paths:
                continue

            if i < self._clip_index:
                # 완료된 글자는 마지막 프레임 고정 표시
                frame_idx = len(clip.frame_paths) - 1
            elif i == self._clip_index:
                fps = max(1e-6, clip.fps * self._play_speed)
                frame_idx = int(self._clip_elapsed * fps)
                frame_idx = max(0, min(frame_idx, len(clip.frame_paths) - 1))
            else:
                # 아직 시작 전 글자는 첫 프레임 표시
                frame_idx = 0

            cell_rect = pygame.Rect(rect.x + pad_x + i * (cell_w + gap), rect.y + 6, cell_w, cell_h)
            surf = self._load_surface(clip.frame_paths[frame_idx], cell_rect.size)
            if surf is None:
                continue
            x = cell_rect.x + (cell_rect.width - surf.get_width()) // 2
            y = cell_rect.y + (cell_rect.height - surf.get_height()) // 2
            screen.blit(surf, (x, y))
            drawn = True

        return drawn

    def _clip_duration(self, clip: _SequenceClip) -> float:
        if clip.fps <= 1e-9 or not clip.frame_paths:
            return 0.0
        return len(clip.frame_paths) / clip.fps

    def _load_clip(self, codepoint: int) -> _SequenceClip | None:
        base = self._frames_root / str(codepoint)
        if not base.exists():
            return None
        fps = 30.0
        frames: list[Path] = []
        meta_path = base / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                fps = float(meta.get("fps", 30.0) or 30.0)
                listed = meta.get("frames") or []
                if isinstance(listed, list):
                    for name in listed:
                        p = base / str(name)
                        if p.exists():
                            frames.append(p)
            except Exception:
                pass
        if not frames:
            frames = sorted(base.glob("*.png"))
        if not frames:
            return None
        return _SequenceClip(codepoint=codepoint, fps=max(1.0, fps), frame_paths=frames)

    def _load_surface(self, path: Path, target_size: tuple[int, int]) -> pygame.Surface | None:
        tw, th = target_size
        if tw <= 0 or th <= 0:
            return None
        key = (str(path), tw, th)
        cached = self._surface_cache.get(key)
        if cached is not None:
            return cached
        try:
            loaded = pygame.image.load(str(path))
            # display surface가 아직 없으면 convert_alpha가 실패할 수 있어 안전 분기
            if pygame.display.get_surface() is not None:
                raw = loaded.convert_alpha()
            else:
                raw = loaded
        except Exception:
            return None
        rw, rh = raw.get_size()
        if rw <= 0 or rh <= 0:
            return None
        scale = min(tw / rw, th / rh, 1.0)
        nw = max(1, int(round(rw * scale)))
        nh = max(1, int(round(rh * scale)))
        if (nw, nh) != (rw, rh):
            if hasattr(pygame.transform, "smoothscale"):
                surf = pygame.transform.smoothscale(raw, (nw, nh))
            else:
                surf = pygame.transform.scale(raw, (nw, nh))
        else:
            surf = raw
        self._surface_cache[key] = surf
        return surf
