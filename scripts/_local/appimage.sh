#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

if [ "$1" == "run" ]; then
    "$DIST_DIR"/*.AppImage "${@:2}"
    exit 0
fi

if [ ! -f /usr/local/bin/appimagetool ]; then
    sudo wget -nc https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage -O /usr/local/bin/appimagetool
    #sudo wget -nc https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-x86_64.AppImage -O /usr/local/bin/appimagetool
    sudo chmod +x /usr/local/bin/appimagetool
fi

poetry build -f wheel

if [ ! -d venv-builder ]; then
    python3 -m venv venv-builder
    . venv-builder/bin/activate
    pip install appimage-builder
fi

. venv-builder/bin/activate

bash "$SCRIPTS_DIR/linux_meta/build.sh"

bash "$SCRIPTS_DIR/appimage/build.sh" "$@"
