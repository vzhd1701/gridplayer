#!/bin/bash

# sudo snap install snapcraft --classic

set -e

if [ "$1" == "--no-build" ]; then
    NO_BUILD="1"
fi

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

BUILD_DIR_SNAP="$BUILD_DIR/snap"
mkdir -p "$BUILD_DIR_SNAP"

# Preparation

rm -f "$BUILD_DIR_SNAP"/*.whl
cp "$DIST_DIR"/*.whl "$BUILD_DIR_SNAP"
cp -R "$BUILD_DIR/meta" "$BUILD_DIR_SNAP"

cp "$SCRIPTS_DIR/_helpers/blacklist_pyqt.txt" "$BUILD_DIR_SNAP"
cp "$SCRIPTS_DIR/_helpers/blacklist_vlc_linux.txt" "$BUILD_DIR_SNAP"
cp "$SCRIPTS_DIR/_helpers/blacklist_snap.txt" "$BUILD_DIR_SNAP"
cp "$SCRIPTS_DIR/_helpers/blacklist_clean.sh" "$BUILD_DIR_SNAP"

cp "$SCRIPT_DIR/apt_dl.sh" "$BUILD_DIR_SNAP"

chmod +x "$BUILD_DIR_SNAP"/*.sh

mkdir -p "$BUILD_DIR_SNAP/snap"
copy_with_app_vars "$SCRIPT_DIR/snapcraft.yaml" "$BUILD_DIR_SNAP/snap"

WHL_FILE=$(cd "$BUILD_DIR_SNAP" && ls *.whl)
sed -i "s#{WHL_FILE}#$WHL_FILE#g" "$BUILD_DIR_SNAP/snap/snapcraft.yaml"

[ -n "$NO_BUILD" ] && exit 0

# Build

(cd "$BUILD_DIR_SNAP" && snapcraft pack "$@")

# Result

mv "$BUILD_DIR_SNAP"/*.snap "$DIST_DIR"
