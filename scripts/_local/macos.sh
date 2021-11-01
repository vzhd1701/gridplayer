#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

# install python with venv, poetry
brew install gnu-sed wget
brew install node graphicsmagick imagemagick
npm install --global create-dmg

pip install urllib3 virtualenv

mkdir -p "$BUILD_DIR"

poetry export --without-hashes -o "$BUILD_DIR/requirements.txt"

bash "$SCRIPTS_DIR/pyinstaller/build_mac.sh"

bash "$SCRIPTS_DIR/macos/build_dmg.sh"
