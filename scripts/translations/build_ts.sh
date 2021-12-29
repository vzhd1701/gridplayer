#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

DEST_TS_FILE="$RESOURCES_DIR/translations/en_US.ts"

poetry run pylupdate5 -noobsolete -verbose $(find "$APP_BASE_DIR" -name "*.py" -printf "%p ") -ts "$DEST_TS_FILE"
