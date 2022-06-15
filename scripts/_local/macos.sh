#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

check() {
    which $1 >/dev/null
}

# install poetry
if ! check poetry; then
    echo "Installing poetry"

    ln -s /etc/ssl/* /Library/Frameworks/Python.framework/Versions/3.*/etc/openssl
    curl -sSL https://install.python-poetry.org | python3 -
    echo "export PATH=\"/Users/admin/Library/Python/3.8/bin:\$PATH\"" >> ~/.bash_profile
    source ~/.bash_profile
fi

brew install gnu-sed wget node graphicsmagick imagemagick
check create-dmg || npm install --global create-dmg

pip3 install urllib3 virtualenv

. "scripts/init_app_vars.sh"

mkdir -p "$BUILD_DIR"

poetry export --without-hashes -o "$BUILD_DIR/requirements.txt"

bash "$SCRIPTS_DIR/pyinstaller/build_mac.sh"

bash "$SCRIPTS_DIR/macos/build_dmg.sh"
