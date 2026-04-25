#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

source "scripts/init_app_vars.sh"

DEFAULT_DMG_FILE="$DIST_DIR/$APP_NAME $APP_VERSION.dmg"
TARGET_DMG_FILE="$DIST_DIR/$APP_NAME $APP_VERSION"_"$APP_TARGET_ARCH_SUFFIX.dmg"

create_default_dmg() {
    create-dmg --overwrite "$DIST_DIR/$APP_NAME.app" "$DIST_DIR"
}

create_fallback_dmg() {
    hdiutil create \
        -ov \
        -fs HFS+ \
        -srcfolder "$DIST_DIR/$APP_NAME.app" \
        -volname "$APP_NAME" \
        -format UDZO \
        "$TARGET_DMG_FILE"
}

if command -v create-dmg >/dev/null 2>&1 && create_default_dmg; then
    mv -f "$DEFAULT_DMG_FILE" "$TARGET_DMG_FILE"
else
    echo "create-dmg failed, falling back to hdiutil packaging"
    create_fallback_dmg
fi
