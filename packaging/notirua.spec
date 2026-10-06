# -*- mode: python ; coding: utf-8 -*-
# Release bundle (M6). Run through packaging/build_app.py, which prepares the
# build venv (LGPL PyAV wheel, compiled catalogs, icons) and checks the result.
#
# One onedir folder holds two programs sharing the same libraries:
#   Notirua      windowed app (Notirua.app on macOS)
#   notirua-cli  command line (a different name: macOS and Windows file
#                systems ignore case, so "notirua" would clash with "Notirua")
import os
import sys
from importlib.metadata import version
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).resolve().parent
PACKAGING = ROOT / "packaging"
ICON_DIR = Path(os.environ["NOTIRUA_ICON_DIR"])
VERSION = version("notirua")
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

datas = [
    (str(ROOT / "src/notirua/resources/models/basic_pitch_nmp.onnx"), "notirua/resources/models"),
    (str(ROOT / "src/notirua/resources/icons"), "notirua/resources/icons"),
    (str(ROOT / "docs/LICENSES.md"), "docs"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "licenses"), "licenses"),
    *copy_metadata("notirua"),  # notirua.__version__ reads it
]
for mo in sorted((ROOT / "locales").glob("*/LC_MESSAGES/notirua.mo")):
    lang = mo.parent.parent.name
    if lang != "en_XA":  # pseudo-locale, for testing only
        datas.append((str(mo), f"locales/{lang}/LC_MESSAGES"))
if IS_LINUX:
    # Linux has no CJK font we can count on (DECISIONS D8, D12).
    fonts = PACKAGING / "fonts"
    if not any(fonts.glob("*.otf")) and not any(fonts.glob("*.ttc")):
        raise SystemExit("packaging/fonts is empty: run packaging/fetch_fonts.py first")
    datas.append((str(fonts), "fonts"))

# Never bundled: frameworks Basic Pitch or music21 may try to import, and test tools.
EXCLUDES = [
    "torch", "tensorflow", "tflite_runtime", "coremltools", "matplotlib", "IPython",
    "jedi", "tkinter", "_tkinter", "pytest", "PIL", "pandas", "sympy",
]  # fmt: skip
# Qt modules Notirua does not use; QtPdf and QtPdfWidgets are the only add-ons.
EXCLUDES += [
    f"PySide6.{m}"
    for m in (
        "Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic", "Qt3DRender",
        "QtBluetooth", "QtCharts", "QtDataVisualization", "QtDesigner", "QtGraphs",
        "QtHelp", "QtHttpServer", "QtLocation", "QtMultimedia", "QtMultimediaWidgets",
        "QtNfc", "QtOpenGL", "QtOpenGLWidgets", "QtPositioning", "QtQml", "QtQuick",
        "QtQuick3D", "QtQuickControls2", "QtQuickWidgets", "QtRemoteObjects", "QtScxml",
        "QtSensors", "QtSerialBus", "QtSerialPort", "QtSpatialAudio", "QtSql",
        "QtStateMachine", "QtSvgWidgets", "QtTest", "QtTextToSpeech", "QtUiTools",
        "QtWebChannel", "QtWebEngineCore", "QtWebEngineQuick", "QtWebEngineWidgets",
        "QtWebSockets", "QtWebView", "QtXml",
    )
]  # fmt: skip


# The virtual keyboard input plugin pulls in QtQuick and QtQml (about 30 MB);
# Linux keeps its other input plugins (ibus, compose) for Korean input.
UNUSED_QT_BINARY = ("qtvirtualkeyboard", "QtVirtualKeyboard", "QtQuick", "QtQml")


def keep(entry):
    """Drop data and libraries Notirua never uses."""
    dest = entry[0].replace("\\", "/")
    if any(name in dest for name in UNUSED_QT_BINARY):
        return False
    # music21's bundled corpus (scores) is never used.
    if dest.startswith("music21/corpus/") and not dest.endswith(".py"):
        return False
    # Babel only names languages in their own language (language_name), so it
    # needs the base language files, not every region (ko, not ko_KR).
    if dest.startswith("babel/locale-data/"):
        stem = Path(dest).stem
        return "_" not in stem
    return True


def analysis(script):
    a = Analysis(
        [str(PACKAGING / script)],
        pathex=[str(ROOT / "src")],
        datas=datas,
        hiddenimports=["notirua.resources.models"],
        excludes=EXCLUDES,
        noarchive=False,
    )
    a.datas = [e for e in a.datas if keep(e)]
    a.binaries = [e for e in a.binaries if keep(e)]
    return a


gui = analysis("entry_gui.py")
cli = analysis("entry_cli.py")
icon = str(ICON_DIR / ("notirua.icns" if IS_MAC else "notirua.ico"))

gui_exe = EXE(
    PYZ(gui.pure),
    gui.scripts,
    [],
    exclude_binaries=True,
    name="Notirua",
    console=False,
    icon=icon,
    target_arch=None,
)
cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    [],
    exclude_binaries=True,
    name="notirua-cli",
    console=True,
    icon=icon,
)
coll = COLLECT(
    gui_exe,
    cli_exe,
    gui.binaries,
    gui.datas,
    cli.binaries,
    cli.datas,
    name="Notirua",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="Notirua.app",
        icon=icon,
        bundle_identifier="io.github.jerry-leem.notirua",
        version=VERSION,
        info_plist={
            "CFBundleName": "Notirua",
            "CFBundleDisplayName": "Notirua",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "14.0",  # DECISIONS D13
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Copyright (c) Jerry Leem. MIT License.",
        },
    )
