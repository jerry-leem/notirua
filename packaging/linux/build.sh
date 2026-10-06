#!/usr/bin/env bash
# Build the Linux x86_64 bundle in Docker (M6), from macOS or Linux.
#   packaging/linux/build.sh            LGPL PyAV wheel (once), bundle, check, AppImage
# Outputs: dist/lgpl-av/av-*linux_x86_64.whl, dist/linux/app/Notirua,
#          dist/Notirua-<version>-linux-x86_64.AppImage
# The FFmpeg build and the uv cache live in Docker volumes, so reruns are fast.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE=notirua-linux-build

if [ ! -s "$ROOT/packaging/fonts/NotoSansCJKkr-Regular.otf" ]; then
    (cd "$ROOT" && uv run python packaging/fetch_fonts.py)
fi

docker build --platform linux/amd64 -t "$IMAGE" "$ROOT/packaging/linux"
docker run --rm --platform linux/amd64 \
    -v "$ROOT:/src" \
    -v notirua-linux-work:/work \
    -v notirua-linux-cache:/cache \
    -w /src \
    "$IMAGE" bash -euo pipefail -c '
        uv sync --locked
        if ! ls dist/lgpl-av/av-*linux_x86_64.whl >/dev/null 2>&1; then
            uv run python packaging/build_lgpl_av.py --work /work/lgpl-av
        fi
        uv run python packaging/build_app.py --venv /work/app-venv --dist dist/linux/app
        uv run python packaging/linux/make_appimage.py --app dist/linux/app/Notirua
    '
