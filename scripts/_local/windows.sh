#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

# install python with venv, poetry
# install wget, zip

mkdir -p "$BUILD_DIR"
poetry export --without-hashes -o "$BUILD_DIR/requirements.txt"

bash "$SCRIPTS_DIR/pyinstaller/build_win.sh"

if [ "$1" == "build" ]; then
    exit 0
fi

bash "$SCRIPTS_DIR/windows/build_packages.sh"

# Remove directory produced by pyinstaller
#find "$DIST_DIR" -maxdepth 1 -mindepth 1 -type d -exec rm -r {} \;
