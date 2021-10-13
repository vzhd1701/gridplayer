#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"
. "$SCRIPT_DIR/build_functions.sh"

VLC_URL="https://get.videolan.org/vlc/3.0.16/win64/vlc-3.0.16-win64.zip"
PYINSTALLER_VERSION="4.5.1"

mkdir -p "$BUILD_DIR"

if [ ! -d "$BUILD_DIR/venv" ]; then
    python -m venv "$BUILD_DIR/venv"
    . "$BUILD_DIR/venv/Scripts/activate"
    python -m pip install --upgrade pip

    pip install --no-binary pydantic -r "$BUILD_DIR/requirements.txt"
    pip install pyinstaller=="$PYINSTALLER_VERSION"
else
    . "$BUILD_DIR/venv/Scripts/activate"
fi

# Copy icons to build dir
cp "$RESOURCES_DIR/icons/main/sys/windows.ico" "$BUILD_DIR/main.ico"
cp "$RESOURCES_DIR/icons/playlist/sys/windows.ico" "$BUILD_DIR/mime.ico"

get_python_vlc_version > "$BUILD_DIR/python-vlc.version"

# Make version_info
copy_with_app_vars "$SCRIPT_DIR/version_info.py" "$BUILD_DIR"

cp "$SCRIPT_DIR/hook_lib.py" "$BUILD_DIR"

copy_with_app_vars "$SCRIPT_DIR/pyinstaller_win.spec" "$BUILD_DIR/$APP_NAME.spec"

pyinstaller --ascii --clean --noconfirm "$BUILD_DIR/$APP_NAME.spec"

# Post-build
# =============

echo "Moving all bundle files into lib dir"

BASE_DIR="$DIST_DIR/$APP_NAME"
LIB_DIR="$DIST_DIR/lib"

mkdir "$LIB_DIR"
mv $BASE_DIR/* "$LIB_DIR" &> /dev/bull

# Move main exe back into base dir
mv "$LIB_DIR/$APP_NAME.exe" "$BASE_DIR"
mv "$LIB_DIR/$APP_NAME.exe.manifest" "$BASE_DIR"

# Copy base libs so that subprocess could still access them
cp "$LIB_DIR/base_library.zip" "$BASE_DIR"
cp "$LIB_DIR"/python3*.dll "$BASE_DIR"

mv "$LIB_DIR" "$BASE_DIR"

echo "Embedding VLC"

VLC_EMBED_SRC=$(realpath "$BUILD_DIR/libVLC")

if [ ! -d "$VLC_EMBED_SRC" ]; then
    wget -q -nc -O "$BUILD_DIR/vlc.zip" "$VLC_URL" || true
    unzip -oq "$BUILD_DIR/vlc.zip" -d "$BUILD_DIR"

    mkdir -p "$VLC_EMBED_SRC/plugins"

    mkdir "$VLC_EMBED_SRC/plugins/access"
    mkdir "$VLC_EMBED_SRC/plugins/audio_filter"
    mkdir "$VLC_EMBED_SRC/plugins/audio_output"

    cp "$BUILD_DIR"/vlc-*/plugins/access/libfilesystem_plugin.dll "$VLC_EMBED_SRC/plugins/access"
    cp "$BUILD_DIR"/vlc-*/plugins/audio_filter/libscaletempo_*.dll "$VLC_EMBED_SRC/plugins/audio_filter"
    cp "$BUILD_DIR"/vlc-*/plugins/audio_output/libdirectsound_plugin.dll "$VLC_EMBED_SRC/plugins/audio_output"

    cp -a "$BUILD_DIR"/vlc-*/plugins/codec "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/demux "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/video_chroma "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/video_output "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/libvlc.dll "$VLC_EMBED_SRC"
    cp -a "$BUILD_DIR"/vlc-*/libvlccore.dll "$VLC_EMBED_SRC"
fi

if [ ! -d "$DIST_DIR/$APP_NAME/libVLC" ]; then
    mv "$VLC_EMBED_SRC" "$DIST_DIR/$APP_NAME/libVLC"
fi
