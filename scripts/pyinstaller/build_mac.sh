#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"
. "$SCRIPT_DIR/build_functions.sh"

VLC_URL="https://get.videolan.org/vlc/3.0.16/macosx/vlc-3.0.16-intel64.dmg"
PYINSTALLER_VERSION="4.5.1"

mkdir -p "$BUILD_DIR"

if [ ! -d "$BUILD_DIR/venv" ]; then
    python -m venv "$BUILD_DIR/venv"
    . "$BUILD_DIR/venv/bin/activate"
    python -m pip install --upgrade pip

    pip install --no-binary pydantic -r "$BUILD_DIR/requirements.txt"
    pip install pyinstaller=="$PYINSTALLER_VERSION"
else
    . "$BUILD_DIR/venv/bin/activate"
fi

# Copy icons to build dir
cp "$RESOURCES_DIR/icons/main/sys/macos.icns" "$BUILD_DIR/main.icns"
cp "$RESOURCES_DIR/icons/playlist/sys/macos.icns" "$BUILD_DIR/mime.icns"

get_python_vlc_version > "$BUILD_DIR/python-vlc.version"

copy_with_app_vars "$SCRIPT_DIR/pyinstaller_mac.spec" "$BUILD_DIR/$APP_NAME.spec"

pyinstaller --ascii --clean --noconfirm "$BUILD_DIR/$APP_NAME.spec"

# Post-build
# =============

echo "Embedding VLC"

VLC_EMBED_SRC=$(realpath "$BUILD_DIR/libVLC")

if [ ! -d "$VLC_EMBED_SRC" ]; then
    wget -q -nc -O "$BUILD_DIR/vlc.dmg" "$VLC_URL" || true

    hdiutil attach "$BUILD_DIR/vlc.dmg"

    VLC_SRC="/Volumes/VLC media player/VLC.app/Contents/MacOS"

    mkdir -p "$VLC_EMBED_SRC"

    cp -a "$VLC_SRC/lib" "$VLC_EMBED_SRC"
    cp -a "$VLC_SRC/plugins" "$VLC_EMBED_SRC"

    #mkdir -p "$VLC_EMBED_SRC/plugins"
    #while IFS= read -r plugin_file; do
    #    cp "$VLC_SRC/plugins/$plugin_file" "$VLC_EMBED_SRC/plugins" || true
    #done < "$SCRIPT_DIR/vlc_plugins_wl.txt"

    hdiutil detach "/Volumes/VLC media player"
fi

if [ ! -d "$DIST_DIR/$APP_NAME.app/Contents/MacOS/libVLC" ]; then
    mv "$VLC_EMBED_SRC" "$DIST_DIR/$APP_NAME.app/Contents/MacOS/libVLC"
fi
