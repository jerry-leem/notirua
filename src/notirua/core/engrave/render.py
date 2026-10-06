"""Run LilyPond as a separate, time-limited process (SPEC 6.6) behind :class:`Engraver`."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from notirua.core.engrave.lilypond import ly_string
from notirua.core.errors import EngraveError, EngraveTimeoutError
from notirua.core.progress import CancelToken

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 180.0
_ERROR_LINE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+): (?:fatal )?error: (?P<msg>.*)$", re.M
)


class Engraver(Protocol):
    def engrave(
        self,
        source: str,
        out_pdf: Path,
        cancel: CancelToken | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> Path: ...


def bundled_fonts_dir() -> Path | None:
    """Fonts shipped with the app (Noto Sans CJK on Linux, DECISIONS D8), if any.

    ``NOTIRUA_FONTS_DIR`` overrides; a frozen app looks in ``<bundle>/fonts``;
    a source checkout uses ``packaging/fonts`` filled by ``packaging/fetch_fonts.py``.
    """
    env = os.environ.get("NOTIRUA_FONTS_DIR")
    bundle_root = getattr(sys, "_MEIPASS", None)
    if env:
        candidate = Path(env)
    elif bundle_root:
        candidate = Path(bundle_root) / "fonts"
    else:
        candidate = Path(__file__).resolve().parents[4] / "packaging" / "fonts"
    if candidate.is_dir() and any(candidate.glob("*.otf")):
        return candidate
    return None


def with_font_dirs(source: str, font_dirs: Sequence[Path]) -> str:
    """Let LilyPond's fontconfig see extra font folders before anything is drawn."""
    lines = [
        f"#(ly:font-config-add-directory {ly_string(d.resolve().as_posix())})" for d in font_dirs
    ]
    return "\n".join([*lines, source]) if lines else source


def parse_errors(stderr: str) -> list[str]:
    return [f"line {m['line']}: {m['msg']}" for m in _ERROR_LINE.finditer(stderr)]


class LilyPondEngraver:
    def __init__(self, executable: Path, font_dirs: Sequence[Path] = ()) -> None:
        self.executable = executable
        self.font_dirs = list(font_dirs)

    def version(self) -> str:
        result = subprocess.run(
            [str(self.executable), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=_creationflags(),
        )
        return result.stdout.splitlines()[0] if result.stdout else ""

    def engrave(
        self,
        source: str,
        out_pdf: Path,
        cancel: CancelToken | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> Path:
        """Render ``source`` to ``out_pdf``.

        LilyPond runs in a temporary ASCII-named folder; the PDF is moved to its
        final (possibly non-ASCII) path by Python, which avoids code-page issues
        on Windows.
        """
        with tempfile.TemporaryDirectory(prefix="notirua-ly-") as tmp:
            work = Path(tmp)
            (work / "score.ly").write_text(with_font_dirs(source, self.font_dirs), encoding="utf-8")
            cmd = [str(self.executable), "-s", "-dno-point-and-click", "-o", "score", "score.ly"]
            env = dict(os.environ)
            env.setdefault("LANG", "en_US.UTF-8")
            started = time.monotonic()
            proc = subprocess.Popen(
                cmd,
                cwd=work,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=_creationflags(),
            )
            try:
                while True:
                    try:
                        _stdout_b, stderr_b = proc.communicate(timeout=0.25)
                        break
                    except subprocess.TimeoutExpired:
                        if cancel is not None and cancel.cancelled:
                            proc.kill()
                            proc.communicate()
                            cancel.raise_if_cancelled()
                        if time.monotonic() - started > timeout_s:
                            proc.kill()
                            proc.communicate()
                            raise EngraveTimeoutError(f"after {timeout_s:.0f}s") from None
            finally:
                if proc.poll() is None:
                    proc.kill()
            stderr = stderr_b.decode("utf-8", errors="replace")
            pdf = work / "score.pdf"
            if proc.returncode != 0 or not pdf.is_file():
                errors = parse_errors(stderr)
                log.error("lilypond failed (%s): %s", proc.returncode, stderr[-4000:])
                raise EngraveError("; ".join(errors[:3]) or f"exit code {proc.returncode}")
            if stderr.strip():
                log.debug("lilypond warnings: %s", stderr[-2000:])
            out_pdf.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(pdf), str(out_pdf))
            return out_pdf


def _creationflags() -> int:
    return 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
