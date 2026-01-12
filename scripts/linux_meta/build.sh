#!/bin/bash

#apt install desktop-file-utils appstream-util

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

BUILD_DIR_META="$BUILD_DIR/meta"
mkdir -p "$BUILD_DIR_META"

copy_with_app_vars "$SCRIPT_DIR/app.desktop" "$BUILD_DIR_META/${APP_ID}.desktop"

desktop-file-validate "$BUILD_DIR_META/${APP_ID}.desktop"

copy_with_app_vars "$SCRIPT_DIR/app.appdata.xml" "$BUILD_DIR_META/${APP_ID}.appdata.xml"

appstream-util validate "$BUILD_DIR_META/${APP_ID}.appdata.xml"

copy_with_app_vars "$SCRIPT_DIR/mime.xml" "$BUILD_DIR_META/${APP_ID}.xml"

rm -rf "$BUILD_DIR_META/icons"

#ICON_NAME="application-x-gridplayer-playlist"
ICON_NAME="${APP_ID}.gpls"

ICON_SIZES=("16x16" "16x16@2x" "24x24" "24x24@2x" "32x32" "32x32@2x" "48x48" "48x48@2x" "64x64" "128x128" "256x256" "256x256@2x")
for i_size in "${ICON_SIZES[@]}"; do
    install -Dm644 "$RESOURCES_DIR/icons/main/png/${i_size}.png" "$BUILD_DIR_META/icons/hicolor/${i_size}/apps/${APP_ID}.png"
    install -Dm644 "$RESOURCES_DIR/icons/playlist/png/${i_size}.png" "$BUILD_DIR_META/icons/hicolor/${i_size}/mimetypes/${ICON_NAME}.png"
done

#install -Dm644 "$RESOURCES_DIR/icons/main/svg/normal.svg" "$BUILD_DIR_META/icons/hicolor/scalable/apps/${APP_ID}.svg"

install -Dm644 "$RESOURCES_DIR/icons/main/svg/big.svg" "$BUILD_DIR_META/icons/hicolor/scalable/apps/${APP_ID}.svg"
install -Dm644 "$RESOURCES_DIR/icons/main/svg/symbolic.svg" "$BUILD_DIR_META/icons/hicolor/scalable/apps/${APP_ID}-symbolic.svg"
install -Dm644 "$RESOURCES_DIR/icons/main/svg/symbolic.svg" "$BUILD_DIR_META/icons/hicolor/symbolic/apps/${APP_ID}-symbolic.svg"

install -Dm644 "$RESOURCES_DIR/icons/playlist/svg/big.svg" "$BUILD_DIR_META/icons/hicolor/scalable/mimetypes/${ICON_NAME}.svg"
install -Dm644 "$RESOURCES_DIR/icons/playlist/svg/symbolic.svg" "$BUILD_DIR_META/icons/hicolor/scalable/mimetypes/${ICON_NAME}-symbolic.svg"
install -Dm644 "$RESOURCES_DIR/icons/playlist/svg/symbolic.svg" "$BUILD_DIR_META/icons/hicolor/symbolic/mimetypes/${ICON_NAME}-symbolic.svg"
