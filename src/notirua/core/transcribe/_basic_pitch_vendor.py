# Copyright 2022 Spotify AB
# Modifications copyright 2026 Notirua contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Vendored from basic-pitch 0.4.0 (basic_pitch/inference.py, note_creation.py,
# constants.py). Changes: removed TensorFlow/CoreML/TFLite/librosa/pretty_midi/
# mir_eval dependencies, kept only ONNX Runtime inference and polyphonic note
# decoding (no pitch bends), added progress and cancellation hooks.
"""Basic Pitch ONNX inference and note decoding using only numpy and scipy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import numpy.typing as npt
import scipy.signal

FFT_HOP = 256
AUDIO_SAMPLE_RATE = 22050
AUDIO_WINDOW_LENGTH = 2
ANNOTATIONS_FPS = AUDIO_SAMPLE_RATE // FFT_HOP
ANNOT_N_FRAMES = ANNOTATIONS_FPS * AUDIO_WINDOW_LENGTH
AUDIO_N_SAMPLES = AUDIO_SAMPLE_RATE * AUDIO_WINDOW_LENGTH - FFT_HOP
MIDI_OFFSET = 21
MAX_FREQ_IDX = 87
N_OVERLAPPING_FRAMES = 30

_INPUT = "serving_default_input_2:0"
_OUTPUTS = ["StatefulPartitionedCall:1", "StatefulPartitionedCall:2", "StatefulPartitionedCall:0"]

Array = npt.NDArray[np.float32]


def run_inference(
    session: Any,
    audio_22k_mono: Array,
    progress: Callable[[float], None] | None = None,
    check_cancel: Callable[[], None] | None = None,
) -> dict[str, Array]:
    """Run the model over overlapping 2 s windows; returns note/onset/contour matrices."""
    overlap_len = N_OVERLAPPING_FRAMES * FFT_HOP
    hop_size = AUDIO_N_SAMPLES - overlap_len
    original_length = audio_22k_mono.shape[0]
    audio = np.concatenate(
        [np.zeros((overlap_len // 2,), dtype=np.float32), audio_22k_mono.astype(np.float32)]
    )
    starts = list(range(0, audio.shape[0], hop_size))
    outputs: dict[str, list[Array]] = {"note": [], "onset": [], "contour": []}
    for n, i in enumerate(starts):
        if check_cancel is not None:
            check_cancel()
        window = audio[i : i + AUDIO_N_SAMPLES]
        if window.shape[0] < AUDIO_N_SAMPLES:
            window = np.pad(window, (0, AUDIO_N_SAMPLES - window.shape[0]))
        x = window[np.newaxis, :, np.newaxis]
        note, onset, contour = session.run(_OUTPUTS, {_INPUT: x})
        outputs["note"].append(note)
        outputs["onset"].append(onset)
        outputs["contour"].append(contour)
        if progress is not None:
            progress((n + 1) / len(starts))
    return {k: _unwrap(np.concatenate(v), original_length) for k, v in outputs.items()}


def _unwrap(output: Array, original_length: int) -> Array:
    n_olap = N_OVERLAPPING_FRAMES // 2
    output = output[:, n_olap:-n_olap, :]
    n_frames = int(np.floor(original_length * (ANNOTATIONS_FPS / AUDIO_SAMPLE_RATE)))
    return output.reshape(-1, output.shape[2])[:n_frames, :]


def model_frames_to_time(n_frames: int) -> npt.NDArray[np.float64]:
    original_times = np.arange(n_frames) * FFT_HOP / AUDIO_SAMPLE_RATE
    window_numbers = np.floor(np.arange(n_frames) / ANNOT_N_FRAMES)
    window_offset = (FFT_HOP / AUDIO_SAMPLE_RATE) * (
        ANNOT_N_FRAMES - (AUDIO_N_SAMPLES / FFT_HOP)
    ) + 0.0018  # upstream alignment constant
    result: npt.NDArray[np.float64] = original_times - (window_offset * window_numbers)
    return result


def _hz_to_midi(freq: float) -> float:
    return float(12 * (np.log2(freq) - np.log2(440.0)) + 69)


def _infer_onsets(onsets: Array, frames: Array, n_diff: int = 2) -> Array:
    diffs = []
    for n in range(1, n_diff + 1):
        appended = np.concatenate([np.zeros((n, frames.shape[1])), frames])
        diffs.append(appended[n:, :] - appended[:-n, :])
    frame_diff = np.min(diffs, axis=0)
    frame_diff[frame_diff < 0] = 0
    frame_diff[:n_diff, :] = 0
    peak = np.max(frame_diff)
    if peak > 0:
        frame_diff = np.max(onsets) * frame_diff / peak
    result: Array = np.max([onsets, frame_diff], axis=0).astype(np.float32)
    return result


def output_to_notes_polyphonic(
    frames: Array,
    onsets: Array,
    onset_thresh: float,
    frame_thresh: float,
    min_note_len: int,
    infer_onsets: bool = True,
    max_freq: float | None = None,
    min_freq: float | None = None,
    melodia_trick: bool = True,
    energy_tol: int = 11,
) -> list[tuple[int, int, int, float]]:
    """Decode activations into ``(start_frame, end_frame, midi_pitch, amplitude)``."""
    frames = frames.copy()
    onsets = onsets.copy()
    n_frames = frames.shape[0]
    if max_freq is not None:
        idx = int(np.round(_hz_to_midi(max_freq) - MIDI_OFFSET))
        onsets[:, idx:] = 0
        frames[:, idx:] = 0
    if min_freq is not None:
        idx = int(np.round(_hz_to_midi(min_freq) - MIDI_OFFSET))
        onsets[:, :idx] = 0
        frames[:, :idx] = 0
    if infer_onsets:
        onsets = _infer_onsets(onsets, frames)

    peak_thresh_mat = np.zeros(onsets.shape)
    peaks = scipy.signal.argrelmax(onsets, axis=0)
    peak_thresh_mat[peaks] = onsets[peaks]

    onset_idx = np.where(peak_thresh_mat >= onset_thresh)
    onset_time_idx = onset_idx[0][::-1]
    onset_freq_idx = onset_idx[1][::-1]

    remaining = frames.astype(np.float64).copy()
    note_events: list[tuple[int, int, int, float]] = []
    for note_start_idx, freq_idx in zip(onset_time_idx, onset_freq_idx, strict=True):
        if note_start_idx >= n_frames - 1:
            continue
        i = note_start_idx + 1
        k = 0
        while i < n_frames - 1 and k < energy_tol:
            k = k + 1 if remaining[i, freq_idx] < frame_thresh else 0
            i += 1
        i -= k
        if i - note_start_idx <= min_note_len:
            continue
        remaining[note_start_idx:i, freq_idx] = 0
        if freq_idx < MAX_FREQ_IDX:
            remaining[note_start_idx:i, freq_idx + 1] = 0
        if freq_idx > 0:
            remaining[note_start_idx:i, freq_idx - 1] = 0
        amplitude = float(np.mean(frames[note_start_idx:i, freq_idx]))
        note_events.append((int(note_start_idx), int(i), int(freq_idx) + MIDI_OFFSET, amplitude))

    if melodia_trick:
        shape = remaining.shape
        while np.max(remaining) > frame_thresh:
            i_mid, freq_idx = np.unravel_index(np.argmax(remaining), shape)
            remaining[i_mid, freq_idx] = 0
            i = i_mid + 1
            k = 0
            while i < n_frames - 1 and k < energy_tol:
                k = k + 1 if remaining[i, freq_idx] < frame_thresh else 0
                remaining[i, freq_idx] = 0
                if freq_idx < MAX_FREQ_IDX:
                    remaining[i, freq_idx + 1] = 0
                if freq_idx > 0:
                    remaining[i, freq_idx - 1] = 0
                i += 1
            i_end = i - 1 - k
            i = i_mid - 1
            k = 0
            while i > 0 and k < energy_tol:
                k = k + 1 if remaining[i, freq_idx] < frame_thresh else 0
                remaining[i, freq_idx] = 0
                if freq_idx < MAX_FREQ_IDX:
                    remaining[i, freq_idx + 1] = 0
                if freq_idx > 0:
                    remaining[i, freq_idx - 1] = 0
                i -= 1
            i_start = i + 1 + k
            if i_end - i_start <= min_note_len:
                continue
            amplitude = float(np.mean(frames[i_start:i_end, freq_idx]))
            note_events.append((int(i_start), int(i_end), int(freq_idx) + MIDI_OFFSET, amplitude))

    return note_events


def model_output_to_note_events(
    output: dict[str, Array],
    onset_thresh: float = 0.5,
    frame_thresh: float = 0.3,
    min_note_len_ms: float = 127.70,
    min_freq: float | None = None,
    max_freq: float | None = None,
    melodia_trick: bool = True,
) -> list[tuple[float, float, int, float]]:
    """Return ``(start_s, end_s, midi_pitch, amplitude 0..1)`` tuples."""
    min_note_len = int(np.round(min_note_len_ms / 1000 * (AUDIO_SAMPLE_RATE / FFT_HOP)))
    notes = output_to_notes_polyphonic(
        output["note"],
        output["onset"],
        onset_thresh=onset_thresh,
        frame_thresh=frame_thresh,
        min_note_len=min_note_len,
        min_freq=min_freq,
        max_freq=max_freq,
        melodia_trick=melodia_trick,
    )
    times = model_frames_to_time(output["contour"].shape[0])
    return [(float(times[s]), float(times[e]), p, a) for s, e, p, a in notes]
