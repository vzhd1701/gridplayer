#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

process_requirements() {
    requirements="$1"

    packages_del=(
        "pyqt5-qt5" "pyqt5-sip" "pyqt5"
        "brotlicffi" "cffi" "pycparser"
        "pyobjc-core" "pyobjc-framework-cocoa"
    )

    for package in "${packages_del[@]}"; do
        sed -i "/^$package==/d" "$requirements"
    done
}

BUILD_DIR_PYTHON_DEPS="$BUILD_DIR/flatpak_python_deps"
mkdir -p "$BUILD_DIR_PYTHON_DEPS"

poetry export --without-hashes -o "$BUILD_DIR_PYTHON_DEPS/requirements.txt"
process_requirements "$BUILD_DIR_PYTHON_DEPS/requirements.txt"

cd "$BUILD_DIR_PYTHON_DEPS"

python3 -m venv venv
. venv/bin/activate

pip install PyYAML requirements-parser

wget -nc -q https://github.com/flatpak/flatpak-builder-tools/raw/master/pip/flatpak-pip-generator

rm -f dependencies.*

python flatpak-pip-generator --requirements-file="$BUILD_DIR_PYTHON_DEPS/requirements.txt" --yaml --output dependencies
mv dependencies.yaml dependencies.yml
