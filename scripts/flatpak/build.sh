#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

BUILD_DIR_FLATPAK="$BUILD_DIR/flatpak"
mkdir -p "$BUILD_DIR_FLATPAK"

# Preparation

cp "$DIST_DIR"/*.tar.gz "$BUILD_DIR_FLATPAK"
cp -R "$BUILD_DIR/meta" "$BUILD_DIR_FLATPAK"

cp "$SCRIPT_DIR"/dependencies/*.yml "$BUILD_DIR_FLATPAK"
cp "$SCRIPT_DIR"/libvlc/* "$BUILD_DIR_FLATPAK"

if [ ! -f "$BUILD_DIR/flatpak_python_deps/dependencies.yml" ]; then
    "$SCRIPT_DIR/generate_dependencies.sh"
fi
cp "$BUILD_DIR/flatpak_python_deps/dependencies.yml" "$BUILD_DIR_FLATPAK/dependencies.yml"

cat "$SCRIPT_DIR/app.yml" "$SCRIPT_DIR/app_local.yml" > "$BUILD_DIR_FLATPAK/$APP_ID.yml"
replace_app_vars "$BUILD_DIR_FLATPAK/$APP_ID.yml"

TAR_FILE=$(cd "$BUILD_DIR_FLATPAK" && ls *.tar.gz)
TAR_FILE_SHA256=$(sha256sum "$BUILD_DIR_FLATPAK/$TAR_FILE" | cut -d ' ' -f 1)
sed -i "s#{TAR_FILE}#$TAR_FILE#g" "$BUILD_DIR_FLATPAK/$APP_ID.yml"
sed -i "s#{TAR_FILE_SHA256}#$TAR_FILE_SHA256#g" "$BUILD_DIR_FLATPAK/$APP_ID.yml"

if [ ! -d "$BUILD_DIR_FLATPAK/shared-modules" ]; then
    git clone -n https://github.com/flathub/shared-modules "$BUILD_DIR_FLATPAK/shared-modules"
    (cd "$BUILD_DIR_FLATPAK/shared-modules" && git checkout -q 50314360ded6fa3b9f0b602513b1164b7a6636ed)
fi

# Prevent strange freezing
flatpak permission-reset ${APP_ID}

# Build

cd "$BUILD_DIR_FLATPAK"

if [ "$1" == "install" ]; then
    flatpak run org.flatpak.Builder -v \
        --user --install \
        --ccache \
        --force-clean \
        flatpak_build \
        ${APP_ID}.yml
    exit 0
fi

flatpak run org.flatpak.Builder -v \
    --ccache \
    --force-clean \
    --repo=repo \
    --subject="Build of ${APP_ID} `date +\"%F %T\"`" \
    flatpak_build \
    ${APP_ID}.yml

flatpak build-bundle repo ${APP_MODULE}.flatpak ${APP_ID} --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo
rm -rf repo

# Result

mv "$BUILD_DIR_FLATPAK"/*.flatpak "$DIST_DIR"
