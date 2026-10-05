# -*- mode: python ; coding: utf-8 -*-
# M0-S5 spike spec. Build: uv run pyinstaller --noconfirm spikes/s5_bundle/s5.spec
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]

a = Analysis(
    [str(ROOT / "spikes" / "s5_bundle" / "app.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(ROOT / "src" / "notirua" / "resources" / "models" / "basic_pitch_nmp.onnx"), "notirua/resources/models"),
        (str(ROOT / "locales"), "locales"),
    ],
    hiddenimports=["notirua.resources.models"],
    excludes=["torch", "tensorflow", "matplotlib", "music21", "tkinter", "PySide6.QtWebEngineCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="notirua-spike", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="notirua-spike")
