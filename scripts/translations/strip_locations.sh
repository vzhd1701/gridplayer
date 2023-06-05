#!/bin/bash

set -e

for ts_file in resources/translations/*.ts; do
    if [[ $(basename "$ts_file") == "en_US.ts" ]]; then
        continue
    fi

    sed -i -E '/^[[:space:]]*<location .*\/>$/d' "$ts_file"
done
