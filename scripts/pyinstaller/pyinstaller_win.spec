# -*- mode: python ; coding: utf-8 -*-

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

excludes = [
    "altgraph",
    "PyQt5.QtBluetooth",
    "PyQt5.QtDBus",
    "PyQt5.QtDesigner",
    "PyQt5.QtHelp",
    "PyQt5.QtLocation",
    "PyQt5.QtNetworkAuth",
    "PyQt5.QtNfc",
    "PyQt5.QtOpenGL",
    "PyQt5.QtPositioning",
    "PyQt5.QtPrintSupport",
    "PyQt5.QtQml",
    "PyQt5.QtQuick",
    "PyQt5.QtQuick3D",
    "PyQt5.QtQuickWidgets",
    "PyQt5.QtRemoteObjects",
    "PyQt5.QtSensors",
    "PyQt5.QtSerialPort",
    "PyQt5.QtSql",
    "PyQt5.QtTest",
    "PyQt5.QtTextToSpeech",
    "PyQt5.QtWebChannel",
    "PyQt5.QtWebSockets",
    "PyQt5.QtXml",
    "PyQt5.QtXmlPatterns",
    "PyQt5.QtMultimedia",
    "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtNetwork",
]

del_bins = [
    r"PyQt5\Qt5\bin\d3dcompiler_47",
    r"PyQt5\Qt5\bin\libEGL",
    r"PyQt5\Qt5\bin\libGLESv2",
    r"PyQt5\Qt5\bin\opengl32sw",
    r"PyQt5\Qt5\bin\Qt5DBus",
    r"PyQt5\Qt5\bin\Qt5Network",
    r"PyQt5\Qt5\bin\Qt5Qml",
    r"PyQt5\Qt5\bin\Qt5Quick",
    r"PyQt5\Qt5\bin\Qt5WebSockets",
    r"PyQt5\Qt5\plugins\imageformats\qgif",
    r"PyQt5\Qt5\plugins\imageformats\qicns",
    r"PyQt5\Qt5\plugins\imageformats\qjpeg",
    r"PyQt5\Qt5\plugins\imageformats\qtga",
    r"PyQt5\Qt5\plugins\imageformats\qtiff",
    r"PyQt5\Qt5\plugins\imageformats\qwbmp",
    r"PyQt5\Qt5\plugins\imageformats\qwebp",
    r"PyQt5\Qt5\plugins\platforms\qminimal",
    r"PyQt5\Qt5\plugins\platforms\qoffscreen",
    r"PyQt5\Qt5\plugins\platforms\qwebgl",
    r"PyQt5\Qt5\plugins\platformthemes\qxdgdesktopportal",
]

del_data = []

add_data = [
    (os.path.join(BUILD_DIR, "mime.ico"), '.')
]
add_data += collect_data_files('streamlink.plugins', include_py_files=True)
add_data += copy_metadata('python-vlc')

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
