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

Simple media player that can play multiple videos at the same time, with MPV or VLC. You can
play as many videos as you like, the only limit is your hardware. It supports all video
formats that MPV and VLC support (which is all of them). You can save your playlist retaining
information about the position, sound volume, loops, aspect ratio, etc.

## Features

- Cross-platform (Linux, Mac, and Windows)
- Support for any video and audio format (MPV and VLC)
- Support for (almost) any streaming
  URLs ([streamlink](https://streamlink.github.io/plugins.html) + [yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md))
- Play a whole list in one cell: m3u, pls and xspf playlists, folders, YouTube playlists, IPTV channels
- Cookie support for streams that need a login
- Skip sponsors and other marked parts of YouTube videos with [SponsorBlock](https://sponsor.ajay.app/)
- Hardware & software video decoding
- Control video aspect, playback speed, zoom
- Set loop fragments with frame precision
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

[![Download Windows Installer](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_windows_installer.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.5.5/GridPlayer-0.5.5-win64-install.exe)
[![Download Windows Portable](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_windows_portable.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.5.5/GridPlayer-0.5.5-win64-portable.zip)

Via [scoop](https://scoop.sh/):

```shell
scoop install gridplayer
```

**Compatible with Windows 10 and 11.**

### Linux

[![Get it from the Flathub](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_flathub.png)](https://flathub.org/apps/details/com.vzhd1701.gridplayer)
[![Get it from the Snap Store](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_snap.png)](https://snapcraft.io/gridplayer)
[![Download AppImage](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_appimage.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.5.5/GridPlayer-0.5.5-x86_64.AppImage)

**For better system integration install via Flathub.**

The Snap plays with VLC only for now. MPV comes to it with the move to Qt 6.

#### Note on AppImage

The AppImage is built on `manylinux_2_34` (glibc 2.34), so it runs on Ubuntu 22.04+, Debian 12+, Fedora 35+,
RHEL / AlmaLinux / Rocky 9+ and other distros of the same age or newer.

You may need to set execute permissions on AppImage file in order to run it:

```shell
chmod +x GridPlayer-0.5.5-x86_64.AppImage
```

### MacOS

[![Download DMG](https://raw.githubusercontent.com/vzhd1701/gridplayer/master/resources/public/dl_dmg.png)](https://github.com/vzhd1701/gridplayer/releases/download/v0.5.5/GridPlayer.0.5.5_arm64.dmg)

The button gets the DMG for Apple Silicon (`arm64`). For an Intel Mac, get
[GridPlayer.0.5.5_intel64.dmg](https://github.com/vzhd1701/gridplayer/releases/download/v0.5.5/GridPlayer.0.5.5_intel64.dmg).

MPV needs macOS 12 or later. On older versions, VLC plays the videos.

**DMG image is not signed.** You will have to add an exception to run this app.

- [How to open an app that hasn’t been notarized or is from an unidentified developer](https://support.apple.com/en-euro/HT202491)
- [Open a Mac app from an unidentified developer](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unidentified-developer-mh40616/mac)

If you get "GridPlayer is damaged and can't be opened" error, run this command in the Terminal app:

```shell
sudo xattr -rd com.apple.quarantine /Applications/GridPlayer.app
```

### Install with [UV](https://docs.astral.sh/uv/)

```shell
uv tool install gridplayer
```

**Python 3.10 or later required.**

This type of installation doesn't come with a player library. It needs libmpv or VLC installed on your system, see
[libmpv not found](#when-a-mode-isnt-available) for libmpv, or the [VLC official page](https://www.videolan.org/vlc/)
for VLC (on Linux, the `vlc` package).

Some distros (e.g. Ubuntu) might also require `libxcb-xinerama0` package.

### From source

```shell
uv tool install git+https://github.com/vzhd1701/gridplayer.git
```

The same notes about the Python version and external packages from above apply here.

## Command line options

```shell
gridplayer [options] [FILE|URL ...]
```

Any arguments that are not options are treated as media files, folders, `.gpls` playlists, media lists (`.m3u`,
`.m3u8`, `.pls`, `.xspf`), or streaming URLs (`https://`, `rtsp://`, ...) to open on startup. A folder or a media list
plays in one cell, one file after another. Unrecognized options are rejected with an error; use `--` to open
dash-prefixed filenames.

| Option                | Description                                                                                                            |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `--user-data-dir PATH` | Store settings and log files in `PATH` instead of the default location. Relative paths are resolved against the current working directory. |
| `--platform {auto,xcb,wayland}` | Linux only. Display server to run on, in place of the Window system setting: `xcb` (X11 or Xwayland) or `wayland`. `auto` goes by the setting. VLC Hardware needs `xcb`. |
| `--self-check`        | Check that GridPlayer can play the given files with VLC and MPV, showing and sounding nothing, print what it found and exit. |
| `--version`           | Show the application version and exit.                                                                                 |
| `--help`              | Show the available options and exit.                                                                                   |

### User data directory

By default, settings and logs are stored in the system application data directory (see below). On the Windows portable
build, if a `portable_data` folder exists next to the executable, it is used automatically.

You can point GridPlayer at any directory for its data:

```shell
# via command line option
gridplayer --user-data-dir ./my_data

# via environment variable
export GP_USER_DATA_DIR=/path/to/my_data
gridplayer
```

The command line option takes precedence over the environment variable. Setting either one on all platforms and
installation types stores data in the given directory instead of the standard system location.

### Default data directory locations

Without a custom user data directory, settings (`settings.ini`) and log (`gridplayer.log`) files are stored in the
standard application data location:

| Platform | Location                                              |
| -------- | ----------------------------------------------------- |
| Windows  | `C:\Users\<USER>\AppData\Roaming\vzhd1701\GridPlayer` |
| Linux    | `~/.local/share/vzhd1701/GridPlayer`                  |
| macOS    | `~/Library/Application Support/vzhd1701/GridPlayer`   |

**Settings -> Open data folder** opens this directory, whichever package you are running.

On Linux, `XDG_DATA_HOME` is respected instead of `~/.local/share` when set. Sandboxed packages store the directory
inside their own sandbox: `~/.var/app/com.vzhd1701.gridplayer/data/vzhd1701/GridPlayer` for Flatpak, and
`~/snap/gridplayer/current/.local/share/vzhd1701/GridPlayer` for Snap.

## Video Decoder settings

GridPlayer plays videos with MPV or VLC. The packages come with both (the Snap with VLC only, for
now), and MPV is the default. Installed with UV or from source, it uses whichever you have.

Each can decode in two ways:

- Hardware (default) uses the GPU. It offers high performance and is the recommended choice.
- Software uses only the CPU. This may cause a high CPU load with high-resolution videos.

With VLC you can also choose how videos are split between processes:

- Multi-process plays videos in separate processes, 4 to a process by default (the "Videos per
  process" setting). If VLC crashes on a video, only the videos in its process stop.
- Single process plays videos inside GridPlayer. It uses a little less memory, but loads many
  videos more slowly, and a VLC crash closes GridPlayer.

MPV always uses a single process. Due to OS inter-process restrictions, Hardware with VLC is
single process only on macOS.

When there are more videos than the decoder can keep up with, "Skip frames to play more videos"
makes MPV play about half the frames of each video instead of slowing down. It doesn't help videos
with no frames it can skip.

Hardware with MPV can also decode on the CPU and still draw on the GPU ("Decode on the CPU"). On
a strong CPU this plays the most videos, and it uses less video memory. On Auto, the default, a
video you open decodes on the CPU only when video memory is running low. That works on Windows 10
and later, and on Linux with NVIDIA. Elsewhere Auto decodes on the GPU.

If memory keeps growing as you close videos that way, as it can on NVIDIA, turn off "Hand frames
straight to the GPU". It costs a little more CPU, which only shows once the CPU can't keep up.

### MPV's video output

Hardware with MPV gets the picture to the screen in one of three ways ("Video output"; the **?**
next to it compares them on your system):

- **Copy** copies each frame back into memory and GridPlayer draws it. It works everywhere and uses the
  most CPU. The default on Linux.
- **Shared** draws all the videos with OpenGL on one surface, with no copy. The default on macOS. A
  change to or from Shared works after a restart.
- **Direct** lets MPV draw each video into a window of its own, with Direct3D 11 on Windows. It uses
  the least CPU and video memory, but the edges of the videos flicker while you resize the window.
  The default on Windows. On Linux it needs X11, and macOS doesn't have it.

"Picture quality" sets how sharp a video looks when it's scaled. Auto uses Fast for small videos and
High for big ones.

To add your own mpv options, turn on "Use mpv.conf" under Experimental. "Open" makes the file in the
[data directory](#default-data-directory-locations), and "Check" shows the lines mpv can't use.

### When a mode isn't available

Settings show modes that can't run greyed out, with the reason. Here's how to fix each one.

**libmpv not found:** the packages come with libmpv, so this is for an install with UV or from
source. MPV needs libmpv, not only the MPV player:

- Windows: there's no official installer. Download an `mpv-dev-x86_64` archive from
  [mpv-winbuild](https://github.com/shinchiro/mpv-winbuild-cmake/releases), extract
  `libmpv-2.dll` with [7-Zip](https://www.7-zip.org/) and put it in `%LOCALAPPDATA%\Programs\mpv`, or
  next to `mpv.exe` if you have MPV on your `PATH`.
- Linux: install your distribution's libmpv package. On Debian and Ubuntu it's `libmpv2`. It has to be
  0.37 or later.
- macOS: `brew install mpv`, or on an Intel Mac `sudo port install mpv` with [MacPorts](https://www.macports.org/).

**VLC not found:** install [VLC](https://www.videolan.org/vlc/).

**libmpv or VLC won't load, or libmpv is too old:** update it to the latest version. It also has to
match GridPlayer's architecture (64-bit or 32-bit).

**VLC Hardware needs X11:** VLC can't draw into a Wayland window directly. Install Xwayland or
log in to an X11 session, and GridPlayer will use it. Software and MPV work without it.
On a Wayland desktop, the Window system setting picks X11 or Wayland. On Auto, GridPlayer runs
on Wayland where the desktop draws the window frames (KDE, sway and most others, not GNOME).
VLC Hardware and MPV's Direct video output always run on X11, and the setting shows it. A change
works after a restart.

## Streaming cookies

Some links won't resolve without a login, especially YouTube with it's *"Sign in to confirm you're not a
bot"*. GridPlayer can store cookies and pass them to both yt-dlp and Streamlink.

Go to **Settings -> Streaming -> Cookies** and import a `cookies.txt` file, or paste one from the clipboard.

### Exporting cookies from your browser

Export from a private window, and close it when you're done:

1. Open a private browsing window and log in to your site (youtube in this example).
2. In the same tab, go to `https://www.youtube.com/robots.txt` (any static page on the site).
3. Export/copy cookies for the site with a browser extension ([FF](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/), [Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)).
4. Close the window **without logging out**. Logging out kills the session you just exported.
5. Import the `cookies.txt` file into GridPlayer, or paste it.

YouTube rotates cookies on open tabs. If you export from your normal session it will go stale within hours.
A private window you never reopen has nothing left to rotate them. For the same reason, don't use one
export in two places at once.

More detail in the [yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).

### Where cookies are stored

`cookies.txt` in the [user data directory](#default-data-directory-locations), in the standard Netscape format.

The file isn't encrypted, so treat it like a password. Import only the domains you need, and clear the store when
you're done with them.

## Network settings

A proxy, an address family and a user agent shared by everything GridPlayer fetches with: yt-dlp,
Streamlink and the player itself.

Go to **Settings -> Streaming -> Network**.

| Setting | What it does |
| --- | --- |
| **Proxy** | `System` follows the machine's own proxy settings. `None` connects directly, ignoring them. `Custom` takes an address of your own. |
| **Proxy address** | `http://host:port`, or `socks5h://host:port` to resolve names at the proxy rather than locally. |
| **Request timeout** | How long to wait on a request before giving up. Applies while a link is being resolved, not while it is playing. `Auto` leaves each tool on its own default, which is 20 seconds for both. |
| **User agent** | How the player identifies itself. `Auto` leaves each tool on its own. A link that came with a user agent of its own keeps it. |
| **Force IPv4** | Skip IPv6. Fixes a connection that stalls on IPv6 that is offered but does not work, and sites that turn away your IPv6 address. |
| **Verify TLS certificates** | Turn off only for a proxy that signs traffic with its own certificate. |

### What these apply to

**http and https links only**, apart from the user agent.

The player has no proxy setting it honours everywhere, no way to be held to one address family, and no
way to be told whose certificates to trust. So when any of those is set, links stop being handed to the
player and are fetched by GridPlayer instead, then served to the player from `127.0.0.1`.

Links of other kinds — `rtsp`, `rtmp` and so on — are opened by the player itself and go out directly.
Only the user agent reaches those. If you need those proxied too, proxy the whole machine.

## JavaScript runtime

YouTube scrambles its stream addresses with a script that has to be run to undo. GridPlayer doesn't ship
an engine to run it with, so if YouTube links stop playing, install one of these and restart:

| Engine | Size | Speed | |
| --- | --- | --- | --- |
| **[Deno](https://docs.deno.com/runtime/getting_started/installation/)** | ~110 MB | fastest | Recommended. Sandboxed by default. |
| **[Node](https://nodejs.org/)** | ~80 MB | fastest | Version 22 or newer. Just as good, and you may have it already. |
| **[QuickJS](https://github.com/quickjs-ng/quickjs/releases)** (`qjs`) | ~2 MB | ~7x slower | Tiny, but adds a few seconds to every YouTube link. |
| **[Bun](https://bun.sh/)** | ~90 MB | fast | Version 1.2.11 or newer. |

Any one of them is enough, and GridPlayer uses the best one it finds. It looks in these places, in order:

1. The folder named in **Settings -> Streaming -> Link Resolution -> JavaScript runtime**, if you set one.
2. The GridPlayer [data directory](#default-data-directory-locations) — drop the binary in next to
   `settings.ini`. The **Open data folder** button at the bottom of the settings window takes you there.
3. The usual install locations: your `PATH`, `~/.deno/bin` and `~/.bun/bin`, and on macOS the Homebrew
   folders (`/opt/homebrew/bin`, `/usr/local/bin`).

Installing an engine the ordinary way is normally all it takes. Two cases need a hand:

- **Snap** can't see anything outside itself, and hidden folders like `~/.deno` are blocked, so put the
  binary in the data folder.
- **Node managed by nvm** lives in a folder per version, which nothing can guess. Name it in the settings.

**Settings -> Streaming -> Link Resolution -> Test a YouTube link** names the one that will actually be used and where it is, since only one of several installed ever runs.

Not every link needs one. YouTube often hands out addresses that need no unscrambling at all, and nothing
else GridPlayer plays uses this. It's worth installing when YouTube specifically starts failing.

## Known issues

### Linux (Snap): Error when opening a file from the mounted disk

You need to allow GridPlayer snap to access removable storage devices via Snap Store or by running:

```shell
sudo snap connect gridplayer:removable-media
```

### Linux (Snap): mounted drives are not visible in file selection dialog

You will also see following error if you run GridPlayer from terminal:

```shell
GLib-GIO-WARNING **: Error creating IO channel for /proc/self/mountinfo: Permission denied (g-file-error-quark, 2)
```

To fix this, you need to allow GridPlayer snap to access system mount information and disk quotas via Snap Store or by
running:

```shell
sudo snap connect gridplayer:mount-observe
```

### Linux: black screen issue with VLC Hardware or MPV Direct

The simplest fix is a mode that GridPlayer draws itself: MPV with the Copy or Shared video output, or Software (VLC
or MPV). See [Video Decoder settings](#video-decoder-settings).

To keep VLC Hardware or MPV Direct:

- If no compositor is running, GridPlayer switches the overlay to opaque automatically. If the overlay is still a black
  screen, switch on "Opaque overlay (fix black screen)" checkbox in settings.
- Depending on the window manager, the overlay might be a bit glitchy with these modes. Enabling compositor might
  help.

### macOS: some deinterlace modes and subtitle files are greyed out

The MPV that comes with the macOS package is a smaller build. It has no Discard, Blend, Bob, Linear or Film NTSC
(IVTC) deinterlacing, and reads only SRT, ASS/SSA, WebVTT and MKS subtitle files, not VobSub (`.idx`/`.sub`),
MicroDVD, SAMI and others. These show greyed out. VLC has them all: pick it in **Settings -> Advanced -> Video
Decoder**.

## Geting help

If you found a bug or have a feature request,
please [open a new issue](https://github.com/vzhd1701/gridplayer/issues/new/choose).

If you have a question about the program or have difficulty using it, you are welcome
to [the discussions page](https://github.com/vzhd1701/gridplayer/discussions). You can also mail me directly, I'm always
happy to help.

## Attributions

This software was build using

- **Python** by [Python Software Foundation](https://www.python.org/)
  - Licensed under *Python Software Foundation License*
- **Qt** by [Qt Project](https://www.qt.io/)
  - Licensed under *GPL 2.0, GPL 3.0, and LGPL 3.0*
- **VLC** by [VideoLAN](https://www.videolan.org/)
  - Licensed under *GPL 2.0 or later*
- **MPV** by [mpv contributors](https://mpv.io/)
  - Licensed under *GPL 2.0 or later*
- **FFmpeg** by [FFmpeg developers](https://ffmpeg.org/)
  - Licensed under *GPL 2.0 or later*
- **MPVKit** by [mpvkit](https://github.com/mpvkit/MPVKit), the libmpv built for macOS
  - Licensed under *LGPL 3.0*

### Python packages

- **PyQt** by [Riverbank Computing](https://riverbankcomputing.com/)
  - Licensed under *Riverbank Commercial License and GPL v3*
- **python-vlc** by [Olivier Aubert](https://github.com/oaubert/python-vlc)
  - Licensed under *GPL 2.0 and LGPL 2.1*
- **python-mpv** by [jaseg](https://github.com/jaseg/python-mpv)
  - Licensed under *GPL 2.0 or later, or LGPL 2.1 or later*
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
- **Lucide Icons** by [Lucide Contributors](https://lucide.dev/)
  - Licensed under *ISC License*

### Data

- **SponsorBlock** by [Ajay Ramachandran and contributors](https://sponsor.ajay.app/)
  - Licensed under *CC BY-NC-SA 4.0*

### Ideas

- **[gridplayermpv](https://github.com/Brick2892/gridplayermpv)**, a fork by [Brick2892](https://github.com/Brick2892):
  MPV drawing into windows of its own (Direct), Picture quality and your own mpv options

## Translations

<!-- CROWDIN-CONTRIBUTORS-START -->

<table>
  <tbody>
    <tr>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/VenusGirl"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/14432528/medium/3284b34db4ef3cda16835c5a18c797d0.jpg" />
          <br />
          <sub><b>VenusGirl</b></sub></a>
        <br />
        <sub><b>886 words</b></sub>
        <br /><sub><b><code title="Korean">ko</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/LOUIS_Sylvain"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/14983555/medium/af7d7ab185011ffda0bd01b41fc05ccf.png" />
          <br />
          <sub><b>Sylvain LOUIS</b></sub>
          <br />
          <sub><b>(LOUIS_Sylvain)</b></sub></a>
        <br />
        <sub><b>886 words</b></sub>
        <br /><sub><b><code title="French">fr</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/Gabriel-BS1"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15681015/medium/50b012437410a2a9c27236c0ce05b1b1.png" />
          <br />
          <sub><b>GBS ~ TECH</b></sub>
          <br />
          <sub><b>(Gabriel-BS1)</b></sub></a>
        <br />
        <sub><b>886 words</b></sub>
        <br /><sub><b><code title="Portuguese, Brazilian">pt-BR</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/Granberg"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/12416181/medium/2864d29be808543d56f9e210a06ad934.jpg" />
          <br />
          <sub><b>Göran</b></sub>
          <br />
          <sub><b>(Granberg)</b></sub></a>
        <br />
        <sub><b>875 words</b></sub>
        <br /><sub><b><code title="Swedish">sv-SE</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/royhendum"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/17390478/medium/ab5a65a9b43bbae930fe45baa1a5e51f.png" />
          <br />
          <sub><b>Roy Hendum</b></sub>
          <br />
          <sub><b>(royhendum)</b></sub></a>
        <br />
        <sub><b>875 words</b></sub>
        <br /><sub><b><code title="Norwegian">no</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/zxas"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/16338184/medium/90d1c13645360de47426fcd50d7630df.jpeg" />
          <br />
          <sub><b>z Z</b></sub>
          <br />
          <sub><b>(zxas)</b></sub></a>
        <br />
        <sub><b>851 words</b></sub>
        <br /><sub><b><code title="Chinese Traditional">zh-TW</code></b></sub>
      </td>
    </tr>
    <tr>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/davidev1"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/13229273/medium/03b55ef5010bbc801f432e51e4a50171.jpg" />
          <br />
          <sub><b>Davide V.</b></sub>
          <br />
          <sub><b>(davidev1)</b></sub></a>
        <br />
        <sub><b>752 words</b></sub>
        <br /><sub><b><code title="Italian">it</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/Vistaus"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/12732621/medium/bbca85454e90b7362cbbe57e5cd54489.jpeg" />
          <br />
          <sub><b>Heimen Stoffels</b></sub>
          <br />
          <sub><b>(Vistaus)</b></sub></a>
        <br />
        <sub><b>751 words</b></sub>
        <br /><sub><b><code title="Dutch">nl</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/japanese.john.doe.774"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15405594/medium/1e457ad578b4390a744f8b1af85533fa.png" />
          <br />
          <sub><b>七篠孝志</b></sub>
          <br />
          <sub><b>(japanese.john.doe.774)</b></sub></a>
        <br />
        <sub><b>751 words</b></sub>
        <br /><sub><b><code title="Japanese">ja</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/DominikPott"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15472688/medium/6e48ea2f0a8564252086d2d7775d2f21.png" />
          <br />
          <sub><b>DominikPott</b></sub></a>
        <br />
        <sub><b>751 words</b></sub>
        <br /><sub><b><code title="German">de</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/Azoaz6001"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15591465/medium/ae7a5aafbc99dc9ac4ba3a8c5bf42dcb_default.png" />
          <br />
          <sub><b>Azoaz6001</b></sub></a>
        <br />
        <sub><b>751 words</b></sub>
        <br /><sub><b><code title="Arabic">ar</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/wyg945"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15682575/medium/e3d1504b9b88be18745f758cb4f11d77.png" />
          <br />
          <sub><b>Yagang Wang</b></sub>
          <br />
          <sub><b>(wyg945)</b></sub></a>
        <br />
        <sub><b>751 words</b></sub>
        <br /><sub><b><code title="Chinese Simplified">zh-CN</code></b></sub>
      </td>
    </tr>
    <tr>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/Golbinex"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/17664878/medium/1b0e9f044a085950575bcf53e3581336.jpeg" />
          <br />
          <sub><b>Kryštof Baksa</b></sub>
          <br />
          <sub><b>(Golbinex)</b></sub></a>
        <br />
        <sub><b>674 words</b></sub>
        <br /><sub><b><code title="Czech">cs</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/IngrownMink4"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/14414288/medium/53f8a637c2fa88786f85808ebee55807.jpg" />
          <br />
          <sub><b>Sergio Varela</b></sub>
          <br />
          <sub><b>(IngrownMink4)</b></sub></a>
        <br />
        <sub><b>652 words</b></sub>
        <br /><sub><b><code title="Spanish">es-ES</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/fifi132"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15774079/medium/0e0d2651e73807bbb9050e8fd3e44f18.png" />
          <br />
          <sub><b>rafal132</b></sub>
          <br />
          <sub><b>(fifi132)</b></sub></a>
        <br />
        <sub><b>598 words</b></sub>
        <br /><sub><b><code title="Polish">pl</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/a2942"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/16794451/medium/184acbf1f2f0e4adf1dc62822bd5acfd.jpg" />
          <br />
          <sub><b>a2942</b></sub></a>
        <br />
        <sub><b>496 words</b></sub>
        <br /><sub><b><code title="Chinese Simplified">zh-CN</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/LiberiFatali"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15598851/medium/610ee0a4acb813a2832ac2c927e79cfb_default.png" />
          <br />
          <sub><b>LiberiFatali</b></sub></a>
        <br />
        <sub><b>456 words</b></sub>
        <br /><sub><b><code title="Vietnamese">vi</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/samu112"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15157130/medium/e119d6e287f4e49464eac1ee32974bac_default.png" />
          <br />
          <sub><b>samu112</b></sub></a>
        <br />
        <sub><b>438 words</b></sub>
        <br /><sub><b><code title="Hungarian">hu</code></b></sub>
      </td>
    </tr>
    <tr>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/asolis2020"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15661045/medium/6ba336a35aa362fa47b5adf11919141b_default.png" />
          <br />
          <sub><b>asolis2020</b></sub></a>
        <br />
        <sub><b>266 words</b></sub>
        <br /><sub><b><code title="Spanish">es-ES</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/SolarCTP"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15384684/medium/f0197a7e2769ecc2788a18091a7afb0b.png" />
          <br />
          <sub><b>SolarCTP</b></sub></a>
        <br />
        <sub><b>164 words</b></sub>
        <br /><sub><b><code title="Italian">it</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/PrinceNorris"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/13962625/medium/907539fd79ca32a8a08d400a1aa043f7_default.png" />
          <br />
          <sub><b>Sebastian Jasiński</b></sub>
          <br />
          <sub><b>(PrinceNorris)</b></sub></a>
        <br />
        <sub><b>163 words</b></sub>
        <br /><sub><b><code title="Polish">pl</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/reiss404"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/17071680/medium/8b927c3a2c3389c590128dc1f89dbeab.jpeg" />
          <br />
          <sub><b>Manuel</b></sub>
          <br />
          <sub><b>(reiss404)</b></sub></a>
        <br />
        <sub><b>133 words</b></sub>
        <br /><sub><b><code title="German">de</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/aportuguesecoder"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/17032790/medium/7ae1612b2227266f02dd7c6af1bb0d67.jpeg" />
          <br />
          <sub><b>Armando Gomes</b></sub>
          <br />
          <sub><b>(aportuguesecoder)</b></sub></a>
        <br />
        <sub><b>121 words</b></sub>
        <br /><sub><b><code title="Portuguese">pt-PT</code></b></sub>
      </td>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/Akronos"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/16284890/medium/db02e5c7b29dce08b02cd94a93b0ef0e_default.png" />
          <br />
          <sub><b>Akronos</b></sub></a>
        <br />
        <sub><b>112 words</b></sub>
        <br /><sub><b><code title="Czech">cs</code></b></sub>
      </td>
    </tr>
    <tr>
      <td align="center" valign="top">
        <a href="https://crowdin.com/profile/WackyFox"><img alt="logo" style="width: 64px" src="https://crowdin-static.cf-downloads.crowdin.com/avatar/15807071/medium/21329dc32cf56b0743914d5ef724d1e3.jpeg" />
          <br />
          <sub><b>Владимир Ларин</b></sub>
          <br />
          <sub><b>(WackyFox)</b></sub></a>
        <br />
        <sub><b>108 words</b></sub>
        <br /><sub><b><code title="Hebrew">he</code></b></sub>
      </td>
    </tr>
  </tbody>
</table>
<!-- CROWDIN-CONTRIBUTORS-END -->

## License

This software is licensed under the terms of the GNU General Public License version 3 (GPLv3). Full text of the license
is available in the [LICENSE](https://github.com/vzhd1701/gridplayer/blob/master/LICENSE) file
and [online](https://www.gnu.org/licenses/gpl-3.0.html).
