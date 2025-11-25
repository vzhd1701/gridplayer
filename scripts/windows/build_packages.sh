#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

source "scripts/init_app_vars.sh"

# Get machine architecture
if [ -z "$BUILD_ARCH" ]; then
    BUILD_ARCH=$(python -c "import platform; print('win32' if platform.architecture()[0] == '32bit' else 'win64')")
fi

# Convert c:\path to c:\\path
escapeSubst() { sed 's/[&#\]/\\&/g'; }

ISCC="/c/Program Files (x86)/Inno Setup 6/ISCC.exe"

echo "Building installer"

cp "$SCRIPT_DIR/installer.iss" "$BUILD_DIR/installer.iss"

# Update installer.iss for architecture
if [ "$BUILD_ARCH" = "win32" ]; then
    sed -i 's/ArchitecturesAllowed=x64/ArchitecturesAllowed=x86/g' "$BUILD_DIR/installer.iss"
    sed -i 's/ArchitecturesInstallIn64BitMode=x64/ArchitecturesInstallIn64BitMode=x86/g' "$BUILD_DIR/installer.iss"
    sed -i 's/Flags: nowait postinstall skipifsilent 64bit/Flags: nowait postinstall skipifsilent/g' "$BUILD_DIR/installer.iss"
    INSTALLER_SUFFIX="win32-install"
    PORTABLE_SUFFIX="win32-portable"
else
    INSTALLER_SUFFIX="win64-install"
    PORTABLE_SUFFIX="win64-portable"
fi

APP_SRC=$(cygpath -w "$DIST_DIR/$APP_NAME" | escapeSubst)

replace_app_vars "$BUILD_DIR/installer.iss"

sed -i "s#{APP_SRC}#$APP_SRC#g" "$BUILD_DIR/installer.iss"
PYTHONPATH="$ROOT_DIR" python "$SCRIPT_DIR/generate_file_associations.py" "{APP_FILE_ASSOCIATIONS}" "$BUILD_DIR/installer.iss"

"$ISCC" //O"dist" //F"$APP_NAME-$APP_VERSION-$INSTALLER_SUFFIX" "$BUILD_DIR/installer.iss"

echo "Building portable zip"

pushd "$DIST_DIR"

mkdir "$APP_NAME/portable_data"

zip -r "$APP_NAME-$APP_VERSION-$PORTABLE_SUFFIX.zip" "$APP_NAME"

rmdir "$APP_NAME/portable_data"

popd
