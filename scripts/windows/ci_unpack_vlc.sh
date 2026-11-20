#!/bin/bash
# CI's Windows tests on arm64: the VLC the package bundles, for
# BUILD_WIN_ARCH, unpacked into build/vlc and given to the app by
# PYTHON_VLC_LIB_PATH. Chocolatey has only the x64 VLC, which an arm64
# Python can't load.

set -e

. "scripts/windows/vlc_pins.sh"

mkdir -p build/vlc
curl -fsSL -o "build/$VLC_ARCHIVE" "$VLC_URL"
echo "$VLC_SHA256 *build/$VLC_ARCHIVE" | sha256sum -c -
unzip -q -o "build/$VLC_ARCHIVE" -d build/vlc

libvlc="$PWD/build/vlc/vlc-$VLC_VERSION/libvlc.dll"
test -f "$libvlc"
echo "PYTHON_VLC_LIB_PATH=$(cygpath -w "$libvlc")" >> "$GITHUB_ENV"
