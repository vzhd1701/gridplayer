#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

echo "Building UI files..."

FILES="$RESOURCES_DIR/ui/*"
for ui_src_file in $FILES
do
    ui_src=$(basename $ui_src_file)
    ui_dest="${ui_src%.*}_ui.py"

    echo "Converting $ui_src -> $ui_dest..."

    poetry run pyuic5 "$ui_src_file" -o "$APP_BASE_DIR/dialogs/$ui_dest"
done

# strip comments
sed -i 's/^#.*$//g' "$APP_BASE_DIR/dialogs"/*_ui.py

dos2unix "$APP_BASE_DIR/dialogs"/*_ui.py
poetry run black "$APP_BASE_DIR/dialogs"/*_ui.py
