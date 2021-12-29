#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

crowdin.bat download -c "$SCRIPT_DIR/crowdin.yml" --identity ".local/crowdin.yml" --skip-untranslated-files --export-only-approved "$@"
