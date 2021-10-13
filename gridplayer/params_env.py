import os
import sys

IS_PYINSTALLER = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
IS_SNAP = "SNAP" in os.environ
IS_APPIMAGE = "APPIMAGE" in os.environ
IS_FLATPAK = "FLATPAK_ID" in os.environ
