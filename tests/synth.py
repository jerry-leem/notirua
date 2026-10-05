"""Synthesized audio fixtures. No recorded audio is committed (SPEC 9.1)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt

SR = 44_100

C_MAJOR_SCALE = [60, 62, 64, 65, 67, 69, 71, 72]


def midi_to_hz(pitch: float) -> float:
    return float(440.0 * 2.0 ** ((pitch - 69) / 12.0))


def tone(pitch: int, seconds: float, sr: int = SR, harmonics: int = 4) -> npt.NDArray[np.float32]:
    """A harmonic tone with a short attack and exponential decay."""
    t = np.arange(int(seconds * sr)) / sr
    f0 = midi_to_hz(pitch)
    wave = np.zeros_like(t)
    for h in range(1, harmonics + 1):
        if f0 * h < sr / 2:
            wave += np.sin(2 * np.pi * f0 * h * t) / h
    attack = np.minimum(1.0, t / 0.01)
    release = np.minimum(1.0, (seconds - t) / 0.02).clip(0, 1)
    envelope = attack * release * np.exp(-1.5 * t)
    return (0.3 * wave * envelope).astype(np.float32)


def karplus_strong(
    pitch: int, seconds: float, sr: int = SR, seed: int = 0
) -> npt.NDArray[np.float32]:
    """Plucked-string synthesis for guitar/bass fixtures."""
    rng = np.random.default_rng(seed)
    period = max(2, round(sr / midi_to_hz(pitch)))
    buf = rng.uniform(-1, 1, period)
    out = np.empty(int(seconds * sr), dtype=np.float32)
    for i in range(out.size):
        out[i] = buf[i % period]
        buf[i % period] = 0.996 * 0.5 * (buf[i % period] + buf[(i + 1) % period])
    return (0.4 * out).astype(np.float32)


def render_notes(
    notes: Sequence[tuple[float, float, int]],
    total_s: float | None = None,
    sr: int = SR,
    plucked: bool = False,
) -> npt.NDArray[np.float32]:
    """Render ``(start_s, duration_s, pitch)`` notes into mono audio."""
    end = max(s + d for s, d, _ in notes) + 0.5
    n = int((total_s or end) * sr)
    out = np.zeros(n, dtype=np.float32)
    for i, (start, dur, pitch) in enumerate(notes):
        seg = karplus_strong(pitch, dur, sr, seed=i) if plucked else tone(pitch, dur, sr)
        a = int(start * sr)
        b = min(n, a + seg.size)
        out[a:b] += seg[: b - a]
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * 0.8).astype(np.float32)


def scale_notes(
    bpm: float = 120.0, pitches: Sequence[int] = C_MAJOR_SCALE, lead_in_beats: int = 2
) -> list[tuple[float, float, int]]:
    """Quarter notes at ``bpm`` after a short lead-in."""
    beat = 60.0 / bpm
    return [((lead_in_beats + i) * beat, beat * 0.9, p) for i, p in enumerate(pitches)]


def click_track(bpm: float, seconds: float, sr: int = SR) -> npt.NDArray[np.float32]:
    """Short noise bursts on every beat (useful for beat-tracking tests)."""
    out = np.zeros(int(seconds * sr), dtype=np.float32)
    rng = np.random.default_rng(1)
    beat = 60.0 / bpm
    burst = (
        rng.uniform(-1, 1, int(0.02 * sr)) * np.exp(-np.linspace(0, 8, int(0.02 * sr)))
    ).astype(np.float32)
    t = 0.0
    while t < seconds - 0.05:
        a = int(t * sr)
        out[a : a + burst.size] += 0.6 * burst
        t += beat
    return out


def to_stereo(mono: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    return np.stack([mono, mono]).astype(np.float32)


def write_wav(path: Path, audio: npt.NDArray[np.float32], sr: int = SR) -> Path:
    from notirua.core.decode import write_wav as _write

    if audio.ndim == 1:
        audio = to_stereo(audio)
    _write(path, audio, sr)
    return path


_FORMATS: dict[str, tuple[str, str, str]] = {
    # suffix: (container format, codec, sample format)
    "m4a": ("ipod", "aac", "fltp"),
    "alac.m4a": ("ipod", "alac", "s16p"),
    "mp4": ("mp4", "aac", "fltp"),
    "mp3": ("mp3", "libmp3lame", "fltp"),
    "flac": ("flac", "flac", "s16"),
    "opus": ("ogg", "libopus", "flt"),
    "aiff": ("aiff", "pcm_s16be", "s16"),
}


def encode(
    path: Path, audio: npt.NDArray[np.float32], kind: str, sr: int = SR, title: str | None = None
) -> Path:
    """Encode stereo float audio with PyAV into ``kind`` (see ``_FORMATS``)."""
    import av

    fmt, codec, sample_fmt = _FORMATS[kind]
    if audio.ndim == 1:
        audio = to_stereo(audio)
    rate = 48_000 if codec == "libopus" else sr
    if rate != sr:
        import soxr

        audio = soxr.resample(audio.T, sr, rate).T.astype(np.float32)
    with av.open(str(path), mode="w", format=fmt) as container:
        if title:
            container.metadata["title"] = title
        stream = container.add_stream(codec, rate=rate)
        stream.layout = "stereo"
        stream.format = sample_fmt
        frame_size = 1024
        for start in range(0, audio.shape[1], frame_size):
            block = audio[:, start : start + frame_size]
            if sample_fmt.startswith("s16"):
                data = (np.clip(block, -1, 1) * 32767).astype(np.int16)
            else:
                data = block.astype(np.float32)
            if not sample_fmt.endswith("p"):
                data = np.ascontiguousarray(data.T).reshape(1, -1)
            frame = av.AudioFrame.from_ndarray(
                np.ascontiguousarray(data), format=sample_fmt, layout="stereo"
            )
            frame.sample_rate = rate
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return path
