#!/bin/bash

CHANGELOG=$1

sed "0,/### \[/d;/### \[/Q" "$CHANGELOG"

FULL_LOG_URL=$(sed -n 's/### \[.*\](\(.*\)) (.*/\1/p' "$CHANGELOG" | head -1)
if [ -n "$FULL_LOG_URL" ]; then
    echo "**Full Changelog**: $FULL_LOG_URL"
fi
