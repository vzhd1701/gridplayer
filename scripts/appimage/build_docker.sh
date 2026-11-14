#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

BUILD_DIR_APPIMAGE="$BUILD_DIR/appimage_docker"
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
# Built on manylinux_2_34 (EL9), the oldest with a libmpv new enough in its
# packages. No Python AppImage is made for it: 2_28's runs there.
PYTHON_BASE_NAME="manylinux_2_28_x86_64"

cd "$BUILD_DIR_APPIMAGE"

export XDG_CACHE_HOME="$BUILD_DIR_APPIMAGE/cache"
mkdir -p "$XDG_CACHE_HOME"

if ! which jq; then
    yum install -y jq
fi

if [ ! -f "linuxdeploy-x86_64.AppImage" ]; then
    echo "==> Fetching linuxdeploy"

    curl -L -s -O "https://github.com/vzhd1701/linuxdeploy-frozen/releases/download/649fc02/linuxdeploy-x86_64.AppImage"
    chmod +x linuxdeploy-x86_64.AppImage
fi

# Kept by its version, so a kept one of another isn't taken
PYTHON_BASE="base-$PYTHON_VERSION.AppImage"

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
echo "PyQt5/Qt5/plugins/platformthemes" >> blacklist_pyqt.txt

# Cleaning PyQt
./blacklist_clean.sh "./AppDir/opt/python${PYTHON_VERSION}/lib/python${PYTHON_VERSION}/site-packages" blacklist_pyqt.txt

echo "==> Setting up meta & entry point"

# Meta
install -Dm 644 $BUILD_DIR/meta/${APP_ID}.desktop     ./AppDir/usr/share/applications/${APP_ID}.desktop
install -Dm 644 $BUILD_DIR/meta/${APP_ID}.appdata.xml ./AppDir/usr/share/metainfo/${APP_ID}.appdata.xml
install -Dm 644 $BUILD_DIR/meta/${APP_ID}.xml         ./AppDir/usr/share/mime/packages/${APP_ID}.xml
cp -R $BUILD_DIR/meta/icons ./AppDir/usr/share

# AppImage entry point
gcc -fPIC -o ./AppDir/AppRun "$SCRIPT_DIR/AppRun.c" -ldl
strip ./AppDir/AppRun

echo "==> Setting up binary dependencies"

# Qt5/plugins/platforms/libqxcb.so dependencies
yum install -y libxkbcommon-x11 xcb-util xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm || true

# VLC and libmpv: EPEL's, with RPM Fusion's ffmpeg in place of EPEL's, which
# leaves out H.264, HEVC and AAC. Same libraries by name, so both take it.
if [ ! -f /usr/lib64/libmpv.so.2 ]; then
    dnf install -y epel-release dnf-plugins-core
    dnf config-manager --set-enabled crb
    dnf install -y https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-9.noarch.rpm
    dnf install -y vlc vlc-plugins-freeworld mpv-libs
    dnf swap -y ffmpeg-free ffmpeg --allowerasing
fi

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
FALLBACK_LIBS=(
    libva.so.2 libva-drm.so.2 libva-x11.so.2 libva-wayland.so.2
    libvdpau.so.1 libvulkan.so.1 libGLESv2.so.2
    libwayland-client.so.0 libwayland-cursor.so.0 libwayland-egl.so.1
    libpipewire-0.3.so.0 libpulse.so.0
)
FALLBACK_EXCLUDES=()

for lib in "${FALLBACK_LIBS[@]}"; do
    real=$(readlink -f "/usr/lib64/$lib")
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
export UPDATE_INFORMATION="gh-releases-zsync|vzhd1701|gridplayer|$APP_UPDATE_RELEASE|GridPlayer-*x86_64.AppImage.zsync"
export ARCH="x86_64"
export VERSION="$APP_FILE_VERSION"

./linuxdeploy-x86_64.AppImage \
    -l /lib64/libxcb-icccm.so.4 \
    -l /lib64/libxcb-render-util.so.0 \
    -l /lib64/libxcb-util.so.1 \
    -l /lib64/libxcb-image.so.0 \
    -l /lib64/libxcb-keysyms.so.1 \
    -l /lib64/libxkbcommon-x11.so.0 \
    -l /lib64/libxcb-xinerama.so.0 \
    "${FALLBACK_EXCLUDES[@]}" \
    --appdir AppDir \
    --output appimage

chmod 777 "$BUILD_DIR_APPIMAGE/$APP_NAME"*.AppImage*
mv "$BUILD_DIR_APPIMAGE/$APP_NAME"*.AppImage* "$DIST_DIR"
