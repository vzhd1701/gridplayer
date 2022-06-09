import os
import sys
from pathlib import Path

IS_PYINSTALLER = getattr(sys, "frozen", False)
IS_SNAP = "SNAP" in os.environ
IS_APPIMAGE = "APPIMAGE" in os.environ
IS_FLATPAK = "FLATPAK_ID" in os.environ

PYINSTALLER_LIB_ROOT = (
    Path(sys._MEIPASS) if IS_PYINSTALLER else Path.cwd()  # noqa: WPS437
)

VLC_VERSION = None
VLC_PYTHON_VERSION = None
