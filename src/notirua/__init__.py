"""Notirua: turn a song into sheet music and tablature PDFs.

The version follows Semantic Versioning (https://semver.org) and has one
source, ``version`` in ``pyproject.toml``; ``__version__`` reads it from the
installed package metadata.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "Notirua"

try:
    __version__ = version("notirua")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

APP_TITLE = f"{APP_NAME} {__version__}"
