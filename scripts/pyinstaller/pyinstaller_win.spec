# -*- mode: python ; coding: utf-8 -*-

import os

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

excludes = [
    "asyncio",
    "ssl",
    "pyexpat",
    "unicodedata",
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
    "PyQt5.QtWinExtras",
    "PyQt5.QtXml",
    "PyQt5.QtXmlPatterns",
    "PyQt5.QtMultimedia",
    "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtNetwork",
]

del_bins = [
    "d3dcompiler",
    "libcrypto",
    "libeay32",
    "libEGL",
    "libGLES",
    "libssl",
    "opengl32sw",
    "ssleay32",
    "Qt5DBus",
    "Qt5Qml",
    "Qt5Quick",
    "Qt5WebSockets",
    "Qt5Network",
    r"PyQt5\Qt\plugins\audio\qtaudio_wasapi",
    r"PyQt5\Qt\plugins\audio\qtaudio_windows",
    r"PyQt5\Qt\plugins\bearer\qgenericbearer",
    r"PyQt5\Qt\plugins\imageformats\qgif",
    r"PyQt5\Qt\plugins\imageformats\qicns",
    r"PyQt5\Qt\plugins\imageformats\qjpeg",
    r"PyQt5\Qt\plugins\imageformats\qtga",
    r"PyQt5\Qt\plugins\imageformats\qtiff",
    r"PyQt5\Qt\plugins\imageformats\qwbmp",
    r"PyQt5\Qt\plugins\imageformats\qwebp",
    r"PyQt5\Qt\plugins\platforms\qminimal",
    r"PyQt5\Qt\plugins\platforms\qoffscreen",
    r"PyQt5\Qt\plugins\platforms\qwebgl",
    r"PyQt5\Qt\plugins\platformthemes\qxdgdesktopportal",
    r"PyQt5\Qt\plugins\playlistformats\qtmultimedia_m3u",
]

del_data = [
    r"PyQt5\Qt5\translations",
]

add_data = [
    (os.path.join(BUILD_DIR, "python-vlc.version"), '.')
]

block_cipher = None

a = Analysis([os.path.join(SRC_DIR, "__main__.py")],
             binaries=[],
             datas=add_data,
             hiddenimports=[],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[os.path.join(BUILD_DIR, "hook_lib.py")],
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
          icon=[os.path.join(BUILD_DIR, "main.ico"), os.path.join(BUILD_DIR, "mime.ico")],
          manifest=os.path.join(workpath, '{0}.exe.manifest'.format(specnm)))

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=False,
               upx_exclude=[],
               name=APP_NAME)
