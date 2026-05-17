# audio: 사운드 믹싱, TTS 및 비디오 오디오 합성

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "FFmpegAudioMixer":
        from audio.mixer import FFmpegAudioMixer

        return FFmpegAudioMixer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["FFmpegAudioMixer"]
