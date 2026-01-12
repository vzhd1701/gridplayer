# -*- mode: python ; coding: utf-8 -*-

import os
import plistlib

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
APP_ID = "{APP_ID}"
APP_VERSION = "{APP_VERSION}"
SRC_DIR = os.path.abspath("./{APP_MODULE}")
BUILD_DIR = os.path.abspath("./build")

hiddenimports = collect_submodules('streamlink.plugins')

excludes = [
    "PyQt5.QtBluetooth",
    "PyQt5.QtDBus",
    "PyQt5.QtDesigner",
    "PyQt5.QtHelp",
    "PyQt5.QtLocation",
    "PyQt5.QtMacExtras",
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
    "QtDBus",
    "QtOpenGL",
    "QtPrintSupport",
    "QtQml",
    "QtQmlModels",
    "QtQuick",
    "QtWebSockets",
]

del_bins = [
    "QtQml",
    "QtQuick",
    "QtWebSockets",
    "QtNetwork",
    "PyQt5/Qt5/plugins/audio/libqtaudio_coreaudio",
    "PyQt5/Qt5/plugins/bearer/libqgenericbearer",
    "PyQt5/Qt5/plugins/imageformats/libqgif",
    "PyQt5/Qt5/plugins/imageformats/libqico",
    "PyQt5/Qt5/plugins/imageformats/libqjpeg",
    "PyQt5/Qt5/plugins/imageformats/libqmacheif",
    "PyQt5/Qt5/plugins/imageformats/libqmacjp2",
    "PyQt5/Qt5/plugins/imageformats/libqtga",
    "PyQt5/Qt5/plugins/imageformats/libqtiff",
    "PyQt5/Qt5/plugins/imageformats/libqwbmp",
    "PyQt5/Qt5/plugins/imageformats/libqwebp",
    "PyQt5/Qt5/plugins/platforms/libqminimal",
    "PyQt5/Qt5/plugins/platforms/libqoffscreen",
    "PyQt5/Qt5/plugins/platforms/libqwebgl",
    "PyQt5/Qt5/plugins/platformthemes/libqxdgdesktopportal",
    "PyQt5/Qt5/plugins/playlistformats/libqtmultimedia_m3u",
]

del_data = []

add_data = [
    (os.path.join(BUILD_DIR, "mime.icns"), '.')
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
          entitlements_file=None,
          icon=os.path.join(BUILD_DIR, "main.icns"))

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=False,
               upx_exclude=[],
               name=APP_NAME)

with open(os.path.join(BUILD_DIR, "mime_vlc.plist"), "rb") as f:
    mime_plist = plistlib.load(f)

mime_plist["CFBundleDocumentTypes"] += [
    {
        "CFBundleTypeExtensions": ["gpls"],
        "CFBundleTypeIconFile": "mime.icns",
        "CFBundleTypeMIMETypes": "application/x-gridplayer-playlist",
        "CFBundleTypeName": APP_NAME + " playlist file",
        "CFBundleTypeRole": "Viewer",
        "LSItemContentTypes": [APP_ID + ".gpls"],
    }
]

mime_plist["UTExportedTypeDeclarations"] = [
    {
        "UTTypeIdentifier": APP_ID + ".gpls",
        "UTTypeTagSpecification": {
            "public.filename-extension": ["gpls"],
            "public.mime-type": ["application/x-gridplayer-playlist"],
        },
        "UTTypeConformsTo": ["public.text"],
        "UTTypeDescription": APP_NAME + " playlist file",
        "UTTypeIconFile": "mime.icns",
    }
]

info_plist = {
    **mime_plist,

    "LSApplicationCategoryType": "public.app-category.video",

    # App can use GPU
    "NSSupportsAutomaticGraphicsSwitching": True,

    "NSPrincipalClass": "NSApplication",
    "NSRequiresAquaSystemAppearance": False,
}

app = BUNDLE(coll,
             name='{0}.app'.format(APP_NAME),
             info_plist=info_plist,
             icon=os.path.join(BUILD_DIR, "main.icns"),
             bundle_identifier=APP_ID,
             version=APP_VERSION)
