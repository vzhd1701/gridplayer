#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

PYLUPDATE=$(uv run --frozen which pylupdate5)
DEST_TS_FILE="$RESOURCES_DIR/translations/en_US.ts"

TEMPD=$(mktemp -d)

echo "Copying code into $TEMPD"
cp -a "$APP_BASE_DIR" "$TEMPD"

APP_BASE_TMP="$TEMPD/$APP_MODULE"

echo "Putting translate calls on single lines"

# pylupdate5 misses a translate(***) whose text does not start on the line it opens on
uv run --frozen python "$SCRIPT_DIR/flatten_translate_calls.py" "$APP_BASE_TMP"

echo "Extracting translation lines"
cp "$DEST_TS_FILE" "$APP_BASE_TMP/en_US.ts"

(cd "$APP_BASE_TMP" && $PYLUPDATE -noobsolete -verbose $(find ./ -name "*.py" -printf "%p ") -ts "en_US.ts")

cp "$APP_BASE_TMP/en_US.ts" "$DEST_TS_FILE"

rm -rf "$TEMPD"
