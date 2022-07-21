#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

crowdin upload sources -c "$SCRIPT_DIR/crowdin.yml" --identity ".local/crowdin.yml"
