# Linux release build environment (M6). Ubuntu 20.04 has glibc 2.31, the
# oldest Notirua supports (DECISIONS D14), so everything built here also runs
# on newer distributions.
#   docker build --platform linux/amd64 -t notirua-linux-build packaging/linux
#   packaging/linux/build.sh   (runs the whole build in this image)
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    QT_QPA_PLATFORM=offscreen \
    UV_PROJECT_ENVIRONMENT=/opt/notirua-venv \
    UV_CACHE_DIR=/cache/uv \
    UV_LINK_MODE=copy

# Compilers and tools for FFmpeg and PyAV; binutils/file for PyInstaller;
# the X11/xcb, EGL, fontconfig, and D-Bus libraries Qt's plugins link to, so
# PyInstaller can resolve and bundle them.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config nasm ca-certificates curl git file binutils \
        xz-utils squashfs-tools desktop-file-utils \
        libegl1 libgl1 libglib2.0-0 libatomic1 libxkbcommon0 libxkbcommon-x11-0 \
        libfontconfig1 libfreetype6 libx11-6 libx11-xcb1 libdbus-1-3 zlib1g libzstd1 \
        libxcb1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
        libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-xfixes0 \
        libxcb-shm0 libxcb-sync1 libxcb-render0 libxcb-util1 \
    && rm -rf /var/lib/apt/lists/*

# FFmpeg 8.1's assembly needs NASM 2.15 or newer; Ubuntu 20.04 has 2.14.
# Qt 6.5+ needs libxcb-cursor for its X11 plugin; Ubuntu 20.04 has none, so it
# is built here and bundled (MIT/X11 license).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxcb1-dev libxcb-render0-dev libxcb-render-util0-dev libxcb-image0-dev \
        libxcb-shm0-dev xutils-dev m4 \
    && rm -rf /var/lib/apt/lists/* \
    && cd /tmp \
    && curl -fsSLO https://www.nasm.us/pub/nasm/releasebuilds/2.16.03/nasm-2.16.03.tar.xz \
    && echo "1412a1c760bbd05db026b6c0d1657affd6631cd0a63cddb6f73cc6d4aa616148  nasm-2.16.03.tar.xz" \
        | sha256sum -c - \
    && tar xf nasm-2.16.03.tar.xz && (cd nasm-2.16.03 && ./configure --prefix=/usr/local \
        && make -j"$(nproc)" && make install) \
    && curl -fsSLO https://xorg.freedesktop.org/archive/individual/lib/xcb-util-cursor-0.1.5.tar.xz \
    && echo "0caf99b0d60970f81ce41c7ba694e5eaaf833227bb2cbcdb2f6dc9666a663c57  xcb-util-cursor-0.1.5.tar.xz" \
        | sha256sum -c - \
    && tar xf xcb-util-cursor-0.1.5.tar.xz && (cd xcb-util-cursor-0.1.5 \
        && ./configure --prefix=/usr/local && make -j"$(nproc)" && make install) \
    && ldconfig && rm -rf /tmp/* && nasm -v

# auditwheel needs patchelf 0.14.5 or newer; Ubuntu 20.04 has 0.10.
RUN curl -fsSLo /tmp/patchelf.tar.gz \
        https://github.com/NixOS/patchelf/releases/download/0.18.0/patchelf-0.18.0-x86_64.tar.gz \
    && echo "ce84f2447fb7a8679e58bc54a20dc2b01b37b5802e12c57eece772a6f14bf3f0  /tmp/patchelf.tar.gz" \
        | sha256sum -c - \
    && tar xzf /tmp/patchelf.tar.gz -C /usr/local ./bin/patchelf && rm /tmp/patchelf.tar.gz \
    && patchelf --version

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /usr/local/bin/
RUN uv python install 3.11
