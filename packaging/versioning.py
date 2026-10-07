"""The one place that knows where the version lives and where it is repeated.

``version`` in ``pyproject.toml`` is the only source. Everything else is derived
from it or checked against it:

* the app reads it from the installed package metadata (``notirua.__version__``);
* ``uv.lock`` records it for the project itself;
* the README states the current version in a few sentences (``README_PATTERNS``);
* a release build compares the version of the bundled metadata and the Git tag
  with it, so a stale value can never be shipped.

Usage:
    python packaging/versioning.py                 # print the version
    python packaging/versioning.py --tag v0.4.1    # exit 1 unless the tag matches
    python packaging/versioning.py --notes         # release notes with the version filled in
Change the version with ``scripts/bump_version.py``.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"
LOCK = ROOT / "uv.lock"
RELEASE_NOTES = ROOT / "packaging" / "release_notes.md"
SEMVER = re.compile(r"\d+\.\d+\.\d+")

# README sentences that state the *current* version, in Korean and English.
# Links to a particular release (download tables) are chosen by hand and not listed.
# Each pattern keeps group 1 (before the version) and group 2 (after it).
README_PATTERNS = (
    re.compile(r"(현재 버전은 \*\*)\d+\.\d+\.\d+(\*\*)"),
    re.compile(r"(The current version is \*\*)\d+\.\d+\.\d+(\*\*)"),
    re.compile(r"(# notirua )\d+\.\d+\.\d+()"),
    re.compile(r"(`Notirua )\d+\.\d+\.\d+(`)"),
)


def project_version(pyproject: Path = PYPROJECT) -> str:
    return str(tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"])


def lock_version(lock: Path = LOCK) -> str | None:
    """The version ``uv.lock`` records for the project itself."""
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    for package in data.get("package", []):
        if package.get("name") == "notirua":
            return str(package["version"])
    return None


def readme_versions(text: str) -> list[list[str]]:
    """Versions found by each README pattern (an empty list means the sentence is gone)."""
    found = []
    for pattern in README_PATTERNS:
        found.append([m.group(0)[len(m.group(1)) : len(m.group(0)) - len(m.group(2))]
                      for m in pattern.finditer(text)])  # fmt: skip
    return found


def sync_readme(text: str, version: str) -> str:
    for pattern in README_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}{version}{m.group(2)}", text)
    return text


def render_notes(version: str) -> str:
    """Release notes ready to paste: ``{{version}}`` filled in, plain ``\\n`` line ends."""
    notes = RELEASE_NOTES.read_text(encoding="utf-8").replace("{{version}}", version)
    return notes.replace("⁣", "")  # an invisible separator breaks ``` fences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="fail unless this Git tag is v<version>")
    parser.add_argument("--notes", action="store_true", help="print the release notes")
    args = parser.parse_args()
    version = project_version()
    if args.tag is not None:
        if args.tag != f"v{version}":
            print(
                f"tag {args.tag!r} does not match pyproject.toml version {version!r}: "
                "bump the version (scripts/bump_version.py) before tagging",
                file=sys.stderr,
            )
            return 1
    elif args.notes:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")
        print(render_notes(version), end="")
    else:
        print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
