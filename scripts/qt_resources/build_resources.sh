#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

echo "Building resources..."

BUILD_DIR_QT_RESOURCES="$BUILD_DIR/qt_resources"

rm -rf "$BUILD_DIR_QT_RESOURCES"

poetry run python "$SCRIPT_DIR/build_resources.py" "$RESOURCES_DIR" "$BUILD_DIR_QT_RESOURCES"

PYRCC5=$(poetry run which pyrcc5)
(cd "$BUILD_DIR_QT_RESOURCES" && $PYRCC5 resources.qrc -o "$APP_BASE_DIR/resources_bin.py")

dos2unix "$APP_BASE_DIR/resources_bin.py"
