#!/bin/bash

set -e

. "scripts/init_app_vars.sh"

DEST_TS_FILE="${1:-$RESOURCES_DIR/translations/en_US.ts}"

TEMPD=$(mktemp -d)

echo "Copying code into $TEMPD"
cp -a "$APP_BASE_DIR" "$TEMPD"

APP_BASE_TMP="$TEMPD/$APP_MODULE"

echo "Extracting translation lines"
cp "$DEST_TS_FILE" "$APP_BASE_TMP/en_US.ts"

# Run from inside the copy, so each location reads "dialogs/about.py"
# whatever the checkout's path
(cd "$APP_BASE_TMP" && uv run --frozen --project "$OLDPWD" pylupdate6 --no-obsolete . --ts en_US.ts)

# pylupdate6 writes the path with the system's separator: "/" everywhere
sed -i -E '/<location /s#\\#/#g' "$APP_BASE_TMP/en_US.ts"

cp "$APP_BASE_TMP/en_US.ts" "$DEST_TS_FILE"

rm -rf "$TEMPD"
