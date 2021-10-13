#!/bin/bash

if [[ "$OSTYPE" == "darwin"* ]]; then
  function sed() { command gsed "$@"; }
fi

get_python_vlc_version() {
    # Need to run inside venv for pyinstaller

    SITE_PACKAGES=$(python -c 'import site; print(site.getsitepackages()[-1])')
    PYTHON_VLC_VER=$(sed -n 's/__version__ = "\([^"]*\).*/\1/p' "$SITE_PACKAGES/vlc.py")

    echo "$PYTHON_VLC_VER"
}
