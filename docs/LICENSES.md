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
| FFmpeg (built by `packaging/build_lgpl_av.py`: decoders, plus AAC, MP3, and WAV saving) | 8.1.2 | LGPL-2.1-or-later (no GPL or nonfree parts; D13) | https://ffmpeg.org |
| LAME (libmp3lame, linked into FFmpeg's libavcodec for MP3 saving) | 3.100 | LGPL-2.0-or-later | https://lame.sourceforge.io |
| python-soxr / libsoxr | 1.1 | LGPL-2.1+ | https://github.com/dofuuz/python-soxr |
| platformdirs | 4.x | MIT | https://github.com/tox-dev/platformdirs |
| Babel | 2.18 | BSD-3-Clause | https://babel.pocoo.org |
| music21 | 10.x | BSD-3-Clause | https://github.com/cuthbertLab/music21 |
| yt-dlp (reads YouTube links; 0.5.0) | 2026.8.19 | Unlicense (`licenses/yt-dlp/`) | https://github.com/yt-dlp/yt-dlp |
| yt-dlp-ejs (scripts that answer YouTube's player check) | 0.8.0 | Unlicense, MIT, and ISC (`licenses/yt-dlp-ejs/`) | https://github.com/yt-dlp/ejs |
| certifi (CA certificates for HTTPS) | 2026.7 | MPL-2.0 (`licenses/certifi/`) | https://github.com/certifi/python-certifi |
| PySide6 / Qt 6 (Essentials + QtPdf from Addons) | 6.9 | LGPL-3.0 (dynamically linked) | https://www.qt.io/qt-for-python |
| Noto Sans CJK KR (Linux build only) | Sans2.004 | OFL-1.1 (`licenses/noto-cjk/`) | https://github.com/notofonts/noto-cjk |
| PDFium (inside QtPdf) | Qt 6.9 | BSD-3-Clause | https://pdfium.googlesource.com/pdfium |

## Downloaded on first run (with consent)

| Component | Version | License | Source |
|---|---|---|---|
| HT-Demucs 6-stem ONNX (`htdemucs_6s.onnx`) | HF rev `49df9b6` | MIT | https://huggingface.co/StemSplitio/htdemucs-6s-onnx |
| LilyPond (separate process) | 2.26.0 | GPL-3.0-or-later | https://lilypond.org |
| URW base35 fonts (inside LilyPond) | — | AGPL-3.0 with font exception | https://github.com/ArtifexSoftware/urw-base35-fonts |

### Optional, only if you use YouTube links (asked for first, with consent)

| Component | Version | License | Source |
|---|---|---|---|
| Deno (a JavaScript runtime that yt-dlp starts as a separate process) | 2.9.7 | MIT (`licenses/deno/`) | https://github.com/denoland/deno |

## Build and test only (not distributed)

pytest, pytest-qt, pypdf, markdown-it-py, ruff, mypy, PyInstaller (GPL-2.0 with bootloader exception).

## Explicitly excluded

| Component | Reason |
|---|---|
| ADTOF drum models | CC BY-NC-SA 4.0 (non-commercial) |
| TensorFlow, PyTorch | bundle size (SPEC 2); not needed at runtime |
