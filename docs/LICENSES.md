# Third-party licenses

Notirua itself is released under the MIT License (`LICENSE`).

Everything Notirua bundles or downloads, with source and license. This table
is also shown on the app's About screen (M4). Non-commercial (CC BY-NC*) or
unlicensed components are never included (SPEC 7.4).

## Bundled in the installer

| Component | Version | License | Source |
|---|---|---|---|
| Python | 3.11 | PSF-2.0 | https://www.python.org |
| Basic Pitch model + vendored inference code | 0.4.0 (icassp_2022) | Apache-2.0 (`licenses/basic-pitch/`) | https://github.com/spotify/basic-pitch |
| demucs-onnx overlap-add loop (adapted) | 0.3.4 | MIT | https://github.com/StemSplit/demucs-onnx |
| numpy | 2.x | BSD-3-Clause | https://numpy.org |
| scipy | 1.x | BSD-3-Clause | https://scipy.org |
| ONNX Runtime | 1.30 | MIT | https://onnxruntime.ai |
| PyAV | 18.1 | BSD-3-Clause | https://github.com/PyAV-Org/PyAV |
| FFmpeg (built by `packaging/build_lgpl_av.py`, decoders only) | 8.1.2 | LGPL-2.1-or-later (no GPL or nonfree parts; D13) | https://ffmpeg.org |
| python-soxr / libsoxr | 1.1 | LGPL-2.1+ | https://github.com/dofuuz/python-soxr |
| platformdirs | 4.x | MIT | https://github.com/tox-dev/platformdirs |
| Babel | 2.18 | BSD-3-Clause | https://babel.pocoo.org |
| music21 | 10.x | BSD-3-Clause | https://github.com/cuthbertLab/music21 |
| PySide6 / Qt 6 (Essentials + QtPdf from Addons) | 6.9 | LGPL-3.0 (dynamically linked) | https://www.qt.io/qt-for-python |
| Noto Sans CJK KR (Linux build only) | Sans2.004 | OFL-1.1 (`licenses/noto-cjk/`) | https://github.com/notofonts/noto-cjk |
| PDFium (inside QtPdf) | Qt 6.9 | BSD-3-Clause | https://pdfium.googlesource.com/pdfium |

## Downloaded on first run (with consent)

| Component | Version | License | Source |
|---|---|---|---|
| HT-Demucs 6-stem ONNX (`htdemucs_6s.onnx`) | HF rev `49df9b6` | MIT | https://huggingface.co/StemSplitio/htdemucs-6s-onnx |
| LilyPond (separate process) | 2.26.0 | GPL-3.0-or-later | https://lilypond.org |
| URW base35 fonts (inside LilyPond) | — | AGPL-3.0 with font exception | https://github.com/ArtifexSoftware/urw-base35-fonts |

## Build and test only (not distributed)

pytest, pytest-qt, pypdf, ruff, mypy, PyInstaller (GPL-2.0 with bootloader exception).

## Explicitly excluded

| Component | Reason |
|---|---|
| ADTOF drum models | CC BY-NC-SA 4.0 (non-commercial) |
| TensorFlow, PyTorch | bundle size (SPEC 2); not needed at runtime |
