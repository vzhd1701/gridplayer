#!/bin/bash

APP_BASE_DIR=$(realpath "./gridplayer")

echo "Building resources..."

(cd ./resources && pyrcc5 resources.qrc -o "$APP_BASE_DIR/resources_bin.py")

echo "Building UI files..."

FILES="resources/ui/*"
for ui_src_file in $FILES
do
    ui_src=$(basename $ui_src_file)
    ui_dest="${ui_src%.*}_ui.py"

    echo "Converting $ui_src -> $ui_dest..."

    pyuic5 "$ui_src_file" -o "$APP_BASE_DIR/dialogs/$ui_dest"
done
