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

pip install PyYAML requirements-parser packaging

wget -nc -q -O flatpak-pip-generator https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/dda10aa5949811589747e6e485da6ae2e86b5d2b/pip/flatpak-pip-generator.py || [ $? -eq 1 ]

rm -f *.yml

python flatpak-pip-generator --requirements-file="$BUILD_DIR_PYTHON_DEPS/requirements.txt" --yaml --cleanup scripts --output dependencies --prefer-wheels pydantic_core --runtime "org.kde.Sdk//5.15-25.08"
mv dependencies.yaml dependencies.yml

python flatpak-pip-generator --yaml --build-only --output uv_build --prefer-wheels uv_build --runtime "org.kde.Sdk//5.15-25.08" uv_build
mv uv_build.yaml uv_build.yml

md5sum "requirements.txt" > "build.md5"
