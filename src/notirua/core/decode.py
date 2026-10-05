"""Audio decoding via PyAV (FR-1).

Streams are detected from content, not file extensions. Files are opened
through Python file objects so non-ASCII paths work on every OS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from notirua.core.errors import (
    CorruptFileError,
    DecodeError,
    DrmProtectedError,
    MultipleAudioTracksError,
    NoAudioTrackError,
    TooLongError,
)
from notirua.core.progress import CancelToken

log = logging.getLogger(__name__)

SAMPLE_RATE = 44_100
CHANNELS = 2
MAX_DURATION_S = 15 * 60

_DRM_CODEC_TAGS = {"drms", "drmi", "p608", "enca", "encv"}
_DRM_HINTS = ("drm", "encrypted", "fairplay", "decryption")

AudioArray = npt.NDArray[np.float32]


@dataclass(frozen=True)
class AudioStreamInfo:
    index: int
    codec: str
    channels: int
    sample_rate: int
    language: str | None


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    duration_s: float
    streams: list[AudioStreamInfo]
    title: str | None
    container: str


def _open(path: Path) -> Any:
    import av

    try:
        fp = path.open("rb")
    except FileNotFoundError as exc:
        raise DecodeError(f"file not found: {path}") from exc
    try:
        return av.open(fp, mode="r", metadata_errors="ignore")
    except av.error.InvalidDataError as exc:
        fp.close()
        _raise_for_message(str(exc))
        raise CorruptFileError(str(exc)) from exc
    except av.error.FFmpegError as exc:
        fp.close()
        _raise_for_message(str(exc))
        raise DecodeError(str(exc)) from exc


def _raise_for_message(message: str) -> None:
    lowered = message.lower()
    if any(hint in lowered for hint in _DRM_HINTS):
        raise DrmProtectedError(message)


def _is_drm_stream(stream: Any) -> bool:
    tag = str(getattr(stream.codec_context, "codec_tag", "") or "").strip().lower()
    if tag in _DRM_CODEC_TAGS:
        return True
    name = str(getattr(stream.codec_context, "name", "") or "").lower()
    return name in ("none", "") and tag != ""


def probe(path: Path) -> AudioInfo:
    """Inspect a file without decoding it."""
    container = _open(path)
    try:
        streams: list[AudioStreamInfo] = []
        for stream in container.streams.audio:
            if _is_drm_stream(stream):
                raise DrmProtectedError(f"protected audio stream #{stream.index}")
            ctx = stream.codec_context
            streams.append(
                AudioStreamInfo(
                    index=stream.index,
                    codec=str(ctx.name),
                    channels=int(ctx.channels or 0),
                    sample_rate=int(ctx.sample_rate or 0),
                    language=stream.metadata.get("language"),
                )
            )
        if not streams:
            raise NoAudioTrackError(f"no audio stream in {path.name}")
        duration = float(container.duration or 0) / 1_000_000.0
        if duration <= 0:
            first = container.streams.audio[0]
            if first.duration and first.time_base:
                duration = float(first.duration * first.time_base)
        metadata = {k.lower(): v for k, v in (container.metadata or {}).items()}
        title = metadata.get("title") or None
        return AudioInfo(
            path=path,
            duration_s=duration,
            streams=streams,
            title=title.strip() if title else None,
            container=str(container.format.name),
        )
    finally:
        container.close()


def decode(
    path: Path,
    *,
    stream_index: int | None = None,
    start_s: float | None = None,
    end_s: float | None = None,
    max_duration_s: float = MAX_DURATION_S,
    progress: Any = None,
    cancel: CancelToken | None = None,
) -> AudioArray:
    """Decode to float32 stereo at 44.1 kHz, shape ``(2, n_samples)``.

    ``progress`` is an optional ``fraction -> None`` callable.
    """
    import av

    info = probe(path)
    if stream_index is None:
        if len(info.streams) > 1:
            raise MultipleAudioTracksError(count=len(info.streams))
        stream_index = info.streams[0].index
    begin = max(0.0, start_s or 0.0)
    finish = end_s if end_s is not None else info.duration_s
    if finish - begin > max_duration_s + 0.5:
        raise TooLongError(limit=int(max_duration_s // 60))

    container = _open(path)
    try:
        stream = next(s for s in container.streams.audio if s.index == stream_index)
        if begin > 0 and stream.time_base:
            container.seek(int(begin / float(stream.time_base)), stream=stream, backward=True)
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=SAMPLE_RATE)
        chunks: list[AudioArray] = []
        total_expected = max(1.0, (finish - begin) * SAMPLE_RATE)
        produced = 0
        first_time: float | None = None
        try:
            for frame in container.decode(stream):
                if cancel is not None:
                    cancel.raise_if_cancelled()
                if first_time is None and frame.time is not None:
                    first_time = float(frame.time)
                for out in resampler.resample(frame):
                    arr = out.to_ndarray().astype(np.float32, copy=False)
                    chunks.append(arr)
                    produced += arr.shape[1]
                if progress is not None:
                    progress(min(1.0, produced / total_expected))
                if end_s is not None and produced / SAMPLE_RATE >= (end_s - begin) + 1.0:
                    break
            for out in resampler.resample(None):
                chunks.append(out.to_ndarray().astype(np.float32, copy=False))
        except av.error.FFmpegError as exc:
            _raise_for_message(str(exc))
            if not chunks:
                raise CorruptFileError(str(exc)) from exc
            log.warning("decode stopped early after %d samples: %s", produced, exc)
    finally:
        container.close()

    if not chunks:
        raise CorruptFileError("no audio frames decoded")
    audio = np.concatenate(chunks, axis=1)
    # Trim to the requested window (seeking lands on the previous keyframe).
    offset = 0
    if begin > 0 and first_time is not None:
        offset = max(0, round((begin - first_time) * SAMPLE_RATE))
    stop = None if end_s is None else offset + round((end_s - begin) * SAMPLE_RATE)
    audio = audio[:, offset:stop]
    if not np.all(np.isfinite(audio)):
        audio = np.nan_to_num(audio, copy=False)
    if progress is not None:
        progress(1.0)
    return np.ascontiguousarray(audio, dtype=np.float32)


def write_wav(path: Path, audio: AudioArray, sample_rate: int = SAMPLE_RATE) -> None:
    """Write float audio ``(channels, n)`` as 16-bit PCM WAV."""
    import wave

    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped.T * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(audio.shape[0])
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
