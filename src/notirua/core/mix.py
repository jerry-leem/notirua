"""Mix chosen instruments back into one audio file (0.4.0, ROADMAP).

Separated instruments are added as they are (nothing is subtracted from the
original). The sum is turned down only when its peak would pass -1 dBFS.
Pure functions except :func:`write_audio`, which encodes with PyAV.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from pathlib import Path

import numpy as np

from notirua.core.decode import CHANNELS, SAMPLE_RATE, AudioArray, write_wav
from notirua.core.model import STEMS
from notirua.core.progress import CancelToken
from notirua.i18n import N_

PEAK_LIMIT_DB = -1.0
PEAK_LIMIT = float(10 ** (PEAK_LIMIT_DB / 20))

# Format id -> (file suffix, PyAV container, encoder, bit rate). WAV is written directly.
FORMATS: dict[str, tuple[str, str, str, int]] = {
    "mp3": (".mp3", "mp3", "libmp3lame", 320_000),
    "m4a": (".m4a", "ipod", "aac", 256_000),
    "wav": (".wav", "wav", "pcm_s16le", 0),
}
DEFAULT_FORMAT = "mp3"
FORMAT_LABELS = {
    "mp3": N_("MP3 (smaller file)"),
    "m4a": N_("M4A (AAC)"),
    "wav": N_("WAV (no compression)"),
}
FORMAT_FILTERS = {
    "mp3": N_("MP3 file (*.mp3)"),
    "m4a": N_("M4A file (*.m4a)"),
    "wav": N_("WAV file (*.wav)"),
}

# File names (ROADMAP): "<title> - MR", "<title> - <list> 제외", "<title> - <list>".
NAME_WITHOUT_VOCALS = N_("{title} - backing track")
NAME_WITHOUT = N_("{title} - without {instruments}")
NAME_ONLY = N_("{title} - {instruments}")
NAME_ALL = N_("{title} - all instruments")
LIST_PAIR = N_("{first}, {second}")

ENCODE_BLOCK = SAMPLE_RATE * 10


def mix_stems(stems: Mapping[str, AudioArray], include: Collection[str]) -> AudioArray:
    """Sum the chosen instruments; scale the whole mix down if it would clip.

    Raises ``ValueError`` when nothing is chosen or a chosen instrument is missing.
    """
    chosen = [s for s in STEMS if s in include]
    if not chosen or len(chosen) != len(set(include)):
        raise ValueError(f"choose at least one known instrument, got {sorted(include)}")
    missing = [s for s in chosen if s not in stems]
    if missing:
        raise ValueError(f"not separated: {missing}")
    length = max(stems[s].shape[1] for s in chosen)
    mix = np.zeros((CHANNELS, length), dtype=np.float32)
    for s in chosen:
        audio = stems[s]
        mix[:, : audio.shape[1]] += audio.astype(np.float32, copy=False)
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > PEAK_LIMIT:
        mix *= PEAK_LIMIT / peak
    return mix


def join_names(names: Sequence[str], gettext_fn: Callable[[str], str]) -> str:
    """Join translated names with the language's own list pattern."""
    if not names:
        return ""
    joined = names[0]
    for name in names[1:]:
        joined = gettext_fn(LIST_PAIR).format(first=joined, second=name)
    return joined


def mix_name(
    title: str,
    include: Collection[str],
    available: Collection[str],
    gettext_fn: Callable[[str], str],
    instrument_names: Mapping[str, str],
) -> str:
    """A file name (without suffix) that says what the mix holds.

    ``available`` are the instruments that have sound; silent ones do not count
    as left out. Names come from ``instrument_names`` (message ids) in order.
    """
    have = [s for s in STEMS if s in available or s in include]
    kept = [s for s in have if s in include]
    left = [s for s in have if s not in include]

    def names(stems: list[str]) -> str:
        return join_names([gettext_fn(instrument_names[s]) for s in stems], gettext_fn)

    if not left:
        return gettext_fn(NAME_ALL).format(title=title)
    if left == ["vocals"]:
        return gettext_fn(NAME_WITHOUT_VOCALS).format(title=title)
    if len(left) < len(kept):
        return gettext_fn(NAME_WITHOUT).format(title=title, instruments=names(left))
    return gettext_fn(NAME_ONLY).format(title=title, instruments=names(kept))


def available_formats() -> list[str]:
    """Formats this build can write (MP3 needs FFmpeg built with LAME)."""
    import av

    found = []
    for fmt, (_suffix, container, encoder, _rate) in FORMATS.items():
        if fmt == "wav":
            found.append(fmt)
            continue
        try:
            av.codec.Codec(encoder, "w")
        except (av.error.FFmpegError, ValueError):
            continue
        if container in av.formats_available:
            found.append(fmt)
    return found


def write_audio(
    path: Path,
    audio: AudioArray,
    fmt: str,
    progress: Callable[[float], None] | None = None,
    cancel: CancelToken | None = None,
    bit_rate: int | None = None,
    tags: Mapping[str, str] | None = None,
) -> Path:
    """Encode ``audio`` (float, ``(2, n)`` at 44.1 kHz) as ``fmt`` to ``path``.

    ``bit_rate`` (bits per second) replaces the format's default for lossy formats;
    ``tags`` (for example ``{"title": ...}``) go into the file's metadata.
    """
    if fmt not in FORMATS:
        raise ValueError(f"unknown format: {fmt}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "wav":
        write_wav(path, audio)
        if progress is not None:
            progress(1.0)
        return path
    import av

    _suffix, container_name, encoder, default_rate = FORMATS[fmt]
    bit_rate = bit_rate or default_rate
    tmp = path.with_name(f".{path.name}.part")
    total = audio.shape[1]
    try:
        with tmp.open("wb") as fp, av.open(fp, "w", format=container_name) as out:
            stream = out.add_stream(encoder, rate=SAMPLE_RATE)
            assert isinstance(stream, av.audio.stream.AudioStream)
            stream.layout = "stereo"
            stream.bit_rate = bit_rate
            for key, value in (tags or {}).items():
                out.metadata[key] = value
            for start in range(0, total, ENCODE_BLOCK):
                if cancel is not None:
                    cancel.raise_if_cancelled()
                block = np.ascontiguousarray(
                    np.clip(audio[:, start : start + ENCODE_BLOCK], -1.0, 1.0), dtype=np.float32
                )
                frame = av.AudioFrame.from_ndarray(block, format="fltp", layout="stereo")
                frame.sample_rate = SAMPLE_RATE
                frame.pts = start
                for packet in stream.encode(frame):
                    out.mux(packet)
                if progress is not None:
                    progress(min(1.0, (start + block.shape[1]) / max(1, total)))
            for packet in stream.encode(None):
                out.mux(packet)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return path
