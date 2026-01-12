#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

source "scripts/init_app_vars.sh"

create-dmg --overwrite "$DIST_DIR/$APP_NAME.app" "$DIST_DIR" || true

DMG_FILE=$(echo "$DIST_DIR"/GridPlayer*.dmg)

if [ "$(uname -m)" = "arm64" ]; then
    mv "$DMG_FILE" "${DMG_FILE%.dmg}_arm64.dmg"
else
    mv "$DMG_FILE" "${DMG_FILE%.dmg}_intel64.dmg"
fi
