#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

if [ -n "$1" ]; then
    echo "Downloading translation for language $1"
    crowdin.bat download -c "$SCRIPT_DIR/crowdin.yml" --identity ".local/crowdin.yml" --skip-untranslated-strings --export-only-approved --language="$1"
    exit 0
fi

echo "Downloading all completed translations"
crowdin.bat download -c "$SCRIPT_DIR/crowdin.yml" --identity ".local/crowdin.yml" --skip-untranslated-files --export-only-approved
