import os
import sys

IS_PYINSTALLER = getattr(sys, "frozen", False)
IS_SNAP = "SNAP" in os.environ
IS_APPIMAGE = "APPIMAGE" in os.environ
IS_FLATPAK = "FLATPAK_ID" in os.environ

VLC_VERSION = None
VLC_PYTHON_VERSION = None
