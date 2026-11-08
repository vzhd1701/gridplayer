# mpv driver: plan and progress

The findings and traps are in `C:\Projects\test_temp\test_mpv\HANDOFF.md`, and
`grid4.py` there is the working POC. That folder is reference only. This file is
what we build and how far it has got. Tick items only once they have been seen
working.

**Status: Stage 3 built (<https://claude.ai/artifact/8ngdeLCkVxmdQzSEnpxx1c>, real screenshots on its Built board). Open: macOS. Bundling libmpv (12.1) is for later. Stages 1-9 are committed on this branch.**

**Load tests against VLC: `MPV_PERFORMANCE.md`.** No multi-process mode for MPV. New items 10.13-10.16. **10.16 is a long run
still to be started, overnight, by you.**

| | Stage | State |
|---|---|---|
| 1 | Videos load, play and resize in the real grid, with zoom and pan | built, your hand test still open |
| 2 | Finding the libraries, no startup delay, runs with only one of VLC or mpv | **done, macOS not run** |
| 3 | Settings: unavailable drivers greyed out with a reason | **built, macOS still open** |
| 4 | Transport: seek, speed, frame step, looping, end of video | **built, macOS not run** |
| 5 | View: rotate, flip, crop, aspect ratio, screenshots, sync | **built, macOS not run** |
| 6 | Audio: tracks, files, devices, delay, channels | **built, macOS not run** |
| 7 | Subtitles: tracks, files, delay, encoding, style | **built, macOS not run** |
| 8 | Deinterlacing, chapters, bookmarks, SponsorBlock | **built, macOS not run** |
| 9 | Streams, live video, errors and recovery, lists | **built, macOS not run** |
| 10 | Hardening: long churn, memory, real drags, other GPUs | not started |
| 11 | macOS | not started |
| 12 | Packaging, docs, release | not started |

## Rules that hold in every stage

- **The VLC drivers keep working as they are.** Every stage ends with the existing
  tests and real-app scenarios passing on VLC.
- **No sleeping cells.** Rejected: a video on the grid stays loaded.
- `gridplayer/mpv_player/mpv.py` is vendored like `vlc.py`. Don't edit it.
- No commits unless you ask. No translation files. New strings use literal
  `translate("SettingsDialog", "...")` calls and stay short and plain.
- Threads, from the handoff: the GUI thread never waits on mpv, the render thread never
  waits on the mpv core, a resize reaches mpv only after 150 ms of quiet, and closing is
  stop drawing, then free on the render thread, then terminate on another thread.
- Test windows stay off your desktop: offscreen on Windows, or the Linux machines.

## How it fits together

```text
gridplayer/mpv_player/
    mpv.py              vendored python-mpv 1.0.8
    libmpv.py           imports mpv.py against the library that was found
    gl_context.py       a GL context with no Qt: EGL on Linux, WGL on Windows
    renderer.py         the one render thread, slots, readback
    player.py           one mpv instance: options, observers, commands
gridplayer/widgets/video_frame_mpv.py
    VideoFrameMpv(VideoFrameVLC), VideoDriverMpv(VLCVideoDriver), the surface
gridplayer/utils/media_libs.py
    finds libVLC and libmpv without loading them, loads one, remembers what went wrong
```

`VideoDriverManager` owns the one render thread: made on first use, stopped in
`cleanup()`. The frame subclasses `VideoFrameVLC` the way `VideoFrameDummy` does, so the
zoom, pan and placement sums are all shared. Renaming those classes is optional at the
very end.

### Decisions already made

| Question | Answer | Why |
|---|---|---|
| GL on X11 with `QT_XCB_GL_INTEGRATION=none` | The render thread makes its own EGL context with ctypes and Qt never touches GL. To be proven in Stage 1 | The env var stays as it is, so VLC can't be affected. No setting has to be read before `QApplication`, and switching to mpv needs no restart. The other routes were a restart on every switch, or spawning VLC's processes, which changes VLC. **Proven:** `vaapi` zero-copy on X11 and Wayland with the variable set |
| GL on Windows | Same idea, own WGL context | Qt's `offscreen` platform on Windows can't make a GL context (checked: `create()` returns False), so real-app scenarios couldn't run mpv without opening windows. It also avoids `AA_UseDesktopOpenGL`. **Proven:** `nvdec` on a message-only window, 4 cells of 10-bit HEVC. Only run on NVIDIA so far |
| GL on macOS | `QOpenGLContext`, as in the POC, until Stage 11 says otherwise | Never run there, and it needs no env trick |
| Which frame size does the view use | Always the track's size, not the rendered size | The render size changes after each resize. Crop and shift are in picture pixels and must not move |
| When does a cell count as loaded | At its first finished frame, or on `file-loaded` for audio only | No black flash between the status and the picture |
| Picking a driver whose library is missing | The setting stays, this session falls back to the other library, the same way Hardware falls back on Wayland. Said once a run, when the first video opens | Nobody gets locked out by a removed library |
| libVLC's search | Written again in `media_libs.py`, not shared | `vlc.py` searches and loads in one go, and it can't be edited. A check that doesn't load has to be separate |
| libmpv found, won't load, and no VLC | The box says so, and cells stay empty rather than the player closing | Only found out at the first video, by which time the window is up |

### Measured so far (load times, warm)

| | `find_library` | Loading the library |
|---|---|---|
| Windows, 117 MB `libmpv-2.dll` | under 1 ms | 7-11 ms |
| Debian on real Intel, `libmpv.so.2` | about 1 ms | 77-79 ms |
| Ubuntu VM, `libmpv.so.2` | about 1-2 ms | 34-35 ms |

So finding a library is cheap. Loading is what costs on Linux, so a library is loaded only
for the driver in use.

---

## Stage 1: Load, play, resize, zoom and pan in the real grid

Ends with a showing. Nothing past this stage starts until you've seen it.

- [x] 1.1 Vendor `mpv.py`, unedited. Lint-exclude it the way `vlc.py` is excluded
- [x] 1.2 `gl_context.py`: EGL and WGL with no Qt. Spike first, on all machines: does
  EGL keep VAAPI zero-copy on X11 and Wayland, does WGL keep NVDEC
- [x] 1.3 `libmpv.py`: minimal lookup for now, `GP_LIBMPV_PATH` then the system. Stage 2
  finishes it
- [x] 1.4 `VideoDriver.MPV`, its label, and the manager mapping. Not multiprocess
- [x] 1.5 `renderer.py`: render thread, ordered job queue, triple buffer, readback,
  one present per refresh, and these from the handoff: `block_for_target_time=False`,
  `update_cb` set once, the close order
- [x] 1.6 `player.py`: the POC's options including the three memory settings, observers
  that only store values, a flag that gates every command, terminate on its own thread
- [x] 1.7 `video_frame_mpv.py`: `Media` built from `track-list`, `load_finished`,
  `time_changed`, `playback_status_changed`, errors shown in the cell for broken files
- [x] 1.8 The surface: picture size from the track, target snapped to device pixels,
  a render size from what's on show, capped at the picture's own
- [x] 1.9 Works through the app's own actions: play, pause, seek (basic), zoom, pan, all
  grid modes, Free Tiles resize, Single Mode, closing and reopening cells, Reload All.
  Switching VLC to mpv and back with videos open works too (VLC's in-process drivers, Windows)
- [x] 1.10 Real-app scenario `mpv_basics` in `tests/real_app/scenarios` with pixel checks,
  unit tests for the render size and the track list
- [x] 1.11 Verified on: Windows NVDEC, `test_gpu` X11 and Wayland with VAAPI, `test_ubuntu`
  GNOME. For each: `hwdec-current`, pictures moving, zoom and pan pixels right, 0 crashes
- [x] 1.12 VLC unchanged: `uv run pytest`, `just test-real-app`
- [x] 1.13 **Showing:** you ran it by hand, it looks OK so far (2026-11-06). It was: you run it with the command below and drag it around by hand.
  Nothing has been seen in a real window on Windows yet: Windows runs were offscreen, to
  stay off your desktop. `GP_LIBMPV_PATH` is still how to run it on Windows, unless the DLL is
  on PATH or in one of the places in 2.2

```powershell
$env:GP_LIBMPV_PATH = "C:\Projects\test_temp\test_mpv\libmpv-2.dll"
uv run gridplayer
# Settings > Advanced > Video Decoder > Decoder: mpv
```

### Stage 1 results

| Machine | Decoder, real 1080p clip, 4 cells | `mpv_basics` | Resize step, scripted |
|---|---|---|---|
| Windows, RTX 3060, offscreen | `nvdec` (10-bit HEVC) | pass | 1.7 ms, offscreen so not comparable |
| `test_gpu` X11 (Xwayland under sway), no VLC installed | `vaapi` (H.264) | pass, 13 of 13 runs after the audio fix | 12.1 ms |
| `test_gpu` Wayland (sway) | `vaapi` (H.264) | pass, 2 of 2 | not meaningful, sway holds the size |
| `test_ubuntu` X11 | `no`, the VM has no decoder | pass | 10.2 ms |
| `test_ubuntu` Wayland | `no`, the VM has no decoder | pass | 4.6 ms |

Every existing real-app scenario, run on mpv (`REAL_APP_VIDEO_DRIVER=mpv_hw`):

- **Windows, offscreen: 30 of 33 pass.** Before the pixel-shape fix it was 27. The three left
  are for later stages, none about grid or view: `marks` (chapters, 8.2), `tracks` (external
  audio, 6.3), `reopen_closed_video` (end of a video, 4.4; passes on `test_gpu`, fails on Windows).
- **`test_gpu`, real X11 under sway:** 9 more fail, in Free Tiles, grid lines, `mosaic` and Single
  Mode, and all 9 pass offscreen on the same machine. Probably sway holding the window's size,
  which those scenarios depend on. That cause is an inference, not checked further.
- **VLC:** `uv run pytest`: 7667 passed. `pytest -m real_app`: 31 passed, 1 known bug, `mpv_basics`
  skipped with no libmpv path.

Found on the way:

- With no sound device, mpv tries every audio output, and JACK and SDL hang or crash when several
  videos start them at once. The core dump showed SDL's init. It would hit anyone with no working
  sound, so Linux now tries only `pipewire,pulse,alsa`. See 6.7.

## Stage 2: Finding the libraries, no startup delay

- [x] 2.1 `utils/media_libs.py`: `find_libvlc()` and `find_libmpv()` return a path or
  nothing and load nothing. One result per run, so installing a library takes a restart
- [x] 2.2 Places for libmpv: `GP_LIBMPV_PATH`; bundled (PyInstaller `libmpv/`, Snap,
  AppImage, Flatpak); then the system. Windows: PATH, next to the app, next to `mpv.exe`,
  Program Files, `%LOCALAPPDATA%\Programs`, scoop. Linux: `LD_LIBRARY_PATH` and the usual
  folders, then `find_library`. macOS: Homebrew and MacPorts. The folders on Windows and macOS
  are from tests with fake files, no real install of each was tried. The mpv download
  for Windows doesn't normally include the DLL, see 12.1
- [x] 2.3 libVLC's search is mirrored rather than reused, since `vlc.py` can't be edited: embedded,
  `PYTHON_VLC_LIB_PATH`, PATH, registry, Program Files, the current folder; `VLC.app` on macOS.
  If they ever disagree, the load still decides when VLC is the pick
- [x] 2.4 VLC imports become lazy, per driver. Seen: starts and plays on `test_gpu`, which has
  no VLC. Test: the player is made with `vlc.py` and `mpv.py` blocked from loading
- [x] 2.5 `run_app`: load only the library of the driver in use. libmpv loads on the first video.
  It stays on the GUI thread: at most 94 ms once, see the results
- [x] 2.6 Fallbacks. Picked missing, other present: use the other for this session and
  say so once. Both missing: the error box, naming both, with links
- [x] 2.7 Too old or won't load (client API under 2.0, or not a library): treated as not
  available, with the reason logged. Won't load seen with a junk file on Windows and Linux. Too old
  only from unit tests, no old libmpv was to hand. Wrong architecture not tried
- [x] 2.8 Switching live. VLC to mpv: loads on the spot. mpv to VLC: loads on the spot, for every VLC
  driver, in both directions, on the VM. No fork abort, **but that isn't proof**, see the results
  and 10.12
- [x] 2.9 `env.VLC_VERSION` may now be unknown: About box and driver labels manage without. The
  user agent never used it. mpv and python-mpv rows added to About. The versions show once
  loaded, and mpv's once a video has played
- [x] 2.10 Measured before and after, below. No slower on VLC

### Stage 2 results

Process start to window shown and painted, real `main()`, median of 6 or 8 runs. "Before" is the
last commit, with no mpv work.

| Machine | Driver | Before | Now |
|---|---|---|---|
| Windows, offscreen, warm | VLC SP | 400-405 ms | 394-396 ms |
| Windows, offscreen, warm | mpv | | 389 ms |
| VM, X11, warm | VLC Software SP | 278-281 ms | 272-277 ms |
| VM, X11, warm | VLC Hardware | 282 ms | 271 ms |
| VM, X11, warm | mpv | | 275 ms |
| VM, X11, caches dropped, 3 runs | VLC Hardware | 512-550 ms | 478-510 ms |
| VM, X11, caches dropped, 3 runs | mpv | | 470-492 ms |
| `test_gpu`, X11, warm | mpv | | 375 ms |

Nothing is slower, and the small gain on VLC may be noise. Picking VLC doesn't look for anything
first: loading it is the looking. Picking mpv only looks, and loads nothing until a video opens.

Not measured: Windows cold, as there's no way here to empty its file cache, and macOS.

- **The first video's libmpv load, on the GUI thread:** VM 35 ms warm, 94 ms cold. `test_gpu` 75-90
  ms, caches can't be dropped in the container. Windows 7-11 ms warm. A hitch this short, once, isn't
  worth a thread. A slow disk would be worse, so look again if anyone notices.
- **Looking for a library that isn't there:** `find_library` goes on to run gcc and ld, 8 to 45 ms on
  the VM, against about 1 ms when found. So `media_libs` checks the usual folders first, and it only
  happens when something asks about a missing library: the Settings dialog in Stage 3, or a fallback.

Library cases, in the real app:

| Case | Windows | `test_gpu` (no VLC) | VM |
|---|---|---|---|
| mpv picked, not there: VLC stands in, says so once, pick kept | pass, offscreen so not played | | pass, plays |
| mpv picked, junk file: "libmpv won't load", VLC stands in | pass, offscreen so not played | | |
| VLC picked, not there: mpv stands in and plays | | pass | |
| VLC picked, won't load: mpv stands in and plays | pass | | |
| mpv picked, junk file, no VLC: says so, cells stay empty | | pass | |
| Neither, either pick: the box, exit code 1 | | pass, box answered by script | |
| Started on mpv, live to VLC and back | SP and Software | | all 4 VLC drivers, 2 rounds |
| Started on VLC Hardware or Software, live to mpv and back | | | pass |

**The fork abort isn't settled.** Started on mpv, the parent has libmpv, EGL and `libGLdispatch`
loaded when VLC forks 3 processes, and all 3 play. But forcing the abort's old cause, with
`QT_XCB_GL_INTEGRATION=xcb_glx`, doesn't abort on this VM either. So the VM can't reproduce it, and
passing here doesn't show it's safe on a real GPU. `test_gpu` has the GPU but no VLC. See 10.12. If it
does happen, those VLC processes die and their cells show an error. Starting the player on VLC
doesn't load mpv, so a restart gets out of it.

## Stage 3: Settings show what's unavailable

- [x] 3.1 `ComboField` takes `unavailable_choices`, value to reason. `ReasonComboBox` greys
  them out with the reason on the right. Clicks, arrow keys and the wheel skip them. No
  tooltip on the row after all: the reason is already there, in full
- [x] 3.2 Every decoder is listed, always. Grey: VLC Hardware on Wayland, a decoder whose
  library is missing, won't load or is too old. On macOS, Hardware with VLC stays listed and
  locks Processes to Single process. macOS only from unit tests
- [x] 3.3 You picked P1, and for the row first R2, then a bubble instead (see 3.11). Names are now `Hardware <VLC>`,
  `Hardware <MPV>` and so on, no version in the list. New driver `Software <MPV>` (`mpv_sw`, `hwdec=no`); `mpv` became
  `mpv_hw`, so a saved `mpv` goes back to the default and has to be picked again
- [x] 3.4 A saved pick that can't run is kept, shown as what actually runs, and the bubble says so
- [x] 3.5 `tests/test_pure_wayland.py`, `tests/test_video_driver_sw_sp.py` updated, new
  `tests/test_driver_choices.py`
- [x] 3.6 Settings search still finds greyed-out names
- [x] 3.7 Read when the dialog opens: 2-4 ms for looking, nothing at startup
- [x] 3.8 On MPV these grey out: `misc/vlc_options`, the hardware overlay fixes, the border fix,
  and the VLC log level (on another page, so through `SettingsForm.hold_off`). The section
  heading "VLC Options" stays dark: headings have no greyed state
- [ ] 3.9 **Showing:** done on Windows (libmpv there and not, light and dark) and `test_gpu` (no
  VLC, X11 and Wayland). Both libraries on Linux done on `test_gpu`, now VLC is installed there: all
  modes offered, no bubble, VLC's options on for VLC and greyed for MPV. macOS not run
- [x] 3.10 "SP" is gone. You picked B: the Decoder list has `Hardware <VLC>`, `Software <VLC>`,
  `Hardware <MPV>`, `Software <MPV>` and `Dummy`, and a Processes row has Multi-process or Single
  process. Both are one stored value, as before (`vlc_hw_sp` and so on), so saved settings stay
  as they are. On MPV or Dummy it locks on Single process. "Videos per process" shows only with
  Multi-process. README updated
- [x] 3.11 R2 read like a fault for someone just using VLC, so the note under the row is gone. You
  picked V2: a bubble below the Video Decoder block, only when something is unavailable. An "i"
  and "Some modes aren't available" normally; a warning sign and "MPV can't run. Playing with VLC
  for now." when the pick can't run. Each reason has one link, "How to fix", to a new README
  section, "When a mode isn't available". The link works once the README is on `master`

### Stage 3 results

- Hardware <MPV> and Software <MPV> really differ on `test_gpu`, real 1080p H.264: `vaapi`
  against `no`, on X11 and Wayland, and live both ways with videos open. The test clips are
  4:4:4, which VAAPI can't decode, so they say `no` on both.
- A stand-in is now the same kind as the pick: VLC Software with no VLC runs on Software <MPV>,
  Software <MPV> with no libmpv runs on VLC Software.
- Software <MPV> decodes on the CPU and still draws on the GPU, through OpenGL. See "What Software MPV
  uses" in `MPV_PERFORMANCE.md`.
- `mpv_basics` passes on both MPV drivers on Windows, and on Software <MPV> on `test_gpu`.
- `uv run pytest` 7807 passed, 7 skipped; `pytest -m real_app` on VLC 31 passed, 1 skipped,
  1 xfailed; ruff clean.

## Stage 4: Transport

- [x] 4.1 Seeks: exact or not, many in a row from a bar drag, `_seek_target` logic works
  with mpv's time
- [x] 4.2 `time_changed` throttled from `time-pos` to about what VLC sends. Measured: reading it 5
  times a second instead of every frame saves about 5% of the app's CPU, and plays no more
- [x] 4.3 Frame step, playback rate, Loop A-B, random start, saved position
- [x] 4.4 `loop-file=inf` against end-of-video actions, `is_loop_wrapped`, When Finished
- [x] 4.5 Loaded paused: first frame shows, seeks work while paused
- [x] 4.7 From the code review, not seen happen: `VideoDriverMpv.set_pause` compares with the last state mpv
  confirmed, not the last asked for, so a pause then an unpause in quick succession can leave it paused. Compare
  with what was last asked for
- [x] 4.6 Scenario `playback` runs on mpv too, bugs in `KNOWN_BUGS` until fixed

### Stage 4 results

- **Frame step was wrong, and only showed off 30 fps.** mpv goes to the first frame at or after a time, and
  the time was cut down to whole milliseconds, which puts it in the frame before. At 30 fps the two cancelled out.
  At 23.976 a step could skip a frame, and in an mkv Previous got stuck on one frame. Now the time is always in the
  frame on show, and a seek aims half a frame back, so it goes to the frame nearest the time.
- **A random start showed the video's first frame as loaded**, then jumped. The length is only known at `file-loaded`,
  when the first frame is already on its way. It's now picked in mpv's `on_preloaded` hook, before anything is
  decoded, and goes through `start` like a saved position. python-mpv doesn't have hooks, so they're called
  on its library directly.
- Exact seeks stay, for a bar drag too. 100 seeks in 3 s on a clip with keyframes about 4 s apart: 1080p60 shows 64
  frames on Hardware <MPV> and 41 on Software, 4K60 14 on Software, and all land on the right frame at once.
- A saved position doesn't become where the loop goes back to: `loop-file` goes round to 0.
- Checked against VLC, the same: a seek to the very end for each end action, stop then play, speed through a reload,
  on to the next file. A paused seek stays "on its way" until it plays, as on VLC, and it's harmless.
- Time reports go by the video's time, so 10 a second at 2x and 2.5 at 0.5x. Kept: a loop's end is then overshot by the
  same amount at any speed.
- Known and left: on a video under about 170 ms the end action never runs, since no time report gets through
  (VLC doesn't load the 0.5 s test clip here at all). At 240 fps and up a frame step would land a frame short, mpv
  allowing 5 ms either side of a seek; not tried.
- New scenario `mpv_transport`. `playback` now runs on both <MPV> drivers too.
- `mpv_transport` and `playback` pass on both <MPV> drivers on Windows, and on X11 and Wayland on `test_gpu`.

## Stage 5: View and pictures

- [x] 5.1 Rotate and flip. `video-rotate` for turns. Flips at paint time, since `vf` would
  knock out zero-copy
- [x] 5.2 Files that say how to turn: track `orientation` from `demux-rotation`, and the
  `dw`/`dh` trap
- [x] 5.3 Crop, crop shapes, aspect ratio, View Mode, anchors, shift past edges, SAR, list tags
- [x] 5.4 Sync view, zoom to cursor, zoom to selection
- [x] 5.5 Screenshots from the slot's pixels at a size worth saving: re-render at the picture's
  own size first, don't save a thumbnail of a small cell. `ScreenshotView` agrees
- [x] 5.6 Pause on live video keeps the last frame
- [x] 5.7 Real-app scenarios `aspect_ratio`, `crop_ratio`, `pixel_shape`, `list_shape` on mpv

### Stage 5 results

- **A paused video could lose its only frame, a bug from Stage 1.** mpv waits 200 ms for a frame to be rendered and
  then lets it go, saying nothing. With 16 cells opened paused, about half never finished loading, since no other
  frame was coming. The same could hit a paused seek on a busy grid. The renderer now tells when that may have
  happened (an update over 150 ms old with no frame in it) and draws again, mpv still having the frame. 16 and 36
  cells opened paused now all load, in 1.5 and 3 s.
- **Screenshots have all the picture's pixels.** Asked for one, the video is rendered once at the picture's own size,
  the frame is saved, and it goes back to the cell's size. From a 333x187 frame, a 1280x720 screenshot has its
  1-pixel detail, paused or playing. If no frame comes in 2 s it saves what's on show.
- Turned and flipped pictures: `video-rotate` for turns, painted flips, and a flip costs the same as any scaled paint
  (1.8 ms at 1080p, 9 ms at 4K). Transpose is a turn and a flip. A crop, a zoom and a screenshot all go by the picture
  as shown. The render size of a turned picture stopped at the wrong side's pixels: fixed.
- **Flips are the same on every driver, your call.** VLC flips the frame as stored, so on a file on its side, a phone
  video, Flip Horizontal comes out up and down on screen. MPV does the same, and VLC stays as it is. Every turn and flip
  of a file turned by nothing, 90, 180 and 270 was checked to come out the same on Software VLC and both <MPV> drivers,
  on screen and in a screenshot.
- `aspect_ratio`, `crop_ratio`, `pixel_shape` and `list_shape` passed on MPV with nothing to change. New scenario
  `mpv_view` for the rest: turns and flips on a plain file and one that turns itself, View Mode, anchors, shift past
  the edges, zoom to selection, zoom to cursor, sync, screenshots.
- `mpv_view` passes on both <MPV> drivers on Windows, and on X11 and Wayland on `test_gpu`. The four older scenarios
  pass on Windows on both drivers, and on Hardware on X11 and Wayland.
- 5.6 was tried on a video with no length, which the app takes as live. **A real live stream isn't seen as live yet**:
  see 9.2.

## Stage 6: Audio

- [x] 6.1 Mute, volume (scale matches VLC's), audio-only cells with their placeholder
- [x] 6.2 Track list and selection, language picks, default track, ids that survive reloads
- [x] 6.3 External audio: `audio-add`, which track came from which file
- [x] 6.4 Devices from `audio-device-list`, mapped to `AudioDevice`, pick survives a reload
- [x] 6.5 Channel mode (`audio-channels`, `af`), delay
- [x] 6.6 Scenarios `tracks`, `external_audio_jump` on mpv. The sound half of `tracks` runs inside `mpv_audio`. Its subtitle
  half and `external_audio_jump`, which turns on picking a subtitle, move to 7.6: that does nothing on <MPV> yet
- [x] 6.7 Linux audio outputs are limited to `pipewire,pulse,alsa` (see Stage 1 results). **JACK stays out, your call.**
  A JACK-only machine gets ALSA or silence. Checked on PulseAudio and PipeWire with null sinks, and with no sound server

### Stage 6 results

- **Picking a device could stop a video from loading.** Told a device while the sound was starting, mpv opened the
  default one and never said it was playing, so the cell sat there until it timed out. Tracks and the device now go in
  from the `on_preloaded` hook, before anything starts. That also means a track picked by language is the first one
  decoded, not a switch just after.
- **What comes out, measured.** Two null sinks on `test_gpu`, what they got read back, the same file through the app, on
  PulseAudio and PipeWire. Against VLC, on PulseAudio:

| | <MPV> | VLC |
|---|---|---|
| Volume 100 / 75 / 50, level of a tone | 0.125 / 0.053 / 0.016 | 0.125 / 0.053 / 0.015 (VLC's measured without the app) |
| Reversed, Left, Right on a stereo track | swapped, left in both, right in both | the same |
| Mono on a stereo track | 0.062 of each in both | the same |
| Stereo, Dolby Surround, Headphones on a stereo track | unchanged | the same |
| A one-channel track, in both ears | 0.125 | the same |

- **Fixed after the first round, your call to fix them first:**
  - One-channel tracks came out 3 dB down: mpv's mix and PipeWire each do that going from one channel to two. Such a track,
    and Mono, now go out on two channels at the right level. It follows a track switch and a file being added.
  - Headphones on a surround track now has VLC's room effect, with `sofalizer` and the file VLC does it with, set to VLC's
    levels: within 0.002 on all 12 readings, from Software VLC on Windows, in a file. It needs VLC's file beside libVLC, so with no
    VLC, or on Linux, where VLC has none either and plays the plain mix, it's the plain mix. A filter that won't start
    gives way to the plain mix, since it would leave no sound at all.
  - A track saved by number now also says where it comes among the sound tracks, which means the same on both drivers. Older
    playlists go by the number. 7.7 does the same for subtitles.
- **Fixed on VLC, on Linux:** a device picked went back to the default after a reload. VLC says it has the device, then its
  output opens on the default one, so for about 3 s of playing it's asked again whenever it says otherwise. And going back to the
  machine's own didn't move what was playing, so that now reloads. Seen on the sinks on all four VLC drivers on PulseAudio.
  The sound files that stopped coming up in the first round were my test swapping them too fast: fine at a person's pace.
- **Left as they are:**
  - Left and Right on a surround track: <MPV> takes that side of the stereo mix. VLC has no one answer to match, what it does
    differs by output.
  - **VLC on PipeWire:** moving one video's sound makes WirePlumber remember that device for every "Movie" stream, so it reaches
    other cells and outlives a restart, and "the machine's own" stays on it. <MPV> keeps each cell apart if nothing else has
    left a device remembered, but goes along with what VLC left. It's PipeWire's own memory, and any way round it would be a hack nobody has tried: left as it is.
  - Not tried: a track that says one channel and decodes to two, as some AAC could, would come out 3 dB up.
  - Disabling the only thing left, the sound of a song or the picture of a video with no sound: the menu and the cell say it's
    off while it plays on. It's the same on VLC, and it's the block and the frame that do it. Reloaded, it plays.
- Sound files: mp3, m4a, aac, flac, ac3, wav, ogg, oga, spx, mka and opus all make a sound on <MPV>, also after a seek. So
  the warning about files VLC can't play beside a video isn't shown on <MPV>. Names a URI has to spell out work, added
  and at load. A file that won't open leaves the video playing without it.
- A sound file longer than the video: the video's length counts, on both ways of adding it.
- Devices: a video moved to another sink plays there and stays there through a reload, seen on the sinks. The names are the
  same as VLC's, on Windows and PulseAudio, so a playlist's pick is found on either driver. On PipeWire <MPV> lists
  `pipewire/` devices and uses that output.
- **Reading the device list could silence a big grid.** An mpv that has read it stays connected to the sound server, a client more
  for each cell, and PulseAudio takes 64: of 80 cells 31 had sound, and nothing else could connect. It's now read by an mpv that
  does nothing else and closes (11 ms, 91 the first time), shared for 5 s. 40 cells: 40 clients, all with sound, loaded in 1.2 s.
- Delay: +1 s came out later on the sound server, -1 s earlier in a file written by mpv.
- Picture off and on, playing and paused, through a reload and for the tray. Both off is refused, here as in VLC.
- Rig traps: on an idle PulseAudio null sink, sound starts about 1.6 s late, on the old commit as well, and `mpv_transport` fails
  unless a silent `pacat` keeps it awake. On PipeWire, `parec` starts too late to catch much (`pw-record` is fine), and
  WirePlumber's saved state decides where a stream starts, so clear it between runs.
- `mpv_audio` passes on both <MPV> drivers on Windows, on X11 and Wayland on `test_gpu` with PulseAudio, offscreen with PipeWire, and
  with no sound server (Hardware on X11, Software on Wayland). `mpv_transport`, `playback` and `mpv_view` pass with PulseAudio,
  `mpv_transport` with PipeWire.
- Windows is checked by mpv's own word and by writing to a file, with everything muted: nobody has heard this stage yet.

## Stage 7: Subtitles

- [x] 7.1 Track list, selection, language, default and forced, no subtitle
- [x] 7.2 External files, `.idx`/`.sub`, what happens when a new file reloads tracks
- [x] 7.3 Delay, encoding (`sub-codepage`)
- [x] 7.4 Style settings mapped from `SUBTITLE_STYLE_SETTINGS`, applied live
- [x] 7.5 Size and sharpness: they stay on show and the same size on screen, see below
- [x] 7.6 Scenarios `tracks` whole and `external_audio_jump` on mpv, in `ALSO_ON_MPV`
- [x] 7.7 A subtitle saved by number also says where it comes among them, as `AudioTrackId` does

### Stage 7 results

Scenario `mpv_subtitles` is new. It passes on both MPV drivers on Windows (libmpv 0.41) and on X11 and Wayland
(libmpv 0.40), with `tracks` and `external_audio_jump` on MPV too. VLC's bug in `external_audio_jump` doesn't happen on MPV.

**Older libmpv.** It works back to 0.35. What each refuses was read from the real one, on Debian 12 and Ubuntu 24.04 in a chroot on
`test_gpu`, and comes from `option_info` and `profile_list` at the start (`SubtitleLimits`). A refused option gives no error and the
line just stays as it was, but the `fast` profile asked for at the start would have stopped 0.35 from playing at all.

| | 0.35 (Debian 12) | 0.37 (Ubuntu 24.04) | 0.40 (Debian 13) | 0.41 dev (Windows) |
| --- | --- | --- | --- | --- |
| `fast` profile | none, defaults are it but for dither and HDR peaks | yes | yes | yes |
| Outline options | `sub-border-*` | `sub-border-*` | `sub-outline-*` | `sub-outline-*` |
| `sub-border-style` | none | none | yes | yes |
| Largest `sub-margin-x` | 300 | 300 | 300 | no limit |
| `sub-pos` | whole numbers | any | any | any |

Default, shadow, box, outline and raised lines look the same on all four, at the same heights. `sub-back-color` is empty unless the
box is on: it's all that 0.35 and 0.37 go by for a box, and on 0.40 a colour with no box showed where the shadow goes.
`mpv_subtitles`, `tracks`, `external_audio_jump` and `mpv_audio` pass on 0.35, and `mpv_subtitles`, `mpv_audio` and `mpv_view` on 0.37.
`mpv_view` and the flips in `mpv_subtitles` don't run on 0.35: Debian 12's ffmpeg can't make their turned clips.

**Left:** up to 0.40, zoomed in far enough, the side margin stops at 300 and a line can be wider than what's on show. On 0.35 raising
goes by whole percents of the height.

**What it looks like, measured against VLC on a black clip.** `sub-font-size=50` gives the same width and height of text
as VLC within 1%, on Windows and Linux. The bottom gap is mpv's own 34, the same as VLC Hardware (4.4% of the height).
VLC Software has it at 7%, and more on small videos. Same font, same bold, colours, outline, shadow and box. VLC's text
sits a little left of centre, and mpv's is centred. `sub-scale` also grows `sub-margin-x` and `-y`, so those are divided by it.

Raising them (`subtitles/margin`) goes by the picture's pixels, or the screen's for a picture smaller than its cell, as VLC
Hardware does in all 4 cases measured. It goes through `sub-pos`, the one thing that reaches ASS as well. Nothing else in
the settings reaches ASS on either driver, for which `sub-ass-override=yes`.

**Style changes as it plays.** No reload on MPV, where VLC opens every video again.

**Three things VLC does and mpv's frame doesn't, each found by comparing pictures:**

- **Flips would mirror the text**, flips being painted over what mpv drew. While a subtitle shows on a flipped video, mpv flips
  the picture itself, by a shader (`_FLIP_SHADER`), and painting takes over when none does. Not always a shader: any shader takes
  mpv off its fast path. 4 x 1080p60 flipped on the i7-4790K's GPU: 0 frames in 4800 dropped with no flip, about 650 painted,
  about 2350 by shader. A shader is a file mpv has to read, so it's written to the cache folder. `memory://` doesn't work.
  Switching can show one frame the wrong way round.
- **Fill and zoom would cut them off**, with mpv drawing them at the bottom of a frame the view then cuts. Fill is the default, so
  in a wide cell there would be none at all. As on VLC Hardware, they now stay at the bottom of what's on show, the same size on
  screen (`sub-pos` and `sub-scale`, `sub-margin-x` for what's cut off the sides). VLC Software does cut them off.
  **Left:** panned sideways while zoomed, the line stays centred on the whole picture and can go off the side. And the frame stops at the
  picture's own size, so a line in a zoomed picture is a little soft. `video-crop` would solve both, but it means mpv drawing only what's
  on show, and a pan then waits for a new frame: not done.
- **A small picture blurs them**, the frame stopping at the picture's own size. While one shows, the frame goes up to the cell's.

**No seek to show a line.** VLC needs one (`_nudge_into_view`), which costs a hitch. mpv shows a line picked part way through it in
about 0.1 s, playing or paused, in a track or a file, so `is_late_with_subtitles` leaves it out.

**Files.** Asked for an `.idx` by its URI, mpv on Windows doesn't find its `.sub`, so they go by path. Each track says which file it
came from (`external-filename`), so two files with the same name and different extensions are told apart, which VLC's
names can't do. Left alone, mpv takes a file over the track the file marks, so `sid` is always said.

| File | MPV | VLC |
|---|---|---|
| srt, vtt, ass, ssa, sub (MicroDVD), smi, sami, mpl2, pjs, aqt, jss, rt, stl, txt, utf, mks, idx | reads them | not all compared |
| ttml, dfxp, dks | doesn't, the video plays on | ttml and dks read |
| psb, usf | doesn't, the video plays on | shows nothing either |
| UTF-16 with a mark at the start | **the first letter of a line is wrong** if it isn't Latin | reads it |
| UTF-16 with no mark | doesn't open it, even with the set named | not compared |
| cdg, scc, smil, tt | not tried, no file to hand | not tried |

Every other character set in the list reads correctly. The 3 of seven bits (ISO-2022) look like UTF-8, which mpv tries first, so they go
with a `+`. Nothing named, mpv worked out Windows-1251, Windows-1252 and Shift_JIS by itself.

**Also left:**

- A file with several tracks added while playing: mpv forgets their languages, so the menu numbers them until the next load.
- Turned on its side, the line is bigger than VLC's and wraps: mpv goes by the height of the frame.
- A long word in a narrow Fill cell runs off the sides, on VLC too at a smaller size.
- The character set also reaches ASS here, where it doesn't on VLC.
- Not run: macOS. VLC Hardware on Windows not compared, only on Linux. Nobody has looked at this on a real screen: I read screenshots
  and pixels.

## Stage 8: Everything that hangs off time

- [x] 8.1 Deinterlacing: map modes to `vf`/`deinterlace`. **Retest `hwdec_extra_frames=0`**,
  flagged as unsafe to assume in the handoff
- [x] 8.2 Chapters from `chapter-list`, `chapters_changed`
- [x] 8.3 Bookmarks, SponsorBlock: run their scenarios, fix timing assumptions written for VLC
- [x] 8.4 Scenario `marks`, `navigation` on mpv

### Stage 8 results

Scenario `mpv_deinterlace` is new, and `marks` and `navigation` now also run on MPV. Bookmarks and SponsorBlock needed no
changes: nothing in them turned out to depend on VLC's timing. Chapters come from `chapter-list`, and any that change after
the load go on through `chapters_changed`.

**Deinterlacing.** A bar moving fast, made interlaced, and rows compared with the next: 5100 is combed and 0 is clean. VLC Software
gives the same on the same clip but for Phosphor, combed on purpose there, and Film, which stays combed on this clip as it isn't film. MPV's
Film isn't reliably either way on it. VLC's Film hasn't been run on a film clip.

| Setting | On MPV | Pictures a second, on 30 fps |
| --- | --- | --- |
| Automatic | `deinterlace=auto` from 0.40. Before that the app asks mpv for `video-frame-info/interlaced`, and it's On once a frame says so | 60 if the file says interlaced, else 30 |
| On, mode Auto | `deinterlace=yes`, mpv's own choice. Frames stay on the GPU: `hwdec-current` stays `nvdec` or `vaapi` | 60 (VLC's stand-in here is X, at 30) |
| Off | nothing | 30 |
| Discard, Blend, Mean | `field`, `convolution`, `scale` down and up, all back to full height | 30 |
| Bob, Linear | `separatefields`, then `scale` up | 60 |
| Yadif, Yadif (2x) | `yadif` | 30, 60 |
| X | `bwdif`, one picture per frame. **Not what VLC does**, mpv has nothing like it | 30 |
| Phosphor | `bwdif`, one picture per field. **Not what VLC does**: it doesn't simulate a CRT | 60 |
| Film NTSC (IVTC) | `fieldmatch=combmatch=full,yadif=deint=interlaced,decimate` | 24 |

Going back to Automatic from the menu takes no reload on MPV, where VLC has to reopen the video. A video taking on new defaults from the Playlist window
can still reload once: that goes by `is_reopen_needed`, which is VLC's rule. Harmless, and left.

**What's particular to the filters.** Each trap here was measured:

- Frames still on the GPU stop a filter for good, and only a log line says so. So a mode by name switches decoding to `auto-copy`
  and the filter only goes in once `hwdec-current` says so. The other way round, the filter leaves first. The picture stops for
  0.3-1 s at the switch. A saved mode starts in `auto-copy` with no switch.
- A filter this libmpv hasn't got ends the file if it's there as the file opens, so filters go in at `file-loaded`. `set vf` then says
  nothing and leaves the dead filter in the list, where `vf set` gives an error, on all of 0.35, 0.37, 0.40 and 0.41. A refused mode goes to
  mpv's own, and stays refused for the whole run, as it's true of the libmpv: later videos start on the right decoder. A libmpv built without
  the GPL parts has no `fieldmatch`, for one. Forced in the scenario with a filter that doesn't exist.
- The decoder changing twice in a moment, as it does when a mode's refused, stopped the picture until the next keyframe, 8 s here, in 2
  runs of 16. So every decoder change on an open file seeks to where it is. After that, 32 refusals and 20 quick switches by hand: 0.77 s at most.
- `pp`, the plain way to Blend, is gone from FFmpeg 8.
- Plain `fieldmatch` left 46 of 120 sampled frames combed on hardware decoding, and none with `combmatch=full`.

**`hwdec_extra_frames=0` holds.** 1080i50 H.264, seeking and pausing through 12 rounds: 4 and 9 cells on NVDEC, 4 and 9 on VAAPI on
a real X11. No errors, and the decoder never left the GPU. I didn't hash the frames as the handoff did, so that's no errors and
no fallback, not every frame proven right. MPEG-2 decodes in software on both machines under `hwdec=auto`.

- Reading `video-frame-info` while a video closes crashed the app: 6 runs of 24 on 0.35 and 0.37, none before this stage. python-mpv's `terminate()` drops the
  handle at once, and the event thread goes on being told the time, so the read goes to libmpv with no handle. Now nothing reads it: mpv is asked with `expand-text`, which waits on nothing, and everything sent to mpv
  takes one lock that terminating waits for. 0 of 65 after, 15 of those on 0.40 with a mode by name. Those 15 weren't run before the fix. **Not changed:** the reads at load
  (`_read_media`, `_on_preloaded`) only check the closing flag, so could meet the same thing in a far smaller window. Not seen. For 10.1.

**After `/code-review`.** Fixed:

- Going to Automatic could lose the filter. A frame that's been through a deinterlacer, mpv's own or a filter, never says it's interlaced, on 0.41 and whichever mode, so
  On to Automatic took the filter off. Paused, the picture stayed combed; Off to Automatic did too, as nothing asked. Now it asks when the setting changes and at each restart,
  which is where a paused video with the filter just off comes back. Playing, the filter comes off and goes back: the picture stops 0.25-0.29 s, 24 runs of 24 clean.
- Two threads working out what to tell mpv could cross and leave a filter on a video set to Off: the same lock. Read in the code, not seen.
- A failing `vf set` counted a mode as refused for the whole run even when clearing the filter or closing. Read in the code, not seen.
- Chapters changing after the load split `Media` into copies, and track choices stopped reaching the driver. Now set in place, on VLC as well. Read in the code, not seen.
- The scenario's size check read `video-params`, from before the filters, so could never fail. It now reads `video-out-params`. Discard on 361 rows gives 362 and Mean 360, and
  the filters that halve the height leave mpv thinking the pixels are twice as wide, measured. The app draws by the size from before the filters, so neither shows.

Not fixed, on purpose or for now:

- **A filter going in just as the decoder comes back from the GPU, not fixed.** Yadif, Off, Yadif quickly could give a filter GPU frames, which stops it for good. I couldn't make it happen:
  0 of 95 on NVDEC, gaps of 0 to 400 ms. Waiting for mpv to report the decoder first made things worse: on a codec with no hardware (FFV1) it stayed combed in 44 of 44, as a report of
  None isn't sure to be followed by anything, so that was taken out. With it out, 0 of 44 on FFV1.
- **Bob and Linear on an odd height do nothing.** `separatefields` won't start, and only a log line says so, while the mode stays ticked. Interlaced video with an odd height is very unusual, and
  it would have to apply to that one video, not the whole run. For 10.1.
- **Paused within a moment of picking a mode**, the picture on show can be one from before the filter, until it plays or steps. Picked by script right before pausing: seen in 9 runs of
  12 on 0.37 in software, and 5 of 6 with Yadif on 0.40 on Wayland. Pause first and it's fine. It's how mpv treats a filter changing while playing.

**Run on:** Windows 0.41, both drivers: everything in the real-app suite. `test_gpu` 0.40 real X11 and Wayland with zero-copy `vaapi`, and offscreen in software:
`mpv_deinterlace`, `marks`, `navigation`. 0.35 and 0.37 in the chroots, software only: the same three. VLC on Linux: `marks` on both, `navigation` on Hardware.

**Left:**

- Made clips only. No real broadcast recording, DVD or film rip has been through this, and PAFF or MBAFF H.264 not at all.
- 9 cells of 1080i with On on the i7-4790K's GPU play at about half speed, though 9 with it Off and 4 with it On keep up. Automatic should do the
  same to an interlaced file, not measured. `estimated-vf-fps` said 50 throughout, so it doesn't show this. Speed at 9 cells on NVDEC not measured.
- Automatic on 0.35 and 0.37 can show combed frames until the first report of the time, 200 ms at most by the code, not measured. It asks about the frame
  every 200 ms for as long as a video is open and hasn't said interlaced. The core's share of that hasn't been measured; the read it replaced took about 70 us. The same goes
  for Automatic with a mode by name on any libmpv, which also changes decoder again after each reload of an interlaced file.
- VLC Hardware not compared: on Windows a screenshot offscreen hadn't finished after 100 s, and on Linux it wasn't tried.
- AMD and macOS not run. Nobody has looked at this on a real screen: I read pixels.

## Stage 9: Streams, errors, recovery

- [x] 9.1 `MediaInput` with HTTP headers and the stream proxy. A list's user agent and referrer reach the server, and any other header goes along too, which VLC can't do. `ytdl=no` stays. `is_adaptive` means VLC's demuxer, so no seek retries on MPV. Cookies go through the proxy as they do on VLC; no scenario of its own
- [x] 9.2 Live: no length, pause as stop, reconnects, seeks and speed ignored. The Stage 5 finding no longer shows: a live HLS link is seen as live, no length, and doesn't go round
- [x] 9.3 Sizes and dubs: `streams`, `dubs`, held to on MPV from now on
- [x] 9.4 Errors: what mpv said is told, tagged MPV, with `player/video_init_timeout` and no GL context reporting. An mpv crash takes the app with it, as there's only the one process: nothing to catch it with
- [x] 9.5 `video_block_recovery`, When Video Fails, list cells moving on: `stream_errors`
- [x] 9.6 File lengths with no VLC are read by libmpv in the same separate process. Done with it: 10.20
- [x] 9.7 "Log level (MPV)" under Logging levels, greyed out unless on MPV, off by default, applied with no reload. `hwdec-current` falling back goes in the log at Info

### Stage 9 results

You said YouTube was broken on MPV. It opened and played when I tried it, so this is what I found once I did more with it. I don't know which of these you ran into:

- **Every seek stopped the video 5.6-6 s.** It was the same picture and sound behind one demuxer that VLC is given as one playlist. Not the proxy: straight from YouTube it was the same, and mpv's own EDL, how its YouTube support does it, was just as slow. With the sound opened as an audio file, the same stream took 0.25-0.8 s, within microseconds of the picture. Why one demuxer costs that I don't know: nothing is read for 3.6 s. It only happens on YouTube, 0.05 s from a server here, so no local test can guard it.
- **On Debian 12 (0.35, FFmpeg 5.1.9) nothing the proxy serves as a playlist played past its first segment.** FFmpeg turns down a playlist's segments if their links look like no file, as the proxy's do. mpv then reads one segment as if it were the video and says it plays. Nothing tested this until `streams` was told to wait past it.
- **On 0.40 with FFmpeg 7.1 most seeks went back to the start,** 6 of 9 past what had been read, from a server here as well. The playlist made of a fragmented file for VLC is the cause. Opened as the file it is, 9 of 9, and in a third to a fifth of the time: 0.40 s against 1.06-2.06 s.
- **With that, seeking back after a seek into the cache stopped the video 25 s or more,** on real YouTube only. mpv goes on from the end of what's cached a fragment at a time, and the next seek waits for it. `demuxer-seekable-cache=no` ends that: 18 of 18 landed, against 10 of 18. Only where part of it is a fragmented file: on HLS of TS segments the same option leaves the sound up to 0.8 s behind after a seek, catching up over 6 s, where on YouTube's files and YouTube's HLS with a file for the sound it was 0.02 s, then 0.001 s.

So on MPV a stream goes in as it comes: picture and sound as two links, a fragmented file as that file.

| YouTube, 360p or 720p, seek to 0.2-0.5 s past it, one video | Before | Now |
|---|---|---|
| Windows, 0.41, forward | 5.6-6 s | 0.4-1.2 s |
| Windows, 0.41, a long way back | 5.6-7 s | 1.9-2.9 s, 7 s at the worst, to 20 s from 600 s |
| Linux, 0.40, past what's been read | back to the start | 0.6-1.2 s |
| Linux, 0.40, a long way back | back to the start | 1.7-3.1 s |
| Picking another size | | 0.8-1.1 s |
| Round at the end, from 3 s before it | | about 1 s stopped |

VLC, for comparison: about 2 s, up to 5 s, but it lands short of where it was asked. At 2160p60 AV1 on Windows it was 1.6-2.8 s with four videos open. That was measured before the file route and isn't measured since.

**Found on VLC as well, both from the proxy:**

- A live stream that went away froze for good, with no message, even once it came back. A response with no length can only say it's over by closing, and the proxy kept the connection open. Now it closes. Both drivers then try again and say why: "Not found" for a 404. **This changes VLC.** `live` passes on both.
- The proxy's error handling itself crashed on its own "No data returned from stream", so the failure was never noted.

**Other traps found:**

- mpv's log comes after its events. An error read at once had no reason with it, so a failure waits 0.1 s for it.
- An mp4 with its index at the end, from a server that can't seek, hung until the 120 s timeout: mpv says playback restarted with no frame, then stays open at the end. It's now "Video stopped before initialization", as on VLC, at once.
- `keep-open` pauses at the end, and the block saved that with the video, so a reload after a failure came back paused. `keep-open-pause=no`.
- A live stream paused, as on VLC, is let go of. Paused for real it went on downloading and came back behind. Stopped, mpv only has black to draw, so `render_size` holds the picture until it plays.
  Audio and subtitle files added to it are opened again with it, its tracks are read again, and if it doesn't play within `player/video_init_timeout` it says
  "Buffering timeout", as VLC does. Unit tests only.
- Only the proxy's links have FFmpeg's segment check turned off. A link mpv opens itself keeps it.
- File lengths by libmpv go by mpv's number for each file asked for, so a file given up on can't answer for the next. Counting the files mpv started didn't do:
  one let go of before it starts never does, and every file after came back with no length.

**Run on:** Windows, 0.41: the whole real-app suite, with `live`, `stream_errors`, `streams` and `dubs` now held to on both MPV drivers too, and `mpv_streams` new. `test_gpu`: 0.40 on real X11 and Wayland with zero-copy `vaapi` and offscreen in software, and 0.35 and 0.37 in the chroots: `mpv_streams`, `stream_errors`, `live`, `streams`, `dubs`, `marks`, `navigation`, `playback`, `mpv_transport`. VLC, Windows: `live` and `stream_errors` as well as the rest. Real YouTube: one video and four cells with a live one beside them on Windows, one video on Linux; no AMD and no VLC on Linux.

### Seeking: exact or fast

You decided: a setting, "Seeking" under Video Decoder, greyed out unless on MPV, as mpv.net has it: Exact, Exact for bookmarks and chapters
(the default, as mpv.net's and mpv's own), and Fast. Fast lands on a key frame. Exact seeks decode from the key frame to the time: 2160p60 AV1 on the
CPU took 0.5-5.5 s, against 0.2-1.1 s on the key frame, which is about what VLC does by landing short.

- Each seek says what it's for (`SeekAim`): by hand (the bar, seek keys, a random place), a mark (a bookmark, a chapter, a time typed in), or always
  exact: frame steps, the other videos following one with Seek synced (and the one followed, so they agree), loops, SponsorBlock skips, a place put back.
  The [ALL] seeks are exact, as the others following one are. VLC's drivers take it and have no use for it.
- A fast seek lands on the key frame at or before it, short as VLC lands, never past the end. So one forwards could go back: 3 s on from 19 s, a key
  frame every 6 s, was 18 s, and pressed again, 18 s again. One forwards that lands where it was or behind goes on exactly, so it costs what an exact one
  does only where there's no key frame between. The player looks at where it landed on mpv's playback restart, and only for the last seek mpv has taken:
  one made before can land after the next is made, and was taken for it.
- Tried first and dropped: by so much (`relative+keyframes`), which mpv takes to the key frame past it. With none after it, before the end, mpv went to the
  start: on a 20 s clip with key frames at 0 and 10 s, 50% from 1.48 s, counted from the 1.40 s last reported, aimed past 10 s and went to 0 s.
- What the scenarios held to: `mpv_deinterlace` now takes the middle as from 8 s, its clip's key frame being at 8.3 s.
- 4K 60 fps H.264, a key frame every 4 s, on this machine: exact 0.33-0.39 s in software and 1.41-1.53 s with `hwdec=auto`, fast 0.02-0.09 s. A test
  pattern decodes far more easily than a film. YouTube itself not measured since.
- `mpv_seeking`: where each lands, by the setting, on 0.35, 0.37, 0.40 and 0.41.

**Left:**

- A long way back can take 7 s, about the same as the playlist did on Windows and more than VLC's 2-5 s. mpv works through fragments to get there: not looked into further.
- **YouTube turned me down with 429 after a long run of testing, on both machines,** for a while, so go easy with these. It's what the scenarios here are for. It cleared by itself.
- A stream's sound whose link fails leaves the video playing silent, with only a log line. Read in the code, not tried.
- On Linux yt-dlp had no JavaScript runtime here, so it was given other formats than Windows. Not run with one.
- Not run: AMD, macOS, cookies on MPV, DASH live. Nobody has looked at this on a real screen or listened: I read pixels, `avsync` and the track list.

## Stage 10: Hardening

- [ ] 10.1 Long churn on readback in the real driver, including a native memory checker if
  one can be run. Handoff open question 3
- [ ] 10.2 Real window drags on Windows: port `drag_probe.py` to the app, 0 backward moves.
  This one moves the mouse, so it runs when you say
- [ ] 10.3 By hand on a screen with X11 and Linux, if you have such a machine. Handoff open
  question 1
- [ ] 10.4 AMD on Windows and any other GPU we can reach. HEVC and 10-bit through VAAPI needs
  a newer chip than `test_gpu`
- [ ] 10.5 The Linux `mallopt` arena limit: decide on applying it only when mpv is in use
- [ ] 10.6 `churn.py`'s 30 KB per close on X11: check it's bounded
- [ ] 10.7 GLES: `GL_BGRA` needs desktop GL as written, read RGBA where it's missing
- [ ] 10.8 Render thread stall watchdog: only if something has needed it by then
- [x] 10.9 Cells not on show, as in Single Mode, still render and read back every frame. Render
  them small or not at all. Done: a hidden cell's frames are taken with `skip_rendering`, so it
  plays on at its pace (taking none, mpv waits 200 ms on each), and the last one taken is drawn as
  it's shown again, about 50 ms later. Not before its first frame, as that's what says it has
  loaded, and not while a screenshot waits on one. `mpv_hidden_cells`: 3 cells, 4 s in Single
  Mode, 100 draws for the one on show and 0 for the others, on both MPV drivers
- [ ] 10.10 `load_scripts=no` leaves mpv's built-in scripts running, about 5 Lua threads per
  video. They cost no measured memory, but each has threads: check whether to turn them off
- [ ] 10.11 **Your decision:** a low VRAM option (`-copy` or software for new videos when over
  budget), and an mpv decoder setting
- [x] 10.12 mpv to VLC Hardware live, on a real GPU with X11. Passes on `test_gpu`, 2 rounds, and the
  pass counts: with the old cause forced, decoder processes do die with signal 6 there. NVIDIA on
  Linux not run. See `MPV_PERFORMANCE.md`
- [x] 10.13 Skip frames, with `vd-lavc-skipframe=nonref`: the setting "Skip frames to play more videos"
  on the Video Decoder page, off by default, for both MPV drivers, applied with no reload. 16x1080p60
  goes from 7 to 31 fps. It costs half the frames at any load, 4x1080p60 goes from 60 to 31. No use on
  video with no B frames. Automatic left out: it would need ignoring the startup burst, a way back,
  and a way to hide the pause: each switch stops a video for about a third of a second
- [ ] 10.16 **To run overnight, by you.** All of it, about 4.5 hours, from Git Bash at the repo root on Windows:
  `GP_LIBMPV_PATH='C:\path\to\libmpv-2.dll' bash tests/real_app/bench/overnight.sh`. It starts `test_gpu` too. The PC has
  to stay awake, your screen stays clear, and changing virtual desktop stops the Windows part. Results in
  `build/bench/overnight` and on `test_gpu` in `/opt/bench_out/overnight`. Then ask me to read them into
  `MPV_PERFORMANCE.md`. What it answers:
  - Crashes, hangs and leaks: churn and soak (10.1), the reason multi-process stays off the table. A 1-minute churn on
    `test_gpu` left about 1 GB in use with every video closed, up from 80 MB, and 30 s on Windows about 320 MB, up from 60.
    Leak, or an allocator holding on to it? Not known yet
  - Real grids: different files in every cell, 10-bit HEVC, phone clips, 2 containers. So far it was always one file repeated
  - The limits again, 3 runs each, as most points are one run, and VLC's freeze at 36 cells on both machines
  - On Windows what the first run didn't reach, and on Windows the hitch at switching frame skipping
  - Not in it: audio (Stage 6), other GPUs and macOS. Nor the compositor's share on Windows, which takes a window on a screen
- [ ] 10.17 **Later, your call (2026-11-06):** Software <MPV> becomes fully software, as people expect software not to touch
  the GPU at all. Today it's `hwdec=no` and still draws through OpenGL.
  - Draw with libmpv's own software render API rather than OpenGL. Not tried yet: measure CPU, scaling quality and how
    many videos it plays against today's mode
  - Today's mode, CPU decoding drawn on the GPU, moves to a flag on Hardware <MPV>, something like "Decode on the CPU". It plays
    the most on a strong CPU, so it stays available
  - Saved `mpv_sw` settings: decide whether they become the new mode or Hardware <MPV> with the flag on
  - A stand-in for Software VLC with no VLC should then be the new mode (see Stage 3 results)
- [x] 10.18 A window minimized or in the tray rendered and read back every frame of every video. Done as 10.9, your call (2026-11-08), with no
  setting: nothing on screen changes, as a minimized window's preview is the picture from before. The cell goes by its own show and hide,
  and by the window's `away_changed`, as coming back it can be shown before the window says it's no longer minimized. `mpv_hidden_cells`:
  minimized and in the tray, 0 draws in 4 s, played at full pace, drawn again 50 ms after. On the offscreen platform only: a real window
  on Windows and Linux not tried
- [ ] 10.19 Small savings the review found, by reckoning and not yet measured, for when the CPU matters more than the code: each render round visits
  every video, not just those with a frame (at most about 4% of a core at 64 cells); the placement is worked out on each paint (about 1% at 9
  cells). 4.2: the time is still sent by mpv each frame, so the saving of `notime` isn't had yet
- [x] 10.20 Done in 9.6. File lengths in lists are read by VLC. With only libmpv there, lists show none. libmpv could read them too, in a
  process of its own as now
- [x] 10.14 Don't fill the cell black before drawing a picture that covers it: app CPU 61% to 47% at
  1x1080p. Applies to VLC's software drivers too, so test those. Done: only the bars beside the
  picture are filled, reaching a pixel under its edge so a pixel it only partly covers at a screen
  scale of 1.25 or 1.5 is never left unpainted. One 1080p cell, two runs each, painting before and
  after: `test_gpu` X11, Hardware MPV 4.2/3.7 to 2.8/2.9 ms, GUI thread 32/29% to 24/25%; Software
  MPV 3.5/3.3 to 2.5/2.4 ms; Software VLC SP 6.7/6.3 to 6.1/5.6 ms. Windows, a real window on the
  other desktop: 0.44/0.53 to 0.42/0.41 ms, too little to show in the app's CPU
- [ ] 10.15 Cached render parameters instead of python-mpv building them per frame, about 2-5% CPU

## Stage 11: macOS

- [ ] 11.1 Spike on `test_macos`: GL context, render API, VideoToolbox interop, readback
- [ ] 11.2 Same Stage 1 checks
- [ ] 11.3 Own CGL context only if the Qt one causes trouble

## Stage 12: Packaging and release

- [ ] 12.1 **Your decision, later (you said so on 2026-11-06):** bundle libmpv or not, per platform. Windows has no system
  libmpv and no standard installer for it, so unbundled means a manual DLL out of a 7z. The
  DLL here is 117 MB, a smaller LGPL build may do. Decide before the `Get MPV` link is final:
  mpv.io's normal Windows download doesn't have the DLL
- [ ] 12.2 PyInstaller, AppImage, Flatpak, Snap, Chocolatey as decided. Fail loudly, keep the
  existing tools. Flatpak and Snap can't see a system libmpv, so the README's "How to fix" won't
  work there unless they ship it: check, and say so in the README
- [ ] 12.3 About box, licences (python-mpv and libmpv are GPL or LGPL, compatible)
- [ ] 12.4 Real-app job in CI for mpv, if the runners can get a GL context
- [ ] 12.5 README, CHANGELOG. Short trap list in `AGENTS.md`, rules only
- [ ] 12.6 Remove this file, or keep it as you like

---

## Log

Newest first. What was finished and seen working, and anything that changed the plan.

- 2026-11-08: Stage 9 built, see Stage 9 results. YouTube on MPV seeks in about a second, not 6, and no longer goes back to the start on 0.40 or stops after the first segment on 0.35: streams go to mpv as they come, not as made for VLC. Two proxy bugs found on the way, fixed for VLC too: a live stream that went away froze for good.
- 2026-11-07: Code review of Stage 8: going to Automatic no longer loses the filter, and three fixes from reading the code. One suspected fault couldn't be made to happen and its fix made things worse, so it's out. See Stage 8 results.
- 2026-11-07: Stage 8 committed, see Stage 8 results. All deinterlace modes and chapters work on MPV, from libmpv 0.35 up. Bookmarks and
  SponsorBlock needed nothing. X and Phosphor are stand-ins. `hwdec_extra_frames=0` holds.
- 2026-11-07: Stage 7 committed, see Stage 7 results. Works on libmpv from 0.35 up. Style changes with no reload, and lines stay on show in Fill and zoom. Flips stay painted, with a shader only while a subtitle shows.
- 2026-11-07: Stage 6 built and committed, see Stage 6 results. Tracks and the device now go in before mpv starts anything.
  Output measured against VLC. JACK stays out, your call. Two device bugs on VLC on Linux fixed along the way.
- 2026-11-07: Stage 5 built, see Stage 5 results. It turned up a Stage 1 bug, a paused video losing its only frame on a
  busy grid, and that live streams aren't seen as live on MPV yet, now under 9.2.
- 2026-11-06: Stage 4 built, see Stage 4 results: frame step and random start fixed, the rest held up. `mpv_transport` and `playback` pass on
  both <MPV> drivers on Windows, and on X11 and Wayland on `test_gpu`.
- 2026-11-06: Stages 1-3, the frame-skip setting, the bench and these docs committed on `mpv`. The docs moved to `docs/`.
- 2026-11-06: Code review fixes. Reproduced first: on Software <MPV> a cell could report loaded with a black picture (3 of 4 cells
  on Windows, playing), as mpv was rendered before it had a frame. One video failing to render no longer stops the render
  thread for all of them. A size change while playing, a random start with no length, a live stream with a duration and an audio-only
  stream with a picture track are fixed, the last three by reading the code, as VLC does them. New: 4.7, 10.20.
- 2026-11-06: Cleanup pass over Stages 1-3 (`/simplify`). No behaviour meant to change, except a combo's list now has the screen cap on the
  Decoder popup too. Left as they are, for a decision: the one stored driver value (your pick, 3.10), the second search for libVLC, and VLC loading at
  startup. New: 10.18, 10.19.
- 2026-11-06: Fully software MPV put down for later, with CPU decoding as a flag on Hardware <MPV>, your call: 10.17.
- 2026-11-06: Your hand test looks OK so far, 1.13 ticked. Both libraries on Linux checked on `test_gpu` rather than
  the VM. Software <MPV> measured against Hardware: the decoder stays idle, the GPU still draws.
- 2026-11-06: Long checks put off to run overnight, 10.16, with one command to start them. Before stopping: Hardware VLC on Windows
  measured at last, in a real window on the other desktop, level with MPV on how much plays and cheaper, VRAM above all. Switching
  frame skipping stops a video for about a third of a second.
- 2026-11-06: 10.13 built as a setting, your call: a switch on the Video Decoder page. The bench moved to
  `tests/real_app/bench` with its own README, and works on `test_gpu` and Windows.
- 2026-11-06: Load tests of VLC against MPV on `test_gpu` and Windows, see `MPV_PERFORMANCE.md`. The
  decoder is the limit, not the GIL, so no multi-process mode for MPV. 10.12 settled for Intel. VLC is
  now installed on `test_gpu`.
- 2026-11-06: The note became a bubble below the Video Decoder block (your pick, V2), with "How to
  fix" linking to a new README section.
- 2026-11-06: "SP" replaced by a Processes row (your pick, B). The note no longer reads as a fault
  when a library is just not installed.
- 2026-11-06: Stage 3 built with your pick, P1 + R2. Added Software <MPV>, and the driver names
  now say VLC or MPV with no version. See Stage 3 results.
- 2026-11-06: Stage 2 built and tested, see Stage 2 results. Startup is no slower on VLC. The
  fork abort stays open as 10.12, since the VM doesn't reproduce it even with its old cause.
- 2026-11-05: Stage 1 built and tested on all machines, see Stage 1 results. Own GL contexts
  replaced the Qt one in the handoff, and that held up. Waiting for your hand test.
- 2026-11-05: Plan written. Read the handoff, POC and driver code. Measured library lookup
  and load times. Confirmed Qt's offscreen platform can't make a GL context on Windows.
