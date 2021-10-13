#!/bin/bash

DIST_DIR="$1"
BL_LIST_FILE="$2"

while IFS= read -r del_file; do
    echo "Removing $DIST_DIR/$del_file"
    find "$DIST_DIR" -iwholename "$DIST_DIR/$del_file" -exec rm -rf {} +
done < "$BL_LIST_FILE"
