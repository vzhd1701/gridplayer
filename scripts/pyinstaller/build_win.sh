#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

# Get machine architecture
if [ -z "$BUILD_ARCH" ]; then
    BUILD_ARCH=$(python -c "import platform; print('win32' if platform.architecture()[0] == '32bit' else 'win64')")
fi

VLC_URL="https://get.videolan.org/vlc/3.0.21/$BUILD_ARCH/vlc-3.0.21-$BUILD_ARCH.zip"
PYINSTALLER_VERSION="6.16.0"

mkdir -p "$BUILD_DIR"

init_venv "$BUILD_DIR/venv-pyinstaller"

# Reduce size by installing src version of pydantic
export PIP_NO_BINARY="pydantic"

pip install -r "$BUILD_DIR/requirements.txt"
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

echo "Embedding VLC"

VLC_EMBED_SRC=$(realpath "$BUILD_DIR/libVLC")

if [ ! -d "$VLC_EMBED_SRC" ]; then
    wget -q -nc -O "$BUILD_DIR/vlc.zip" "$VLC_URL" || true
    unzip -oq "$BUILD_DIR/vlc.zip" -d "$BUILD_DIR"

    mkdir -p "$VLC_EMBED_SRC/plugins"

    mkdir "$VLC_EMBED_SRC/plugins/audio_output"

    cp "$BUILD_DIR"/vlc-*/plugins/audio_output/libdirectsound_plugin.dll "$VLC_EMBED_SRC/plugins/audio_output"

    cp -a "$BUILD_DIR"/vlc-*/plugins/access "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/audio_filter "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/audio_mixer "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/codec "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/demux "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/misc "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/packetizer "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/stream_filter "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/video_chroma "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/video_output "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/d3d9 "$VLC_EMBED_SRC/plugins"
    cp -a "$BUILD_DIR"/vlc-*/plugins/d3d11 "$VLC_EMBED_SRC/plugins"

    mkdir -p "$VLC_EMBED_SRC/plugins/video_filter"
    cp "$BUILD_DIR"/vlc-*/plugins/video_filter/libtransform_plugin.dll "$VLC_EMBED_SRC/plugins/video_filter"

    "$BUILD_DIR"/vlc-*/vlc-cache-gen.exe "$VLC_EMBED_SRC/plugins"

    cp -a "$BUILD_DIR"/vlc-*/libvlc.dll "$VLC_EMBED_SRC"
    cp -a "$BUILD_DIR"/vlc-*/libvlccore.dll "$VLC_EMBED_SRC"
fi

if [ ! -d "$DIST_DIR/$APP_NAME/libVLC" ]; then
    mv "$VLC_EMBED_SRC" "$DIST_DIR/$APP_NAME/libVLC"
fi
