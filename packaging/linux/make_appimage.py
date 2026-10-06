"""Pack the Linux bundle into an AppImage (M6). Runs inside the build image.

Usage: python packaging/linux/make_appimage.py [--app dist/linux/app/Notirua] [--out dist]

The AppImage starts the window with no arguments and the command line with
any (``Notirua.AppImage transcribe song.mp3 --out out``), like ``notirua``
from source.

An AppImage is the AppImage runtime (pinned, MIT) followed by a squashfs image
of the AppDir; this is what appimagetool does. appimagetool itself is not used:
being an AppImage, it does not start under x86_64 emulation (Docker on Apple
Silicon).
"""

from __future__ import annotations

import argparse
import shutil
import stat
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "build" / "appimage"

# (url, size, sha256)
RUNTIME = (
    "https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64",
    944_632,
    "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d",
)

APPRUN = """#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
if [ "$#" -eq 0 ]; then
    exec "$HERE/Notirua/Notirua"
fi
exec "$HERE/Notirua/notirua-cli" "$@"
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name=Notirua
Comment=Turn a song into sheet music and TAB
Comment[ko]=노래를 악보와 TAB으로 바꿉니다
Exec=Notirua %f
Icon=notirua
Categories=AudioVideo;Audio;
Terminal=false
"""


def fetch(spec: tuple[str, int, str], name: str) -> Path:
    from notirua.components.download import download

    url, size, sha256 = spec
    path = download(url, WORK / name, expected_size=size, sha256=sha256)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=ROOT / "dist" / "linux" / "app" / "Notirua")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()

    runtime = fetch(RUNTIME, "runtime-x86_64")
    appdir = WORK / "Notirua.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    appdir.mkdir(parents=True)
    shutil.copytree(args.app, appdir / "Notirua", symlinks=True)
    (appdir / "AppRun").write_text(APPRUN, encoding="utf-8")
    (appdir / "AppRun").chmod(0o755)
    (appdir / "notirua.desktop").write_text(DESKTOP, encoding="utf-8")
    icon = ROOT / "src" / "notirua" / "resources" / "icons" / "notirua-256.png"
    shutil.copy2(icon, appdir / "notirua.png")
    (appdir / ".DirIcon").symlink_to("notirua.png")

    image = args.out / f"Notirua-{version('notirua')}-linux-x86_64.AppImage"
    squashfs = WORK / "Notirua.squashfs"
    squashfs.unlink(missing_ok=True)
    subprocess.run(
        ["mksquashfs", str(appdir), str(squashfs), "-root-owned", "-noappend",
         "-comp", "zstd", "-b", "1M", "-quiet"],
        check=True,
    )  # fmt: skip
    with image.open("wb") as out:
        out.write(runtime.read_bytes())
        with squashfs.open("rb") as fs:
            shutil.copyfileobj(fs, out)
    image.chmod(0o755)
    squashfs.unlink()
    print(image, f"{image.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
