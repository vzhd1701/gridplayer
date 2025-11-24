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

cp "$DIST_DIR/requirements.txt" "$BUILD_DIR_PYTHON_DEPS/requirements.txt"
process_requirements "$BUILD_DIR_PYTHON_DEPS/requirements.txt"

cd "$BUILD_DIR_PYTHON_DEPS"

if md5sum -c "build.md5"; then
    echo "Skipping dependencies build, requirements didn't change"
    exit 0
fi

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

. venv/bin/activate

pip install PyYAML requirements-parser

wget -nc -q -O flatpak-pip-generator https://github.com/flatpak/flatpak-builder-tools/raw/master/pip/flatpak-pip-generator.py

# Noting useful is stored in /share by python modules
sed -i "s#module\['cleanup'\] = \['/bin', '/share/man/man1'\]#module\['cleanup'\] = \['/bin', '/share'\]#g" flatpak-pip-generator

rm -f dependencies.*

python flatpak-pip-generator --requirements-file="$BUILD_DIR_PYTHON_DEPS/requirements.txt" --yaml --cleanup scripts --output dependencies
mv dependencies.yaml dependencies.yml

# Temporary workaround, maybe they'll fix it later
FIX_WEBSOCKET_URL="s#https://files.pythonhosted.org/packages/d8/3b/2ed38e52eed4cf277f9df5f0463a99199a04d9e29c9e227cfafa57bd3993/websockets-11.0.3.tar.gz#https://files.pythonhosted.org/packages/47/96/9d5749106ff57629b54360664ae7eb9afd8302fad1680ead385383e33746/websockets-11.0.3-py3-none-any.whl#g"
FIX_WEBSOCKET_URL_HASH="s/88fc51d9a26b10fc331be344f1781224a375b78488fc343620184e95a4b27016/6681ba9e7f8f3b19440921e99efbb40fc89f26cd71bf539e45d8c8a25c976dc6/g"
sed -i "$FIX_WEBSOCKET_URL" dependencies.yml
sed -i "$FIX_WEBSOCKET_URL_HASH" dependencies.yml

md5sum "requirements.txt" > "build.md5"
