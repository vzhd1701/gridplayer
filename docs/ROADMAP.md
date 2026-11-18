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

## Surviving a GPU reset (MPV)

From the MPV plan, 10.8 (2026-11-11). Left for later: rare, and it can't be tested without forcing resets on a real
Windows PC. Worth doing if someone reports the app closing like this.

What happens today: MPV draws with OpenGL contexts of its own, made without asking to survive a reset. When Windows
resets the GPU's driver, NVIDIA's OpenGL driver is known to close such an app ("lost connection with the display
driver"), as it does most OpenGL apps. Not seen here yet. Mesa on Linux replaces such a context by itself, so there
it should only glitch. VLC Hardware draws with Direct3D and has the same kind of exposure.

How often, at a guess:

- A GPU reset: Windows restarts the driver when something hangs the GPU for 2 s, nearly always a game or another
  GPU-heavy app. On a healthy PC none or one or two a year; more with overclocks, failing cards, buggy laptop drivers.
- A driver update while the app runs: ones you install yourself, you close apps first. Windows Update sometimes puts in
  a display driver quietly, perhaps once or twice a year.
- Not a cause: sleep, plugging monitors, remote desktop. Windows keeps GPU memory across those.
- A render call stuck for good, what a watchdog would catch: never reported, it would take a driver bug. A cleanup
  already stops waiting for it after 5 s, and Reload All brings the videos back.

When it hits, the app closes; unsaved playlist changes are lost.

How it would work:

- Make the contexts with reset notification (`WGL_ARB_create_context_robustness`, the EGL one on Linux).
- Ask `glGetGraphicsResetStatus` once a render round, or once a second.
- On a reset: a new context, every video's render context made again, and the frames drawn again.
- Copy output has only our contexts. Shared shares Qt's, which would need the same, and Qt 5's QOpenGLWidget doesn't
  come back after a reset: likely only with Qt 6.

What it would cost:

- Speed: nothing to measure, expected. The setting is made once, the check is one cheap call that doesn't wait on the
  GPU, and bounds checking is done in hardware on current GPUs. Run the bench before and after anyway.
- Code: a few hundred lines, on a path that only runs on a real reset, so a bug in it could hide for long.
- Testing: `dxcap -forcetdr` (Windows' optional Graphics Tools) forces a reset. It blanks the screens for a second and
  kills any game running. First step: force one with MPV playing and see what happens today, and build this only if
  the app really closes.

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

## Maybe some day

Ideas talked about and put aside. None is wanted soon; they're here so they aren't lost.

### A read-ahead cache for streams on VLC

From the VLC read-ahead notes (2026-10). mpv's demuxer cache reads ahead, keeps what was played and knows which parts
are loaded; VLC 3 has none of that, and libVLC doesn't say how far ahead it has read. Every stream already goes through
the app's own proxy (all but `direct`), a plain relay with no cache, so that is where one would go:

- The proxy keeps the segments it fetched, and reads ahead of the one playing, so a seek back is instant.
- The seek bar shows what the proxy has, as mpv's cache ranges are shown.

Not measured: whether VLC's own `:adaptive-maxbuffer` would read further ahead through the playlists the proxy makes.

### Gamepad hotkeys

Planned 2026-10-07, not started. The plan is in `GAMEPAD.md`:

- SDL2 through `pysdl2` (Qt's gamepad module isn't in PyQt5 and is gone from Qt 6), behind an interface so SDL3 can
  replace it.
- A pad button is a fourth kind of key in the keymap (`Pad LB+A`), beside keyboard, mouse and the mouse drag keys, so
  saving, conflicts and the shortcuts editor work as they do.
- Phases: a spike in every package first, then the bindings, then moving through menus and dialogs, then the sticks.
- Six questions in the plan to answer before building: the library, on by default, default bindings, chords, menus
  in the first phase, the binding format.

### Split mode

Talked about 2026-11-03. A grid mode like tmux or i3: each new video
splits a tile in two, and dragging a line between tiles resizes both sides. Put aside until someone asks for it: most
of its layouts can be made already (Fixed Grid with spans and templates, Free Tiles with snapping, Mosaic), and it
costs a whole mode that works against the videos' shapes.

### An endless canvas for Free Tiles

From the On Window Resize work (2026-10-31). Free Tiles on a page bigger than the window: zoom in and pan around the
tiles, zoom out no further than all of them fitting, Shift and the middle button to pan.
