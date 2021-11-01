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
APP_ID = "{APP_ID}"
APP_VERSION = "{APP_VERSION}"
SRC_DIR = os.path.abspath("./{APP_MODULE}")
BUILD_DIR = os.path.abspath("./build")

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

del_data = [
    "PyQt5/Qt5/translations",
]

add_data = [
    (BUILD_DIR + '/python-vlc.version', '.'),
    (BUILD_DIR + '/mime.icns', '.')
]


block_cipher = None


a = Analysis([os.path.join(SRC_DIR, "__main__.py")],
             binaries=[],
             datas=add_data,
             hiddenimports=[],
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

mime_plist = {
    # Mostly copy/paste from VLC.app format support
    "UTImportedTypeDeclarations": [
        {
            "UTTypeIdentifier": "com.adobe.flash.video",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "Flash Video File",
            "UTTypeTagSpecification": {
                "public.mime-type": ["video/x-flv"],
                "public.filename-extension": ["flv", "f4v", "f4a", "f4b"],
            },
        },
        {
            "UTTypeIdentifier": "org.videolan.xesc",
            "UTTypeConformsTo": ["public.video"],
            "UTTypeDescription": "Expression Encoder Screen Capture File",
            "UTTypeTagSpecification": {"public.filename-extension": ["xesc"]},
        },
        {
            "UTTypeIdentifier": "com.real.realmedia",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "RealMedia",
            "UTTypeTagSpecification": {
                "com.apple.ostype": ["PNRM"],
                "public.mime-type": [
                    "application/vnd.rn-realmedia",
                    "application/vnd.rn-realmedia-vbr",
                    "text/vnd.rn-realtext",
                    "audio/x-pn-realaudio-plugin",
                ],
                "public.filename-extension": [
                    "rm",
                    "rv",
                    "rmj",
                    "rpm",
                    "rp",
                    "rt",
                    "rmvb",
                    "rmd",
                    "rms",
                    "rmx",
                    "rvx",
                ],
            },
        },
        {
            "UTTypeIdentifier": "org.videolan.vob",
            "UTTypeConformsTo": ["public.video"],
            "UTTypeDescription": "VOB File (DVD Video)",
            "UTTypeTagSpecification": {"public.filename-extension": ["vob"]},
        },
        {
            "UTTypeIdentifier": "org.xiph.ogg-video",
            "UTTypeConformsTo": ["public.video"],
            "UTTypeDescription": "Ogg Video File",
            "UTTypeTagSpecification": {"public.filename-extension": ["ogm", "ogv"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.axv",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "Annodex Video File",
            "UTTypeTagSpecification": {"public.filename-extension": ["axv"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.gxf",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "General eXchange Format File",
            "UTTypeTagSpecification": {"public.filename-extension": ["gxf"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.mxf",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "Material Exchange Format",
            "UTTypeTagSpecification": {"public.filename-extension": ["mxf"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.divx",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "DivX file",
            "UTTypeTagSpecification": {"public.filename-extension": ["divx"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.wtv",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "Windows Recorded TV Show",
            "UTTypeTagSpecification": {"public.filename-extension": ["wtv"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.mpeg-stream",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "MPEG-2 Stream",
            "UTTypeTagSpecification": {
                "public.filename-extension": [
                    "m2p",
                    "ps",
                    "tp",
                    "ts",
                    "m2t",
                    "m2ts",
                    "mts",
                    "mt2s",
                ]
            },
        },
        {
            "UTTypeIdentifier": "org.matroska.mkv",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "Matroska Video File",
            "UTTypeTagSpecification": {"public.filename-extension": ["mkv"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.webm",
            "UTTypeConformsTo": ["public.movie", "org.matroska.mkv"],
            "UTTypeDescription": "WebM Video File",
            "UTTypeTagSpecification": {"public.filename-extension": ["webm"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.rec",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "Topfield PVR Recording",
            "UTTypeTagSpecification": {"public.filename-extension": ["rec"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.vro",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "DVD Video Recording Format",
            "UTTypeTagSpecification": {"public.filename-extension": ["vro"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.tod",
            "UTTypeConformsTo": ["public.movie"],
            "UTTypeDescription": "JVC Everio Video Capture File",
            "UTTypeTagSpecification": {"public.filename-extension": ["tod"]},
        },
        {
            "UTTypeIdentifier": "org.videolan.nsv",
            "UTTypeConformsTo": ["public.video"],
            "UTTypeDescription": "Nullsoft Streaming Video",
            "UTTypeTagSpecification": {"public.filename-extension": ["nsv"]},
        },
        {
            "UTTypeIdentifier": "com.mythtv.nuv",
            "UTTypeConformsTo": ["public.video"],
            "UTTypeDescription": "NuppleVideo File",
            "UTTypeTagSpecification": {"public.filename-extension": ["nuv"]},
        },
    ],
    "CFBundleDocumentTypes": [
        {
            "CFBundleTypeExtensions": ["gpls"],
            "CFBundleTypeIconFile": "mime.icns",
            "CFBundleTypeMIMETypes": "application/x-gridplayer-playlist",
            "CFBundleTypeName": APP_NAME + " playlist file",
            "CFBundleTypeRole": "Viewer",
            "LSItemContentTypes": [APP_ID + ".gpls"],
        },
        {
            "CFBundleTypeName": "Flash Video File",
            "LSItemContentTypes": ["com.adobe.flash.video"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Expression Encoder Screen Capture File",
            "CFBundleTypeExtensions": ["xesc"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "RealPlayer Media Files",
            "LSItemContentTypes": [
                "com.real.realmedia-vbr",
                "com.real.realmedia",
            ],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "VOB File (DVD Video)",
            "CFBundleTypeExtensions": ["vob"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "DAT file",
            "CFBundleTypeExtensions": ["dat"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Ogg MPEG-4 Video File",
            "CFBundleTypeExtensions": ["ogm"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Ogg Video File",
            "CFBundleTypeExtensions": ["ogv"],
            "CFBundleTypeMIMETypes": ["video/ogg"],
            "LSItemContentTypes": ["org.xiph.ogg-video"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Ogg Application File",
            "CFBundleTypeExtensions": ["ogx"],
            "CFBundleTypeMIMETypes": ["application/ogg"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Annodex Application File",
            "CFBundleTypeExtensions": ["anx"],
            "CFBundleTypeMIMETypes": ["application/annodex"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Annodex Video File",
            "CFBundleTypeExtensions": ["axv"],
            "CFBundleTypeMIMETypes": ["video/annodex"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "LSTypeIsPackage": False,
            "CFBundleTypeExtensions": ["gxf"],
            "CFBundleTypeName": "General eXchange Format File",
            "NSPersistentStoreTypeKey": "Binary",
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "LSTypeIsPackage": False,
            "CFBundleTypeExtensions": ["mxf"],
            "CFBundleTypeName": "Material Exchange Format",
            "NSPersistentStoreTypeKey": "Binary",
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "AVI container",
            "LSItemContentTypes": ["public.avi"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Bink Video File",
            "CFBundleTypeExtensions": ["bik"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "EVO Video File",
            "CFBundleTypeExtensions": ["evo"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Apple QuickTime container",
            "LSItemContentTypes": ["com.apple.quicktime-movie"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "DivX file",
            "CFBundleTypeExtensions": ["divx"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "DV file",
            "LSItemContentTypes": ["public.dv-movie"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Advanced Streaming Format",
            "LSItemContentTypes": ["com.microsoft.advanced-systems-format"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Windows Media Video",
            "LSItemContentTypes": [
                "com.microsoft.windows-media-wm",
                "com.microsoft.windows-media-wmv",
            ],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Windows Recorded TV Show",
            "CFBundleTypeExtensions": ["wtv"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "multiplexed MPEG-1/2",
            "LSItemContentTypes": ["public.mpeg"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "MPEG-1 Video File",
            "CFBundleTypeExtensions": ["m1v"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "MPEG-2 Program Stream",
            "CFBundleTypeExtensions": ["m2p", "ps"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "MPEG-2 Transport Stream",
            "CFBundleTypeExtensions": ["tp", "ts", "m2t", "m2ts", "mts", "mt2s"],
            "CFBundleTypeMIMETypes": ["video/mp2t"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "MPEG-2 Video File",
            "LSItemContentTypes": ["public.mpeg-2-video"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "MPEG-4 File",
            "LSItemContentTypes": [
                "com.apple.m4v-video",
                "public.mpeg-4",
            ],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "3GPP File",
            "LSItemContentTypes": ["public.3gpp"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Matroska Video File",
            "CFBundleTypeExtensions": ["mkv"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "WebM Video File",
            "CFBundleTypeExtensions": ["webm"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Topfield PVR Recording",
            "CFBundleTypeExtensions": ["rec"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "DVD Video Recording Format",
            "CFBundleTypeExtensions": ["vro"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "JVC Everio Video Capture File",
            "CFBundleTypeExtensions": ["tod"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeName": "Matroska Elementry Stream",
            "CFBundleTypeExtensions": ["mks"],
            "CFBundleTypeRole": "Viewer",
            "CFBundleTypeIconFile": "mime.icns",
        },
        {
            "CFBundleTypeExtensions": ["nsv"],
            "CFBundleTypeMIMETypes": ["video/nsv"],
            "LSTypeIsPackage": False,
            "NSPersistentStoreTypeKey": "Binary",
            "CFBundleTypeName": "Nullsoft Streaming Video",
            "CFBundleTypeIconFile": "mime.icns",
            "CFBundleTypeRole": "Viewer",
        },
        {
            "CFBundleTypeExtensions": ["nuv"],
            "LSTypeIsPackage": False,
            "NSPersistentStoreTypeKey": "Binary",
            "CFBundleTypeName": "NuppleVideo File",
            "CFBundleTypeIconFile": "mime.icns",
            "LSItemContentTypes": ["com.mythtv.nuv"],
            "CFBundleTypeRole": "Viewer",
        },
    ],
    "UTExportedTypeDeclarations": [
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
    ],

    "LSApplicationCategoryType": "public.app-category.video",
    # App can use GPU
    "NSSupportsAutomaticGraphicsSwitching": True,
    "NSPrincipalClass": "NSApplication",
    "NSRequiresAquaSystemAppearance": False,
}

app = BUNDLE(coll,
             name='{0}.app'.format(APP_NAME),
             info_plist=mime_plist,
             icon=os.path.join(BUILD_DIR, "main.icns"),
             bundle_identifier=APP_ID,
             version=APP_VERSION)
