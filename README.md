![GridPlayer](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/logo.svg)

[![PyPI version](https://img.shields.io/pypi/v/gridplayer)](https://pypi.python.org/pypi/gridplayer)
[![Github All Releases](https://img.shields.io/github/downloads/vzhd1701/gridplayer/total.svg)](https://github.com/vzhd1701/gridplayer/releases/latest)
[![Crowdin](https://badges.crowdin.net/gridplayer/localized.svg)](https://crowdin.com/project/gridplayer)

## Screenshots

[![Screenshot 1](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-001-thumb.png)](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-001.png)
[![Screenshot 2](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-002-thumb.png)](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-002.png)
[![Screenshot 3](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-003-thumb.png)](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-003.png)
[![Screenshot 4](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-004-thumb.png)](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/screenshot-004.png)

## About

Simple VLC-based media player that can play multiple videos at the same time. You can
play as many videos as you like, the only limit is your hardware. It supports all video
formats that VLC supports (which is all of them). You can save your playlist retaining
information about the position, sound volume, loops, aspect ratio, etc.

## Features

- Cross-platform (Linux, Mac, and Windows)
- Support for any video and audio format (VLC)
- Support for (almost) any streaming URLs ([streamlink](https://streamlink.github.io/plugins.html) + [yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md))
- Hardware & software video decoding
- Control video aspect, playback speed, zoom
- Set loop fragments with frame percision
- Configurable grid layout
- Easy swap videos with drag-n-drop
- Playlist retains settings for each video

## Translation

GridPlayer now supports internationalization! Anyone with a handful of free time and
desire to support this project is [welcome to contribute](https://crowdin.com/project/gridplayer).
No coding skills or special software required, all dialogs are well documented and
there are not many strings to translate.

Huge thanks to [every contributor](https://github.com/vzhd1701/gridplayer#translations)!

## Installation

### Windows

[![Download Windows Installer](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_windows_installer.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.5.0/GridPlayer-0.5.0-win64-install.exe)
[![Download Windows Portable](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_windows_portable.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.5.0/GridPlayer-0.5.0-win64-portable.zip)

```shell
$ scoop install gridplayer
```

**Compatible with Windows 7, 8, 10, 11.**

### Linux

[![Get it from the Flathub](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_flathub.png)](https://flathub.org/apps/details/com.vzhd1701.gridplayer)
[![Get it from the Snap Store](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_snap.png)](https://snapcraft.io/gridplayer)
[![Download AppImage](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_appimage.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.5.0/GridPlayer-0.5.0-x86_64.AppImage)

**For better system integration install via Flathub.**

#### Note on AppImage

The AppImage was built using Ubuntu Focal Fossa libraries, so compatibility is Ubuntu 20+.

You may need to set execute permissions on AppImage file in order to run it:

```shell
$ chmod +x GridPlayer-0.5.0-x86_64.AppImage
```

### MacOS

[![Download DMG](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_dmg.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.5.0/GridPlayer.0.5.0.dmg)

**DMG image is not signed.** You will have to add an exception to run this app.

- [How to open an app that hasn’t been notarized or is from an unidentified developer](https://support.apple.com/en-euro/HT202491)
- [Open a Mac app from an unidentified developer](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unidentified-developer-mh40616/mac)

If you get "GridPlayer is damaged and can't be opened" error, run this command in the Terminal app:

```shell
$ sudo xattr -rd com.apple.quarantine /Applications/GridPlayer.app
```

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

## Video Decoder settings

GridPlayer supports two video output modes:

- Hardware (default) mode uses available GPU to render video. This mode offers high performance and is a recommended mode.
- Software mode is entirely independent of GPU and only uses the CPU to render video. This mode may cause a high CPU load with high-resolution videos.

Due to libvlc software library limitations, video decoding is split into parallel processes. You can control how many videos are handled by a single decoder process using the "Videos per process" setting. Setting this option too high may cause a high CPU load and application freeze. The optimal value is 4 videos per process.

There is also "Hardware SP" mode. It handles video decoding within the same process in which GridPlayer runs. It is not recommended to use with many videos (>4-6) because it may cause high CPU load and application freeze.

Due to OS inter-process restrictions, "Hardware SP" is the only available hardware mode in macOS.

## Known issues

#### Linux (Snap): Error when opening a file from the mounted disk

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

#### Linux: black screen issue when using hardware decoder

Switch on "Opaque overlay (fix black screen)" checkbox in settings.

Depending on the window manager, the overlay might be a bit glitchy with the hardware decoder. Enabling compositor might help.

## Geting help

If you found a bug or have a feature request, please [open a new issue](https://github.com/vzhd1701/gridplayer/issues/new/choose).

If you have a question about the program or have difficulty using it, you are welcome to [the discussions page](https://github.com/vzhd1701/gridplayer/discussions). You can also mail me directly, I'm always happy to help.

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
- **streamlink** by [Christopher Rosell, Streamlink Team](https://github.com/streamlink/streamlink)
  - Licensed under *BSD-2-Clause License*
- **yt-dlp** by [Contributors](https://github.com/yt-dlp/yt-dlp)
  - Licensed under *Unlicense License*

### Graphics

- **Hack Font** by [Source Foundry](http://sourcefoundry.org/hack/)
  - Licensed under *MIT License*
- **Basic Icons** by [Icongeek26](https://www.flaticon.com/authors/icongeek26)
  - Licensed under *Flaticon License*
- **Suru Icons** by [Sam Hewitt](https://snwh.org/)
  - Licensed under *Creative Commons Attribution-Share Alike 4.0*
- **Clean App Download Buttons** by [Tony Thomas](https://medialoot.com/item/clean-app-download-buttons/)
  - Licensed under *MediaLoot License*
- **Flag Icons** by [Panayiotis Lipiridis](https://github.com/lipis/flag-icons)
  - Licensed under *MIT License*

## Translations

### Arabic

- [azoaz6001](https://crowdin.com/profile/azoaz6001)

### German

- [DominikPott](https://crowdin.com/profile/dominikpott)

### Spanish

- [Sergio Varela](https://crowdin.com/profile/ingrownmink4)
- [asolis2020](https://crowdin.com/profile/asolis2020)

### French

- [Sylvain LOUIS](https://crowdin.com/profile/louis_sylvain)

### Hungarian

- [samu112](https://crowdin.com/profile/samu112)

### Italian

- [Davide V.](https://crowdin.com/profile/davidev1)
- [SolarCTP](https://crowdin.com/profile/solarctp)

### Japanese

- [七篠孝志](https://crowdin.com/profile/japanese.john.doe.774)

### Korean

- [VenusGirl](https://venusgirls.tistory.com/)

### Dutch

- [Heimen Stoffels](https://crowdin.com/profile/vistaus)

### Polish

- [rafal132](https://crowdin.com/profile/fifi132)
- [Sebastian Jasiński](https://crowdin.com/profile/princenorris)

### Portuguese, Brazilian

- [GBS ~ TECH](https://crowdin.com/profile/gabriel-bs1)

### Chinese Simplified

- [Yagang Wang](https://crowdin.com/profile/wyg945)
- [1017346](https://crowdin.com/profile/1017346)
- [焦新营](https://crowdin.com/profile/j149697726)
- [loser7788](https://crowdin.com/profile/loser7788)

## License

This software is licensed under the terms of the GNU General Public License version 3 (GPLv3). Full text of the license is available in the [LICENSE](https://github.com/vzhd1701/gridplayer/blob/master/LICENSE) file and [online](https://www.gnu.org/licenses/gpl-3.0.html).
