"""Change the app version everywhere it is written down.

Usage: uv run python scripts/bump_version.py 0.4.2

Updates ``version`` in pyproject.toml, runs ``uv lock`` so uv.lock follows, and
rewrites the README sentences that state the current version. Installers, window
titles, ``--version``, and release file names read the version from
pyproject.toml when they are built, and tests/test_versions.py fails if any copy
drifts. Links to a specific release in the README are edited by hand.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

import versioning  # noqa: E402

VERSION_LINE = re.compile(r'(?m)^(version = ")[^"]+(")')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="new version, MAJOR.MINOR.PATCH")
    args = parser.parse_args()
    if not versioning.SEMVER.fullmatch(args.version):
        print(f"not a MAJOR.MINOR.PATCH version: {args.version!r}", file=sys.stderr)
        return 2
    old = versioning.project_version()

    text = versioning.PYPROJECT.read_text(encoding="utf-8")
    text, count = VERSION_LINE.subn(rf"\g<1>{args.version}\g<2>", text, count=1)
    if count != 1:
        print('no `version = "..."` line in pyproject.toml', file=sys.stderr)
        return 1
    versioning.PYPROJECT.write_text(text, encoding="utf-8")

    readme = versioning.README.read_text(encoding="utf-8")
    versioning.README.write_text(versioning.sync_readme(readme, args.version), encoding="utf-8")

    subprocess.run(["uv", "lock"], cwd=ROOT, check=True)
    print(f"{old} -> {args.version}")
    print("Next: commit, merge, then tag v" + args.version + " (the release build checks the tag).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
