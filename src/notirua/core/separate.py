"""Source separation (FR-2) behind a replaceable :class:`Separator` protocol (SPEC 5.5).

:class:`DemucsOnnxSeparator` runs the ``htdemucs_6s`` ONNX export from
demucs-onnx (MIT). The overlap-add loop follows ``demucs_onnx.inference``
(_chunked_separate_single) but lives here so we control downloads, progress,
and cancellation, and avoid the package's Hugging Face Hub dependency.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from notirua.core.decode import SAMPLE_RATE, AudioArray
from notirua.core.progress import CancelToken

log = logging.getLogger(__name__)

HTDEMUCS_6S_SOURCES: tuple[str, ...] = ("drums", "bass", "other", "vocals", "guitar", "piano")
SEGMENT_S = 7.8
N_SAMPLES = int(SEGMENT_S * SAMPLE_RATE)  # 343,980 — fixed input length of the export
SILENCE_RMS_DB = -45.0


def default_accelerate() -> bool:
    """DirectML on Windows only. On macOS, CoreML cannot compile this export
    (NeuralNetwork format) or runs ~100x slower than CPU (MLProgram); see
    docs/DECISIONS.md, M0-S2."""
    return sys.platform == "win32"


class Separator(Protocol):
    sources: tuple[str, ...]

    def separate(
        self,
        audio: AudioArray,
        progress: Callable[[float], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> dict[str, AudioArray]: ...


def transition_window(segment: int, overlap_frac: float = 0.25) -> AudioArray:
    transition = int(segment * overlap_frac)
    window = np.ones(segment, dtype=np.float32)
    fade = np.linspace(0, 1, transition, dtype=np.float32)
    window[:transition] = fade
    window[-transition:] = fade[::-1]
    return window


class DemucsOnnxSeparator:
    sources = HTDEMUCS_6S_SOURCES

    def __init__(self, model_path: Path, accelerate: bool | None = None) -> None:
        from notirua.core.runtime import make_session

        self.model_path = model_path
        if accelerate is None:
            accelerate = default_accelerate()
        self._session: Any = make_session(model_path, accelerate=accelerate, low_memory=True)
        self.providers: list[str] = list(self._session.get_providers())

    def separate(
        self,
        audio: AudioArray,
        progress: Callable[[float], None] | None = None,
        cancel: CancelToken | None = None,
        wanted: Sequence[str] | None = None,
    ) -> dict[str, AudioArray]:
        from notirua.core.runtime import run_with_fallback

        if audio.ndim != 2 or audio.shape[0] != 2:
            raise ValueError(f"expected (2, samples), got {audio.shape}")
        keep = list(wanted) if wanted else list(self.sources)
        total = audio.shape[1]
        overlap = N_SAMPLES // 4
        stride = N_SAMPLES - overlap
        n_chunks = max(1, (total + stride - 1) // stride)
        window = transition_window(N_SAMPLES)
        out = {s: np.zeros((2, total), dtype=np.float32) for s in keep}
        weight = np.zeros(total, dtype=np.float32)
        for i in range(n_chunks):
            if cancel is not None:
                cancel.raise_if_cancelled()
            start = i * stride
            end = min(start + N_SAMPLES, total)
            chunk = audio[:, start:end]
            if chunk.shape[1] < N_SAMPLES:
                chunk = np.pad(chunk, ((0, 0), (0, N_SAMPLES - chunk.shape[1])))
            x = chunk[np.newaxis, ...].astype(np.float32, copy=False)
            length = end - start
            w = window[:length]
            self._session, results = run_with_fallback(
                self._session, self.model_path, ["stems"], {"mix": x}
            )
            stems = results[0][0]  # (S, 2, N)
            for s in keep:
                out[s][:, start:end] += stems[self.sources.index(s), :, :length] * w
            weight[start:end] += w
            if progress is not None:
                progress((i + 1) / n_chunks)
        weight = np.maximum(weight, 1e-8)
        for s in out:
            out[s] /= weight
        return out


def rms_db(audio: AudioArray) -> float:
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64)))) if audio.size else 0.0
    return float(20.0 * np.log10(max(rms, 1e-10)))


def is_silent(audio: AudioArray, threshold_db: float = SILENCE_RMS_DB) -> bool:
    """FR-2: stems below the RMS threshold are marked silent and skipped."""
    return rms_db(audio) < threshold_db


def noise_gate(
    audio: AudioArray,
    sample_rate: int = SAMPLE_RATE,
    relative_db: float = -40.0,
    floor_db: float = -55.0,
    frame_s: float = 0.025,
) -> AudioArray:
    """Silence separation residue before transcription.

    The separator leaves faint (~-60 dB) bleed where an instrument is silent.
    Basic Pitch normalises its input, so that bleed would be heard as loud
    notes. Frames quieter than ``relative_db`` below the stem's loud level (or
    ``floor_db`` absolute) are muted with short ramps so no clicks are added.
    """
    if audio.size == 0:
        return audio
    frame = max(1, int(frame_s * sample_rate))
    mono = audio.mean(axis=0) if audio.ndim == 2 else audio
    n_frames = int(np.ceil(mono.size / frame))
    padded = np.zeros(n_frames * frame, dtype=np.float32)
    padded[: mono.size] = mono
    rms = np.sqrt(np.mean(padded.reshape(n_frames, frame) ** 2, axis=1) + 1e-20)
    level_db = 20 * np.log10(rms)
    loud = float(np.percentile(level_db, 95))
    threshold = max(floor_db, loud + relative_db)
    keep = (level_db >= threshold).astype(np.float32)
    # Hold open for a few frames so note tails are not chopped, then ramp.
    hold = np.convolve(keep, np.ones(5, dtype=np.float32), mode="same") > 0
    gain = np.convolve(hold.astype(np.float32), np.ones(3, dtype=np.float32) / 3, mode="same")
    envelope = np.repeat(gain, frame)[: mono.size]
    result: AudioArray = (audio * envelope).astype(np.float32)
    return result
