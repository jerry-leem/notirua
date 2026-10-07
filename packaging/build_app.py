"""Build the Notirua bundle for this platform (M6).

Usage: uv run python packaging/build_app.py [--av-wheel PATH] [--skip-check]

1. Creates a clean build venv (``build/app-venv``) from ``uv.lock`` with the
   runtime and build dependencies, but takes PyAV from the LGPL-only wheel
   made by ``build_lgpl_av.py`` instead of PyPI (DECISIONS D13).
2. Installs Notirua itself (not editable, so its metadata can be bundled).
3. Compiles the message catalogs and packs the icons.
4. Runs PyInstaller with ``packaging/notirua.spec`` into ``dist/app``.
5. Runs ``check_bundle.py`` on the result.

Signing, notarization, and installers are separate steps.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

import icons  # noqa: E402
import versioning  # noqa: E402

# Wheel platform tag fragments per platform (``build_lgpl_av.py`` output names). A Python
# built as universal2 (the python.org installer, found on CI runners) makes a universal2
# wheel; its slice for this machine is what the bundle uses.
WHEEL_TAGS = {
    ("darwin", "arm64"): ("macosx_14_0_arm64", "macosx_14_0_universal2"),
    ("darwin", "x86_64"): ("macosx_14_0_x86_64", "macosx_14_0_universal2"),
    ("linux", "x86_64"): ("linux*_x86_64",),
    ("win32", "AMD64"): ("win_amd64",),
}


def run(cmd: list[str | Path], **kwargs: object) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)  # type: ignore[call-overload]


def find_av_wheel() -> Path:
    tags = WHEEL_TAGS.get((sys.platform, platform.machine()))
    if tags is None:
        raise SystemExit(f"no LGPL PyAV build for {sys.platform} {platform.machine()}")
    folder = ROOT / "dist" / "lgpl-av"
    for tag in tags:  # the first tag that has a wheel wins
        wheels = sorted(folder.glob(f"av-*{tag}*.whl"))
        if wheels:
            return wheels[-1]
    raise SystemExit(
        f"no LGPL PyAV wheel ({', '.join('*' + t + '*' for t in tags)}) in dist/lgpl-av: "
        "run packaging/build_lgpl_av.py"
    )


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def prepare_venv(venv: Path, av_wheel: Path) -> Path:
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required")
    if venv.exists():
        shutil.rmtree(venv)
    run([uv, "venv", "--python", "3.11", venv])
    python = venv_python(venv)
    requirements = venv.parent / "app-requirements.txt"
    run(
        [uv, "export", "--frozen", "--no-dev", "--group", "build", "--no-emit-project",
         "--no-hashes", "--output-file", requirements],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )  # fmt: skip
    lines = requirements.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.startswith("av==")]
    if len(kept) == len(lines):
        raise SystemExit("av is missing from the exported requirements")
    requirements.write_text("\n".join(kept) + "\n", encoding="utf-8")
    run([uv, "pip", "install", "--python", python, "-r", requirements])
    # Rebuild Notirua from the current source: a cached wheel of an older version
    # must never end up in the bundle.
    run(
        [uv, "pip", "install", "--python", python, "--no-deps", "--refresh-package", "notirua",
         "--reinstall-package", "notirua", av_wheel, ROOT],
    )  # fmt: skip
    return python


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--av-wheel", type=Path)
    parser.add_argument("--venv", type=Path, default=ROOT / "build" / "app-venv")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist" / "app")
    parser.add_argument("--skip-check", action="store_true")
    args = parser.parse_args()

    python = prepare_venv(args.venv, args.av_wheel or find_av_wheel())
    run([python, "-m", "babel.messages.frontend", "compile", "-d", "locales", "-D", "notirua"],
        cwd=ROOT)  # fmt: skip
    icon_dir = ROOT / "build" / f"icons-{sys.platform}"
    icons.write(icon_dir)
    env = {**os.environ, "NOTIRUA_ICON_DIR": str(icon_dir)}
    run(
        [python, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", args.dist, "--workpath", ROOT / "build" / f"pyinstaller-{sys.platform}",
         ROOT / "packaging" / "notirua.spec"],
        cwd=ROOT,
        env=env,
    )  # fmt: skip
    bundle = args.dist / ("Notirua.app" if sys.platform == "darwin" else "Notirua")
    if args.skip_check:
        return 0
    version = versioning.project_version()  # not the build venv: it must not vouch for itself
    check = [python, ROOT / "packaging" / "check_bundle.py", bundle, "--version", version]
    return subprocess.run([str(c) for c in check]).returncode


if __name__ == "__main__":
    sys.exit(main())
