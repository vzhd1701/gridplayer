#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

BLACK=$(poetry run which black)
PYLUPDATE=$(poetry run which pylupdate5)
DEST_TS_FILE="$RESOURCES_DIR/translations/en_US.ts"

TEMPD=$(mktemp -d)

echo "Copying code into $TEMPD"
cp -a "$APP_BASE_DIR" "$TEMPD"

APP_BASE_TMP="$TEMPD/$APP_MODULE"

echo "Expanding source code lines"

# Expanding all lines so it will be easier for PYLUPDATE to parse long translate(***)
$BLACK -q -l 200000000000 -C --exclude "resources_bin.py" "$APP_BASE_TMP"

echo "Extracting translation lines"
cp "$DEST_TS_FILE" "$APP_BASE_TMP/en_US.ts"

(cd "$APP_BASE_TMP" && $PYLUPDATE -noobsolete -verbose $(find ./ -name "*.py" -printf "%p ") -ts "en_US.ts")

cp "$APP_BASE_TMP/en_US.ts" "$DEST_TS_FILE"

rm -rf "$TEMPD"
