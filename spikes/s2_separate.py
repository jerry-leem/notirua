"""M0-S2 spike: htdemucs_6s separation time and peak memory on a synthesized mix.

Usage: uv run python spikes/s2_separate.py [--seconds 240] [--cpu]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notirua.components.manager import manager_from_settings
from notirua.core.separate import DemucsOnnxSeparator, rms_db
from tests import synth


def peak_rss_mb() -> float:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()  # type: ignore[attr-defined]
        ctypes.windll.psapi.GetProcessMemoryInfo(  # type: ignore[attr-defined]
            handle, ctypes.byref(counters), counters.cb
        )
        return counters.PeakWorkingSetSize / (1024 * 1024)
    import resource

    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / (1024 * 1024) if sys.platform == "darwin" else usage / 1024


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=240)
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()
    bpm = 120
    beat = 60 / bpm
    n_beats = int(args.seconds / beat)
    piano = synth.render_notes(
        [(i * beat, beat * 0.9, 60 + (i * 7) % 12) for i in range(n_beats)], args.seconds
    )
    bass = synth.render_notes(
        [(i * beat, beat * 0.9, 36 + (i * 5) % 12) for i in range(n_beats)],
        args.seconds,
        plucked=True,
    )
    clicks = synth.click_track(bpm, args.seconds)
    mix = synth.to_stereo(0.4 * piano + 0.4 * bass + 0.3 * clicks)
    model = manager_from_settings().require("htdemucs_6s")
    t0 = time.perf_counter()
    sep = DemucsOnnxSeparator(model, accelerate=False if args.cpu else None)
    t_load = time.perf_counter() - t0
    t1 = time.perf_counter()
    stems = sep.separate(mix)
    t_run = time.perf_counter() - t1
    print(
        f"providers={sep.providers} load={t_load:.1f}s run={t_run:.1f}s "
        f"audio={args.seconds:.0f}s rtf={t_run / args.seconds:.3f} peak_rss={peak_rss_mb():.0f}MB"
    )
    for name, audio in stems.items():
        print(f"  {name:7s} rms={rms_db(audio):6.1f} dB")


if __name__ == "__main__":
    main()
