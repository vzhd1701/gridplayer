#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

source "scripts/init_app_vars.sh"

create-dmg --overwrite "$DIST_DIR/$APP_NAME.app" "$DIST_DIR" || true
