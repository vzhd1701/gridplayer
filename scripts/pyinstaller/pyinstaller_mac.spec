# -*- mode: python ; coding: utf-8 -*-

import importlib.util
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
# Info.plist takes nothing but numbers for the bundle version
APP_VERSION = "{APP_VERSION_NUMERIC}"
APP_TARGET_ARCH = "{APP_TARGET_ARCH}"
SRC_DIR = os.path.abspath("./{APP_MODULE}")
BUILD_DIR = os.path.abspath("./build")

hiddenimports = collect_submodules('streamlink.plugins')

# PyQt6's modules the app doesn't import, from the installed wheel's own list:
# Qt 6 has more than Qt 5 had, and each brings its Qt libraries
PYQT_USED = {"QtCore", "QtGui", "QtWidgets", "QtOpenGL", "QtOpenGLWidgets", "QtSvg", "QtSvgWidgets"}
excludes = [
    "PyQt6." + name.split(".")[0]
    for name in os.listdir(os.path.dirname(importlib.util.find_spec("PyQt6").origin))
    if name.startswith("Qt") and name.split(".")[0] not in PYQT_USED
] + ["PyQt6.uic", "PyQt6.lupdate"]

del_bins = [
    # brought in only by the TUIO touch plugin, touches sent over the network;
    # "QtNetwork" is the bundle's own link to the framework
    "QtNetwork",
    "PyQt6/Qt6/lib/QtNetwork.framework",
    "PyQt6/Qt6/plugins/generic/libqtuiotouchplugin",
    "PyQt6/Qt6/plugins/imageformats/libqgif",
    "PyQt6/Qt6/plugins/imageformats/libqmacheif",
    "PyQt6/Qt6/plugins/imageformats/libqmacjp2",
    "PyQt6/Qt6/plugins/imageformats/libqtga",
    "PyQt6/Qt6/plugins/imageformats/libqtiff",
    "PyQt6/Qt6/plugins/imageformats/libqwbmp",
    "PyQt6/Qt6/plugins/imageformats/libqwebp",
    "PyQt6/Qt6/plugins/platforms/libqminimal",
    "PyQt6/Qt6/plugins/platforms/libqoffscreen",
]

# the rest of a framework whose binary went: its Info.plist and signature
# left behind, its links lead nowhere and codesign fails
del_data = [
    "QtNetwork",
    "PyQt6/Qt6/lib/QtNetwork.framework",
]

add_data = [
    (os.path.join(BUILD_DIR, "mime.icns"), '.')
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
          target_arch=APP_TARGET_ARCH,
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
    },
    # media lists, played in a cell one file after another
    {
        "CFBundleTypeExtensions": ["m3u", "m3u8", "pls", "xspf"],
        "CFBundleTypeIconFile": "mime.icns",
        "CFBundleTypeName": "Media list",
        "CFBundleTypeRole": "Viewer",
    },
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

    # Qt 6.12's own minimum: PyQt6's wheels are macosx_14_0
    "LSMinimumSystemVersion": "14.0",

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
