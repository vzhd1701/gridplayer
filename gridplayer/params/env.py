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

if IS_FLATPAK:
    FLATPAK_RUNTIME_DIR = (
        Path(os.environ["XDG_RUNTIME_DIR"])
        / "app"
        / os.environ["FLATPAK_ID"]
        / "gridplayer"
    )
    FLATPAK_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
else:
    FLATPAK_RUNTIME_DIR = None
