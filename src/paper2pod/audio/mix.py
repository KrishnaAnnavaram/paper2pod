"""Mixing of PCM16 mono clips: per-clip loudness normalisation, pauses, chapters, WAV output.

Uses numpy when it is installed (``paper2pod[fast]``) and falls back to the standard library.
"""
from __future__ import annotations

import math
import sys
import wave
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import MissingDependency

try:  # optional speed-up
    import numpy as _np
except ImportError:  # pragma: no cover - exercised when numpy is absent
    _np = None

FULL_SCALE = 32768.0


def _samples(pcm: bytes) -> array:
    data = array("h")
    data.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if sys.byteorder == "big":
        data.byteswap()
    return data


def _to_bytes(data: array) -> bytes:
    if sys.byteorder == "big":
        data = array("h", data)
        data.byteswap()
    return data.tobytes()


def rms_and_peak(pcm: bytes) -> tuple[float, float]:
    """Return (RMS, peak) of PCM16 audio, both scaled to 0..1."""
    if len(pcm) < 2:
        return 0.0, 0.0
    if _np is not None:
        x = _np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype="<i2").astype(_np.float64) / FULL_SCALE
        return float(_np.sqrt(_np.mean(x * x))), float(_np.max(_np.abs(x)))
    data = _samples(pcm)
    total = sum(s * s for s in data)
    return math.sqrt(total / len(data)) / FULL_SCALE, max(abs(min(data)), max(data)) / FULL_SCALE


def normalize_loudness(pcm: bytes, target_dbfs: float = -20.0, peak_ceiling: float = 0.95) -> bytes:
    """Scale a clip to a target RMS level without letting its peak exceed ``peak_ceiling``."""
    rms, peak = rms_and_peak(pcm)
    if rms <= 0 or peak <= 0:
        return pcm
    gain = min(10 ** (target_dbfs / 20) / rms, peak_ceiling / peak)
    if _np is not None:
        x = _np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype="<i2").astype(_np.float64) * gain
        return _np.clip(_np.round(x), -32768, 32767).astype("<i2").tobytes()
    data = _samples(pcm)
    scaled = array("h", (max(-32768, min(32767, int(round(s * gain)))) for s in data))
    return _to_bytes(scaled)


def silence(ms: int, sample_rate: int) -> bytes:
    return b"\x00\x00" * int(sample_rate * ms / 1000)


@dataclass
class Chapter:
    title: str
    start_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def mix_clips(clips: list[tuple[int, bytes]], segment_titles: list[str], sample_rate: int,
              pause_ms: int = 300, normalize: bool = True) -> tuple[bytes, list[Chapter]]:
    """Concatenate ``(segment index, pcm)`` clips in order with pauses; one chapter per segment."""
    out = bytearray()
    chapters: list[Chapter] = []
    current = None
    for segment, pcm in clips:
        if segment != current:
            if out:
                out += silence(pause_ms * 2, sample_rate)  # a slightly longer breath between segments
            title = segment_titles[segment] if 0 <= segment < len(segment_titles) else f"Part {segment + 1}"
            chapters.append(Chapter(title, round(len(out) / 2 / sample_rate, 2)))
            current = segment
        elif out:
            out += silence(pause_ms, sample_rate)
        out += normalize_loudness(pcm) if normalize else pcm
    return bytes(out), chapters


def write_wav(path: Path, pcm: bytes, sample_rate: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return path


def wav_duration(path: Path) -> float:
    """Measured duration of a WAV file in seconds."""
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())


def export_mp3(wav_path: Path, mp3_path: Path, bitrate: str = "128k") -> Path:
    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise MissingDependency("pydub", "mp3") from exc
    AudioSegment.from_wav(str(wav_path)).export(str(mp3_path), format="mp3", bitrate=bitrate)
    return Path(mp3_path)
