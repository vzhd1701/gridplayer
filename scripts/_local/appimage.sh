#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

if [ "$1" == "run" ]; then
    "$DIST_DIR"/*.AppImage "${@:2}"
    exit 0
fi

poetry build -f wheel

bash "$SCRIPTS_DIR/linux_meta/build.sh"

bash "$SCRIPTS_DIR/appimage/build.sh" "$@"
