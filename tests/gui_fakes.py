"""Fake engines and helpers shared by the GUI tests."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPainter, QPdfWriter

from notirua import settings as settings_mod
from notirua.components.manager import ComponentManager
from notirua.core.errors import EngraveError
from notirua.core.pipeline import Engines, Pipeline
from notirua.core.progress import CancelToken
from tests.test_pipeline import Counter, FakeDrums, FakeSeparator, FakeTranscriber


def make_pdf(path: Path) -> bytes:
    """A real two-page PDF so QtPdf can load the preview (needs a QApplication)."""
    writer = QPdfWriter(str(path))
    painter = QPainter(writer)
    painter.drawText(200, 200, "page 1")
    writer.newPage()
    painter.drawText(200, 200, "page 2")
    painter.end()
    return path.read_bytes()


class PdfEngraver:
    def __init__(self, counter: Counter, data: bytes) -> None:
        self.counter = counter
        self.data = data
        self.fail = False

    def engrave(
        self, source: str, out_pdf: Path, cancel: CancelToken | None = None, timeout_s: float = 0
    ) -> Path:
        if self.fail:
            raise EngraveError("broken on purpose")
        self.counter.engrave += 1
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        out_pdf.write_bytes(self.data)
        return out_pdf


class FakeJob:
    def __init__(self, tmp_path: Path, pdf: bytes) -> None:
        self.counter = Counter()
        self.delay = 0.0
        self.engraver = PdfEngraver(self.counter, pdf)
        engines = Engines(
            separator=lambda: FakeSeparator(self.counter, self.delay),
            pitched=lambda: FakeTranscriber(self.counter),
            drums=FakeDrums,
            engraver=lambda: self.engraver,
        )
        self.pipeline = Pipeline(engines, cache_root=tmp_path / "cache")


def no_components(user: settings_mod.Settings) -> ComponentManager:
    m = ComponentManager(user.components_path, platform_key="linux-x86_64")
    m.components = []
    return m
