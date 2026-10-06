"""Check a built Notirua bundle before it is packed into an installer (M6).

Usage: python packaging/check_bundle.py dist/app/Notirua [--version X.Y.Z]

Fails (exit 1) when the bundle carries something it must not (ML frameworks,
GPL FFmpeg, unused Qt add-ons) or misses something it needs (catalogs, license
notices, the transcription model, version metadata, Linux fonts), and when the
bundled command line does not start.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PARTS = ("torch", "tensorflow", "tflite_runtime", "coremltools", "matplotlib")
# Only QtPdf and QtPdfWidgets come from PySide6-Addons.
# QtQuick (macOS), libQt6Quick.so.6 (Linux), Qt6Quick.dll (Windows).
FORBIDDEN_QT = re.compile(r"Qt6?(WebEngine|3D|Quick|Qml|Multimedia|Charts|VirtualKeyboard)")
GPL_FFMPEG = re.compile(rb"--enable-gpl|--enable-nonfree|libx264|libx265|(?<![L])GPL version \d")
FFMPEG_LIB = re.compile(r"(avcodec|avformat|avutil|swresample|avfilter|swscale)", re.IGNORECASE)


def is_ffmpeg(path: Path) -> bool:
    is_library = path.suffix in (".dylib", ".so", ".dll") or ".so." in path.name
    return is_library and FFMPEG_LIB.search(path.name) is not None


def internal_dir(bundle: Path) -> Path:
    """The folder holding libraries and data (PyInstaller's ``_internal``)."""
    for candidate in (bundle / "_internal", bundle / "Contents" / "Resources", bundle):
        if (candidate / "notirua").is_dir() or (candidate / "base_library.zip").is_file():
            return candidate
    raise SystemExit(f"not a Notirua bundle: {bundle}")


def cli_path(bundle: Path) -> Path:
    name = "notirua-cli.exe" if sys.platform == "win32" else "notirua-cli"
    for candidate in (bundle / name, bundle / "Contents" / "MacOS" / name):
        if candidate.is_file():
            return candidate
    raise SystemExit(f"{name} not found in {bundle}")


def problems(bundle: Path, expected_version: str | None) -> list[str]:
    found: list[str] = []
    root = internal_dir(bundle)
    files = [p for p in bundle.rglob("*") if p.is_file()]
    for p in files:
        rel = p.relative_to(bundle).as_posix()
        parts = set(re.split(r"[/.\-_]", rel.lower()))
        if parts & set(FORBIDDEN_PARTS):
            found.append(f"forbidden framework: {rel}")
        if FORBIDDEN_QT.search(p.name):
            found.append(f"unused Qt module: {rel}")
        if is_ffmpeg(p) and GPL_FFMPEG.search(p.read_bytes()):
            found.append(f"FFmpeg library is not LGPL-only: {rel}")
    if not any(is_ffmpeg(p) for p in files):
        found.append("no FFmpeg libraries found (is av bundled?)")

    needed = [
        "notirua/resources/models/basic_pitch_nmp.onnx",
        "docs/LICENSES.md",
        "LICENSE",
        "locales/ko/LC_MESSAGES/notirua.mo",
    ]
    if sys.platform.startswith("linux"):
        needed.append("fonts")
    for rel in needed:
        if not (root / rel).exists():
            found.append(f"missing: {rel}")
    if list(root.glob("locales/en_XA")):
        found.append("pseudo-locale en_XA is bundled")
    if not list(root.glob("notirua-*.dist-info")):
        found.append("missing notirua package metadata (version)")
    if not list(root.rglob("qtbase_ko.qm")):
        found.append("missing Qt's own Korean translation (qtbase_ko.qm)")

    cli = cli_path(bundle)
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    run = subprocess.run([str(cli), "--version"], capture_output=True, text=True, env=env)
    if run.returncode != 0:
        found.append(f"notirua-cli --version failed: {run.stderr.strip()[-500:]}")
    elif expected_version and expected_version not in run.stdout:
        found.append(f"notirua-cli --version printed {run.stdout.strip()!r}")
    run = subprocess.run(
        [str(cli), "--lang", "ko", "languages"], capture_output=True, text=True, env=env
    )
    if run.returncode != 0 or "ko" not in run.stdout:
        found.append(f"notirua-cli languages failed: {(run.stdout + run.stderr).strip()[-500:]}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args()
    found = problems(args.bundle, args.version)
    for line in found:
        print("FAIL", line)
    if not found:
        print("bundle OK:", args.bundle)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
