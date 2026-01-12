#!/bin/bash

set -e
set -x

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

process_requirements() {
    requirements="$1"

    packages_del=(
        "pyqt5-qt5" "pyqt5-sip" "pyqt5"
        "brotlicffi" "cffi" "pycparser"
        "pyobjc-core" "pyobjc-framework-cocoa" "exceptiongroup" "six"
    )

    # exceptiongroup not needed with Python >3.11

    for package in "${packages_del[@]}"; do
        sed -i "/^$package==/d" "$requirements"
    done

    # 4.9.3 doesnt compile with libxml2 >2.13.9
    sed -i 's/\(lxml==\)[0-9]\+\(\.[0-9]\+\)*/\15.3.0/g' "$requirements"
}

BUILD_DIR_PYTHON_DEPS="$BUILD_DIR/flatpak_python_deps"
mkdir -p "$BUILD_DIR_PYTHON_DEPS"

cp "$BUILD_DIR/requirements.txt" "$BUILD_DIR_PYTHON_DEPS/requirements.txt"
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

#wget -nc -q -O flatpak-pip-generator https://github.com/flatpak/flatpak-builder-tools/raw/master/pip/flatpak-pip-generator.py

# Noting useful is stored in /share by python modules
#sed -i "s#module\['cleanup'\] = \['/bin', '/share/man/man1'\]#module\['cleanup'\] = \['/bin', '/share'\]#g" flatpak-pip-generator

rm -f dependencies.*

python "$SCRIPTS_DIR/flatpak/flatpak-pip-generator.py" --requirements-file="$BUILD_DIR_PYTHON_DEPS/requirements.txt" --yaml --cleanup scripts --output dependencies --use-prebuilt-wheels pydantic_core
mv dependencies.yaml dependencies.yml

md5sum "requirements.txt" > "build.md5"
