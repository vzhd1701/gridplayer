# Known issues

Glitches whose cause is outside GridPlayer: Qt, graphics drivers, VLC, mpv, the desktop. Each says what is seen and where,
why, what the app does about it, and what would end it. The measurements stay where they were made; each entry links to
them. A glitch of our own goes to the plan or the ROADMAP instead, to be fixed.

When one ends (a new Qt, a driver), check it and take it out, saying so in the commit.

## MPV Shared on Wayland: the header jumps as the window is resized

- **Seen:** Wayland with Qt's own header (GNOME), MPV's Shared output, the window dragged bigger or smaller: the header's
  title and buttons, and the top of the picture with them, jump up 2-4 px and back, over and over. Copy and VLC Software
  don't.
- **Why:** Qt 6.12.0's bug. Now and then a frame drawn for the new size goes into a buffer still a few rows short, drawn
  from the bottom up, so its top rows are cut off. A bare window with a `QOpenGLWidget` and nothing of ours does it on
  6.12.0 and not on 5.15, 6.10.2 or 6.11.2; nor without Qt's header. Likely from qtbase `ed4bf9c993` (April 2026: the
  `wl_egl_window` resized after `eglMakeCurrent`, QTBUG-95817).
- **What the app does:** nothing more can be done from Python (no vsync, an early resize, `QT_WAYLAND_DISABLE_RESIZECHECK`
  were tried). Auto in Window system takes X11 on GNOME, so only a Wayland chosen by hand gets it. The Flatpak, on Qt
  6.11, doesn't. Staying on 6.12 rather than 6.11 on Linux was decided 2026-11-19.
- **What would end it:** qtbase `94f9621051` (dev, 2026-11-09: the header in subsurfaces) should; or our own window frame
  (ROADMAP). Check each Qt release.
- **Measured:** `docs/archive/QT6_PLAN.md`, 4.2.

## MPV Shared on X11: the picture lags a window being made bigger

- **Seen:** X11 (or Xwayland), MPV's Shared output, the window dragged bigger: the cells and their overlays jump down and
  back as it grows.
- **Why:** mostly the graphics driver. A frame for the old size shows in the grown window, drawn from the bottom up. On
  `test_ubuntu` (VMware's SVGA3D) Ubuntu 24.04's Mesa 25.2.8 does it, the same on Qt 6.11 and 6.12, Qt 5 worse; Mesa
  26.2.6 and the Flatpak (Mesa 26.2.7 of its runtime) resize smoothly.
- **What the app does:** `utils/gl_window_size.py` holds Qt's paint while X11 already has a size Qt hasn't taken yet
  (asked over its own xcb connection), which takes most of it away.
- **What would end it:** a newer Mesa on the system. The AppImage, Snap and pip install use the system's drivers.
- **Not known:** real GPUs; only the VM's was tried.
- **Measured:** `docs/archive/QT6_PLAN.md`, 4.2.

## MPV Shared on Windows: the window opens white for a moment

- **Seen:** Windows, MPV's Shared output, OpenGL drawn by one GPU while the screen is on another (an NVIDIA card, with
  the screen on the CPU's AMD graphics): the window opens white, and the empty cells come ~140 ms later. Not on the
  screen's own GPU, nor with Copy or Direct.
- **Why:** the first frame Qt draws with OpenGL in a window crosses to the other GPU late. A bare Qt window with a
  `QOpenGLWidget` and nothing of ours does it too. The app paints its first frame ~65 ms after the window shows, the
  same as with Copy; that frame then reaches the screen ~140 ms later.
- **What the app does:** nothing. With Shared the window is drawn with OpenGL from the start (`main/run.py`, the grid's
  surface made before the window is shown), since a window shown without it is made again as the first video comes:
  gone from the screen for a moment, on Windows and Linux both. The white at the start was the better of the two.
  Tried 2026-11-20 and dropped:
  - keeping the window out of sight until drawn: the app can't tell when its frame is on the screen, so the window came
    later and still white;
  - drawing a first frame ahead, in a window of a pixel nobody sees (on a thread of its own, and with Qt before the
    player is made): white down to ~35 ms, but the app was slower to start;
  - a window off the screen or out of sight drawing first, a context without a window, no alpha channel in the window
    (the black line fix off): no change.
- **What would end it:** OpenGL on the screen's GPU (Windows' Graphics settings, or the NVIDIA Control Panel, for
  Python or the app's exe), though MPV then decodes on that GPU too.
- **Measured:** 2026-11-20, an RTX with the screen on an AMD iGPU, by filming the window on the screen; only here.

## VLC on Windows: a sound of 1.2 s or less is cut to its first 100 ms

- **Seen:** Windows, any VLC driver, a file of sound alone (a WAV from a soundboard) of 1.2 s or less: on each pass only
  about its first 100 ms plays, and its time never moves off 0. MPV plays it out, and so does the VLC app.
- **Why:** on Windows the app sends VLC's sound out through DirectSound (`--aout=directsound`, `vlc_player/instance.py`);
  the VLC app uses WASAPI. VLC 3 reads 1000 ms of a file ahead (`file-caching`), so a sound that short is read to its
  end before any of it has played. VLC's DirectSound output can wait for its sound to play out only once some of it has,
  so the input ends, or goes round, at once. With a video track the picture holds it back, so a short video's sound
  plays.
- **What the app does:** nothing. Reading less ahead for short sounds alone (`:file-caching=50`, given after parsing every
  small local file first) made one of 0.3 s or more play out, but was dropped (2026-11-24): another step in loading
  every small file, numbers found on one machine, sounds under 0.3 s still cut, and MPV, the default, plays them right.
  Given to every file, that cache costs a short video about 7 of 45 frames a pass.
- **What would end it:** MPV, for anyone playing such files. Or VLC's WASAPI output, if the reason for DirectSound (likely
  that WASAPI's volume is the whole process's, so cells couldn't have their own) no longer held.
- **Measured:** 2026-11-24, libVLC 3.0.24 alone and in the app, tones and a 1.05 s WAV: any rate and channels, looped by
  `:input-repeat` or by the media list player or not at all; 1.3 s and longer play out; WASAPI plays them all. The
  real-app scenario `short_loops` holds MPV to playing a 1 s sound out.

## Others

- **Hardware VLC resizes slowly.** VLC can't redraw its picture at a new size; it catches up only with its next frame.
  Left as it is: MPV is the answer for live resizing. Windows and macOS. `VLC.md`, 10.36.
- **MPV Direct flickers a little on cell borders while resizing.** As good as it got. `VLC.md`, 10.36.
- **MPV Direct could crash the app in graphics drivers** (NVIDIA and AMD on Windows, Linux X11) when several of its outputs
  come and go at once. Avoided by starting them one at a time. `MPV_DIRECT_CRASHES.md`.
- **Hardware VLC on Linux X11 held the GUI over a minute loading 36 cells of 1080p30**, single and multi-process; the X
  server's path, not Windows. Measured 2026-11-09, not again since. `MPV_PERFORMANCE.md`, "VLC's freeze at 36 cells".
- **Qt's header on GNOME's Wayland has GNOME's colours, not the app's theme,** and follows GNOME's light or dark. Qt has
  no way to give it ours; the app draws a line under it. Our own frame would end it (ROADMAP). `docs/archive/QT6_PLAN.md`,
  4.2.
- **On Wayland the window's place isn't restored.** Wayland doesn't let an app place its own window. ROADMAP, Qt 6.
- **Hiding the taskbar button does nothing under sway:** its X11 doesn't take the request. `docs/archive/QT6_PLAN.md`, 4.1.
