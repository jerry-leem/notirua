"""Build a PyAV wheel on an LGPL-only, decode-focused FFmpeg (DECISIONS D13).

Usage: uv run python packaging/build_lgpl_av.py [--work build/lgpl-av] [--out dist/lgpl-av]

The PyPI ``av`` wheels link FFmpeg against libx264/libx265 (GPL), which would
put a bundled app under GPL terms. This script:

1. downloads pinned FFmpeg and PyAV sources (SHA-256 checked),
2. builds LAME (libmp3lame, LGPL) as a static library for MP3 saving (0.4.0),
3. configures FFmpeg with ``--disable-everything`` plus only the demuxers,
   decoders, parsers, and filters Notirua needs, and the encoders for "Make
   audio file" (AAC, MP3 through LAME, WAV); no ``--enable-gpl``,
   ``--enable-nonfree``, or other external codec libraries,
4. builds the PyAV wheel against it and vendors the libraries into the wheel
   (delocate on macOS, auditwheel on Linux),
5. installs the wheel into a scratch venv and runs :func:`check_lgpl` plus an
   encode and decode round trip for every format.

macOS and Linux build LAME and FFmpeg from source here. On Windows, both are
built with MinGW GCC inside MSYS2 (``.github/workflows/release.yml``) using the
flags from ``--print-configure-flags`` (LAME is expected in ``PREFIX/../lame``),
and this script then runs with ``--ffmpeg-prefix``.
``check_lgpl`` is the same everywhere.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path, PurePath, PurePosixPath

# Oldest macOS Notirua supports, Intel and Apple Silicon alike (DECISIONS D13).
MACOS_MIN = "14.0"

FFMPEG_VERSION = "8.1.2"
FFMPEG_URL = f"https://ffmpeg.org/releases/ffmpeg-{FFMPEG_VERSION}.tar.xz"
FFMPEG_SIZE = 11_710_924
FFMPEG_SHA256 = "464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c"

# LAME 3.100 (LGPL-2.0-or-later), linked statically into libavcodec for MP3 saving.
LAME_VERSION = "3.100"
LAME_URL = (
    f"https://downloads.sourceforge.net/project/lame/lame/{LAME_VERSION}/lame-{LAME_VERSION}.tar.gz"
)
LAME_SIZE = 1_524_133
LAME_SHA256 = "ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e"

PYAV_VERSION = "18.1.0"
PYAV_URL = (
    "https://files.pythonhosted.org/packages/8d/f4/"
    "f22114d30d3435e38c6af2b4870f37b864403dca6ae7af747a289ce0a18e/av-18.1.0.tar.gz"
)
PYAV_SIZE = 4_451_061
PYAV_SHA256 = "47bfc286e1bc9de7ab4681fc2b575cd2460a66919d31ffe1bd5aa54fae531a28"

# What FR-1 needs to read: audio files and the audio track of common videos.
DEMUXERS = [
    "aac", "ac3", "aiff", "asf", "caf", "eac3", "flac", "matroska", "mov",
    "mp3", "ogg", "w64", "wav",
]  # fmt: skip
PCM = [
    "pcm_alaw", "pcm_f32be", "pcm_f32le", "pcm_f64be", "pcm_f64le", "pcm_mulaw",
    "pcm_s16be", "pcm_s16le", "pcm_s24be", "pcm_s24le", "pcm_s32be", "pcm_s32le",
    "pcm_s8", "pcm_u8",
]  # fmt: skip
DECODERS = [
    "aac", "aac_fixed", "ac3", "alac", "eac3", "flac", "mp1", "mp1float", "mp2",
    "mp2float", "mp3", "mp3float", "opus", "vorbis", "wmapro", "wmav1", "wmav2",
    *PCM,
]  # fmt: skip
PARSERS = ["aac", "ac3", "flac", "mpegaudio", "opus", "vorbis"]
# PyAV's AudioResampler builds an abuffer -> aformat -> abuffersink graph.
FILTERS = ["abuffer", "abuffersink", "aformat", "anull", "aresample", "buffer", "buffersink"]
# "Make audio file" writes MP3 (LAME), M4A (AAC), and WAV; the rest let the
# built wheel test itself.
ENCODERS = ["aac", "alac", "flac", "libmp3lame", "pcm_s16be", "pcm_s16le"]
MUXERS = ["aiff", "flac", "ipod", "mov", "mp3", "mp4", "wav"]

# Anything here in the FFmpeg configuration means the build is not LGPL-only.
FORBIDDEN = ("--enable-gpl", "--enable-nonfree", "libx264", "libx265", "libxvid", "libfdk")


def _run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    full_env = dict(env or os.environ)
    if sys.platform == "darwin":
        full_env.setdefault("MACOSX_DEPLOYMENT_TARGET", MACOS_MIN)
        # FFmpeg is built for this machine only. A universal2 Python (CI runners) would
        # otherwise build and tag a universal2 wheel whose other half has no FFmpeg.
        full_env.setdefault("ARCHFLAGS", f"-arch {platform.machine()}")
    subprocess.run(cmd, cwd=cwd, env=full_env, check=True)


def _download(url: str, target: Path, size: int, sha256: str) -> Path:
    from notirua.components.download import download

    return download(url, target, expected_size=size, sha256=sha256)


def configure_flags(prefix: PurePath, lame: PurePath | None = None) -> list[str]:
    """FFmpeg's configure flags; LAME's static build is in ``lame`` (default ``prefix/../lame``)."""
    lame = lame or prefix.parent / "lame"
    flags = [
        f"--prefix={prefix}",
        "--enable-shared",
        "--disable-static",
        "--disable-programs",
        "--disable-doc",
        "--disable-network",
        "--disable-autodetect",
        "--disable-everything",
        "--enable-protocol=file,pipe",
        "--enable-swresample",
        *(f"--enable-demuxer={x}" for x in DEMUXERS),
        *(f"--enable-decoder={x}" for x in DECODERS),
        *(f"--enable-parser={x}" for x in PARSERS),
        *(f"--enable-filter={x}" for x in FILTERS),
        *(f"--enable-encoder={x}" for x in ENCODERS),
        *(f"--enable-muxer={x}" for x in MUXERS),
        "--enable-libmp3lame",
        f"--extra-cflags=-I{lame / 'include'}",
        f"--extra-ldflags=-L{lame / 'lib'}",
    ]
    if platform.machine().lower() in ("x86_64", "amd64") and shutil.which("nasm") is None:
        flags.append("--disable-x86asm")
    return flags


def build_lame(work: Path) -> Path:
    """LAME as a static, position-independent library (no command-line encoder)."""
    prefix = work / "lame"
    if (prefix / "lib" / "libmp3lame.a").is_file():
        return prefix
    archive = _download(LAME_URL, work / f"lame-{LAME_VERSION}.tar.gz", LAME_SIZE, LAME_SHA256)
    src = work / f"lame-{LAME_VERSION}"
    if not src.is_dir():
        with tarfile.open(archive) as tar:
            tar.extractall(work, filter="data")
    flags = [
        f"--prefix={prefix}",
        "--disable-shared",
        "--enable-static",
        "--with-pic",
        "--disable-frontend",
        "--disable-gtktest",
        "--disable-decoder",
    ]
    if sys.platform == "darwin":
        # LAME's 2017 config.guess does not know Apple Silicon.
        machine = platform.machine()
        flags.append(f"--host={'aarch64' if machine == 'arm64' else machine}-apple-darwin")
    _run(["./configure", *flags], cwd=src)
    _run(["make", f"-j{os.cpu_count() or 2}"], cwd=src)
    _run(["make", "install"], cwd=src)
    return prefix


def build_ffmpeg(work: Path) -> Path:
    prefix = work / "ffmpeg"
    lame = build_lame(work)
    flags = configure_flags(prefix, lame)
    # Rebuild when the configuration changed (a new encoder, LAME, ...).
    stamp = prefix / "notirua-configure.txt"
    if (prefix / "lib" / "pkgconfig" / "libavcodec.pc").is_file() and (
        stamp.is_file() and stamp.read_text(encoding="utf-8") == "\n".join(flags)
    ):
        return prefix
    shutil.rmtree(prefix, ignore_errors=True)
    archive = _download(
        FFMPEG_URL, work / f"ffmpeg-{FFMPEG_VERSION}.tar.xz", FFMPEG_SIZE, FFMPEG_SHA256
    )
    src = work / f"ffmpeg-{FFMPEG_VERSION}"
    if not src.is_dir():
        with tarfile.open(archive) as tar:
            tar.extractall(work, filter="data")
    if (src / "ffbuild" / "config.mak").is_file():
        _run(["make", "distclean"], cwd=src)
    _run(["./configure", *flags], cwd=src)
    _run(["make", f"-j{os.cpu_count() or 2}"], cwd=src)
    _run(["make", "install"], cwd=src)
    stamp.write_text("\n".join(flags), encoding="utf-8")
    return prefix


def build_wheel(work: Path, prefix: Path, out: Path) -> Path:
    sdist = _download(PYAV_URL, work / f"av-{PYAV_VERSION}.tar.gz", PYAV_SIZE, PYAV_SHA256)
    raw = work / "raw-wheel"
    shutil.rmtree(raw, ignore_errors=True)
    env = dict(os.environ)
    if sys.platform == "win32":
        # PyAV finds FFmpeg through MSVC's INCLUDE and LIB on Windows.
        for var, sub in (("INCLUDE", "include"), ("LIB", "lib")):
            env[var] = str(prefix / sub) + os.pathsep + env.get(var, "")
    else:
        env["PKG_CONFIG_PATH"] = str(prefix / "lib" / "pkgconfig")
        env["LDFLAGS"] = f"-Wl,-rpath,{prefix / 'lib'} " + env.get("LDFLAGS", "")
    _run(["uv", "build", "--wheel", "--out-dir", str(raw), str(sdist)], env=env)
    wheel = next(raw.glob("av-*.whl"))
    # Repair into a scratch folder first: ``out`` may hold wheels for other
    # platforms (one checkout serves the macOS and the Docker Linux builds).
    repaired = work / "repaired-wheel"
    shutil.rmtree(repaired, ignore_errors=True)
    repaired.mkdir(parents=True)
    if sys.platform == "darwin":
        env["DYLD_LIBRARY_PATH"] = str(prefix / "lib")
        repair = ["uvx", "--from", "delocate", "delocate-wheel", "-w", str(repaired)]
    elif sys.platform == "win32":
        repair = ["uvx", "delvewheel", "repair", "--add-path", str(prefix / "bin"),
                  "-w", str(repaired)]  # fmt: skip
    else:
        env["LD_LIBRARY_PATH"] = str(prefix / "lib")
        repair = ["uvx", "auditwheel", "repair", "--plat", "manylinux_2_31_x86_64",
                  "-w", str(repaired)]  # fmt: skip
    _run([*repair, str(wheel)], env=env)
    built = next(repaired.glob("av-*.whl"))
    out.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy2(built, out / built.name))


def check_lgpl() -> list[str]:
    """Problems with the FFmpeg inside the active ``av`` (empty = LGPL-only)."""
    import av

    problems = []
    meta = av._core.library_meta  # type: ignore[attr-defined]
    for name, info in meta.items():
        if "LGPL" not in info["license"]:
            problems.append(f"{name}: license {info['license']}")
        for word in FORBIDDEN:
            if word in info["configuration"]:
                problems.append(f"{name}: configured with {word}")
    folder = Path(av.__file__).parent
    for lib in [*folder.parent.glob("av*.libs/*"), *folder.glob(".dylibs/*"), *folder.glob("*")]:
        if any(bad in lib.name for bad in ("x264", "x265", "xvid", "fdk")):
            problems.append(f"GPL/nonfree library bundled: {lib.name}")
    return sorted(set(problems))


SELF_TEST = textwrap.dedent(
    """
    import sys, tempfile
    from pathlib import Path
    import numpy as np, av
    sys.path.insert(0, sys.argv[1])
    from build_lgpl_av import check_lgpl
    problems = check_lgpl()
    assert not problems, problems
    tmp = Path(tempfile.mkdtemp())
    assert "--enable-libmp3lame" in av._core.library_meta["libavcodec"]["configuration"]
    for name, fmt, codec, sample in (("a.mp3", "mp3", "libmp3lame", "fltp"),
                                     ("a.m4a", "ipod", "aac", "fltp"),
                                     ("a.flac", "flac", "flac", "s16"),
                                     ("a.wav", "wav", "pcm_s16le", "s16")):
        path = tmp / name
        with av.open(str(path), "w", format=fmt) as out:
            stream = out.add_stream(codec, rate=44100)
            stream.layout = "stereo"
            t = np.arange(44100) / 44100
            tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
            data = np.stack([tone, tone])
            if sample == "s16":
                data = (data * 32767).astype(np.int16).T.reshape(1, -1)
            frame = av.AudioFrame.from_ndarray(data, format=sample, layout="stereo")
            frame.sample_rate = 44100
            for p in stream.encode(frame):
                out.mux(p)
            for p in stream.encode(None):
                out.mux(p)
        with av.open(str(path)) as inp:
            resampler = av.AudioResampler(format="fltp", layout="stereo", rate=22050)
            n = sum(f.samples for fr in inp.decode(audio=0) for f in resampler.resample(fr))
        assert n > 20000, (name, n)
        print("decoded", name, n)
    print("LGPL-only:", av.__version__, av.ffmpeg_version_info)
    """
)


def self_test(wheel: Path, work: Path) -> None:
    venv = work / "test-venv"
    shutil.rmtree(venv, ignore_errors=True)
    _run(["uv", "venv", "--python", "3.11", str(venv)])
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    _run(["uv", "pip", "install", "--python", str(python), str(wheel), "numpy"])
    script = work / "self_test.py"
    script.write_text(SELF_TEST, encoding="utf-8")
    # Run outside the build folders so the freshly built libraries are not picked up by path.
    _run([str(python), "-I", str(script), str(Path(__file__).resolve().parent)], cwd=venv)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=root / "build" / "lgpl-av")
    parser.add_argument("--out", type=Path, default=root / "dist" / "lgpl-av")
    parser.add_argument(
        "--ffmpeg-prefix", type=Path, help="use an FFmpeg already built with these flags"
    )
    parser.add_argument(
        "--lame-prefix",
        help="LAME's install folder for --print-configure-flags (default: PREFIX/../lame)",
    )
    parser.add_argument(
        "--print-configure-flags",
        metavar="PREFIX",
        help="print FFmpeg's configure flags for PREFIX and exit (Windows CI)",
    )
    args = parser.parse_args()
    if args.print_configure_flags:
        # An MSYS2 path such as /d/a/notirua/ffmpeg: keep its forward slashes.
        lame = PurePosixPath(args.lame_prefix) if args.lame_prefix else None
        print(" ".join(configure_flags(PurePosixPath(args.print_configure_flags), lame)))
        return
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    prefix = args.ffmpeg_prefix.resolve() if args.ffmpeg_prefix else build_ffmpeg(work)
    wheel = build_wheel(work, prefix, args.out.resolve())
    self_test(wheel, work)
    print(wheel)


if __name__ == "__main__":
    main()
