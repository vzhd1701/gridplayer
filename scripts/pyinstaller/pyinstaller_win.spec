# -*- mode: python ; coding: utf-8 -*-

import importlib.util
import os

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, copy_metadata

def strip_list(src_list, items_to_strip):
    for x in src_list.copy():
        for r in items_to_strip:
            if x[0].startswith(r):
                try:
                    src_list.remove(x)
                    print('----> Removed {}'.format(x[0]))
                except ValueError:
                    print('----> !MISSING! {}'.format(x[0]))

APP_NAME = "{APP_NAME}"
SRC_DIR = os.path.abspath("./{APP_MODULE}")
BUILD_DIR = os.path.abspath("./build")

hiddenimports = collect_submodules('streamlink.plugins')
# the WinRT media controls load the projections they hand out by name
hiddenimports += collect_submodules('winrt')

# PyQt6's modules the app doesn't import, from the installed wheel's own list:
# Qt 6 has more than Qt 5 had, and each brings its Qt libraries
PYQT_USED = {"QtCore", "QtGui", "QtWidgets", "QtOpenGL", "QtOpenGLWidgets", "QtSvg", "QtSvgWidgets"}
excludes = [
    "PyQt6." + name.split(".")[0]
    for name in os.listdir(os.path.dirname(importlib.util.find_spec("PyQt6").origin))
    if name.startswith("Qt") and name.split(".")[0] not in PYQT_USED
] + ["PyQt6.uic", "PyQt6.lupdate", "altgraph"]

del_bins = [
    r"PyQt6\Qt6\bin\d3dcompiler_47",
    r"PyQt6\Qt6\bin\opengl32sw",
    # brought in only by the TUIO touch plugin, touches sent over the network
    r"PyQt6\Qt6\bin\Qt6Network",
    r"PyQt6\Qt6\plugins\generic\qtuiotouchplugin",
    r"PyQt6\Qt6\plugins\imageformats\qgif",
    r"PyQt6\Qt6\plugins\imageformats\qicns",
    r"PyQt6\Qt6\plugins\imageformats\qtga",
    r"PyQt6\Qt6\plugins\imageformats\qtiff",
    r"PyQt6\Qt6\plugins\imageformats\qwbmp",
    r"PyQt6\Qt6\plugins\imageformats\qwebp",
    r"PyQt6\Qt6\plugins\platforms\qdirect2d",
    r"PyQt6\Qt6\plugins\platforms\qminimal",
    r"PyQt6\Qt6\plugins\platforms\qoffscreen",
]

del_data = []

add_data = [
    (os.path.join(BUILD_DIR, "mime.ico"), '.')
]
add_data += [
    (os.path.join(SRC_DIR, "resources"), os.path.join("gridplayer", "resources")),
]
add_data += collect_data_files('streamlink.plugins', include_py_files=True)

block_cipher = None

a = Analysis([os.path.join(SRC_DIR, "__main__.py")],
             binaries=[],
             datas=add_data,
             hiddenimports=hiddenimports,
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=excludes,
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

print("Removing unneeded binaries...")
strip_list(a.binaries, del_bins)

print("Removing unneeded data...")
strip_list(a.datas, del_data)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name=APP_NAME,
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=False,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None ,
          version=os.path.join(BUILD_DIR, "version_info.py"),
          icon=os.path.join(BUILD_DIR, "main.ico"))

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=False,
               upx_exclude=[],
               name=APP_NAME)
