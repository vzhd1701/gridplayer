# Roadmap

Ideas kept for later. Nothing here is planned yet or promised. Each one says where it came from.

## Playback stats for a cell

From the MPV plan, 10.31 (2026-11-11).

A panel the app draws over a cell, showing:

- dropped frames
- what decodes the video: the GPU or the CPU, and which decoder
- frames a second
- how much is cached

mpv's own stats script shows these, but it stays off. It needs mpv's key bindings, which the app turns off. It draws its
panel into the picture, and it costs a thread for each video.

How it would work:

- Read mpv's properties only while the panel is shown, so it costs nothing until then.
- Show VLC's figures where VLC has them.

Already decided: mpv's scripts don't become a setting. None of them can be reached in the app. Users' own scripts stay off,
as they would seek and change tracks behind the app's back, once for each video.

## Qt 6

The next big step after MPV (said 2026-11-11). What it brings for Wayland:

- Sharp windows at fractional scales (125%, 150%), from Qt 6.5. Qt 5 is blurry there, on Wayland and on Xwayland alike.
- Fewer rough edges: focus and activation, popups, the clipboard.
- Still no placing of windows: Wayland doesn't let an app put its own window anywhere, so the window's place isn't
  restored on any Qt.

### Our own window frame on GNOME

GNOME draws no frames for apps on Wayland. Qt draws its own then, a thick flat band in the window's colour with no
shadow, dialogs too, so they blend into the window behind. That's why Auto in Window system stays on X11 there
(`utils/wayland_frames.py`).

With Qt 6 the app could draw a frame of its own: a thin border, its own title bar (title, minimize, maximize, close,
double-click to maximize, moved and resized by the desktop), and a shadow. Newer Qt 6 can tell the desktop where the
window really ends inside the shadow, so maximizing and tiling leave no gaps; Qt 5 can't, which is why this waits.
Every dialog needs the same frame. Then Auto could take Wayland on GNOME too.

Another way is the QAdwaitaDecorations plugin, GNOME's look for Qt's frame, but a packaged app has its own Qt and the
plugin must be built for exactly that one: a compiled part to keep up for every Qt release and CPU.
