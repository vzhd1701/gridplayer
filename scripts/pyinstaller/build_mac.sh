#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

VLC_URL="https://get.videolan.org/vlc/3.0.21/macosx/vlc-3.0.21-intel64.dmg"
PYINSTALLER_VERSION="6.16.0"

mkdir -p "$BUILD_DIR"

init_venv "$BUILD_DIR/venv-pyinstaller"

# Reduce size by installing src version of pydantic
export PIP_NO_BINARY="pydantic"

pip install -r "$BUILD_DIR/requirements.txt"
pip install pyinstaller=="$PYINSTALLER_VERSION"

# Copy icons to build dir
cp "$RESOURCES_DIR/icons/main/sys/macos.icns" "$BUILD_DIR/main.icns"
cp "$RESOURCES_DIR/icons/playlist/sys/macos.icns" "$BUILD_DIR/mime.icns"

cp "$SCRIPT_DIR/mime_vlc.plist" "$BUILD_DIR/mime_vlc.plist"

copy_with_app_vars "$SCRIPT_DIR/pyinstaller_mac.spec" "$BUILD_DIR/$APP_NAME.spec"

pyinstaller --clean --noconfirm "$BUILD_DIR/$APP_NAME.spec"

# Post-build
# =============

echo "Embedding VLC"

mkdir -p "$BUILD_DIR/libVLC"
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
