#!/bin/bash

set -e

# choco install zip innosetup

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

source "scripts/init_app_vars.sh"

# Convert c:\path to c:\\path
escapeSubst() { sed 's/[&#\]/\\&/g'; }

ISCC="/c/Program Files (x86)/Inno Setup 6/ISCC.exe"

echo "Building installer"

cp "$SCRIPT_DIR/installer.iss" "$BUILD_DIR/installer.iss"

# win64 or winarm64, as BUILD_WIN_ARCH says, the one the package was built for
INSTALLER_SUFFIX="$APP_TARGET_ARCH_SUFFIX-install"
PORTABLE_SUFFIX="$APP_TARGET_ARCH_SUFFIX-portable"

# Inno Setup's name for it: the arm64 installer won't start on x64 Windows,
# nor the x64 one on arm64, where the arm64 package is the one to have
INNO_ARCH="$APP_TARGET_ARCH"

APP_SRC=$(cygpath -w "$DIST_DIR/$APP_NAME" | escapeSubst)

replace_app_vars "$BUILD_DIR/installer.iss"

sed -i "s#{APP_SRC}#$APP_SRC#g" "$BUILD_DIR/installer.iss"
sed -i "s#{INNO_ARCH}#$INNO_ARCH#g" "$BUILD_DIR/installer.iss"
PYTHONPATH="$ROOT_DIR" python "$SCRIPT_DIR/generate_file_associations.py" "{APP_FILE_ASSOCIATIONS}" "$BUILD_DIR/installer.iss"

"$ISCC" //O"dist" //F"$APP_NAME-$APP_FILE_VERSION-$INSTALLER_SUFFIX" "$BUILD_DIR/installer.iss"

echo "Building portable zip"

pushd "$DIST_DIR"

mkdir "$APP_NAME/portable_data"

zip -r "$APP_NAME-$APP_FILE_VERSION-$PORTABLE_SUFFIX.zip" "$APP_NAME"

rmdir "$APP_NAME/portable_data"

popd
