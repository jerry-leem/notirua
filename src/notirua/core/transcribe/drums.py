"""Rule-based drum transcription (SPEC 6.3). Results are for reference only.

Onsets are detected separately in three frequency bands so simultaneous hits
(kick + hi-hat) are both found. Each band's hits are then classified by
spectral balance and decay time and stored as General MIDI percussion numbers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt
import scipy.signal

from notirua.core.decode import AudioArray
from notirua.core.model import NoteEvent
from notirua.core.progress import CancelToken

KICK, SNARE, CLOSED_HAT, OPEN_HAT, LOW_TOM, MID_TOM, HIGH_TOM, CRASH, RIDE = (
    36,
    38,
    42,
    46,
    41,
    45,
    50,
    49,
    51,
)

N_FFT = 1024
HOP = 256

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class DrumSettings:
    delta: float = 1.2  # peak must exceed local median by this many std devs
    min_gap_s: float = 0.05
    open_hat_decay_s: float = 0.12
    crash_decay_s: float = 0.35
    tom_tonality: float = 0.35


class DrumTranscriber(Protocol):
    def transcribe(
        self,
        audio: AudioArray,
        sample_rate: int,
        progress: Callable[[float], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> list[NoteEvent]: ...


def _band_flux(mag: FloatArray, freqs: FloatArray, lo: float, hi: float) -> FloatArray:
    band = mag[(freqs >= lo) & (freqs < hi)]
    if band.size == 0:
        return np.zeros(mag.shape[1])
    logb = np.log1p(50.0 * band)
    flux = np.maximum(0.0, np.diff(logb, axis=1)).sum(axis=0)
    result: FloatArray = np.concatenate([[0.0], flux])
    return result


def _peaks(flux: FloatArray, fps: float, delta: float, min_gap_s: float) -> npt.NDArray[np.intp]:
    if not np.any(flux):
        return np.array([], dtype=np.intp)
    width = max(3, int(fps * 0.5) | 1)
    med = scipy.signal.medfilt(flux, width)
    resid = flux - med
    std = resid.std() or 1.0
    peaks, _ = scipy.signal.find_peaks(
        flux, height=med + delta * std, distance=max(1, int(min_gap_s * fps))
    )
    return peaks


def _decay_time(energy: FloatArray, start: int, fps: float) -> float:
    seg = energy[start : start + int(fps * 1.0)]
    if seg.size == 0 or seg.max() <= 0:
        return 0.0
    peak_i = int(np.argmax(seg[: max(1, int(fps * 0.03))]))
    peak = seg[peak_i]
    below = np.nonzero(seg[peak_i:] < 0.25 * peak)[0]
    frames = int(below[0]) if below.size else seg.size - peak_i
    return frames / fps


class RuleBasedDrumTranscriber:
    def __init__(self, settings: DrumSettings | None = None) -> None:
        self.settings = settings or DrumSettings()

    def transcribe(
        self,
        audio: AudioArray,
        sample_rate: int,
        progress: Callable[[float], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> list[NoteEvent]:
        s = self.settings
        mono = audio.mean(axis=0) if audio.ndim == 2 else audio
        if mono.size < N_FFT or not np.any(mono):
            return []
        freqs, _t, spec = scipy.signal.stft(
            mono, fs=sample_rate, nperseg=N_FFT, noverlap=N_FFT - HOP, boundary=None, padded=False
        )
        mag = np.abs(spec).astype(np.float64)
        fps = sample_rate / HOP
        if cancel is not None:
            cancel.raise_if_cancelled()
        bands = {
            "low": (20.0, 150.0),
            "mid": (150.0, 2500.0),
            "high": (5000.0, 16000.0),
        }
        energy = {
            name: mag[(freqs >= lo) & (freqs < hi)].sum(axis=0) for name, (lo, hi) in bands.items()
        }
        total = sum(energy.values()) + 1e-12
        events: list[NoteEvent] = []
        for i, (name, (lo, hi)) in enumerate(bands.items()):
            flux = _band_flux(mag, freqs, lo, hi)
            for p in _peaks(flux, fps, s.delta, s.min_gap_s):
                window = slice(p, min(mag.shape[1], p + int(0.06 * fps)))
                share = float(energy[name][window].sum() / total[window].sum())
                decay = _decay_time(energy[name], p, fps)
                pitch = self._classify(name, share, decay, mag[:, window], freqs, energy, window)
                if pitch is None:
                    continue
                t = p / fps
                strength = float(flux[p] / (flux.max() or 1.0))
                events.append(NoteEvent(t, t + 0.1, pitch, int(40 + 87 * min(1.0, strength))))
            if progress is not None:
                progress((i + 1) / len(bands))
        return _dedupe(events, s.min_gap_s)

    def _classify(
        self,
        band: str,
        share: float,
        decay: float,
        window_mag: FloatArray,
        freqs: FloatArray,
        energy: dict[str, FloatArray],
        window: slice,
    ) -> int | None:
        s = self.settings
        if band == "low":
            if share < 0.2:
                return None
            # Kicks are short; a low hit that rings and has pitch above 80 Hz is a floor tom.
            centroid = _centroid(window_mag, freqs, 20, 400)
            return LOW_TOM if decay > 0.25 and centroid > 110 else KICK
        if band == "mid":
            if share < 0.25:
                return None
            tonality = _tonality(window_mag, freqs, 150, 2500)
            if tonality > s.tom_tonality:
                centroid = _centroid(window_mag, freqs, 150, 1000)
                return HIGH_TOM if centroid > 350 else MID_TOM
            return SNARE
        # high band
        if share < 0.15:
            return None
        low_share = float(energy["low"][window].sum() / (energy["high"][window].sum() + 1e-12))
        if decay >= s.crash_decay_s:
            return CRASH if low_share > 0.05 else RIDE
        return OPEN_HAT if decay >= s.open_hat_decay_s else CLOSED_HAT


def _centroid(mag: FloatArray, freqs: FloatArray, lo: float, hi: float) -> float:
    sel = (freqs >= lo) & (freqs < hi)
    spectrum = mag[sel].sum(axis=1)
    if spectrum.sum() <= 0:
        return 0.0
    return float((freqs[sel] * spectrum).sum() / spectrum.sum())


def _tonality(mag: FloatArray, freqs: FloatArray, lo: float, hi: float) -> float:
    """1 - spectral flatness within the band (0 = noise, 1 = pure tone)."""
    sel = (freqs >= lo) & (freqs < hi)
    spectrum = mag[sel].sum(axis=1) + 1e-12
    flatness = float(np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum))
    return 1.0 - flatness


def _dedupe(events: list[NoteEvent], gap: float) -> list[NoteEvent]:
    events.sort(key=lambda e: (e.pitch, e.start_s))
    result: list[NoteEvent] = []
    for e in events:
        if result and result[-1].pitch == e.pitch and e.start_s - result[-1].start_s < gap:
            continue
        result.append(e)
    return sorted(result, key=lambda e: (e.start_s, e.pitch))
