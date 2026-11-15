#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

# Get machine architecture
if [ -z "$BUILD_ARCH" ]; then
    BUILD_ARCH=$(python -c "import platform; print('win32' if platform.architecture()[0] == '32bit' else 'win64')")
fi

# VideoLAN's own server: get.videolan.org can pick a mirror running at a
# few KB/s. The SHA-256s are the ones published beside each file.
VLC_VERSION="3.0.24"
VLC_URL="https://download.videolan.org/pub/videolan/vlc/$VLC_VERSION/$BUILD_ARCH/vlc-$VLC_VERSION-$BUILD_ARCH.zip"
if [ "$BUILD_ARCH" = "win32" ]; then
    VLC_SHA256="8511356afd680817f3aea624c63032d0936f3d77b2175fb36c8fc16adf9744e8"
else
    VLC_SHA256="fcf30850371ad10c9373cc4f0f4501e7dee49e3e9ae9f20c72fb2661a1ca6323"
fi
PYINSTALLER_VERSION="6.22.3"

# shinchiro's libmpv builds, the ones mpv.io points to for Windows. GitHub
# keeps only the last month of them, the SourceForge mirror keeps a weekly
# one for good, so it comes from there.
LIBMPV_BUILD="20261108-git-55d3feb45c"
if [ "$BUILD_ARCH" = "win32" ]; then
    LIBMPV_ARCHIVE="mpv-dev-i686-$LIBMPV_BUILD.7z"
    LIBMPV_SHA256="b5140046b4d48d8866ef3c968e591b0022cb4eb75c554aae8f12fd66ebbfcc66"
else
    LIBMPV_ARCHIVE="mpv-dev-x86_64-$LIBMPV_BUILD.7z"
    LIBMPV_SHA256="7c147cb7ceaba717414e782ef4398de728f679db6e86daaa8aeb175670cb7994"
fi
LIBMPV_URL="https://downloads.sourceforge.net/project/mpv-player-windows/libmpv/$LIBMPV_ARCHIVE"
# the mpv commit the build is of, which GitHub takes short
LIBMPV_COMMIT="${LIBMPV_BUILD##*-git-}"

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

echo "Embedding VLC"

VLC_EMBED_SRC=$(realpath "$BUILD_DIR/libVLC")

if [ ! -d "$VLC_EMBED_SRC" ]; then
    # Downloaded to a side name first, so a broken download is not kept
    # as the zip by the next run
    if [ ! -f "$BUILD_DIR/vlc.zip" ]; then
        wget -q -O "$BUILD_DIR/vlc.zip.part" "$VLC_URL"
        echo "$VLC_SHA256 *$BUILD_DIR/vlc.zip.part" | sha256sum -c -
        mv "$BUILD_DIR/vlc.zip.part" "$BUILD_DIR/vlc.zip"
    fi

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

    # Subtitles need both of these, and neither says so when it is missing:
    # the track is decoded and selected, and nothing is ever drawn.
    # blend composites the subpicture onto the frame, scale fits bitmap
    # subtitles (DVD, PGS) to it.
    cp "$BUILD_DIR"/vlc-*/plugins/video_filter/libblend_plugin.dll "$VLC_EMBED_SRC/plugins/video_filter"
    cp "$BUILD_DIR"/vlc-*/plugins/video_filter/libscale_plugin.dll "$VLC_EMBED_SRC/plugins/video_filter"

    # freetype draws the text ones
    cp -a "$BUILD_DIR"/vlc-*/plugins/text_renderer "$VLC_EMBED_SRC/plugins"

    "$BUILD_DIR"/vlc-*/vlc-cache-gen.exe "$VLC_EMBED_SRC/plugins"

    cp -a "$BUILD_DIR"/vlc-*/libvlc.dll "$VLC_EMBED_SRC"
    cp -a "$BUILD_DIR"/vlc-*/libvlccore.dll "$VLC_EMBED_SRC"
fi

if [ ! -d "$DIST_DIR/$APP_NAME/libVLC" ]; then
    mv "$VLC_EMBED_SRC" "$DIST_DIR/$APP_NAME/libVLC"
fi

echo "Embedding libmpv"

# libmpv-2.dll is all of it, ffmpeg and the rest built in
LIBMPV_EMBED_SRC="$BUILD_DIR/libmpv-$BUILD_ARCH"

if [ ! -d "$LIBMPV_EMBED_SRC" ]; then
    if [ ! -f "$BUILD_DIR/$LIBMPV_ARCHIVE" ]; then
        wget -q -O "$BUILD_DIR/$LIBMPV_ARCHIVE.part" "$LIBMPV_URL"
        mv "$BUILD_DIR/$LIBMPV_ARCHIVE.part" "$BUILD_DIR/$LIBMPV_ARCHIVE"
    fi

    echo "$LIBMPV_SHA256 *$BUILD_DIR/$LIBMPV_ARCHIVE" | sha256sum -c -

    mkdir -p "$LIBMPV_EMBED_SRC.part"
    7z e -y -o"$LIBMPV_EMBED_SRC.part" "$BUILD_DIR/$LIBMPV_ARCHIVE" libmpv-2.dll
    mv "$LIBMPV_EMBED_SRC.part" "$LIBMPV_EMBED_SRC"
fi

if [ ! -d "$DIST_DIR/$APP_NAME/libmpv" ]; then
    cp -a "$LIBMPV_EMBED_SRC" "$DIST_DIR/$APP_NAME/libmpv"
fi

echo "Adding licences"

# VLC and libmpv are GPL builds: their licences go with them, and where
# their source is
LICENSES_DIR="$DIST_DIR/$APP_NAME/licenses"
LIBMPV_LICENSES="$BUILD_DIR/libmpv-licenses-$LIBMPV_COMMIT"

if [ ! -d "$LIBMPV_LICENSES" ]; then
    mkdir -p "$LIBMPV_LICENSES.part"
    wget -q -O "$LIBMPV_LICENSES.part/mpv-Copyright.txt" "https://raw.githubusercontent.com/mpv-player/mpv/$LIBMPV_COMMIT/Copyright"
    wget -q -O "$LIBMPV_LICENSES.part/mpv-GPL-2.0.txt" "https://raw.githubusercontent.com/mpv-player/mpv/$LIBMPV_COMMIT/LICENSE.GPL"
    mv "$LIBMPV_LICENSES.part" "$LIBMPV_LICENSES"
fi

rm -rf "$LICENSES_DIR"
mkdir -p "$LICENSES_DIR"

cp "$ROOT_DIR/LICENSE" "$LICENSES_DIR/GridPlayer-GPL-3.0.txt"
unzip -p "$BUILD_DIR/vlc.zip" "vlc-$VLC_VERSION/COPYING.txt" > "$LICENSES_DIR/VLC-GPL-2.0.txt"
cp "$LIBMPV_LICENSES"/* "$LICENSES_DIR"

cat > "$LICENSES_DIR/SOURCES.txt" <<EOF
Where the source of what is bundled here is:

GridPlayer $APP_VERSION
    $APP_URL

libmpv ($LIBMPV_ARCHIVE)
    mpv: https://github.com/mpv-player/mpv/tree/$LIBMPV_COMMIT
    built with FFmpeg and the libraries it takes by
    https://github.com/shinchiro/mpv-winbuild-cmake, whose build files name
    each one's source; the build: $LIBMPV_URL

VLC $VLC_VERSION (libVLC)
    https://download.videolan.org/pub/videolan/vlc/$VLC_VERSION/vlc-$VLC_VERSION.tar.xz
    the build: $VLC_URL
EOF
