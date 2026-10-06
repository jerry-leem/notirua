"""M0-S5/S6 spike: minimal bundled app.

Opens an empty Qt window (or runs headless with --smoke), runs one ONNX
inference with the bundled Basic Pitch model, decodes audio with PyAV, and
switches the gettext language to prove catalogs load inside the bundle.
"""

from __future__ import annotations

import sys

import numpy as np


def smoke() -> int:
    import av

    # CI pipes stdout with the ANSI code page on Windows; the Korean line below needs UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from notirua import i18n
    from notirua.core.runtime import make_session
    from notirua.core.transcribe.pitched import default_model_path

    session = make_session(default_model_path(), accelerate=False)
    x = np.zeros((1, 43844, 1), dtype=np.float32)
    outputs = session.run(None, {"serving_default_input_2:0": x})
    print("onnx ok", [o.shape for o in outputs])
    print("pyav", av.__version__)
    print("languages", i18n.available_languages())
    i18n.set_language("en")
    english = i18n._("Piano")
    i18n.set_language("ko")
    korean = i18n._("Piano")
    print("i18n", english, "->", korean)
    return 0 if korean != english else 1


def gui() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication(sys.argv)
    label = QLabel("Notirua bundle spike")
    label.resize(320, 120)
    label.show()
    if "--quit" in sys.argv:
        QTimer.singleShot(1500, app.quit)
    return app.exec()


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        raise SystemExit(smoke())
    code = smoke()
    raise SystemExit(code or gui())
