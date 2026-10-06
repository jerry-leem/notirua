"""English-only rotating log in the user log folder (NFR-5)."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from notirua import paths


def ensure_std_streams() -> None:
    """Give a windowed app (no console) real ``stdout``/``stderr``.

    PyInstaller's windowed Windows build leaves both as ``None``; libraries that
    print warnings (music21 imports) then crash with "'NoneType' has no 'write'".
    """
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115


def configure(verbose: bool = False) -> None:
    ensure_std_streams()
    root = logging.getLogger()
    if any(getattr(h, "_notirua", False) for h in root.handlers):
        return
    root.setLevel(logging.DEBUG)
    try:
        log_dir = paths.log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "notirua.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        file_handler._notirua = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)
    except OSError:
        pass
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    console._notirua = True  # type: ignore[attr-defined]
    root.addHandler(console)
