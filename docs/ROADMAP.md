# Roadmap

Ideas kept for later. Nothing here is planned yet or promised. Each one says where it came from. What's built but not
yet tried on some hardware is in `NEEDS_TESTING.md`.

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

## Restart Now

Talked about 2026-11-19. Some settings work only after a restart (the video driver or MPV's output, when it changes
whether MPV draws with GL; the window system; the language). The "Restart to apply" message only says so. When what
draws the videos is what waits for the restart, the videos already open stay as they are until then rather than being
made again twice, once as a stand-in and once after the restart; the ones opened next take the new settings.

A "Restart Now" button beside it would start the app again with the same playlist and cells, unsaved changes kept as
unsaved. Left for later because it has to work in every package: the Windows exe and installer, the `.app`, the
AppImage, the Flatpak and Snap sandboxes, and from source. And the new copy must wait for the old one to close, or the
single-instance check hands it back to the old one.

## Qt 6

Moved to PyQt6 6.12 on the `qt6` branch (2026-11-19), stage by stage in `docs/archive/QT6_PLAN.md`. What it brought for
Wayland:

- Sharp windows at fractional scales (125%, 150%): Qt 6 draws at 1.5 where Qt 5 drew at 2 and the compositor scaled it
  down (seen on sway).
- Fewer rough edges: focus and activation, popups, the clipboard.
- Still no placing of windows: Wayland doesn't let an app put its own window anywhere, so the window's place isn't
  restored on any Qt.

### Our own window frame on GNOME

GNOME draws no frames for apps on Wayland. Qt draws its own then: on Qt 6 its adwaita decoration, in GNOME's colours
and light or dark as GNOME is, not as the app's theme is, with a line of ours under its header. That's why Auto in
Window system stays on X11 there (`utils/wayland_frames.py`).

With Qt 6 the app could draw a frame of its own: a thin border, its own title bar (title, minimize, maximize, close,
double-click to maximize, moved and resized by the desktop), and a shadow. Newer Qt 6 can tell the desktop where the
window really ends inside the shadow, so maximizing and tiling leave no gaps; Qt 5 couldn't. Left for after the move.
Every dialog needs the same frame. Then Auto could take Wayland on GNOME too.

It would also end a glitch of Qt 6.12's frame: with MPV Shared, the header jumps up and down a few pixels as the window
is resized (Qt's bug, not in 6.11; `docs/findings/KNOWN_ISSUES.md`). Qt's development branch draws the frame apart from the window
from 2026-11-09, which should end it too: try each Qt release.

Another way is the QAdwaitaDecorations plugin, GNOME's look for Qt's frame, but a packaged app has its own Qt and the
plugin must be built for exactly that one: a compiled part to keep up for every Qt release and CPU.

## Architecture refactor

After the move to Qt 6 (said 2026-11-18), so the big diff of each isn't fought twice. What and in what order is in
`docs/reviews/ARCHITECTURE_REVIEW.md`, a read of the whole app done 2026-11-16. In short: the managers, connections, commands,
actions, menu, block parts, drivers, resolvers and settings are each a closed list written out by hand in one file, so
a feature means editing five to thirteen files, and a plugin could edit none of them. Each list becomes a registry
that things add themselves to.

- If only five are done: `Player`'s hand wiring (1), the flat commands and context (2), the frozen actions and menu
  (3), the settings singletons (7) and the block parts (5); the cheap ones on the way, `[ALL]` as a loop (4),
  resolver and list-format registries (10) and a lifecycle with teardown (16).
- Its "A possible order" goes in steps that each leave the app working, from guard rails and quick registries to a
  plugin loader with one of the app's own features moved onto it.

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

Planned 2026-10-07, not started. The plan is in `docs/plans/GAMEPAD.md`:

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
