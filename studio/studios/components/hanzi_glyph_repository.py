"""
한자 획 데이터 저장소.

단일 소스:
- resource/svgs/{codepoint}.svg (예: 11904.svg)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from core.paths import get_repo_root
from .svg_path_parser import Point, parse_svg_path_to_polyline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HanziGlyph:
    character: str
    strokes: tuple[str, ...]
    polylines: tuple[tuple[Point, ...], ...]


class HanziGlyphRepository:
    """`character` 기준으로 glyph를 조회하는 저장소."""

    def __init__(self, graphics_txt_path: Path | None = None) -> None:
        root = get_repo_root()
        self._svg_dir = root / "resource" / "svgs"
        _ = graphics_txt_path
        self._glyph_map: dict[str, HanziGlyph] = {}
        self._loaded: bool = True

    def load(self) -> None:
        # SVG 파일 직접 조회 방식만 사용한다.
        return

    def get(self, character: str) -> HanziGlyph | None:
        key = (character or "").strip()
        if not key:
            return None
        cached = self._glyph_map.get(key)
        if cached is not None:
            return cached

        # SVG 파일 사용: resource/svgs/{ord(char)}.svg
        svg_glyph = self._load_from_svg_file(key)
        if svg_glyph is not None:
            self._glyph_map[key] = svg_glyph
            return svg_glyph
        return None

    def _load_from_svg_file(self, character: str) -> HanziGlyph | None:
        if len(character) != 1:
            return None
        code = ord(character)
        svg_path = self._svg_dir / f"{code}.svg"
        if not svg_path.exists():
            return None
        try:
            root = ET.parse(svg_path).getroot()
            polylines: list[tuple[Point, ...]] = []
            strokes: list[str] = []
            # make-me-a-hanzi 형식: id="make-me-a-hanzi-animation-{n}" path를 우선 사용
            for el in root.iter():
                tag = el.tag.split("}")[-1]
                if tag != "path":
                    continue
                pid = (el.attrib.get("id") or "").strip()
                if not pid.startswith("make-me-a-hanzi-animation-"):
                    continue
                d = (el.attrib.get("d") or "").strip()
                if not d:
                    continue
                pts = parse_svg_path_to_polyline(d)
                if len(pts) >= 2:
                    polylines.append(tuple(pts))
                    strokes.append(d)
            if not polylines:
                return None
            return HanziGlyph(character=character, strokes=tuple(strokes), polylines=tuple(polylines))
        except Exception as ex:
            logger.debug("SVG glyph 로드 실패 char=%s path=%s err=%s", character, svg_path, ex)
            return None
