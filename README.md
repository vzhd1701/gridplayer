![GridPlayer](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/logo.png)

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/vzhd1701/gridplayer)](https://github.com/vzhd1701/gridplayer/releases/latest)
[![PyPI version](https://img.shields.io/pypi/v/gridplayer)](https://pypi.python.org/pypi/gridplayer)

## Screenshots

[![Screenshot 1](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-001-thumb.png)](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-001.png)
[![Screenshot 2](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-002-thumb.png)](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-002.png)
[![Screenshot 3](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-003-thumb.png)](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-003.png)

## About

Simple VLC-based media player that can play multiple videos at the same time. You can
play as many videos as you like, the only limit is your hardware. It supports all video
formats that VLC supports (which is all of them). You can save your playlist retaining
information about the position, sound volume,  loops, aspect ratio, etc.

## Features

- Cross-platform (Linux, Mac, and Windows)
- Support for any video format (VLC)
- Hardware & software video decoding
- Control video aspect, playback speed, zoom
- Set loop fragments with frame percision
- Configurable grid layout
- Easy swap videos with drag-n-drop
- Playlist retains settings for each video

## Installation

### Windows

[![Download Windows Installer](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_windows_installer.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.1.5/GridPlayer-0.1.5-win64-install.exe)
[![Download Windows Portable](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_windows_portable.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.1.5/GridPlayer-0.1.5-win64-portable.zip)

### Linux

[![Get it from the Flathub](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_flathub.png)](https://flathub.org/apps/details/com.vzhd1701.gridplayer)
[![Get it from the Snap Store](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_snap.png)](https://snapcraft.io/gridplayer)
[![Download AppImage](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_appimage.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.1.5/GridPlayer-0.1.5-x86_64.AppImage)

**For better system integration install via Flathub.**

#### Note on AppImage

You may need to set execute permissions on AppImage file in order to run it:

```shell
$ chmod +x GridPlayer-0.1.5-x86_64.AppImage
```

### MacOS

[![Download DMG](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_dmg.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.1.5/GridPlayer.0.1.5.dmg)

**DMG image is not signed.** You will have to add an exception to run this app.

- [How to open an app that hasn’t been notarized or is from an unidentified developer](https://support.apple.com/en-euro/HT202491)
- [Open a Mac app from an unidentified developer](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unidentified-developer-mh40616/mac)

### PIP

```shell
$ pip install -U gridplayer
```

**Python 3.8 or later required.**

This type of installation will also require a `vlc` package present in your system.
Please refer to [VLC official page](https://www.videolan.org/vlc/) for instructions on how to install it.

Some distros (e.g. Ubuntu) might also require `libxcb-xinerama0` package.

### From source

This project uses [poetry](https://python-poetry.org/) for dependency management and packaging. You will have to install it first. See [poetry official documentation](https://python-poetry.org/docs/) for instructions.

```shell
$ git clone https://github.com/vzhd1701/gridplayer.git
$ cd gridplayer/
$ poetry install --no-dev
$ poetry run gridplayer
```

The same notes about the Python version and external packages from **PIP** installation apply here.

## Known issues

#### Linux (Snap): [X screen](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-x.png) when opening a file from the mounted disk

You need to allow GridPlayer snap to access removable storage devices via Snap Store or by running:

```shell
$ sudo snap connect gridplayer:removable-media
```

#### Linux (Snap): mounted drives are not visible in file selection dialog

You will also see following error if you run GridPlayer from terminal:

```shell
GLib-GIO-WARNING **: Error creating IO channel for /proc/self/mountinfo: Permission denied (g-file-error-quark, 2)
```

To fix this, you need to allow GridPlayer snap to access system mount information and disk quotas via Snap Store or by running:

```shell
$ sudo snap connect gridplayer:mount-observe
```

#### Linux (KDE): black screen issue when using hardware decoder

Switch on "Opaque overlay (fix black screen)" checkbox in settings.

Overlay might be a bit glitchy in KDE with hardware decoder.

#### MacOS: "GridPlayer" is damaged and can't be opened

To fix this, you need to execute the following command using terminal:

```shell
$ sudo xattr -rd com.apple.quarantine /Applications/GridPlayer.app
```

## Attributions

This software was build using

- **Python** by [Python Software Foundation](https://www.python.org/)
  - Licensed under *Python Software Foundation License*
- **Qt** by [Qt Project](https://www.qt.io/)
  - Licensed under *GPL 2.0, GPL 3.0, and LGPL 3.0*
- **VLC** by [VideoLAN](https://www.videolan.org/)
  - Licensed under *GPL 2.0 or later*

### Python packages

- **PyQt** by [Riverbank Computing](https://riverbankcomputing.com/)
  - Licensed under *Riverbank Commercial License and GPL v3*
- **python-vlc** by [Olivier Aubert](https://github.com/oaubert/python-vlc)
  - Licensed under *GPL 2.0 and LGPL 2.1*
- **pydantic** by [Samuel Colvin](https://github.com/samuelcolvin/pydantic)
  - Licensed under *MIT License*

### Graphics

- **Hack Font** by [Source Foundry](http://sourcefoundry.org/hack/)
  - Licensed under *MIT License*
- **Basic Icons** by [Icongeek26](https://www.flaticon.com/authors/icongeek26)
  - Licensed under *Flaticon License*
- **Suru Icons** by [Sam Hewitt](https://snwh.org/)
  - Licensed under *Creative Commons Attribution-Share Alike 4.0*
- **Clean App Download Buttons** by [Tony Thomas](https://medialoot.com/item/clean-app-download-buttons/)
  - Licensed under *MediaLoot License*

## License

This software is licensed under the terms of the GNU General Public License version 3 (GPLv3). Full text of the license is available in the [LICENSE](https://github.com/vzhd1701/gridplayer/blob/master/LICENSE) file and [online](https://www.gnu.org/licenses/gpl-3.0.html).
