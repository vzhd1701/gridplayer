#!/bin/bash

set -e
set -x

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

BUILD_DIR_FLATPAK="$BUILD_DIR/flatpak"
mkdir -p "$BUILD_DIR_FLATPAK"

# System reqs

if ! command -v flatpak; then
    sudo apt install -y flatpak
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
fi

flatpak install --system -y flathub org.kde.Platform//5.15-24.08
flatpak install --system -y flathub org.kde.Sdk//5.15-24.08
flatpak install --system -y flathub com.riverbankcomputing.PyQt.BaseApp//5.15-24.08
flatpak install --system -y flathub org.flatpak.Builder

# Preparation

cp "$DIST_DIR"/*.tar.gz "$BUILD_DIR_FLATPAK"
cp -R "$BUILD_DIR/meta" "$BUILD_DIR_FLATPAK"

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
    (cd "$BUILD_DIR_FLATPAK/shared-modules" && git checkout -q 0529b121864669aa14fac1c67b5684a4bc6542b8)
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
