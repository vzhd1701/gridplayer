#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

mkdir -p "$BUILD_DIR/python_deps"

cp "poetry.lock" "$BUILD_DIR/python_deps"

cd "$BUILD_DIR/python_deps"

python3 -m venv venv
. venv/bin/activate

pip install toml PyYAML

wget -nc -q https://github.com/flatpak/flatpak-builder-tools/raw/master/poetry/flatpak-poetry-generator.py
wget -nc -q https://github.com/flatpak/flatpak-builder-tools/raw/master/flatpak-json2yaml.py

python flatpak-poetry-generator.py --production "poetry.lock"
python flatpak-json2yaml.py -o generated-poetry-sources.yml generated-poetry-sources.json
