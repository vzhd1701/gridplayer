#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

source "scripts/init_app_vars.sh"

# Convert c:\path to c:\\path
escapeSubst() { sed 's/[&#\]/\\&/g'; }

ISCC="/c/Program Files (x86)/Inno Setup 6/ISCC.exe"

echo "Building installer"

cp "$SCRIPT_DIR/installer.iss" "$BUILD_DIR/installer.iss"

APP_SRC=$(cygpath -w "$DIST_DIR/$APP_NAME" | escapeSubst)
APP_EXT_DESC="$DISP_NAME Playlist"
APP_EXT="gpls"

replace_app_vars "$BUILD_DIR/installer.iss"

sed -i "s#{APP_SRC}#$APP_SRC#g" "$BUILD_DIR/installer.iss"
sed -i "s#{APP_EXT}#$APP_EXT#g" "$BUILD_DIR/installer.iss"
sed -i "s#{APP_EXT_DESC}#$APP_EXT_DESC#g" "$BUILD_DIR/installer.iss"

"$ISCC" //O"dist" //F"$APP_NAME-$APP_VERSION-win64-install" "$BUILD_DIR/installer.iss"

echo "Building portable zip"

pushd "$DIST_DIR"

mkdir "$APP_NAME/portable_data"

zip -r "$APP_NAME-$APP_VERSION-win64-portable.zip" "$APP_NAME"

rmdir "$APP_NAME/portable_data"

popd
