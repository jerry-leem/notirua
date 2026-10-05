"""Tempo, beat grid, meter, and key estimation (FR-4, SPEC 6.2).

Beat tracking follows Ellis (2007) "Beat Tracking by Dynamic Programming":
an onset-strength envelope, a tempo estimate from its autocorrelation with a
log-normal prior, then dynamic programming that trades onset strength
against deviation from the tempo period. Only numpy/scipy are used.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
import scipy.signal

from notirua.core.decode import AudioArray
from notirua.core.model import NoteEvent

log = logging.getLogger(__name__)

ANALYSIS_SR = 22_050
HOP = 512
N_FFT = 2048
FPS = ANALYSIS_SR / HOP

FloatArray = npt.NDArray[np.float64]


@dataclass
class Analysis:
    tempo_bpm: float
    beat_times: list[float]
    time_signature: tuple[int, int] = (4, 4)
    downbeat_index: int = 0  # index into beat_times of the first downbeat
    key: str = "C major"
    notes_used_for_key: int = 0
    extra: dict[str, float] = field(default_factory=dict)


def onset_envelope(audio: AudioArray, sample_rate: int) -> FloatArray:
    """Spectral-flux onset strength at ``FPS`` frames per second."""
    import soxr

    mono = audio.mean(axis=0) if audio.ndim == 2 else audio
    if sample_rate != ANALYSIS_SR:
        mono = soxr.resample(mono.astype(np.float32), sample_rate, ANALYSIS_SR)
    if mono.size < N_FFT:
        return np.zeros(1)
    _f, _t, spec = scipy.signal.stft(
        mono, fs=ANALYSIS_SR, nperseg=N_FFT, noverlap=N_FFT - HOP, boundary=None, padded=False
    )
    mag = np.log1p(100.0 * np.abs(spec))
    flux = np.maximum(0.0, np.diff(mag, axis=1)).mean(axis=0)
    flux = np.concatenate([[0.0], flux])
    # Remove slow trends and normalise.
    flux = flux - scipy.signal.medfilt(flux, 31 if flux.size > 31 else 1)
    flux = np.maximum(flux, 0.0)
    std = flux.std()
    result: FloatArray = flux / std if std > 0 else flux
    return result


def estimate_tempo(
    envelope: FloatArray, prior_bpm: float = 120.0, min_bpm: float = 50.0, max_bpm: float = 220.0
) -> float:
    if envelope.size < int(FPS * 4) or not np.any(envelope):
        return prior_bpm
    env = envelope - envelope.mean()
    ac = scipy.signal.fftconvolve(env, env[::-1], mode="full")[env.size - 1 :]
    lags = np.arange(ac.size)
    bpms = np.where(lags > 0, 60.0 * FPS / np.maximum(lags, 1), 0.0)
    valid = (bpms >= min_bpm) & (bpms <= max_bpm)
    prior = np.exp(-0.5 * ((np.log2(np.maximum(bpms, 1e-6)) - np.log2(prior_bpm)) / 1.0) ** 2)
    score = np.where(valid, ac * prior, -np.inf)
    best = int(np.argmax(score))
    # Refine with parabolic interpolation around the peak.
    if 1 <= best < ac.size - 1:
        a, b, c = score[best - 1], score[best], score[best + 1]
        if np.isfinite(a) and np.isfinite(c) and (a - 2 * b + c) != 0:
            best_f = best + 0.5 * (a - c) / (a - 2 * b + c)
            return float(60.0 * FPS / best_f)
    return float(bpms[best])


def track_beats(envelope: FloatArray, tempo_bpm: float, tightness: float = 100.0) -> FloatArray:
    """Return beat times (seconds) via dynamic programming."""
    period = 60.0 * FPS / tempo_bpm
    n = envelope.size
    if n < 2 or not np.any(envelope):
        return np.arange(0.0, n / FPS, 60.0 / tempo_bpm)
    # Smooth the envelope with a Gaussian of width ~ period/32.
    win = scipy.signal.windows.gaussian(int(period) * 2 + 1, std=max(1.0, period / 32))
    local = np.convolve(envelope, win, mode="same")
    score = local.copy()
    backlink = -np.ones(n, dtype=int)
    lo = round(-2 * period)
    hi = round(-period / 2)
    offsets = np.arange(lo, hi + 1)
    penalty = -tightness * np.log(-offsets / period) ** 2
    for t in range(n):
        prev = t + offsets
        ok = prev >= 0
        if not np.any(ok):
            continue
        cand = score[prev[ok]] + penalty[ok]
        j = int(np.argmax(cand))
        if cand[j] > 0:
            score[t] = local[t] + cand[j]
            backlink[t] = prev[ok][j]
    # Start from the best-scoring frame in the last period.
    tail = max(0, n - int(period))
    t = tail + int(np.argmax(score[tail:]))
    beats = [t]
    while backlink[t] >= 0:
        t = backlink[t]
        beats.append(t)
    frames = np.array(beats[::-1], dtype=float)
    times: FloatArray = frames / FPS
    return _extend_grid(times, n / FPS, 60.0 / tempo_bpm)


def _extend_grid(beats: FloatArray, duration: float, period_s: float) -> FloatArray:
    """Pad the beat grid to cover the whole file so every note maps to a beat."""
    if beats.size == 0:
        return np.arange(0.0, duration + period_s, period_s)
    head = []
    t = beats[0] - period_s
    while t > -period_s:
        head.append(t)
        t -= period_s
    tail = []
    t = beats[-1] + period_s
    while t < duration + period_s:
        tail.append(t)
        t += period_s
    return np.concatenate([np.array(head[::-1]), beats, np.array(tail)])


def estimate_downbeat(envelope: FloatArray, beat_times: Sequence[float], beats_per_bar: int) -> int:
    """Pick the bar phase whose beats carry the most onset energy."""
    if beats_per_bar <= 1 or len(beat_times) < beats_per_bar * 2:
        return _first_nonnegative(beat_times)
    frames = np.clip((np.asarray(beat_times) * FPS).astype(int), 0, envelope.size - 1)
    strengths = envelope[frames]
    totals = [float(strengths[p::beats_per_bar].mean()) for p in range(beats_per_bar)]
    phase = int(np.argmax(totals))
    first = _first_nonnegative(beat_times)
    idx = phase
    while idx < first:
        idx += beats_per_bar
    return idx


def _first_nonnegative(beat_times: Sequence[float]) -> int:
    for i, t in enumerate(beat_times):
        if t >= -1e-6:
            return i
    return 0


_MAJOR_NAMES = ["C", "D-", "D", "E-", "E", "F", "F#", "G", "A-", "A", "B-", "B"]


def estimate_key(notes: Sequence[NoteEvent]) -> str:
    """Krumhansl–Schmuckler via music21, weighting pitch classes by duration."""
    if not notes:
        return "C major"
    weights = np.zeros(12)
    for n in notes:
        weights[n.pitch % 12] += max(0.05, n.end_s - n.start_s)
    from music21 import analysis, note, stream

    s = stream.Stream()
    for pc, w in enumerate(weights):
        if w > 0:
            s.append(note.Note(pc + 60, quarterLength=float(w)))
    solution = analysis.discrete.KrumhanslSchmuckler().getSolution(s)
    tonic = solution.tonic.name.replace("-", "b")
    return f"{tonic} {solution.mode}"


def analyze(
    mix: AudioArray,
    sample_rate: int,
    notes: Sequence[NoteEvent] = (),
    time_signature: tuple[int, int] | None = None,
    tempo_override: float | None = None,
    key_override: str | None = None,
    downbeat_shift: int = 0,
    drums: AudioArray | None = None,
) -> Analysis:
    env = onset_envelope(mix, sample_rate)
    if drums is not None and drums.size:
        drum_env = onset_envelope(drums, sample_rate)
        m = min(env.size, drum_env.size)
        env = env[:m] + 0.5 * drum_env[:m]
    tempo = tempo_override or estimate_tempo(env)
    beats = track_beats(env, tempo)
    if tempo_override is None and beats.size > 4:
        inner = np.diff(beats)
        tempo = float(60.0 / np.median(inner))
    ts = time_signature or (4, 4)
    downbeat = estimate_downbeat(env, list(beats), ts[0]) + downbeat_shift
    downbeat = int(np.clip(downbeat, 0, max(0, beats.size - 1)))
    key = key_override or estimate_key(notes)
    return Analysis(
        tempo_bpm=round(tempo, 1),
        beat_times=[float(b) for b in beats],
        time_signature=ts,
        downbeat_index=downbeat,
        key=key,
        notes_used_for_key=len(notes),
    )
