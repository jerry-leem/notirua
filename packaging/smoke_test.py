"""Try an installed Notirua like a user would (release check).

Usage: uv run python packaging/smoke_test.py --cli PATH [--gui PATH] [--work DIR]

Synthesizes a short song (piano, clicks, a sung line), installs the components
with the bundled command line, makes sheet music, saves a backing track as MP3
and a mix as M4A, decodes both back, and checks that the window stays open.
Needs the internet for the components on first use. Set NOTIRUA_SMOKE_YOUTUBE to a video
link to also try a real YouTube download.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(cmd: list[str | Path], expect: int = 0) -> str:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    done = subprocess.run(
        [str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    print(done.stdout[-2000:], done.stderr[-2000:], sep="\n", flush=True)
    if done.returncode != expect:
        raise SystemExit(f"failed ({done.returncode}, expected {expect}): {cmd}")
    return done.stdout


def make_song(path: Path) -> Path:
    from tests import synth

    seconds = 12.0
    piano = synth.render_notes(synth.scale_notes(100), total_s=seconds)
    drums = synth.click_track(100, seconds)
    sung = synth.voice(seconds)
    n = min(piano.size, drums.size, sung.size)
    return synth.write_wav(path, synth.to_stereo(0.5 * piano[:n] + 0.5 * drums[:n] + sung[:n]))


def check_audio(path: Path, seconds: float) -> None:
    from notirua.core.decode import SAMPLE_RATE, decode

    audio = decode(path)
    length = audio.shape[1] / SAMPLE_RATE
    print(f"{path.name}: {audio.shape[0]} channels, {length:.2f} s", flush=True)
    if audio.shape[0] != 2 or abs(length - seconds) > 0.2:
        raise SystemExit(f"unexpected audio in {path}")


def check_window(gui: Path) -> None:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    proc = subprocess.Popen([str(gui)], env=env)
    time.sleep(15)
    alive = proc.poll() is None
    proc.kill()
    proc.wait()
    if not alive:
        raise SystemExit(f"the window app exited early with {proc.returncode}")
    print("window app is running", flush=True)


def main() -> None:
    # The CI console uses cp1252; never stop on a Korean message.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--gui", type=Path)
    parser.add_argument("--work", type=Path, default=ROOT / "build" / "smoke")
    args = parser.parse_args()
    work = args.work.resolve()
    song = make_song(work / "노래.wav")
    run([args.cli, "--version"])
    # YouTube support (0.5.0): its parts are in the bundle, and a bad link stops early (exit 2).
    run([args.cli, "--lang", "en", "youtube", "--check"])
    run([args.cli, "--lang", "en", "youtube", "not a link"], expect=2)
    link = os.environ.get("NOTIRUA_SMOKE_YOUTUBE")
    if link:  # a real download needs the internet and a video that YouTube lets this machine see
        run([args.cli, "setup", "--youtube", "--accept-licenses"])
        run(
            [
                args.cli,
                "--lang",
                "en",
                "youtube",
                link,
                "--out",
                work / "youtube",
                "--bitrate",
                "128",
            ]
        )
        if not list((work / "youtube").glob("*.mp3")):
            raise SystemExit("no MP3 was saved from the YouTube link")
    run([args.cli, "setup", "--accept-licenses"])
    run([args.cli, "--lang", "ko", "transcribe", song, "--out", work / "out"])
    pdfs = sorted((work / "out").glob("*.pdf"))
    if not pdfs:
        raise SystemExit("no PDF was made")
    print("PDFs:", [p.name for p in pdfs])
    run([args.cli, "--lang", "ko", "mix", song, "--out", work / "mix"])
    run([args.cli, "--lang", "en", "mix", song, "--out", work / "mix", "--without", "drums",
         "--format", "m4a"])  # fmt: skip
    check_audio(work / "mix" / "노래 - MR.mp3", 12.0)
    check_audio(work / "mix" / "노래 - without Drums.m4a", 12.0)
    if args.gui:
        check_window(args.gui)
    print("smoke test passed")


if __name__ == "__main__":
    main()
