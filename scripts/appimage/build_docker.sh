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

PYTHON_VERSION="3.10"
BASE_IMAGE_NAME="manylinux_2_28_x86_64"

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

if [ ! -f "base.AppImage" ]; then
    echo "==> Fetching Python base image"

    PYTHON_APPIMAGE_URL=$(curl -s "https://api.github.com/repos/niess/python-appimage/releases" | jq -r ".[] | select(.name==\"Python $PYTHON_VERSION\") | .assets[] | select(.name|test(\"$BASE_IMAGE_NAME\")) | .browser_download_url")

    curl -L -s -o base.AppImage "$PYTHON_APPIMAGE_URL" || true
    chmod +x base.AppImage
fi

rm -rf "AppDir"
rm -f "$APP_NAME"*.AppImage*

echo "==> Python ${PYTHON_VERSION} init"

./base.AppImage --appimage-extract > /dev/null
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
gcc -fPIC -o ./AppDir/AppRun "$SCRIPT_DIR/AppRun.c"
strip ./AppDir/AppRun

echo "==> Setting up binary dependencies"

# Qt5/plugins/platforms/libqxcb.so dependencies
yum install -y libxkbcommon-x11 xcb-util xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm || true

# VLC
if ! which vlc; then
    yum install -y https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-8.noarch.rpm
    yum install -y vlc
fi

LIB_DIR="./AppDir/usr/lib"
mkdir -p "$LIB_DIR"

cp /usr/lib64/libvlc* "$LIB_DIR"
cp -a /usr/lib64/vlc "$LIB_DIR"

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
export UPDATE_INFORMATION="gh-releases-zsync|vzhd1701|gridplayer|latest|GridPlayer-*x86_64.AppImage.zsync"
export ARCH="x86_64"
export VERSION="$APP_VERSION"

./linuxdeploy-x86_64.AppImage \
    -l /lib64/libxcb-icccm.so.4 \
    -l /lib64/libxcb-render-util.so.0 \
    -l /lib64/libxcb-util.so.1 \
    -l /lib64/libxcb-image.so.0 \
    -l /lib64/libxcb-keysyms.so.1 \
    -l /lib64/libxkbcommon-x11.so.0 \
    -l /lib64/libxcb-xinerama.so.0 \
    --appdir AppDir \
    --output appimage

chmod 777 "$BUILD_DIR_APPIMAGE/$APP_NAME"*.AppImage*
mv "$BUILD_DIR_APPIMAGE/$APP_NAME"*.AppImage* "$DIST_DIR"
