"""Draw the Notirua app icon: a sound wave becoming beamed notes on a staff.

Usage: uv run python packaging/make_icon.py
Writes src/notirua/resources/icons/notirua-<size>.png (16-2048 px). Large
sizes are drawn at 4096 px and scaled down; small sizes are drawn directly so
edges stay crisp. The installers in M6 turn these into .icns and .ico.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QRadialGradient,
    QTransform,
)

SIZES = (16, 32, 48, 64, 128, 256, 512, 1024, 2048)
MASTER = 4096
OUT = Path(__file__).resolve().parents[1] / "src" / "notirua" / "resources" / "icons"
U = 1024.0  # design units

# Staff: five lines centred on the tile.
STAFF_TOP, STAFF_GAP = 392.0, 60.0
STAFF_LEFT, STAFF_RIGHT = 176.0, 848.0
STAFF_Y = [STAFF_TOP + i * STAFF_GAP for i in range(5)]


def squircle(rect: QRectF, exponent: float = 5.0, steps: int = 720) -> QPainterPath:
    """Continuous-corner tile (superellipse), like modern macOS and iOS icons."""
    cx, cy = rect.center().x(), rect.center().y()
    a, b = rect.width() / 2, rect.height() / 2
    path = QPainterPath()
    for i in range(steps + 1):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        x = cx + a * math.copysign(abs(c) ** (2 / exponent), c)
        y = cy + b * math.copysign(abs(s) ** (2 / exponent), s)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


TILE = squircle(QRectF(100, 100, 824, 824))


def wave_bars() -> QPainterPath:
    """Rounded bars of an audio level meter on the left half."""
    heights = [88, 196, 312, 236, 352, 176, 96]
    width, pitch, x0, cy = 30.0, 50.0, 196.0, 512.0
    path = QPainterPath()
    for i, h in enumerate(heights):
        path.addRoundedRect(QRectF(x0 + i * pitch, cy - h / 2, width, h), width / 2, width / 2)
    return path


def notes() -> QPainterPath:
    """Two beamed eighth notes as one outline so joins are clean."""
    rx, ry, tilt = 64.0, 46.0, -22.0
    stem_w, beam_h = 28.0, 60.0
    heads = [QPointF(606, STAFF_Y[3] + STAFF_GAP / 2), QPointF(774, STAFF_Y[2] + STAFF_GAP / 2)]
    edge = rx * math.cos(math.radians(tilt)) - 3
    stem_x = [h.x() + edge - stem_w for h in heads]
    # Beam: from the left stem's left edge to the right stem's right edge, rising.
    (x1, y1), (x2, y2) = (stem_x[0], 286.0), (stem_x[1] + stem_w, 232.0)

    def beam_top(x: float) -> float:
        return y1 + (y2 - y1) * (x - x1) / (x2 - x1)

    shape = QPainterPath()
    for head, x in zip(heads, stem_x, strict=True):
        ellipse = QPainterPath()
        ellipse.addEllipse(QPointF(0, 0), rx, ry)
        ellipse = QTransform().translate(head.x(), head.y()).rotate(tilt).map(ellipse)
        top = max(beam_top(x), beam_top(x + stem_w)) + 2  # never above the beam
        stem = QPainterPath()
        stem.addRect(QRectF(x, top, stem_w, head.y() - top - 6))
        shape = shape.united(ellipse).united(stem)
    beam = QPainterPath()
    beam.moveTo(x1, y1)
    beam.lineTo(x2, y2)
    beam.lineTo(x2, y2 + beam_h)
    beam.lineTo(x1, y1 + beam_h)
    beam.closeSubpath()
    return shape.united(beam)


def soft_shadow(shape: QPainterPath, size: int, offset: float, blur: float, alpha: int) -> QImage:
    """A blurred copy of ``shape``: drawn small, then scaled up smoothly.

    ``offset`` and ``blur`` are design units, so the look is the same at every size.
    """
    small_size = max(8, round(U / blur))
    small = QImage(small_size, small_size, QImage.Format.Format_ARGB32_Premultiplied)
    small.fill(Qt.GlobalColor.transparent)
    p = QPainter(small)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(small_size / U, small_size / U)
    p.translate(0, offset)
    p.fillPath(shape, QColor(28, 12, 80, alpha))
    p.end()
    return small.scaled(
        size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    detailed = size >= 64

    # Tile shadow, so the icon sits on the desktop rather than floating.
    if detailed:
        shade = soft_shadow(TILE, size, 12, 10, 80)
        p = QPainter(image)
        p.drawImage(0, 0, shade)
        p.end()

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / U, size / U)

    gradient = QLinearGradient(QPointF(100, 100), QPointF(924, 924))
    gradient.setColorAt(0.0, QColor("#5B5CF6"))
    gradient.setColorAt(0.55, QColor("#7C3AED"))
    gradient.setColorAt(1.0, QColor("#A21CAF"))
    p.fillPath(TILE, gradient)
    p.setClipPath(TILE)
    glow = QRadialGradient(QPointF(260, 180), 620)
    glow.setColorAt(0.0, QColor(255, 255, 255, 70))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(TILE, glow)

    line_w = 9.0
    staff = QPainterPath()
    # At 32 px and below the staff turns into noise, so the tiny icon drops it.
    for y in STAFF_Y if size > 32 else []:
        staff.addRoundedRect(
            QRectF(STAFF_LEFT, y - line_w / 2, STAFF_RIGHT - STAFF_LEFT, line_w),
            line_w / 2,
            line_w / 2,
        )
    fade = QLinearGradient(QPointF(STAFF_LEFT, 0), QPointF(STAFF_RIGHT, 0))
    fade.setColorAt(0.0, QColor(255, 255, 255, 0))
    fade.setColorAt(0.45, QColor(255, 255, 255, 95))
    fade.setColorAt(1.0, QColor(255, 255, 255, 120))
    p.fillPath(staff, fade)

    figure = notes()
    bars = wave_bars()
    p.end()

    if detailed:
        shade = soft_shadow(figure.united(bars), size, 14, 8, 90)
        p = QPainter(image)
        p.setClipPath(QTransform().scale(size / U, size / U).map(TILE))
        p.drawImage(0, 0, shade)
        p.end()

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / U, size / U)
    bar_fill = QLinearGradient(QPointF(196, 0), QPointF(520, 0))
    bar_fill.setColorAt(0.0, QColor(255, 255, 255, 150))
    bar_fill.setColorAt(1.0, QColor(255, 255, 255, 235))
    p.fillPath(bars, bar_fill)
    note_fill = QLinearGradient(QPointF(0, 200), QPointF(0, 760))
    note_fill.setColorAt(0.0, QColor("#FFFFFF"))
    note_fill.setColorAt(1.0, QColor("#EDE9FE"))
    p.fillPath(figure, note_fill)
    p.end()
    return image


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QGuiApplication.instance() or QGuiApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("notirua-*.png"):
        old.unlink()
    master = draw(MASTER)
    for size in SIZES:
        if size >= 256:
            image = master.scaled(
                size,
                size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            image = draw(size)
        target = OUT / f"notirua-{size}.png"
        image.save(str(target))
        print(target)


if __name__ == "__main__":
    main()
