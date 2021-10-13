#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

poetry build -f wheel

bash "$SCRIPTS_DIR/linux_meta/build.sh"

bash "$SCRIPTS_DIR/snap/build.sh" "$@"
