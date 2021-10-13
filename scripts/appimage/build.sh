#!/bin/bash

# zsync

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

BUILD_DIR_APPIMAGE="$BUILD_DIR/appimage"
mkdir -p "$BUILD_DIR_APPIMAGE"

# Preparation

cp "$DIST_DIR"/*.whl "$BUILD_DIR_APPIMAGE"
cp -R "$BUILD_DIR/meta" "$BUILD_DIR_APPIMAGE"

cp "$SCRIPTS_DIR/_helpers/blacklist_clean.sh" "$BUILD_DIR_APPIMAGE"
cp "$SCRIPTS_DIR/_helpers/blacklist_pyqt.txt" "$BUILD_DIR_APPIMAGE"
chmod +x "$BUILD_DIR_APPIMAGE/blacklist_clean.sh"

copy_with_app_vars "$SCRIPT_DIR/app.yml" "$BUILD_DIR_APPIMAGE/${APP_NAME}.yml"

cp "$SCRIPT_DIR/AppRun" "$BUILD_DIR_APPIMAGE"

echo "$APP_VERSION" > "$BUILD_DIR_APPIMAGE/VERSION"

if [ ! -d "$BUILD_DIR_APPIMAGE/pkg2appimage" ]; then
    git clone -n https://github.com/AppImage/pkg2appimage "$BUILD_DIR_APPIMAGE/pkg2appimage"
    (cd "$BUILD_DIR_APPIMAGE/pkg2appimage" && git checkout -q 57350cb52552f62a9dc1fa3aca32a502235713f0)
fi

# Build

cd "$BUILD_DIR_APPIMAGE"

export ARCH="x86_64"
export NO_GLIBC_VERSION="1"
export VERSION="$APP_VERSION"

#wget -nc https://github.com/$(wget -q https://github.com/AppImage/pkg2appimage/releases -O - | grep "pkg2appimage-.*-x86_64.AppImage" | head -n 1 | cut -d '"' -f 2)
#chmod +x ./pkg2appimage-*.AppImage
#./pkg2appimage-*.AppImage "./${APP_NAME}.yml"

./pkg2appimage/pkg2appimage "./${APP_NAME}.yml"

cd ..

mv "$BUILD_DIR_APPIMAGE"/out/*.AppImage "$DIST_DIR"
mv "$BUILD_DIR_APPIMAGE"/out/*.zsync "$DIST_DIR"
