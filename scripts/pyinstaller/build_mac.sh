#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname $0 )" && pwd )"

. "scripts/init_app_vars.sh"

assert_target_python_arch() {
    PYTHON_ARCH="$(python -c 'import platform; print(platform.machine())')"

    if [ "$PYTHON_ARCH" != "$APP_TARGET_ARCH" ]; then
        die "Active Python interpreter is $PYTHON_ARCH, but BUILD_MACOS_ARCH=$APP_TARGET_ARCH. Use a native $APP_TARGET_ARCH Python interpreter."
    fi
}

assert_target_dependency_arch() {
    python <<'PY'
import os
import platform
import subprocess
from pathlib import Path

target_arch = os.environ["APP_TARGET_ARCH"]
python_arch = platform.machine()

if python_arch != target_arch:
    raise SystemExit(
        f"Active Python interpreter is {python_arch}, but BUILD_MACOS_ARCH={target_arch}. "
        f"Use a native {target_arch} Python interpreter."
    )

paths_to_check = []

from PyQt5 import QtCore

qtcore_ext = Path(QtCore.__file__).resolve()
paths_to_check.append((qtcore_ext, "PyQt5.QtCore extension"))

qt_framework = qtcore_ext.parent / "Qt5" / "lib" / "QtCore.framework" / "Versions" / "5" / "QtCore"
if qt_framework.exists():
    paths_to_check.append((qt_framework, "QtCore framework"))

try:
    from pydantic_core import _pydantic_core
except ModuleNotFoundError:
    pass
else:
    paths_to_check.append((Path(_pydantic_core.__file__).resolve(), "pydantic-core extension"))

try:
    from objc import _objc
except ModuleNotFoundError:
    pass
else:
    paths_to_check.append((Path(_objc.__file__).resolve(), "PyObjC extension"))

errors = []

for path, label in paths_to_check:
    lipo_result = subprocess.run(
        ["lipo", "-archs", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    if lipo_result.returncode == 0:
        archs = lipo_result.stdout.strip().split()
    else:
        file_result = subprocess.run(
            ["file", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        archs = file_result.stdout.strip().split()

    if target_arch not in archs:
        errors.append(f"{label}: expected {target_arch}, got {' '.join(archs) or 'unknown'} ({path})")

if errors:
    joined = "\n".join(errors)
    raise SystemExit(
        "Installed dependencies are not built for the requested macOS architecture:\n"
        + joined
    )
PY
}

if [ "$APP_TARGET_ARCH" = "arm64" ]; then
    VLC_URL="https://get.videolan.org/vlc/3.0.21/macosx/vlc-3.0.21-arm64.dmg"
else
    VLC_URL="https://get.videolan.org/vlc/3.0.21/macosx/vlc-3.0.21-intel64.dmg"
fi

PYINSTALLER_VERSION="6.17.0"

mkdir -p "$BUILD_DIR"

init_venv "$BUILD_DIR/venv-pyinstaller-$APP_TARGET_ARCH"
assert_target_python_arch

# Reduce size by installing src version of pydantic
export PIP_NO_BINARY="pydantic"

pip install -r "$BUILD_DIR/requirements.txt"
pip install pyinstaller=="$PYINSTALLER_VERSION"
assert_target_dependency_arch

# Copy icons to build dir
cp "$RESOURCES_DIR/icons/main/sys/macos.icns" "$BUILD_DIR/main.icns"
cp "$RESOURCES_DIR/icons/playlist/sys/macos.icns" "$BUILD_DIR/mime.icns"

cp "$SCRIPT_DIR/mime_vlc.plist" "$BUILD_DIR/mime_vlc.plist"

copy_with_app_vars "$SCRIPT_DIR/pyinstaller_mac.spec" "$BUILD_DIR/$APP_NAME.spec"

pyinstaller --clean --noconfirm "$BUILD_DIR/$APP_NAME.spec"

# Post-build
# =============

echo "Embedding VLC"

VLC_EMBED_SRC=$(realpath "$BUILD_DIR")/libVLC-$APP_TARGET_ARCH
VLC_DMG="$BUILD_DIR/vlc-$APP_TARGET_ARCH.dmg"

if [ ! -d "$VLC_EMBED_SRC" ]; then
    wget -q -nc -O "$VLC_DMG" "$VLC_URL" || true

    hdiutil attach "$VLC_DMG"

    VLC_SRC="/Volumes/VLC media player/VLC.app/Contents/MacOS"

    mkdir -p "$VLC_EMBED_SRC"

    cp -a "$VLC_SRC/lib" "$VLC_EMBED_SRC"
    cp -a "$VLC_SRC/plugins" "$VLC_EMBED_SRC"

    #mkdir -p "$VLC_EMBED_SRC/plugins"
    #while IFS= read -r plugin_file; do
    #    cp "$VLC_SRC/plugins/$plugin_file" "$VLC_EMBED_SRC/plugins" || true
    #done < "$SCRIPT_DIR/vlc_plugins_wl.txt"

    hdiutil detach "/Volumes/VLC media player"
fi

rm -rf "$DIST_DIR/$APP_NAME.app/Contents/MacOS/libVLC"
cp -a "$VLC_EMBED_SRC" "$DIST_DIR/$APP_NAME.app/Contents/MacOS/libVLC"
