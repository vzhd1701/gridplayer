#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

assert_target_python_arch() {
    PYTHON_ARCH="$(python -c 'import platform; print(platform.machine())')"

    if [ "$PYTHON_ARCH" != "$APP_TARGET_ARCH" ]; then
        die "Active Python interpreter is $PYTHON_ARCH, but BUILD_MACOS_ARCH=$APP_TARGET_ARCH. Use a native $APP_TARGET_ARCH Python interpreter."
    fi
}

assert_target_dependency_arch() {
    python <<'PY'
import os
import platform
import subprocess
from pathlib import Path

target_arch = os.environ["APP_TARGET_ARCH"]
python_arch = platform.machine()

if python_arch != target_arch:
    raise SystemExit(
        f"Active Python interpreter is {python_arch}, but BUILD_MACOS_ARCH={target_arch}. "
        f"Use a native {target_arch} Python interpreter."
    )

paths_to_check = []

from PyQt5 import QtCore

qtcore_ext = Path(QtCore.__file__).resolve()
paths_to_check.append((qtcore_ext, "PyQt5.QtCore extension"))

qt_framework = qtcore_ext.parent / "Qt5" / "lib" / "QtCore.framework" / "Versions" / "5" / "QtCore"
if qt_framework.exists():
    paths_to_check.append((qt_framework, "QtCore framework"))

try:
    from pydantic_core import _pydantic_core
except ModuleNotFoundError:
    pass
else:
    paths_to_check.append((Path(_pydantic_core.__file__).resolve(), "pydantic-core extension"))

try:
    from objc import _objc
except ModuleNotFoundError:
    pass
else:
    paths_to_check.append((Path(_objc.__file__).resolve(), "PyObjC extension"))

try:
    from curl_cffi import _wrapper
except ModuleNotFoundError:
    pass
else:
    paths_to_check.append((Path(_wrapper.__file__).resolve(), "curl_cffi extension"))

errors = []

for path, label in paths_to_check:
    lipo_result = subprocess.run(
        ["lipo", "-archs", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    if lipo_result.returncode == 0:
        archs = lipo_result.stdout.strip().split()
    else:
        file_result = subprocess.run(
            ["file", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        archs = file_result.stdout.strip().split()

    if target_arch not in archs:
        errors.append(f"{label}: expected {target_arch}, got {' '.join(archs) or 'unknown'} ({path})")

if errors:
    joined = "\n".join(errors)
    raise SystemExit(
        "Installed dependencies are not built for the requested macOS architecture:\n"
        + joined
    )
PY
}

# VideoLAN's own server: get.videolan.org can pick a mirror running at a
# few KB/s. The SHA-256s are the ones published beside each file.
VLC_VERSION="3.0.24"
if [ "$APP_TARGET_ARCH" = "arm64" ]; then
    VLC_URL="https://download.videolan.org/pub/videolan/vlc/$VLC_VERSION/macosx/vlc-$VLC_VERSION-arm64.dmg"
    VLC_SHA256="64a89d93cdd30b0e97131743e246373db82d6826ea882d265d46d74b136da2b7"
else
    VLC_URL="https://download.videolan.org/pub/videolan/vlc/$VLC_VERSION/macosx/vlc-$VLC_VERSION-intel64.dmg"
    VLC_SHA256="1ef6c903e2dc026d4e58ddf7b2a9ed0eb6f8caf80a9a9f46f96490340b962707"
fi

PYINSTALLER_VERSION="6.22.3"

# what libmpv_mac.txt is of, for the licences
LIBMPV_MPVKIT_VERSION="1.1.0-n9.0.2"
LIBMPV_MPV_VERSION="0.41.0"

mkdir -p "$BUILD_DIR"

init_venv "$BUILD_DIR/venv-pyinstaller-$APP_TARGET_ARCH"
assert_target_python_arch

# Reduce size by installing src version of pydantic
export PIP_NO_BINARY="pydantic"

pip install -r "$BUILD_DIR/requirements.txt"
pip install pyinstaller=="$PYINSTALLER_VERSION"
assert_target_dependency_arch

# Copy icons to build dir
cp "$RESOURCES_DIR/icons/main/sys/macos.icns" "$BUILD_DIR/main.icns"
cp "$RESOURCES_DIR/icons/playlist/sys/macos.icns" "$BUILD_DIR/mime.icns"

cp "$SCRIPT_DIR/mime_vlc.plist" "$BUILD_DIR/mime_vlc.plist"

copy_with_app_vars "$SCRIPT_DIR/pyinstaller_mac.spec" "$BUILD_DIR/$APP_NAME.spec"

pyinstaller --clean --noconfirm "$BUILD_DIR/$APP_NAME.spec"

# Post-build
# =============

echo "Embedding VLC"

VLC_EMBED_SRC=$(realpath "$BUILD_DIR")/libVLC-$APP_TARGET_ARCH
VLC_DMG="$BUILD_DIR/vlc-$APP_TARGET_ARCH.dmg"

if [ ! -d "$VLC_EMBED_SRC" ]; then
    # Downloaded to a side name first, so a broken download is not kept
    # as the dmg by the next run
    if [ ! -f "$VLC_DMG" ]; then
        wget -q -O "$VLC_DMG.part" "$VLC_URL"
        echo "$VLC_SHA256 *$VLC_DMG.part" | shasum -a 256 -c -
        mv "$VLC_DMG.part" "$VLC_DMG"
    fi

    hdiutil attach "$VLC_DMG"

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

rm -rf "$DIST_DIR/$APP_NAME.app/Contents/MacOS/libVLC"
cp -a "$VLC_EMBED_SRC" "$DIST_DIR/$APP_NAME.app/Contents/MacOS/libVLC"

echo "Embedding libmpv"

# MPVKit's GPL build, see libmpv_mac.txt: static libraries, linked here into
# one libmpv.2.dylib for this architecture, exporting only mpv's API and
# needing only what macOS has. Not on macOS 10.15 and 11: VLC plays there.
LIBMPV_MIN_MACOS="12.0"
LIBMPV_LIST="$SCRIPT_DIR/libmpv_mac.txt"
LIBMPV_PARTS="$BUILD_DIR/mpvkit"
LIBMPV_EMBED_SRC="$BUILD_DIR/libmpv-$APP_TARGET_ARCH"

macos_slice() {
    local name="$1"
    local file

    # a framework's binary or a .a: whatever lipo reads, for this architecture
    while IFS= read -r -d '' file; do
        if lipo -archs "$file" 2> /dev/null | grep -w "$APP_TARGET_ARCH" > /dev/null; then
            echo "$file"
            return
        fi
    done < <(find "$LIBMPV_PARTS/x/$name" -path '*/macos-*' -type f -print0)

    die "No macOS $APP_TARGET_ARCH library in $name"
}

if [ ! -f "$LIBMPV_EMBED_SRC/libmpv.2.dylib" ]; then
    LIBMPV_LIBS="$LIBMPV_PARTS/lib-$APP_TARGET_ARCH"
    rm -rf "$LIBMPV_LIBS" "$LIBMPV_EMBED_SRC.part"
    mkdir -p "$LIBMPV_PARTS/zips" "$LIBMPV_PARTS/x" "$LIBMPV_LIBS" "$LIBMPV_EMBED_SRC.part"

    while read -r name url sha256; do
        case "$name" in "" | "#"*) continue ;; esac

        zip="$LIBMPV_PARTS/zips/$name.zip"
        if [ ! -f "$zip" ]; then
            wget -q -O "$zip.part" "$url"
            mv "$zip.part" "$zip"
        fi
        echo "$sha256 *$zip" | shasum -a 256 -c -

        if [ ! -d "$LIBMPV_PARTS/x/$name" ]; then
            unzip -q "$zip" -d "$LIBMPV_PARTS/x/$name.part"
            mv "$LIBMPV_PARTS/x/$name.part" "$LIBMPV_PARTS/x/$name"
        fi

        slice="$(macos_slice "$name")"
        if [ "$(lipo -archs "$slice")" = "$APP_TARGET_ARCH" ]; then
            cp "$slice" "$LIBMPV_LIBS/$name.a"
        else
            lipo "$slice" -thin "$APP_TARGET_ARCH" -output "$LIBMPV_LIBS/$name.a"
        fi
    done < "$LIBMPV_LIST"

    echo "_mpv_*" > "$LIBMPV_PARTS/exports.txt"

    LIBMPV_DEPS=()
    for lib in "$LIBMPV_LIBS"/*.a; do
        [ "$(basename "$lib")" = "Libmpv-GPL.a" ] || LIBMPV_DEPS+=("$lib")
    done

    # mpv's macOS parts are Swift: the system's Swift libraries, and the
    # toolchain's for what the system has none of
    SWIFT_TOOLCHAIN_LIBS="$(dirname "$(xcrun --find swiftc)")/../lib/swift/macosx"

    xcrun clang -dynamiclib -arch "$APP_TARGET_ARCH" -mmacosx-version-min="$LIBMPV_MIN_MACOS" \
        -o "$LIBMPV_EMBED_SRC.part/libmpv.2.dylib" -install_name @rpath/libmpv.2.dylib \
        -Wl,-force_load,"$LIBMPV_LIBS/Libmpv-GPL.a" "${LIBMPV_DEPS[@]}" \
        -Wl,-exported_symbols_list,"$LIBMPV_PARTS/exports.txt" -Wl,-dead_strip_dylibs \
        -L"$(xcrun --show-sdk-path)/usr/lib/swift" -L"$SWIFT_TOOLCHAIN_LIBS" -Wl,-rpath,/usr/lib/swift \
        -framework AVFoundation -framework AudioToolbox -framework CoreAudio \
        -framework CoreFoundation -framework CoreMedia -framework CoreVideo \
        -framework VideoToolbox -framework Metal -framework IOSurface \
        -framework QuartzCore -framework Cocoa -framework IOKit -framework OpenGL \
        -framework CoreText -framework CoreGraphics -framework Security \
        -framework SystemConfiguration -framework MediaPlayer -framework Carbon \
        -framework ApplicationServices -framework GameController \
        -lbz2 -liconv -lexpat -lresolv -lxml2 -lz -lc++

    # mpv's API there, and nothing of its own to find beside it (no grep -q:
    # with pipefail, nm cut off by it would fail the check)
    nm -gU "$LIBMPV_EMBED_SRC.part/libmpv.2.dylib" | grep " _mpv_create$" > /dev/null \
        || die "libmpv.2.dylib has no mpv_create"
    if otool -L "$LIBMPV_EMBED_SRC.part/libmpv.2.dylib" | tail -n +3 \
        | grep -vE "^\s+(/System/Library/|/usr/lib/)"; then
        die "libmpv.2.dylib needs libraries macOS doesn't have (above)"
    fi

    mv "$LIBMPV_EMBED_SRC.part" "$LIBMPV_EMBED_SRC"
fi

rm -rf "$DIST_DIR/$APP_NAME.app/Contents/MacOS/libmpv"
cp -a "$LIBMPV_EMBED_SRC" "$DIST_DIR/$APP_NAME.app/Contents/MacOS/libmpv"

echo "Adding licences"

# VLC and libmpv are GPL builds: their licences go with them, and where
# their source is. VLC's .dmg has no licence of its own, so it's VLC's
# repository's at the version.
LICENSES_DIR="$DIST_DIR/$APP_NAME.app/Contents/Resources/licenses"
LICENSES_SRC="$BUILD_DIR/licenses-vlc-$VLC_VERSION-mpv-$LIBMPV_MPV_VERSION-mpvkit-$LIBMPV_MPVKIT_VERSION"

if [ ! -d "$LICENSES_SRC" ]; then
    mkdir -p "$LICENSES_SRC.part"
    wget -q -O "$LICENSES_SRC.part/VLC-GPL-2.0.txt" "https://code.videolan.org/videolan/vlc/-/raw/$VLC_VERSION/COPYING"
    wget -q -O "$LICENSES_SRC.part/mpv-Copyright.txt" "https://raw.githubusercontent.com/mpv-player/mpv/v$LIBMPV_MPV_VERSION/Copyright"
    wget -q -O "$LICENSES_SRC.part/mpv-GPL-2.0.txt" "https://raw.githubusercontent.com/mpv-player/mpv/v$LIBMPV_MPV_VERSION/LICENSE.GPL"
    wget -q -O "$LICENSES_SRC.part/MPVKit-LGPL-3.0.txt" "https://raw.githubusercontent.com/mpvkit/MPVKit/$LIBMPV_MPVKIT_VERSION/LICENSE"
    mv "$LICENSES_SRC.part" "$LICENSES_SRC"
fi

rm -rf "$LICENSES_DIR"
mkdir -p "$LICENSES_DIR"

cp "$ROOT_DIR/LICENSE" "$LICENSES_DIR/GridPlayer-GPL-3.0.txt"
cp "$LICENSES_SRC"/* "$LICENSES_DIR"

{
    cat <<SOURCES
Where the source of what is bundled here is:

GridPlayer $APP_VERSION
    $APP_URL

libmpv (Contents/MacOS/libmpv)
    mpv: https://github.com/mpv-player/mpv/tree/v$LIBMPV_MPV_VERSION
    with MPVKit's patches: https://github.com/mpvkit/MPVKit/tree/$LIBMPV_MPVKIT_VERSION/Sources/BuildScripts/patch
    built by MPVKit $LIBMPV_MPVKIT_VERSION, https://github.com/mpvkit/MPVKit, its static
    libraries linked by scripts/pyinstaller/build_mac.sh. Each library's build,
    which names its source:
SOURCES
    while read -r name url _sha256; do
        case "$name" in "" | "#"*) continue ;; esac
        # .../<owner>/<repository>/releases/download/<tag>/<file>
        repo="${url%%/releases/download/*}"
        tag="${url#*/releases/download/}"
        echo "        $name: $repo/tree/${tag%%/*}"
    done < "$LIBMPV_LIST"
    cat <<SOURCES

VLC $VLC_VERSION (Contents/MacOS/libVLC)
    https://download.videolan.org/pub/videolan/vlc/$VLC_VERSION/vlc-$VLC_VERSION.tar.xz
    the build: $VLC_URL
SOURCES
} > "$LICENSES_DIR/SOURCES.txt"

echo "Signing"

# Ad hoc ("-", no Apple account): PyInstaller signed the bundle before VLC,
# libmpv and the licences went in, which broke its seal, and macOS calls a
# downloaded app with a broken seal damaged. Signed again, it's only from an
# unknown developer, which Privacy & Security's Open Anyway lets through.
codesign --force --deep --sign - "$DIST_DIR/$APP_NAME.app"
codesign --verify --deep --strict "$DIST_DIR/$APP_NAME.app"
