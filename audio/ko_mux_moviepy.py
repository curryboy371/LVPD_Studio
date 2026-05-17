"""
베이스 영상 + 한국어 TTS 합성 오디오 + 동기 자막(TextClip 또는 PIL 폴백) MoviePy mux.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from audio.ko_narration import KoNarrationPlan, load_ko_narration_plan_from_json

logger = logging.getLogger(__name__)


def _repo_font_path() -> Optional[str]:
    from core.paths import DEFAULT_FONT_DIR, FONT_KR_FILENAME

    p = DEFAULT_FONT_DIR / FONT_KR_FILENAME
    return str(p) if p.is_file() else None


def _make_text_clip_pil(
    text: str,
    *,
    width: int,
    height: int,
    font_path: Optional[str],
    fontsize: int,
    duration: float,
    start: float,
) -> Any:
    """ImageMagick 없을 때 PIL ImageClip 폴백."""
    from PIL import Image, ImageDraw, ImageFont
    from moviepy.editor import ImageClip

    font_size = max(18, int(fontsize))
    try:
        if font_path and os.path.isfile(font_path):
            font = ImageFont.truetype(font_path, font_size)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    lines = [text]
    pad = 16
    dummy = Image.new("RGBA", (width, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)
    line_heights = []
    max_w = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        max_w = max(max_w, lw)
        line_heights.append(lh)
    img_h = sum(line_heights) + pad * 2 + max(0, len(lines) - 1) * 8
    img_w = min(width, max_w + pad * 2)
    from studio.shorts.constants import KO_SUBTITLE_BG_RGBA

    img = Image.new("RGBA", (img_w, img_h), KO_SUBTITLE_BG_RGBA)
    draw = ImageDraw.Draw(img)
    y = pad
    for line in lines:
        draw.text((pad, y), line, font=font, fill=(255, 240, 180, 255))
        bbox = draw.textbbox((0, 0), line, font=font)
        y += (bbox[3] - bbox[1]) + 8

    import numpy as np

    arr = np.array(img)
    clip = ImageClip(arr).set_duration(max(0.05, float(duration)))
    clip = clip.set_start(max(0.0, float(start)))
    from studio.shorts.constants import shorts_ko_subtitle_below_video_gap
    from studio.shorts.layout import ShortsLayoutZones, compute_contain_frame_rect

    zones = ShortsLayoutZones.from_frame(width, height)
    frame_rect = compute_contain_frame_rect(zones.middle, (width, height))
    y_pos = frame_rect.bottom + shorts_ko_subtitle_below_video_gap(height)
    clip = clip.set_position(("center", max(0, y_pos)))
    return clip


def _make_subtitle_clip(
    text: str,
    *,
    video_w: int,
    video_h: int,
    font_path: Optional[str],
    fontsize: int,
    duration: float,
    start: float,
) -> Any:
    try:
        from moviepy.editor import TextClip

        kwargs: dict[str, Any] = {
            "txt": text,
            "fontsize": fontsize,
            "color": "white",
            "stroke_color": "black",
            "stroke_width": 1,
            "method": "caption",
            "size": (int(video_w * 0.9), None),
        }
        if font_path:
            kwargs["font"] = font_path
        clip = TextClip(**kwargs)
        clip = clip.set_duration(max(0.05, float(duration)))
        clip = clip.set_start(max(0.0, float(start)))
        from studio.shorts.constants import shorts_ko_subtitle_below_video_gap
        from studio.shorts.layout import ShortsLayoutZones, compute_contain_frame_rect

        zones = ShortsLayoutZones.from_frame(video_w, video_h)
        frame_rect = compute_contain_frame_rect(zones.middle, (video_w, video_h))
        y_pos = frame_rect.bottom + shorts_ko_subtitle_below_video_gap(video_h)
        clip = clip.set_position(("center", max(0, y_pos)))
        return clip
    except Exception as ex:
        logger.debug("TextClip 실패, PIL 폴백: %s", ex)
        return _make_text_clip_pil(
            text,
            width=video_w,
            height=video_h,
            font_path=font_path,
            fontsize=fontsize,
            duration=duration,
            start=start,
        )


def mux_ko_narration_on_video(
    video_path: str | Path,
    plan: KoNarrationPlan,
    output_path: str | Path,
    *,
    keep_base_audio: bool = True,
    fontsize: int = 0,
) -> str:
    """베이스 영상에 TTS·자막을 합성해 저장."""
    from moviepy.editor import AudioFileClip, CompositeAudioClip, CompositeVideoClip, VideoFileClip

    video_path = Path(video_path)
    output_path = Path(output_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"영상 없음: {video_path}")
    if not plan.cues:
        raise ValueError("내레이션 큐 없음")

    ko_audio_path = str(plan.composite_audio_path or "").strip()
    if not ko_audio_path or not os.path.isfile(ko_audio_path):
        raise FileNotFoundError(f"합성 TTS 오디오 없음: {ko_audio_path}")

    from studio.shorts.constants import shorts_ko_subtitle_font_size

    font_path = _repo_font_path()
    video = VideoFileClip(str(video_path))
    fs = int(fontsize) if int(fontsize) > 0 else shorts_ko_subtitle_font_size(int(video.h))
    overlays = []
    try:
        for cue in plan.cues:
            dur = max(0.05, cue.end_sec - cue.start_sec)
            overlays.append(
                _make_subtitle_clip(
                    cue.text,
                    video_w=int(video.w),
                    video_h=int(video.h),
                    font_path=font_path,
                    fontsize=fs,
                    duration=dur,
                    start=cue.start_sec,
                )
            )

        ko_audio = AudioFileClip(ko_audio_path)
        if keep_base_audio and video.audio is not None:
            mixed = CompositeAudioClip([video.audio, ko_audio])
        else:
            mixed = ko_audio

        final = CompositeVideoClip([video, *overlays])
        final = final.set_audio(mixed)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        final.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )
        final.close()
        ko_audio.close()
    finally:
        video.close()

    return str(output_path.resolve())


def mux_from_timeline_json(
    video_path: str | Path,
    timeline_json: str | Path,
    output_path: str | Path,
    **kwargs: Any,
) -> str:
    plan = load_ko_narration_plan_from_json(timeline_json)
    if plan is None:
        raise ValueError(f"timeline JSON 로드 실패: {timeline_json}")
    return mux_ko_narration_on_video(video_path, plan, output_path, **kwargs)
