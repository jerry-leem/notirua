"""English-only rotating log in the user log folder (NFR-5)."""

from __future__ import annotations

import logging
import logging.handlers

from notirua import paths


def configure(verbose: bool = False) -> None:
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
