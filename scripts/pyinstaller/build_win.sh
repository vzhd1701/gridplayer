#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

# Get machine architecture
if [ -z "$BUILD_ARCH" ]; then
    BUILD_ARCH=$(python -c "import platform; print('win32' if platform.architecture()[0] == '32bit' else 'win64')")
fi

if [ "$BUILD_ARCH" = "win32" ]; then
    die "The mpv build is 64-bit only so far"
fi

MPV_URL="https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20261109/mpv-dev-x86_64-20261109-git-8bc468896e.7z"
MPV_SHA256="4e888424015f7146893d03c4d40e2aaf9474d8d47e761bcc6a97489008a7e425"
PYINSTALLER_VERSION="6.22.3"

mkdir -p "$BUILD_DIR"

init_venv "$BUILD_DIR/venv-pyinstaller"

# Reduce size by installing src version of pydantic
export PIP_NO_BINARY="pydantic"

REQUIREMENTS="$BUILD_DIR/requirements.txt"

# curl-cffi has no 32-bit Windows wheel, and its sdist builds against a
# libcurl DLL that nothing bundles, so yt-dlp goes without browser
# impersonation in that build
if [ "$BUILD_ARCH" = "win32" ]; then
    REQUIREMENTS="$BUILD_DIR/requirements-win32.txt"
    grep -v "^curl-cffi==" "$BUILD_DIR/requirements.txt" > "$REQUIREMENTS"
fi

pip install -r "$REQUIREMENTS"
pip install pyinstaller=="$PYINSTALLER_VERSION"

# Copy icons to build dir
cp "$RESOURCES_DIR/icons/main/sys/windows.ico" "$BUILD_DIR/main.ico"
cp "$RESOURCES_DIR/icons/playlist/sys/windows.ico" "$BUILD_DIR/mime.ico"

# Make version_info
copy_with_app_vars "$SCRIPT_DIR/version_info.py" "$BUILD_DIR"

copy_with_app_vars "$SCRIPT_DIR/pyinstaller_win.spec" "$BUILD_DIR/$APP_NAME.spec"

pyinstaller --clean --noconfirm "$BUILD_DIR/$APP_NAME.spec"

# Post-build
# =============

echo "Embedding libmpv"

MPV_ARCHIVE="$BUILD_DIR/mpv-dev.7z"

# Checked before it is kept, so a broken download is not used by the next run
if [ ! -f "$MPV_ARCHIVE" ]; then
    wget -q -O "$MPV_ARCHIVE.part" "$MPV_URL"
    echo "$MPV_SHA256  $MPV_ARCHIVE.part" | sha256sum -c -
    mv "$MPV_ARCHIVE.part" "$MPV_ARCHIVE"
fi

rm -rf "$BUILD_DIR/libmpv-extract"
7z x -y -o"$BUILD_DIR/libmpv-extract" "$MPV_ARCHIVE" libmpv-2.dll

mkdir -p "$DIST_DIR/$APP_NAME/libmpv"
cp "$BUILD_DIR/libmpv-extract/libmpv-2.dll" "$DIST_DIR/$APP_NAME/libmpv/"
