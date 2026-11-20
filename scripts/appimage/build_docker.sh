#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

ARCH=$(uname -m)

BUILD_DIR_APPIMAGE="$BUILD_DIR/appimage_docker/$ARCH"
mkdir -p "$BUILD_DIR_APPIMAGE"

# ======

rm -f "$BUILD_DIR_APPIMAGE"/*.whl
cp "$DIST_DIR"/*.whl "$BUILD_DIR_APPIMAGE"

cp -R "$BUILD_DIR/meta" "$BUILD_DIR_APPIMAGE"

cp "$SCRIPTS_DIR/_helpers/blacklist_clean.sh" "$BUILD_DIR_APPIMAGE"
cp "$SCRIPTS_DIR/_helpers/blacklist_pyqt.txt" "$BUILD_DIR_APPIMAGE"
cp "$SCRIPTS_DIR/_helpers/blacklist_vlc_linux.txt" "$BUILD_DIR_APPIMAGE"
chmod +x "$BUILD_DIR_APPIMAGE/blacklist_clean.sh"

# ======

PYTHON_VERSION="3.14"
# Built on manylinux_2_34 (EL9) for x86_64, the oldest with a libmpv new
# enough in its packages, and on manylinux_2_39 (EL10) for aarch64, as
# PyQt6's wheels are. No Python AppImage is made for them: 2_28's runs there.
PYTHON_BASE_NAME="manylinux_2_28_$ARCH"

cd "$BUILD_DIR_APPIMAGE"

export XDG_CACHE_HOME="$BUILD_DIR_APPIMAGE/cache"
mkdir -p "$XDG_CACHE_HOME"

if ! which jq; then
    yum install -y jq
fi

# What gathers the libraries: x86_64's kept as it was, aarch64's from
# linuxdeploy's own releases, which the kept one has none of
LINUXDEPLOY="linuxdeploy-$ARCH.AppImage"

if [ ! -f "$LINUXDEPLOY" ]; then
    echo "==> Fetching linuxdeploy"

    if [ "$ARCH" = "x86_64" ]; then
        LINUXDEPLOY_URL="https://github.com/vzhd1701/linuxdeploy-frozen/releases/download/649fc02/linuxdeploy-x86_64.AppImage"
        LINUXDEPLOY_SHA256=""
    else
        LINUXDEPLOY_URL="https://github.com/linuxdeploy/linuxdeploy/releases/download/1-alpha-20251107-1/linuxdeploy-aarch64.AppImage"
        LINUXDEPLOY_SHA256="620095110d693282b8ebeb244a95b5e911cf8f65f76c88b4b47d16ae6346fcff"
    fi

    curl -L -s -f -o "$LINUXDEPLOY.part" "$LINUXDEPLOY_URL"
    if [ -n "$LINUXDEPLOY_SHA256" ]; then
        echo "$LINUXDEPLOY_SHA256 *$LINUXDEPLOY.part" | sha256sum -c -
    fi
    mv "$LINUXDEPLOY.part" "$LINUXDEPLOY"
    chmod +x "$LINUXDEPLOY"
fi

# What makes the AppImage of the AppDir: appimagetool puts in the static
# runtime, which needs no libfuse2 on the system (Ubuntu 22.04 and later,
# Fedora, have only FUSE 3). linuxdeploy's own still uses the old one.
APPIMAGETOOL_VERSION="1.9.1"
if [ "$ARCH" = "x86_64" ]; then
    APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
else
    APPIMAGETOOL_SHA256="f0837e7448a0c1e4e650a93bb3e85802546e60654ef287576f46c71c126a9158"
fi
APPIMAGETOOL="appimagetool-$APPIMAGETOOL_VERSION-$ARCH.AppImage"

if [ ! -f "$APPIMAGETOOL" ]; then
    echo "==> Fetching appimagetool"

    curl -L -s -f -o "$APPIMAGETOOL.part" "https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VERSION/appimagetool-$ARCH.AppImage"
    echo "$APPIMAGETOOL_SHA256 *$APPIMAGETOOL.part" | sha256sum -c -
    mv "$APPIMAGETOOL.part" "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

# The runtime it puts in, by release: appimagetool would take the newest
RUNTIME_VERSION="20251108"
if [ "$ARCH" = "x86_64" ]; then
    RUNTIME_SHA256="2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"
else
    RUNTIME_SHA256="00cbdfcf917cc6c0ff6d3347d59e0ca1f7f45a6df1a428a0d6d8a78664d87444"
fi
RUNTIME="runtime-$RUNTIME_VERSION-$ARCH"

if [ ! -f "$RUNTIME" ]; then
    echo "==> Fetching the AppImage runtime"

    curl -L -s -f -o "$RUNTIME.part" "https://github.com/AppImage/type2-runtime/releases/download/$RUNTIME_VERSION/runtime-$ARCH"
    echo "$RUNTIME_SHA256 *$RUNTIME.part" | sha256sum -c -
    mv "$RUNTIME.part" "$RUNTIME"
fi

# Kept by its version, so a kept one of another isn't taken
PYTHON_BASE="base-$PYTHON_VERSION-$ARCH.AppImage"

if [ ! -f "$PYTHON_BASE" ]; then
    echo "==> Fetching Python base image"

    # cp314-cp314-..., not the free-threaded cp314-cp314t-...
    PYTHON_APPIMAGE_URL=$(curl -s "https://api.github.com/repos/niess/python-appimage/releases" | jq -r ".[] | select(.name==\"Python $PYTHON_VERSION\") | .assets[] | select(.name|test(\"-cp[0-9]+-cp[0-9]+-$PYTHON_BASE_NAME\")) | .browser_download_url")

    if [ "$(echo "$PYTHON_APPIMAGE_URL" | grep -c .)" != "1" ]; then
        echo "Not one Python $PYTHON_VERSION base image: '$PYTHON_APPIMAGE_URL'" >&2
        exit 1
    fi

    curl -L -s -f -o "$PYTHON_BASE.part" "$PYTHON_APPIMAGE_URL"
    mv "$PYTHON_BASE.part" "$PYTHON_BASE"
    chmod +x "$PYTHON_BASE"
fi

rm -rf "AppDir"
rm -f "$APP_NAME"*.AppImage*

echo "==> Python ${PYTHON_VERSION} init"

"./$PYTHON_BASE" --appimage-extract > /dev/null
mv squashfs-root AppDir

# cleanup python meta
rm -rf AppDir/usr/share
rm AppDir/python*
rm AppDir/.DirIcon

echo "==> Installing ${APP_MODULE}"

./AppDir/AppRun -m pip install -U pip
./AppDir/AppRun -m pip install -U \
    --no-warn-script-location \
    --no-binary="pydantic" \
    "$BUILD_DIR_APPIMAGE"/*.whl

echo "==> Cleaning up"

# Cleanup python AppRun
rm ./AppDir/AppRun
(cd ./AppDir/usr/bin && ln -sf ../../opt/python${PYTHON_VERSION}/bin/python${PYTHON_VERSION} python${PYTHON_VERSION})

# Cleaning python packages
find "./AppDir/usr/bin" -type l -not \( -name 'python*' -or -name "${APP_MODULE}" \) -delete
find "./AppDir/opt/python${PYTHON_VERSION}/bin" -type f -not \( -name 'python*' -or -name "${APP_MODULE}" \) -delete
rm -rf "./AppDir/opt/python${PYTHON_VERSION}/share"

# Remove libqgtk3.so to avoid GTK glitches
# Remove libxdgdesktopportal.so, since it doesn't work in some distros
# https://github.com/linuxdeploy/linuxdeploy-plugin-qt/commit/808c2065598db8f6c589038960d1053c92496bb8
echo "PyQt6/Qt6/plugins/platformthemes" >> blacklist_pyqt.txt

# Cleaning PyQt
./blacklist_clean.sh "./AppDir/opt/python${PYTHON_VERSION}/lib/python${PYTHON_VERSION}/site-packages" blacklist_pyqt.txt

echo "==> Setting up meta & entry point"

# Meta
install -Dm 644 $BUILD_DIR/meta/${APP_ID}.desktop     ./AppDir/usr/share/applications/${APP_ID}.desktop
install -Dm 644 $BUILD_DIR/meta/${APP_ID}.appdata.xml ./AppDir/usr/share/metainfo/${APP_ID}.appdata.xml
install -Dm 644 $BUILD_DIR/meta/${APP_ID}.xml         ./AppDir/usr/share/mime/packages/${APP_ID}.xml
cp -R $BUILD_DIR/meta/icons ./AppDir/usr/share

# AppImage entry point, which starts the app with this Python
gcc -fPIC -DPYTHON_BIN="\"opt/python${PYTHON_VERSION}/bin/python${PYTHON_VERSION}\"" \
    -DMULTIARCH="\"$ARCH-linux-gnu\"" \
    -o ./AppDir/AppRun "$SCRIPT_DIR/AppRun.c" -ldl
strip ./AppDir/AppRun

echo "==> Setting up binary dependencies"

# Qt6/plugins/platforms/libqxcb.so dependencies; Qt 6.5 and later take
# xcb-cursor too, which many systems don't have
yum install -y libxkbcommon-x11 xcb-util xcb-util-cursor xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm

# VLC and libmpv, and the FFmpeg they share, with H.264, HEVC and AAC: EPEL's
# own FFmpeg leaves those out.
# EL9 (x86_64): negativo17's VLC, libmpv and FFmpeg 7. EPEL 9's VLC takes the
# FFmpeg 5.1 of ffmpeg5-*-free, which nobody has a full one of: HEVC didn't
# play at all ("codec not found"), H.264 went to openh264.
# EL10 (aarch64): EPEL's VLC and libmpv, which take FFmpeg 7, with RPM
# Fusion's in place of EPEL's. Same libraries by name, so both take it.
# negativo17's repo isn't to be mixed with RPM Fusion: one or the other.
# vlc-plugins-extra in both has what VLC plays with as much as decodes with:
# the MKV and MPEG-TS demuxers, and the text renderers that draw subtitles
# (vlc-plugins-base has only a stand-in that draws nothing).
EL_VERSION=$(rpm -E %rhel)

if [ ! -f /usr/lib64/libmpv.so.2 ]; then
    dnf install -y epel-release dnf-plugins-core
    dnf config-manager --set-enabled crb

    if [ "$EL_VERSION" = 9 ]; then
        curl -L -s -f -o /etc/yum.repos.d/negativo17-epel-multimedia.repo \
            https://negativo17.org/repos/epel-multimedia.repo
        dnf install -y vlc vlc-plugins-extra mpv-libs
    else
        dnf install -y "https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-$EL_VERSION.noarch.rpm"
        dnf install -y vlc vlc-plugins-extra vlc-plugins-freeworld mpv-libs
        dnf swap -y ffmpeg-free ffmpeg --allowerasing
    fi
fi

# Loud, rather than an AppImage that plays nothing in H.264 or HEVC
for codec in h264 hevc; do
    python3 -c "
import ctypes, sys
av = ctypes.CDLL('libavcodec.so.61')
av.avcodec_find_decoder_by_name.restype = ctypes.c_void_p
sys.exit(0 if av.avcodec_find_decoder_by_name(b'$codec') else 1)
" || { echo "FFmpeg has no $codec decoder" >&2; exit 1; }
done
ldd /usr/lib64/vlc/plugins/codec/libavcodec_plugin.so | grep -q "libavcodec.so.61" ||
    { echo "VLC doesn't decode with FFmpeg 7" >&2; exit 1; }
for plugin in demux/libmkv_plugin.so demux/libts_plugin.so text_renderer/libfreetype_plugin.so; do
    [ -f "/usr/lib64/vlc/plugins/$plugin" ] || { echo "VLC has no $plugin" >&2; exit 1; }
done

LIB_DIR="./AppDir/usr/lib"
mkdir -p "$LIB_DIR"

cp /usr/lib64/libvlc* "$LIB_DIR"
cp -a /usr/lib64/vlc "$LIB_DIR"

cp -a /usr/lib64/libmpv.so.2* "$LIB_DIR"

# What a system has as a rule, with drivers and plugins of its own that want
# its copy: EL9's libva looks for VAAPI drivers where EL9 keeps them, and is
# older than the drivers of a newer system; host Mesa would get EL9's libwayland.
# Kept apart under their full file names, which have the version, and AppRun
# puts one on the path only when the system has none or an older one.
# JACK's client must be the server's, and libmpv links it: a system without
# JACK has no server for ours to find, but libmpv loads. libgpg-error, which
# linuxdeploy leaves to the system, goes with the libgcrypt it bundles: EL10's
# needs a newer one than Ubuntu 24.04 has.
FALLBACK_LIBS=(
    libva.so.2 libva-drm.so.2 libva-x11.so.2 libva-wayland.so.2
    libvdpau.so.1 libvulkan.so.1 libGLESv2.so.2
    libwayland-client.so.0 libwayland-cursor.so.0 libwayland-egl.so.1
    libpipewire-0.3.so.0 libpulse.so.0 libjack.so.0 libgpg-error.so.0
)
# libusb, which linuxdeploy leaves to the system too, for the FireWire cameras
# of EL9's libavdevice (libdc1394): a Debian or Ubuntu without it has none, and
# libmpv wouldn't load there. EL10's libavdevice has no such cameras
if ldd /usr/lib64/libmpv.so.2 | grep -q "libusb-1.0.so.0"; then
    FALLBACK_LIBS+=(libusb-1.0.so.0)
fi
FALLBACK_EXCLUDES=()

for lib in "${FALLBACK_LIBS[@]}"; do
    # where the linker finds it: EL's libjack is PipeWire's, in a folder of its own
    found=$(ldconfig -p | awk -v lib="$lib" '$1 == lib { print $NF; exit }')
    [ -n "$found" ] || { echo "No $lib to fall back on" >&2; exit 1; }
    real=$(readlink -f "$found")
    mkdir -p "$LIB_DIR/fallback/$lib"
    cp "$real" "$LIB_DIR/fallback/$lib/"
    ln -s "$(basename "$real")" "$LIB_DIR/fallback/$lib/$lib"
    FALLBACK_EXCLUDES+=(--exclude-library "$lib")
done

./blacklist_clean.sh "$LIB_DIR/vlc" blacklist_vlc_linux.txt

# rebuild plugin cache
rm "$LIB_DIR/vlc/plugins/plugins.dat"
/usr/lib64/vlc/vlc-cache-gen "$LIB_DIR/vlc/plugins"

echo "==> Fixing permissions"

chmod 755 -R ./AppDir
find ./AppDir -type f -exec chmod 644 {} \;
chmod a+x ./AppDir/opt/python${PYTHON_VERSION}/bin/*
chmod a+x ./AppDir/usr/bin/*
chmod a+x ./AppDir/AppRun

echo "==> Generating AppImage"

# fuse doesn't work inside docker
export APPIMAGE_EXTRACT_AND_RUN=1
export UPDATE_INFORMATION="gh-releases-zsync|vzhd1701|gridplayer|$APP_UPDATE_RELEASE|GridPlayer-*$ARCH.AppImage.zsync"
export ARCH
export VERSION="$APP_FILE_VERSION"

# linuxdeploy's own strip doesn't know EL10's .relr.dyn sections and stops
# the build; EL's packages come stripped anyway
if [ "$ARCH" = "aarch64" ]; then
    export NO_STRIP=1
fi

# Loaded by name, which linuxdeploy can't see: EL10's SDL2 is sdl2-compat,
# which loads SDL3 and aborts the app without it (FFmpeg's libavdevice links
# SDL2, and libmpv libavdevice)
LOADED_LIBS=()
if [ -e /usr/lib64/libSDL3.so.0 ]; then
    LOADED_LIBS+=(-l /usr/lib64/libSDL3.so.0)
fi

deploy() {
    "./$LINUXDEPLOY" \
        -l /lib64/libxcb-icccm.so.4 \
        -l /lib64/libxcb-render-util.so.0 \
        -l /lib64/libxcb-util.so.1 \
        -l /lib64/libxcb-image.so.0 \
        -l /lib64/libxcb-keysyms.so.1 \
        -l /lib64/libxkbcommon-x11.so.0 \
        -l /lib64/libxcb-cursor.so.0 \
        "${LOADED_LIBS[@]}" \
        "${FALLBACK_EXCLUDES[@]}" \
        --appdir AppDir \
        "$@"
}

# What goes in is known only once it's in
deploy

echo "==> Adding licences"

# VLC, libmpv and much of what they take are GPL or LGPL: the licences of the
# packages each library here came from go with them, and where their source is
LICENSES_DIR="./AppDir/usr/share/licenses"
mkdir -p "$LICENSES_DIR/$APP_MODULE"
cp "$ROOT_DIR/LICENSE" "$LICENSES_DIR/$APP_MODULE/"

PACKAGES=$(
    cd ./AppDir/usr/lib
    find . -type f -name "*.so*" | while read -r file; do
        for system_file in "/usr/lib64/${file#./}" "/usr/lib64/$(basename "$file")"; do
            if [ -e "$system_file" ]; then
                rpm -qf --qf "%{NAME}\n" "$system_file" || true
                break
            fi
        done
    done | grep -v "not owned" | sort -u
)

for package in $PACKAGES; do
    if [ -d "/usr/share/licenses/$package" ]; then
        cp -a "/usr/share/licenses/$package" "$LICENSES_DIR/"
    fi
done

{
    echo "Where the source of what is bundled here is:"
    echo
    echo "GridPlayer $APP_VERSION"
    echo "    $APP_URL"
    echo
    if [ "$EL_VERSION" = 9 ]; then
        THIRD_REPO="negativo17's multimedia repo (EL 9)"
        THIRD_SRPMS="https://negativo17.org/repos/multimedia/epel-9/SRPMS/"
    else
        THIRD_REPO="RPM Fusion (free, EL $EL_VERSION)"
        THIRD_SRPMS="https://download1.rpmfusion.org/free/el/updates/$EL_VERSION/SRPMS/"
    fi

    echo "The libraries come from these packages of AlmaLinux $EL_VERSION, EPEL $EL_VERSION"
    echo "and $THIRD_REPO, each named with its source RPM:"
    echo
    for package in $PACKAGES; do
        rpm -q --qf "    %{NAME}-%{VERSION}-%{RELEASE} (%{SOURCERPM})\n" "$package"
    done
    echo
    echo "Source RPMs:"
    echo "    https://repo.almalinux.org/vault/$EL_VERSION/"
    echo "    https://dl.fedoraproject.org/pub/epel/$EL_VERSION/Everything/source/tree/"
    echo "    $THIRD_SRPMS"
} > "$LICENSES_DIR/SOURCES.txt"

APPIMAGE_FILE="$APP_NAME-$APP_FILE_VERSION-$ARCH.AppImage"

"./$APPIMAGETOOL" --runtime-file "$RUNTIME" --updateinformation "$UPDATE_INFORMATION" \
    AppDir "$APPIMAGE_FILE"

chmod 777 "$BUILD_DIR_APPIMAGE/$APP_NAME"*.AppImage*
mv "$BUILD_DIR_APPIMAGE/$APP_NAME"*.AppImage* "$DIST_DIR"
