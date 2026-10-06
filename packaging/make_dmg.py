"""Sign, notarize, and pack Notirua.app into a disk image (macOS, M6).

Usage: python packaging/make_dmg.py [--app dist/app/Notirua.app] [--out dist]

Signing and notarization run only when their secrets exist (SPEC 7.3,
DECISIONS D17); without them the result is an unsigned image for testing.

- ``NOTIRUA_MACOS_SIGN_IDENTITY``: a "Developer ID Application: ..." identity
  in the keychain. Signs every binary with the hardened runtime.
- ``NOTIRUA_NOTARY_PROFILE``: a ``notarytool store-credentials`` profile name.
  Notarizes the signed image and staples the ticket.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITLEMENTS = ROOT / "packaging" / "entitlements.plist"


def run(cmd: list[str | Path]) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def app_version(app: Path) -> str:
    out = subprocess.run(
        ["/usr/libexec/PlistBuddy", "-c", "Print CFBundleShortVersionString",
         str(app / "Contents" / "Info.plist")],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return out.stdout.strip()


def sign(app: Path, identity: str) -> None:
    """Sign inner binaries first, then the app (``--deep`` is unreliable)."""
    binaries = [
        p
        for p in app.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and (p.suffix in (".so", ".dylib") or os.access(p, os.X_OK))
        and "Contents/MacOS" not in p.as_posix()
    ]
    base = ["codesign", "--force", "--timestamp", "--options", "runtime", "--sign", identity]
    for p in binaries:
        run([*base, p])
    for p in sorted((app / "Contents" / "MacOS").iterdir()):
        run([*base, "--entitlements", ENTITLEMENTS, p])
    run([*base, "--entitlements", ENTITLEMENTS, app])
    run(["codesign", "--verify", "--strict", "--verbose=2", app])


def make_dmg(app: Path, dmg: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "Notirua"
        stage.mkdir()
        run(["ditto", app, stage / app.name])
        (stage / "Applications").symlink_to("/Applications")
        dmg.unlink(missing_ok=True)
        run(["hdiutil", "create", "-volname", "Notirua", "-srcfolder", stage,
             "-fs", "HFS+", "-format", "UDZO", "-ov", dmg])  # fmt: skip


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("make_dmg.py runs on macOS only")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=ROOT / "dist" / "app" / "Notirua.app")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()

    arch = "arm64" if platform.machine() == "arm64" else "x86_64"
    dmg = args.out / f"Notirua-{app_version(args.app)}-macos-{arch}.dmg"
    identity = os.environ.get("NOTIRUA_MACOS_SIGN_IDENTITY")
    profile = os.environ.get("NOTIRUA_NOTARY_PROFILE")
    if identity:
        sign(args.app, identity)
    else:
        print("NOTIRUA_MACOS_SIGN_IDENTITY not set: the image is unsigned")
    make_dmg(args.app, dmg)
    if identity:
        run(["codesign", "--force", "--timestamp", "--sign", identity, dmg])
    if identity and profile:
        run(["xcrun", "notarytool", "submit", dmg, "--keychain-profile", profile, "--wait"])
        run(["xcrun", "stapler", "staple", dmg])
    elif identity:
        print("NOTIRUA_NOTARY_PROFILE not set: the image is signed but not notarized")
    print(dmg, f"{dmg.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
