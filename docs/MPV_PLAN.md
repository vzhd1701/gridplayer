# mpv driver: plan and progress

The findings and traps are in `C:\Projects\test_temp\test_mpv\HANDOFF.md`, and
`grid4.py` there is the working POC. That folder is reference only. This file is
what we build and how far it has got. Tick items only once they have been seen
working.

**Status: Stage 3 built (<https://claude.ai/artifact/8ngdeLCkVxmdQzSEnpxx1c>, real screenshots on its Built board). Open: macOS. Bundling libmpv (12.1) is for later. Stages 1-9 are committed on this branch.**

**Load tests against VLC: `MPV_PERFORMANCE.md`.** No multi-process mode for MPV. New items 10.13-10.16. 10.16, the long run, ran
overnight 2026-11-09: new items 10.21-10.23.

| | Stage | State |
|---|---|---|
| 1 | Videos load, play and resize in the real grid, with zoom and pan | **done**, hand-tested by you on 2026-11-11 |
| 2 | Finding the libraries, no startup delay, runs with only one of VLC or mpv | **done**, macOS on a VM |
| 3 | Settings: unavailable drivers greyed out with a reason | **built**, macOS on a VM |
| 4 | Transport: seek, speed, frame step, looping, end of video | **built**, macOS on a VM with no GPU |
| 5 | View: rotate, flip, crop, aspect ratio, screenshots, sync | **built**, macOS on a VM with no GPU |
| 6 | Audio: tracks, files, devices, delay, channels | **built**, macOS on a VM with no GPU |
| 7 | Subtitles: tracks, files, delay, encoding, style | **built**, macOS on a VM with no GPU |
| 8 | Deinterlacing, chapters, bookmarks, SponsorBlock | **built**, macOS on a VM with no GPU |
| 9 | Streams, live video, errors and recovery, lists | **built**, macOS on a VM with no GPU |
| 10 | Hardening: long churn, memory, real drags, other GPUs | mostly done; open: 10.4 (other GPUs) |
| 11 | macOS | **real GPU run 2026-11-15** (11.4): every scenario passes on a hackintosh; OpenGL 3.2 Core and Shared output on macOS now; Retina, two GPUs, Apple Silicon not run |
| 12 | Packaging, docs, release | not started |
| 13 | GL output, a choice beside readback | **built**, on macOS too since 2026-11-15 (the default there), resize shaking, NVIDIA's black line and a crash closing a cell fixed, one surface for the window (13.5), 120 fps (13.10) |
| 14 | mpv drawing into its own windows, a third output | **started 2026-11-11**, Windows first |

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
- [x] 1.13 **Showing:** you ran it by hand, it looks OK so far (2026-11-06); resizing, zoom and pan OK (2026-11-11). It was: you run it with the command below and drag it around by hand.
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
  sound, so Linux now tries only `pulse,pipewire,alsa` (PipeWire's own first until 10.33). See 6.7.

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
- [x] 3.9 **Showing:** done on Windows (libmpv there and not, light and dark) and `test_gpu` (no
  VLC, X11 and Wayland). Both libraries on Linux done on `test_gpu`, now VLC is installed there: all
  modes offered, no bubble, VLC's options on for VLC and greyed for MPV. macOS VM 2026-11-11: no Output or
  Processes rows, as it should be
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
- [x] 6.7 Linux audio outputs are limited to `pulse,pipewire,alsa` (see Stage 1 results; pulse first since 10.33). **JACK stays out, your call.**
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

**Older libmpv.** It works back to 0.37, Ubuntu 24.04's (client API 2.2); anything older is "libmpv is too old" (see the Log,
2026-11-12). What each refuses was read from the real one, on Debian 12 and Ubuntu 24.04 in a chroot on `test_gpu`, and comes from
`option_info` at the start (`SubtitleLimits`). A refused option gives no error and the line just stays as it was. The 0.35 column is
kept for the record.

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
  Seen 2026-11-09 overnight and fixed, see 10.1.

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
(the default at first, as mpv.net's and mpv's own), and Fast. **Your call (2026-11-15): Exact is the default.** Fast lands on a key frame. Exact seeks decode from the key frame to the time: 2160p60 AV1 on the
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

**Left** (gone through 2026-11-15):

- ~~A long way back can take 7 s~~ **Not any more (2026-11-15).** The YouTube video you gave for MPV testing (729 s, 1080p VP9, Hardware
  MPV, Exact): back a long way 0.9 and 1.3 s, back into what's played 0.9 s, on again 1.5 s; only the first seek, on far,
  4.4 s. The test file in fragments from a slow server (1 MB/s, 0.1 s a request): every seek 0.7-1.3 s, 2-3 requests.
  The 7 s was before the file in fragments was opened as that file (`has_fragmented_file`). VLC, on that slow server,
  11-40 s a seek: its playlist made of the file reads whole fragments; not looked into.
- **YouTube turned me down with 429 after a long run of testing, on both machines,** for a while, so go easy with these. It's what the scenarios here are for. It cleared by itself.
- ~~A stream's sound whose link fails leaves the video playing silent~~ **Fixed (2026-11-15).** Tried: refused from the
  start, MPV played the picture on with no sound track; refused halfway, it stalled 2 s and went on silent. VLC does the
  same. Now the proxy's failure on the sound's link (told once asking again with the link renewed was no better) is
  checked each second with the stall watch: the cell is loaded again, as for a video failing, and once that's no better,
  "Can't play the sound" with the server's answer ("The server refused. The link may have expired.", HTTP 403).
  `StreamControl.sound_failure`, `RecoveryControl._is_sound_lost`; scenario `mpv_stream_sound`. A muted cell is
  loaded again too: rather that than a video whose sound is gone without a word.
- On Linux yt-dlp had no JavaScript runtime here, so it was given other formats than Windows. Not run with one.
- Not run: AMD, macOS, cookies on MPV, DASH live. Nobody has looked at this on a real screen or listened: I read pixels, `avsync` and the track list.
  - **Cookies (2026-11-15): work.** Scenario `cookies`, on VLC and both MPVs: a server that refuses anything without a
    cookie, the cookie in cookies.txt; a file and an HLS stream with its sound apart play, no request without it. A
    link with cookies for its host always goes through the proxy (`needs_relay`), whichever player.
  - **DASH live (2026-11-15): didn't work on MPV, now does through the proxy (9.L1).** FFmpeg's DASH reader, which mpv
    plays DASH with, read what's there at once (about 340 requests in a second, the manifest before each segment), asked
    100 times for segments not out yet, gave up and played what it had, about 15 s; the cell then reconnected and failed.
    The same on DASH-IF's own live test stream (livesim2 testpic_2s): HTTP 425 Too Early, never played. FFmpeg is current
    (N-126497) and its DASH reader has no setting for it. VLC follows it with a reader of its own. YouTube and Twitch
    live are HLS, YouTube's recorded videos two plain files: no manifest.
  - AMD on Linux: no hardware. AMD on Windows passed (2026-11-11).
- [x] 9.L1 **Live DASH on MPV: the proxy serves it as live HLS (your call, 2026-11-15; built the same day).** yt-dlp's
  live DASH formats are marked (`Stream.is_live_dash`); MPV asks for them as `dash_live` (`VideoFrameMpv.stream_to_play`),
  the video at most as tall as the pane. The proxy (`DASHLiveHLS`, `stream_proxy/dash_live.py`) reads the manifest each
  time mpv asks for a playlist again, by the server's clock (its Date), and writes a master playlist of the video and the
  sound in every language (the one asked for the default, else the main one), and a live media playlist of each: what's
  out, at most 60 s back and no further than the manifest keeps, numbered so a segment keeps its number from one reading
  to the next, the init segment as `EXT-X-MAP`. What's served is named by what it is (`video`, `audio:en`), so a new
  period has it picked again by the same rule, the break an `EXT-X-DISCONTINUITY`, the numbers going on. Templates with a
  duration or a timeline, numbered or timed, segment lists (pieces of one file too), base URLs at every level; the
  lowest level that says how wins. Dates and lengths by isodate, as Streamlink reads them. Not: anything with DRM (plays
  nowhere here). VLC as before.
  - Tried: the ffmpeg-made stream for a minute, steady at 6 requests every 2 s, paused and played again, with a cookie
    too; livesim2's three shapes (numbered, timeline by time, timeline by number) at the live edge, no request refused.
  - FFmpeg's HLS reader asks for the init segment again after each reading of the playlist (21 times in a minute,
    about 1 KB each): it makes a new one each time. Left as it is.
  - From `/code-review` (2026-11-15), fixed: a renewed link kept as live HLS, the same part of it (it was handed back as
    the manifest, and the stream died at its first expiry); the cap only on Auto, "Best" the best; a pane not shown yet
    picks for 720 rows, not the tallest; the sound by the language chosen or the settings' languages, not the format's;
    at least 3 segments listed however short the window, and windows written with years and months read; what can't be
    read (an HTML page, a time Python 3.10 can't) a failure of the stream, told on the cell; a timeline repeated for days
    counted past, not gone through; segments named by time numbered on from the last reading, where they drifted by a
    number every few minutes with lengths that vary; the manifest fetched once a second for the picture's playlist and
    the sound's. Left: the picture's size is picked as it loads, as the pane is then; a pane made bigger later keeps it
    (a live stream loaded again to follow it would take seconds to come back).
  - From a second `/code-review` (2026-11-16), fixed: periods (a new one, an ad put in, failed the stream or numbered it
    backwards); every language offered, so mpv's Audio Track menu has them as VLC's does; a Date with no zone ("-0000")
    taken as UTC, where it failed every playlist; a finished stream whose length is only on its period; never more listed
    than the manifest keeps (the floor of 3 from the first review is 1); numbers counted on by time after a while
    unread, where they started anew; a segment list on a higher level no longer beats a template on the representation;
    a manifest a second old let go of. Not taken: Streamlink's DASH reader in place of this one, which is made for its
    own downloader (it waits for each segment to come out, from behind the live edge, and keeps its place itself).
  - Tried after: livesim2's period-a-minute stream for over two minutes on MPV, across two new periods, no request
    refused; the break marked and numbered on in the playlists.
  - Scenario `live_dash`, on VLC and both MPVs: a server that refuses a segment until it's out (`Driver.serve_live_dash`).
  - On the Ubuntu VM too (2026-11-16): every stream scenario (`live_dash`, `mpv_stream_sound`, `cookies` and the rest,
    23 runs over VLC and both MPVs), all pass.
    Without the proxy's HLS, MPV never plays it there.

## Stage 10: Hardening

- [x] 10.1 Long churn on readback in the real driver, including a native memory checker if
  one can be run. Handoff open question 3. Closed 2026-11-11, your call: everything it asked for has run
  - 2026-11-09, overnight: on Linux with glibc's heap checks both MPV churns crashed in 2 minutes. The event thread read the tracks at
    file-loaded, or at preloaded, or after an added file, while `terminate()` freed the handle: the window the Stage 7 notes left. Now those
    reads take `_telling` and look at `_is_closing` inside it, as everything sent to mpv does. Run again with the fix and the same checks: both
    20-minute churns pass, 2915 and 2819 videos opened. Before, the crash came in 2 minutes
  - Windows 20 minutes on both drivers and Linux 10 minutes under an address sanitizer pass. The memory with all closed: 10.22
- [x] 10.2 Real window drags on Windows: port `drag_probe.py` to the app, 0 backward moves.
  This one moves the mouse, so it runs when you say
  - 2026-11-10: tried by you, by hand: drags work as they should.
- [x] 10.3 By hand on a screen with X11 and Linux, if you have such a machine. Handoff open
  question 1
  - 2026-11-11: tested by you, looks alright. It raised 10.32
- [ ] 10.4 AMD on Windows and any other GPU we can reach. HEVC and 10-bit through VAAPI needs
  a newer chip than `test_gpu`
  - **AMD on Windows, run 2026-11-11** on your PC's AMD Radeon iGPU (a `python.exe` copy with no GPU preference, which
    Windows puts on the GPU the screen is on). Open: Linux on NVIDIA or AMD, and a newer Intel for VAAPI.
    - Every MPV scenario passes: the 42 of the suite with Steady, and 9 with Fast in a real window on the other desktop
      ("OpenGL by ATI Technologies Inc.", black line fix off, as Auto has it).
    - Hardware MPV decodes `d3d11va-copy` on AMD, HEVC and 10-bit HEVC too: on the GPU, each frame copied back through the
      CPU. mpv hands d3d11va frames to desktop OpenGL only through ANGLE, so frames stay on the GPU only on NVIDIA (`nvdec`).
      Intel on Windows will be the same as AMD.
    - The bench's mix, a real window on the other desktop (fps, the mix's own rates are 43.5, 39.3 and 36.7; app CPU, 100% a
      core; memory):

      | | 4 | 9 | 16 |
      |---|---:|---:|---:|
      | Hardware MPV, Steady | 43.5 · 53% · 635 MB | 39.3 · 93% · 1491 MB | **28.0** · 118% · 2453 MB |
      | Hardware MPV, Fast | 43.5 · 47% · 791 MB | 39.3 · 115% · 1681 MB | 35.1 · 159% · 2645 MB |
      | Software MPV | 43.5 · 149% · 339 MB | 39.3 · 234% · 777 MB | 36.7 · 375% · 1168 MB |

      The RTX 3060 plays all 16 on Hardware MPV (`MPV_PERFORMANCE.md`, "A real grid"); the iGPU falls behind at 16 on
      Steady, copying every frame back and reading it back again. The CPU (a Ryzen) keeps up with all of it in software.
    - Auto's video memory: DXGI says 48 GB for the iGPU, which uses the system's memory, so Auto never moves a video to the CPU there.
    - The bench's frame counter took `present_rgb32`'s arguments as they were before 10.7, which stopped every Steady and
      Software MPV run loading: fixed.
- [x] 10.5 The Linux `mallopt` arena limit: decide on applying it only when mpv is in use
  - **Measured 2026-11-09, `test_gpu`, real X11, `MALLOC_ARENA_MAX` (what `mallopt(M_ARENA_MAX)` sets), default (8 a core) against 2
    and 4.** Frame rate and CPU the same throughout.
    - Hardware MPV, 16 of the mix playing: 951-988 MB, 2 arenas 782-783, 4 arenas 782-793. Software MPV, 9: 1085-1088 against 989-995.
    - MPV churn, 10 minutes, all closed after 5 and 10: Hardware 1797 / 2126 MB, 2 arenas 897 / 972, 4 arenas 890 / 1101. Software
      1656 / 2169 against 1139 / 1568 (2 arenas).
    - VLC 3.0.24, 2 arenas: 1-4% less (Hardware single process 16: 1759-1784 against 1729-1740; Software single 9: 2430-2476 against
      2329-2400; multi-process 16: 2035-2038 against 1991-1997). Its churn said nothing either way then, as it leaked threads (`VLC.md`, 10.29, fixed since).
  - So it's worth having, for MPV above all, and it costs VLC nothing: apply it always on Linux, not only with MPV.
  - **Built 2026-11-09, 8 arenas (your pick):** `utils/glibc_malloc.py`, first thing in `main()` (and in the real-app driver):
    `mallopt(M_ARENA_MAX, 8)`, and `MALLOC_ARENA_MAX=8` for processes started fresh; forked ones keep it. A `MALLOC_ARENA_MAX`
    already set is left alone, and a libc without the option (musl) too. Checked on `test_gpu`: 64 threads allocating at once make
    64 arenas, the cap's number with it; the resource tracker starts with the variable. Hardware MPV 16, 3 runs each, alternating: no
    cap 985-991 MB and 31.5-32.6 fps; 4 arenas 780-796 MB, 31.0-31.6; 8 arenas 807-820 MB, 29.6-31.8; churn all closed after 10 min,
    8 arenas 1105 MB (4: 1101). Both caps show about 1 fps of 32 less there, the GPU's decoder at its limit; 8 no better than 4, so
    likely not the lock, and not seen with Software MPV or VLC.
  - **2026-11-10:** the same module now also gives back what glibc keeps freed, 2 s after a video is let go of (`VLC.md`, 10.29):
    Hardware MPV churn, all closed after 10 minutes, 519 MB (1105 with the cap alone).
- [x] 10.6 `churn.py`'s 30 KB per close on X11: check it's bounded
  - **Run 2026-11-10, `test_gpu`, real X11, the mix, 25 minutes each (the runner's limit), all closed every 5 minutes.**
    The 30 KB was the prototype's, 369 to 444 MB in 10 minutes. Memory with everything closed, started at 80 MB:
    - Software MPV, fully software now, no Mesa in it: 287, 454, 540, 511 MB, while playing 766, 923, 1091, 1050. It
      levels off and comes back down: bounded, what glibc and libmpv keep of what was used most.
    - Hardware MPV: 339, 440, 463, 576 MB, still going up, about 80 MB each 5 minutes with 6-8 playing, which is 10.21's
      growth in Mesa while playing on this GPU (790 MB an hour at 9), not something kept per close. On Windows the
      20-minute churns of 10.1 came back down with everything closed on both drivers.
- [x] 10.7 GLES: `GL_BGRA` needs desktop GL as written, read RGBA where it's missing
  - **Built 2026-11-10.** On Linux the render thread's EGL context is OpenGL ES where a driver offers no desktop OpenGL, or
    no config or context for it, or where Qt's own is ES, as with the Fast output a context shares only with one of its kind (ES 2 asked, Mesa gives 3.x).
    There, textures are made `GL_RGBA` (ES 2 takes no sized format), and frames are read back BGRA where the driver has
    `GL_EXT_read_format_bgra`, as Mesa's does, else RGBA, painted as `Format_RGBX8888`. PyQt5 has no GL functions for an ES
    context, so Qt's side (the Fast output's grid surface, deleting textures) takes the 7 calls it uses through ctypes there.
    Windows (WGL) and macOS (Qt's) are desktop OpenGL as before.
  - Checked on `test_gpu`, a clip red on the left and blue on the right: Steady with desktop OpenGL refused, read back BGRA
    and, forced, RGBA, the right colours both ways; Fast on the real X11 screen with Qt on ES, drawn and read right.
- [x] 10.8 Render thread stall watchdog and a lost GL context: the rest moved to `docs/ROADMAP.md` (2026-11-11, your call)
  - **Done 2026-11-11:** a cleanup (reload, driver change, all closed) waited for the render thread for good, so one
    stuck in a GL driver's call would have frozen the app. Now it waits 5 s (`STOP_WAIT_MS`), then logs it and leaves
    the thread behind, kept alive (a QThread destroyed while it runs ends the app); the next video gets a new one. Its
    videos' mpvs stay, as one can't go before its render context, but are told to stop playing.
  - Left for later, with how often it could happen and what it would cost: the watchdog itself, and surviving a GPU
    reset or a driver update. See "Surviving a GPU reset" in the roadmap
- [x] 10.9 Cells not on show, as in Single Mode, still render and read back every frame. Render
  them small or not at all. Done: a hidden cell's frames are taken with `skip_rendering`, so it
  plays on at its pace (taking none, mpv waits 200 ms on each), and the last one taken is drawn as
  it's shown again, about 50 ms later. Not before its first frame, as that's what says it has
  loaded, and not while a screenshot waits on one. `mpv_hidden_cells`: 3 cells, 4 s in Single
  Mode, 100 draws for the one on show and 0 for the others, on both MPV drivers
- [x] 10.10 `load_scripts=no` leaves mpv's built-in scripts running, about 5 Lua threads per
  video. They cost no measured memory, but each has threads: check whether to turn them off
  - **Done 2026-11-10: off.** With osc and ytdl already off in libmpv, what runs is stats, the console and, from 0.39, the
    commands, select and positioning scripts the menus use; nothing here uses any of them. Their `load-*` options are set off,
    those this libmpv has: one it lacks stops mpv starting, and nothing can be asked before an mpv has started, so an mpv
    started for it reads the option list once a run (3-4 ms). The console's option took a new name in 0.39; the old one is
    set only where the new isn't there.
  - 8 videos of 1080p playing: Windows, libmpv 0.41, 178 threads to 138 and private memory 3127 to 3081 MB; `test_gpu`,
    93 threads to 53 and 542 to 533 MB. 5 threads a video.
- [x] 10.11 **Your decision:** a low VRAM option (`-copy` or software for new videos when over
  budget), and an mpv decoder setting
  - **Decided (2026-11-09): a setting with Auto / On / Off.** As understood: decoding on the CPU instead of the GPU, Auto
    switching new videos to it when video memory runs low, On always, Off never. To be confirmed when built, with 10.17's flag:
    the two may be one setting.
  - **Decided (2026-11-10): one setting.** 10.17 built "Decode on the CPU" on Hardware MPV with Off / On; Auto goes into the same
    setting when this is built.
  - **Built 2026-11-10: Auto / On / Off, Auto the default.** A video on Auto decides once, in mpv's preload hook, where its size
    is known and nothing is decoded yet: on the GPU if there's room for it, else `hwdec=no` for as long as it's open. A reload
    decides again. `utils/video_memory.py` reads what's left:
    - Windows 10 and later, any GPU: DXGI's `QueryVideoMemoryInfo`, the budget the system gives this process and what it uses of
      it, by ctypes. The system lowers the budget as other programs (a game) take video memory. Of several GPUs, the one this
      process uses most of, which is where GL and so mpv's decoder are; before anything is on one, the first, the system's pick.
      Read here: RTX 3060 budget 11.3 GB, the AMD iGPU's shared 47 GB, Basic Render.
    - Linux with NVIDIA: NVML, what's free on the first GPU. Running out there fails the decoder; Windows and AMD on Linux move
      memory out to system memory instead and slow down.
    - Not read, Auto as Off: Intel (system memory), AMD on Linux (sysfs can't tell an APU's slice of system memory from a
      card's own, and on an APU going to the CPU would be the worse choice), macOS.
    - Room: what's free less a tenth of the total (at least 256 MB) kept for everything else. A video is counted at 128 MB and
      56 bytes a pixel, 244 MB at 1080p, 571 at 2160p. What's given to videos starting counts as used only until it shows in what's
      read: the given less what's been taken since the first of them was given. NVIDIA's decoder takes its memory about 60 ms
      after, and a playlist's videos ask about 60 ms apart, before mpv says what it decodes with; counted until then, 8 opened at
      once got 3 on the GPU where 4 fit. A claim ends when mpv says what it decodes with, as it closes, or after 5 s. A failed
      read is logged and not tried again.
    - Measured, RTX 3060 (DXGI, this process), Fast and Steady alike: H.264 1080p 237-247 MB a video (the same from 1 to 8),
      HEVC 1080p 246, HEVC 10-bit 1080p 364-367, H.264 2160p 570-572. So about 130 MB whatever the size, likely a CUDA context
      for each mpv, and 53 bytes a pixel. 10-bit takes half as much again, which the spare covers: the track doesn't say its bit
      depth as it preloads. `test_gpu` (Intel, VAAPI, the driver's per-process `fdinfo`): 47-52 MB a 1080p video at 8, about
      200 a 2160p one, both outputs, nothing fixed. A video Auto puts on the CPU still takes about 80 MB on the GPU, to be drawn.
    - Checked on Windows with DXGI's real readings, the budget capped 1.5 GB above the app's at the start: 8 1080p videos opened
      at once, 4 on the GPU (252 MB each) and 4 on the CPU, 1333 MB used; with 4 closed, a new one went to the GPU.
    - Tested: `mpv_low_video_memory` with the GPU made up full for the middle of three videos, which decodes on the CPU and the
      others on the GPU, back on the GPU when reloaded with room; on `test_gpu` with real decoding `vaapi`, `no`, `vaapi`.
  - Found doing it, in 10.17: Software MPV showed a file's own turn (a phone video) only after a transform or reload. mpv marks
    no track selected while it preloads, so the turn was worked out with no track. The preload now takes the track mpv will,
    the first the file marks or the first; `mpv_view` checks each turned file as first opened.
- [x] 10.12 mpv to VLC Hardware live, on a real GPU with X11. Passes on `test_gpu`, 2 rounds, and the
  pass counts: with the old cause forced, decoder processes do die with signal 6 there. NVIDIA on
  Linux not run. See `MPV_PERFORMANCE.md`
- [x] 10.13 Skip frames, with `vd-lavc-skipframe=nonref`: the setting "Skip frames to play more videos"
  on the Video Decoder page, off by default, for both MPV drivers, applied with no reload. 16x1080p60
  goes from 7 to 31 fps. It costs half the frames at any load, 4x1080p60 goes from 60 to 31. No use on
  video with no B frames. Automatic left out: it would need ignoring the startup burst, a way back,
  and a way to hide the pause: each switch stops a video for about a third of a second
- [x] 10.16 Ran overnight 2026-11-09, see `MPV_PERFORMANCE.md`, "Overnight". Found: an MPV crash closing a video as it loads, fixed (see 10.1);
  Linux memory growing 790 MB an hour with 9 videos playing, in Mesa (10.21); Software MPV on Windows keeping 1.5 MB a video closed (10.22); VLC
  hanging 42 s at load on Linux and at 29 fps from 9 cells on Windows (10.23, now in `VLC.md`). The limits held over 3 runs. How it was run:
  **To run overnight, by you.** All of it, about 4.5 hours, from Git Bash at the repo root on Windows:
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
- [x] 10.17 **Later, your call (2026-11-06):** Software <MPV> becomes fully software, as people expect software not to touch
  the GPU at all. Today it's `hwdec=no` and still draws through OpenGL.
  - Draw with libmpv's own software render API rather than OpenGL. Not tried yet: measure CPU, scaling quality and how
    many videos it plays against today's mode
  - Today's mode, CPU decoding drawn on the GPU, moves to a flag on Hardware <MPV>, something like "Decode on the CPU". It plays
    the most on a strong CPU, so it stays available
  - Saved `mpv_sw` settings: decide whether they become the new mode or Hardware <MPV> with the flag on
  - A stand-in for Software VLC with no VLC should then be the new mode (see Stage 3 results)
  - **Decided (2026-11-09): yes.** Nobody uses Software MPV yet, so saved `mpv_sw` settings need no care. Measure the software
    render API first (CPU, scaling quality, how many videos play against today's mode), then build.
  - **Built 2026-11-10.** Software MPV draws with libmpv's software renderer (`api_type` "sw") on a render thread of its own, with
    no GL context, straight into the triple buffer's pixels, painted as the Steady output's are. The render service's one renderer is
    of the kind of the first video after a cleanup: a driver change reloads, cleaning up first. Video output (Fast) and "Hand frames straight to the GPU"
    are Hardware MPV's only now. Today's mode is Hardware MPV with "Decode on the CPU" On (Off / On, and 10.11's Auto later, your
    pick). What the software renderer leaves out, done another way:
    - Turns: it ignores `video-rotate` and a file's rotation. `video-rotate=no`, and the file's turn plus the app's goes in as a
      `transpose` filter in the preload hook, before the picture starts, after any deinterlacing, and again for another video
      track. `video-params` is of the picture before the filters, so its shape is turned by the app's own number.
    - Flips while subtitles show: no shaders there, so `hflip` / `vflip` filters. All three share mpv's one `vf` list.
    - Format `bgra`: zimg leaves the fourth byte of `bgr0` at 0, and Qt's RGB32 painting carries it through as alpha, a picture
      you see through. swscale happens to write 255.
  - **Scaler: swscale's fast bilinear** (`sws-allow-zimg=no`), measured against zimg's defaults (lanczos, dithered), zimg bilinear
    with no dither and swscale's bilinear. zimg at its defaults on `test_gpu`: 190% of a core for one 1080p30 video against 90%
    today, its worker threads 85%. Fast bilinear: 107%, and the most played (16x1080p30 29.8 fps, 9x1080p60 48.8). swscale works on
    the render thread, all videos on one: plain bilinear held it at 100% from 9x1080p30 on `test_gpu` (13 fps), fast bilinear at a
    third of a core for 16x1080p60 on Windows. Side by side at 640x360 and 320x180 cells the five look much the same; zimg's
    lanczos is the smoothest, fast bilinear like today's GL bilinear, with the same few jaggies at 36 cells.
  - **Measured, Software MPV against Hardware MPV decoding on the CPU (today's mode), bench clips, finished code.** See
    `MPV_PERFORMANCE.md`, "Fully software MPV". Windows offscreen: less CPU everywhere (16x1080p60 616% to 470%, one 2160p60 167%
    to 88%), half the memory or less (16x1080p30 2402 MB to 1118, 36 small 3878 to 1068), the GPU 20-38% busy to 1-4%, the same
    frame rates. `test_gpu`, real X11: the same CPU, more played past the limit (16x1080p30 20.4 to 29.9 fps, 9x1080p60 28.9 to
    48.8, 16 mixed 12.8 to 24.9, 4x2160p60 10.0 to 14.8), one 1080p30 105% against 90%; the GPU 80-97% busy to 18-38%, what's left
    being the display. So "plays the most on a strong CPU" no longer holds for today's mode; it's kept for your call above, and as
    the way to Fast output with CPU decoding.
  - Churn, Windows, 6 minutes, all closed after 5 and 6: 507 / 247 MB (today's mode 1189 / 1229), threads back to 13-14, video
    memory never above the 163 MB of the start.
  - Tested: unit tests for the render calls, the renderer with no GL, a renderer per kind, the manager's pick, turns and flips
    as filters with deinterlacing. `mpv_basics`, `mpv_view`, `mpv_subtitles` and `mpv_deinterlace` now also run on Software MPV in
    the real-app suite; on Windows those and 8 more pass on it, on `test_gpu` the suite 73 passed, `stream_stalls` failing on both
    MPV drivers as on HEAD there.
  - Not done: HDR. swscale doesn't tone map, so HDR video looks flat on Software MPV, as on Software VLC. The pointer and stride
    aren't 64-byte aligned as render.h prefers; nothing measured showed a cost.
- [x] 10.18 A window minimized or in the tray rendered and read back every frame of every video. Done as 10.9, your call (2026-11-08), with no
  setting: nothing on screen changes, as a minimized window's preview is the picture from before. The cell goes by its own show and hide,
  and by the window's `away_changed`, as coming back it can be shown before the window says it's no longer minimized. `mpv_hidden_cells`:
  minimized and in the tray, 0 draws in 4 s, played at full pace, drawn again 50 ms after. On the offscreen platform only: a real window
  on Windows and Linux not tried
- [x] 10.19 Small savings the review found, by reckoning and not yet measured, for when the CPU matters more than the code: each render round visits
  every video, not just those with a frame (at most about 4% of a core at 64 cells); the placement is worked out on each paint (about 1% at 9
  cells). 4.2: the time is still sent by mpv each frame, so the saving of `notime` isn't had yet
  - **Measured and done 2026-11-10, Windows offscreen.**
  - The render round: left as it is. At 64 cells of 360p60 a round's visits to videos with nothing to do cost 0.4-0.5% of
    the render thread, 1.2-1.4 µs each, 3,500 a second: the thread makes only about 86 rounds a second there, 97% of its
    time rendering.
  - The placement: kept for the cell until anything it's worked out from changes (frame size, track size, cell size,
    screen scale, view, turn, pixel shape). It was 23-30 µs a paint, about 1% of a core at 9 cells of 1080p60, 390 paints a
    second: painting went from 8.1 to 7.5% of a core on Software MPV and 7.2 to 6.3% on Hardware MPV.
  - The time: mpv says it only while paused, where a frame step or a seek has to be told at once. Playing, it's asked for
    every 200 ms, what's sent on in any case, and as a seek lands, rather than an event with every frame for the event
    thread to take: the `notime` of the load tests, 140% to 134% of a core at 36 cells. A time read that hasn't moved,
    a stream waiting for more, isn't sent on, as mpv said nothing then either; one where a seek landed always is. A live
    stream stopped or played by the app, with mpv's pause left alone, goes by the same rule.
- [x] 10.20 Done in 9.6. File lengths in lists are read by VLC. With only libmpv there, lists show none. libmpv could read them too, in a
  process of its own as now
- [x] 10.21 Linux memory grows while playing on `test_gpu`: Hardware MPV 790 MB an hour at 9 videos, Software 244 at 4, VLC 48. The C control
  grows as fast with no Python, and `heaptrack` puts it in Mesa 25.0.7's `libgallium`, the Haswell driver. Try a newer Mesa, and another GPU
  on Linux with 10.4. Nothing for the app to change unless it's found everywhere
  - **Newer Mesa tried 2026-11-11:** Mesa 26.1.6 from trixie-backports, unpacked into `/opt/mesa_new` on `test_gpu` and loaded
    in its place (the system's 25.0.7 left installed). 20-minute soaks, the mix, real X11, alternating with the system's:

    | | Memory, 1 then 18 minutes in | Grows an hour | fps a cell |
    |---|---:|---:|---:|
    | Hardware MPV, 9, Mesa 26.1.6 | 828 → 1275 MB | 1387 MB | 22.4-22.9 |
    | Hardware MPV, 9, Mesa 25.0.7 | 787 → 1234 MB | 1322 MB | 22.1-23.2 |
    | Software MPV, 4, no OpenGL since 10.17 | 447 → 465 MB | 26 MB | 43.0-43.2 |

    So a newer Mesa doesn't change it, and Software MPV, which grew 244 MB an hour when it drew with OpenGL, now barely grows:
    the growth goes with OpenGL on this Haswell GPU. What's left is another GPU on Linux (10.4). Until then, Software MPV is the
    choice on such a machine for a grid left playing for hours.
  - `test_gpu` is a container with the host's own GPU, an Intel Haswell (HD 4600, 2013) on the i915 kernel driver and
    Mesa's `crocus`: so this is real hardware, not a VM's graphics. What's unknown is only whether newer GPUs do it too
    (Intel from 2015 on `iris`, AMD on `radeonsi`, NVIDIA's own driver), and none of those can be had here
  - **Found 2026-11-11: libmpv leaks a GL fence per frame drawn, not Mesa.** libmpv 0.40 and 0.41 call `glFenceSync` in
    `ra_gl_ctx_submit_frame` (`video/out/opengl/context.c`) after every `mpv_render_context_render` that draws, and only
    `ra_gl_ctx_swap_buffers` deletes them, which the render API never calls; closing a video doesn't either. Came with
    mpv 5ae0e0f (v0.40.0), fixed by f74adc4 ("opengl/context: require swap_buffers param for FenceSync", issue #17217),
    first released in 0.42.0. 0.37 and older don't have it. On `crocus` a fence costs about 250 B of heap with a DRM
    syncobj kept, on other drivers less (NVIDIA's 48 MB an hour on Windows is likely the same, not measured).
    - Measured on `test_gpu` (Debian's libmpv 0.40.0) with a copy of `native_bench`: grows whether frames are read back
      or not, with or without a PBO, with `vaapi`, `vaapi-copy` or no hardware decoding; barely when nothing is drawn;
      flat with the fence deleted after each render. heaptrack: the growth is `_mesa_fence_sync` and crocus's fences
      called from `ra_gl_ctx_submit_frame`.
    - The real app, `soak.py`, 9 cells of the mix, 15 min each: 1479 MB an hour as it is, **17 MB an hour** with the
      fence deleted (`glFenceSync` answered by a wrapper keeping the last fence, `glDeleteSync` after
      `mpv_render_context_render` in `RenderCalls.draw`), at the same fps and GUI lateness. Injected at runtime.
    - To apply it: only on libmpv 0.40 and 0.41 (from `mpv-version`), both GL outputs, draw only (not skip). From 0.42
      the last fence of a render could be an upload buffer's that mpv still needs. Bundling 0.42 or later fixes it too.
    - **Built 2026-11-11** (`FrameFences`, `leaks_frame_fences` in `renderer.py`): mpv is handed a wrapped
      `glFenceSync`, and the last fence made while a frame is drawn is deleted after it. On for 0.40.x, 0.41.0 and git
      builds less than 113 commits past v0.41.0 (f74adc4 is `v0.41.0-113`); the Windows test libmpv
      (`v0.41.0-1044-g14f2d48cb`) has the fix, so it's off there. The player now reads `mpv-version` as mpv starts, not
      by an observer, so it's known before the first render context asks for GL functions. mpv still keeps the deleted
      fences' handles in an array, 8 bytes a frame (about 10 MB an hour at 9 videos), which nothing outside can free.
      Soak as before, 15 min, the code as built, no injection: **20 MB an hour** (539 → 550 MB), 39.0-39.2 fps a cell,
      no errors in the log.
    - Left: the i965 VA-API driver grows about 40 MB an hour on its own (libdrm_intel), not followed to the end. Intel's
      old driver (GPUs before 2015), not the app's: closed with the rest.
- [x] 10.22 **Your decision:** Software MPV on Windows keeps about 1.5 MB for each video closed, mpv's direct rendering buffers: 60 to 1838 MB
  in a 20-minute churn with everything closed. With `vd-lavc-dr=no` it stays at 340-400 MB. That cost frames on Linux, 19 against 25, and
  wasn't measured on Windows. Lists playing one video after another would meet it. Hardware MPV keeps about 230 KB a video, not looked into
  - Measured on Windows: off costs nothing while the CPU keeps up (9 and 16x1080p60, 4x4K60, 16 mixed: the same fps, CPU +0-10%), and 13-19% of
    the frames past it (25x1080p60 52 to 45, 9x4K60 58 to 47).
  - **NVIDIA only.** The same 6-minute churn with OpenGL on the AMD iGPU, everything closed: on, 742 then 499 MB; off, 623 then 427 MB. Both give
    memory back. On NVIDIA: on, 1259 then 1517; off, 403 then 340. So it's NVIDIA's driver keeping mpv's mapped buffers. Linux NVIDIA not known
  - **Decided (2026-11-09): direct rendering stays on by default, with a setting to turn it off.** It only matters where the CPU
    decodes and OpenGL draws: libmpv's software render backend has no `get_image`, so the fully software mode of 10.17 has no
    direct rendering at all. So the setting belongs with 10.17's "Decode on the CPU" and Hardware MPV's own fallback to the CPU.
  - **Built 2026-11-10:** "Hand frames straight to the GPU" on the Video Decoder page under the MPV drivers, on by default
    (`player/mpv_direct_rendering`). Off sends `vd-lavc-dr=no`; on leaves mpv its default. It goes for videos opened after, as mpv
    reads it only as a decoder starts. Both MPV drivers, as Hardware MPV falls back to the CPU by itself (deinterlacing, a codec the
    GPU lacks). `churn.py` takes `DR=0`. Checked on Windows, NVIDIA, Software MPV churn, 6 minutes, the mix, all closed after 5 and 6
    minutes (start 60 MB): on 1189 / 1229 MB, off 530 / 471, threads back to 23-24 both. Since 10.17 it sits under "Decode on
    the CPU", Hardware MPV's only: fully software MPV has no direct rendering.
- 10.23-10.28 are VLC's own, not MPV's: moved to `VLC.md` with their numbers (10.23 an overnight load freeze on Linux,
  10.24 and 10.25 single-process freezes, 10.26 VLC's waits, 10.27 32-bit address space, 10.28 single against multi-process; all done).
- [x] 10.30 **Your call (2026-11-11):** what goes by the time to the frame, rather than a setting for finer time. The time
  reaches the app once in 200 ms while playing (4.2, and since 10.19 asked for rather than sent by mpv), on VLC as well; paused,
  every change. Asked whether per-frame time should be a setting: no, as it was never had and would cost CPU everywhere for
  two features. What could show the 200 ms:
  - A-B loop: the end is checked on each time report (`VideoBlock`, `self.time > self.loop_end`), so it can play up to
    200 ms past B. On MPV, mpv's own `ab-loop-a` / `ab-loop-b` turn back at the frame; on VLC, a timer to the end from the
    last report and the rate.
  - SponsorBlock: whether a skip starts late, by how its skips are timed. Not looked at yet.
  - First: measure how far past B each driver goes, and how late a skip starts.
  - **Measured 2026-11-11** (Windows, offscreen, a 30 fps clip, 40 loop passes with B moved to anywhere between report
    ticks, 20 skips from varied starts; script in the scratchpad, not kept):

    | Driver | Time reports | Past B when it turns back | Into a sponsor when skipped |
    |---|---|---|---|
    | Hardware MPV | every 200 ms | median 121 ms, max 234 | median 34 ms, max 168 |
    | Software MPV | every 200 ms | median 102 ms, max 200 | median 34 ms, max 168 |
    | Software VLC, one process | every 250 ms, at times 500 | median 186 ms, max 470 | 85 or 335 ms |

    The seek back then lands in 10-20 ms. So up to 0.2 s past B on MPV and nearly 0.5 s on VLC, shown; a sponsor shows for
    up to 0.17 s on MPV and 0.34 s on VLC. Hardware VLC (processes of its own, a real window) not run; its time comes the
    same way. Fix if wanted: on each report, a one-off timer to B (or a skip's start) from the time and the rate, for both
    drivers and both features; or mpv's own `ab-loop-a`/`ab-loop-b`, MPV only. Your call
  - **Fixed 2026-11-11, you picked the timer:** `TimeAhead` (`video_block_time_ahead.py`), a part of the block. With B or
    a skip's start due before the next report (600 ms at most), a timer tells the time at that moment and the block checks
    it as a report; any report, seek, pause, rate change or stop puts it off. Measured the same way, plus the frame on show
    read off its colour (each frame's number in it) at the moment the block acts:

    | Driver | Picture on show past B when it turns back | Into a sponsor when skipped |
    |---|---|---|
    | Hardware MPV | median -1 ms, p90 19 | median 0, max 0 |
    | Software MPV | median 0, p90 21 | median 0, max 33 (one frame) |
    | Software VLC, one process | median -11 ms, p90 7 | median -17, max 0 |

    Review fixes: only the loop and skip checks run at the mark, the player's time kept otherwise; put off with a
    change of video or a reload; and not done when a report is late (more than 1.25 times the latest gaps), the video
    maybe buffering. Measured again, the same.
    Left: the first pass after Set Loop End, B being where the video already is (up to a report late, as before), and on
    VLC one pass in 39 where the report beat the timer, the GUI being held up by the test's own grabs
- [x] 10.31 Playback stats for a cell: moved to `docs/ROADMAP.md` (2026-11-11, your call)
- [x] 10.32 **Native Wayland when the decoder doesn't need X11 (raised 2026-11-11 after 10.3).** On a Wayland session the
  app still runs through Xwayland whenever there is one (`env._detect_qt_platform`), whatever the decoder, since VLC
  Hardware needs an X11 window. Only VLC Hardware does: MPV both ways and VLC Software play on Wayland natively (Stages
  1-9 ran there on `test_gpu`). Idea: pick the platform from the decoder at startup, and on switching to or from VLC
  Hardware offer a restart.
  - **Built 2026-11-11, your call: a Window system setting** (first called Display, renamed as it reads like the
    screens), Auto / X11 / Wayland, Linux only, on the Video Decoder page. Auto runs on Wayland when the desktop is one
    and draws the window frames, unless the decoder is VLC Hardware. `--platform` still wins over it.
    Picked in `init_app_env.pick_qt_platform`, before Qt starts; "Restart to apply" when a change of either calls for the
    other platform. On Wayland with Xwayland there, VLC Hardware can still be picked (it plays as VLC Software until the
    restart), and the notice says so only when it's the pick.
  - `test_gpu`, sway with Xwayland, the app picking: Hardware MPV Steady and Fast, Software MPV and Software VLC on
    Wayland, `mpv_basics` passes on the three MPV ones; VLC Hardware on X11; Window system X11 with MPV on X11;
    Window system Wayland with VLC Hardware on Wayland, playing as Software VLC. The page and its notice look right there.
  - **Frames (2026-11-11, you saw it):** on GNOME, Qt 5 draws a window's frame itself, a thick flat band in the window's
    colour with no shadow, dialogs too, so they blend into the window. GNOME offers no `zxdg_decoration_manager_v1`, so
    the frame is the app's; KDE, sway and most others draw it, as on X11. Qt 5's only frame plugin is that one (a better
    one, QAdwaitaDecorations, is compiled C++). So Auto stays on X11 where the compositor offers no frames, asked of it
    before Qt starts (`utils/wayland_frames.py`, libwayland by ctypes). Checked: GNOME on `test_ubuntu` (no frames
    offered, Qt's frame 3/30/3/3 px), sway on `test_gpu` (offered, Qt's frame 0)
  - Resizing the window by dragging its edge on native Wayland: fine on Ubuntu (you, 2026-11-11)
  - Review fixes (2026-11-11): shown only on a Wayland desktop with Xwayland; the platform picked after a launch has
    handed its files on; the compositor asked with a 0.5 s limit, any failure taken as no frames; the notice follows the
    page's Window system and says when `--platform wayland` holds it; a restart asked again after one was put off
  - Drags with the mouse on native Wayland, where the fake drag for Xwayland isn't used: fine (you, 2026-11-11)
- [x] 10.33 **MPV plays slow for the first 5 s, sometimes, on Linux (you, 2026-11-11, Ubuntu VM: one video or a grid,
  both MPV drivers, X11 and Wayland; never VLC).** mpv's PipeWire output, started on a sink PipeWire had put to sleep
  after a few quiet seconds, keeps a clock running at about three quarters of the speed until about 5-6 s in, and the
  video follows the sound's clock. Hence "sometimes": with anything played in the seconds before, the sink is awake.
  Muted makes no difference, the output is opened anyway. VLC goes through the pulse layer.
  - Measured on `test_ubuntu` (PipeWire 1.0.5, libmpv 0.37), a synthetic 1080p 23.976 fps clip with sound, frames drawn in
    seconds 1-5 (120 is right): PipeWire's output on a sleeping sink 86-93 in all 6 runs, on an awake one 120; mpv's pulse
    output on a sleeping sink 121-124 in all 6. Both MPV drivers alike.
  - **Fixed: Linux tries `pulse,pipewire,alsa`.** After it: 122-124 a video, one video or 9, both drivers, the sink asleep
    each time. PipeWire's pulse layer has PulseAudio's 64 clients too; a video turned away fails at once and gets
    PipeWire's own output: 70 cells, 61 on pulse and 9 on PipeWire, none silent. The device list is now `pulse/` names on
    PipeWire, as VLC's. `mpv_audio` and `mpv_transport` pass on both drivers there, onto a null sink.
  - Rig trap: an offscreen real-app run has a runtime folder of its own, so no sound server. For sound, run with
    `REAL_APP_QT_PLATFORM=auto` on the desktop's display
- [x] 10.14 Don't fill the cell black before drawing a picture that covers it: app CPU 61% to 47% at
  1x1080p. Applies to VLC's software drivers too, so test those. Done: only the bars beside the
  picture are filled, reaching a pixel under its edge so a pixel it only partly covers at a screen
  scale of 1.25 or 1.5 is never left unpainted. One 1080p cell, two runs each, painting before and
  after: `test_gpu` X11, Hardware MPV 4.2/3.7 to 2.8/2.9 ms, GUI thread 32/29% to 24/25%; Software
  MPV 3.5/3.3 to 2.5/2.4 ms; Software VLC SP 6.7/6.3 to 6.1/5.6 ms. Windows, a real window on the
  other desktop: 0.44/0.53 to 0.42/0.41 ms, too little to show in the app's CPU
- [x] 10.15 Cached render parameters instead of python-mpv building them per frame, about 2-5% CPU
  - `RenderCalls` in the renderer makes a video's two calls, draw and take-not-draw, once, and changes only the size in
    place. It calls python-mpv's `_mpv_render_context_render` itself. A frame's parameters went from 6.3 µs of Python to
    0.15 µs, checked against python-mpv's own, value for value, with the real libmpv.
  - Smaller than the 2-5% guessed: about 1% of a core at 36 cells, where the bench's one run gave 140% to 139%. Not
    benched again, as that is within a run's noise.
- [x] 10.34 **Picture quality: Auto / Fast / High (your call, 2026-11-12).** Every video now gets mpv's `fast` profile,
  plain bilinear: right for small cells, soft on one big video (Single mode, a big cell, full screen).
  - **Auto** (default) picks by the size a cell is drawn at, again on each resize: Fast below about 0.6 MP, `catmull_rom`
    up / bilinear down with no dither up to about 1.5 MP, mpv's own defaults above. The options can change while a video
    plays. Each level names every option it touches, so a switch leaves nothing of the last one behind.
  - **Fast** and **High** hold one level whatever the size.
  - No stepping down when frames drop: it flips up and down, and a decoder's dropped frames aren't helped by a cheaper
    scaler.
  - Hardware MPV, all three outputs. Software MPV stays on swscale's fast bilinear: greyed out there.
  - Measure before picking the limits: fps and GPU at 1, 4, 16 and 36 cells per level, on both machines.
  - Idea from Brick2892's fork (github.com/Brick2892/gridplayermpv, its Auto preset). Ours is written from scratch;
    credit the idea in the CHANGELOG and as co-author of the first `feat` commit (see "Credit" in AGENTS.md).
  - **Built 2026-11-14** (`mpv_player/quality.py`, "Picture quality" under Video Decoder). Measured in
    `docs/MPV_PERFORMANCE.md`, "Picture quality": no middle level, as `catmull_rom` cost the AMD iGPU as much as High
    wherever either cost anything. Auto is High for a picture shown at 1 MP or more (one video over a 1080p window
    is 2 MP), unless shrunk from over 2.5 times the pixels (4K into the window cost the iGPU a tenth); Fast below.
    By the part on show, zoomed or cropped; once High it holds a fifth past either line, against switching to and fro.
    High is mpv's defaults, read from the libmpv in use (`option_info`). The frame says the size shown on screen
    (`set_shown_size`); Copy and Shared render at it while High, as with subtitles on, or mpv's scaler would never
    make a small picture bigger: one 360p over the window then costs NVIDIA's Copy half a core more for the
    read-back. Checked: unit tests, `mpv_basics` (High and Fast switched live) on Copy and Direct, and Auto taking up
    High for one big video and leaving it at four cells, Copy and Direct. Credit in the CHANGELOG still due (12.5).
    The bench's `quality=` sets the setting now (the table's 360p rows were rendered at 640x360 whatever the level).
- [x] 10.35 **mpv options, typed in (your call, 2026-11-12).** An advanced box, `name=value` a line, for Hardware MPV:
  for the few who want libplacebo's options, a decoder of their choice (`hwdec=nvdec`), `gpu-api` or `vo=gpu-next` on
  Direct, without a settings row for each.
  - Applied last, over the settings. Options the app manages itself are refused with a short note under the box, not
    applied quietly: `wid`, `vo` / `gpu-context` / `gpu-api` on Copy and Shared, `hwdec` while a filter needs frames on
    the CPU, the placement and subtitle options of Direct, `ao` and the audio device, `input-*`, scripts, `config`.
  - An option this libmpv doesn't know stops mpv starting (see "libmpv versions" in AGENTS.md): check each name with
    `option_info` once mpv is made and drop an unknown one with a note, so a typo can't stop every video playing.
  - Reach: every video, or the playlist's own, like the other video settings? Decide when building.
  - Also from Brick2892's fork (its "mpv Options"); credit as 10.34.
  - Not done instead: a libplacebo settings page like mpv.net's (shaders take mpv off its fast path, half the frames at
    4x1080p60, see Stage 7), or rows for `gpu-api` / `vo` / `gpu-context` (each default was picked for a bug found; those
    get measured in 14.11's runs instead).
  - **Built 2026-11-14 as a file, not a box (your call):** few would use a box, mostly to get round a driver bug or
    when asked to for a bug report. "Use mpv.conf" in Video Decoder's Experimental section, shown only with an MPV
    driver, with Open (makes the file from a commented template, else picks it out in its folder) and Check, both left
    of the switch and shown only while it's on (`Slot(before_field=True)`). Check
    lists each line skipped and why, as logging is off by default. `mpv.conf` beside `settings.ini`, read as each video
    opens, every video (`mpv_player/conf.py`). mpv's format: `name=value`, a name alone, `no-name`, `#`; profiles
    skipped. Set at once over the app's own just before `loadfile`, a value mpv won't take skipped; then left alone by
    the app (`set_option` passes them by), but for `hwdec`, which deinterlacing in a filter needs its way (skipped
    while one is on). Skipped as the app's own: window, `gpu-context`, sound device, view, tracks, playback, input,
    scripts, other files; `vo` / `gpu-api` only on Direct, Direct's subtitle layout only elsewhere. Checked: unit
    tests, real libmpv (Check and a playing video agree), Direct on `vo=gpu-next` draws. Credit in the CHANGELOG
    still due (12.5).
- [x] 10.36 Hardware VLC resizing like it's stuck in tar, against MPV: VLC's own, in `VLC.md`. Left as it is (your call,
  2026-11-15): VLC's pictures follow their cells late whatever is done, and MPV is the answer for live resizing.

## Stage 11: macOS

- [x] 11.1 Spike on `test_macos`: GL context, render API, VideoToolbox interop, readback. Closed 2026-11-15: the
  VM half below, VideoToolbox and speed on the real Mac (11.4)
  - **Run 2026-11-11 on `test_macos`, a VM with no GPU (macOS 15.1, Intel), Homebrew's libmpv 0.41.** The VM half is done;
    VideoToolbox and anything about speed need a real GPU, see 11.4.
  - Found with nothing set: Homebrew's `/usr/local/lib/libmpv.2.dylib`. Every driver offered, none greyed out.
  - GL: Qt's context on a `QOffscreenSurface` (`QtGLContext`) works as it is. The VM gives Apple's software renderer,
    OpenGL 2.1 (Qt's default on macOS is the legacy 2.1 profile, not 3.2 Core). The render API draws, frames read back right.
  - VideoToolbox: mpv looks at it and decodes on the CPU, as the VM has no hardware decoder. `hwdec-current` says `no`.
  - **Every MPV scenario passes:** all 10 on Hardware MPV, and the 4 that run on Software MPV (`ALSO_ON_SOFTWARE_MPV`).
  - Found and fixed on the way:
    - **A hang at startup, not MPV's, on any driver:** the resource tracker, forked as the process manager starts, can hang for
      good on macOS 15. A framework macOS loads on a thread of its own as the app comes up holds dyld's lock and waits for
      the Objective-C runtime's, and `fork()` takes them the other way round. 1 of the first 2 runs. It starts before Qt now
      (`init_app_env.start_resource_tracker`). Later forks (VLC's processes, the info reader) come once that load is over.
    - **Headphones with Homebrew's libmpv:** its FFmpeg has no `sofalizer`, and its "No such filter: 'sofalizer'" wasn't
      caught, so the room filter would have left no sound at all. It gives way to the plain mix now. And VLC.app keeps the room
      file in `Contents/MacOS/share/hrtfs`, not beside libVLC: found there now (it's used only by a libmpv that has the filter).
    - The scenarios took the menus in the system's language (the VM's is Russian): the driver sets English now.
      `mpv_hidden_cells` timed the window coming back from minimized, which macOS animates, 2 s on this VM: it times from
      the window being seen again now, where the cells were drawn at once.
- [x] 11.2 Same Stage 1 checks: in the scenarios above (`mpv_basics`: play, pause, resize, zoom, pan, pixel shapes, a file
  that says to turn it), on the VM. Settings: the Video Decoder page shows as on Windows, with no Output or Processes rows.
- [x] 11.3 Own CGL context only if the Qt one causes trouble. Closed 2026-11-15, not needed: Qt's context, asked as
  3.2 Core, does VideoToolbox, Copy and Shared on the real Mac (11.4)
- [ ] 11.4 **On a Mac with a real GPU** (a hackintosh is Intel with an AMD or Intel GPU; Apple Silicon needs a real Mac of its own,
  its libmpv arm64 and its OpenGL on Metal):
  - **Ready 2026-11-14: `test_macos_real`**, a hackintosh: i7-4790K, Intel HD 4600 (Haswell, drivers put back by OpenCore
    Legacy Patcher), macOS 15.8.3, one 1080p screen. OpenGL in hardware, 2.1 and 4.1 Core; VideoToolbox decodes H.264 only
    (HEVC, VP9, AV1 on the CPU). MacPorts libmpv 0.42 (Homebrew has no Intel Mac builds any more), VLC 3.0.24. First
    `mpv_basics` on Hardware MPV passed, decoding `videotoolbox-copy`. Not there: Retina, two GPUs, Apple Silicon.
  - **Run overnight 2026-11-15**, in real windows on the Mac's screen (`REAL_APP_QT_PLATFORM=cocoa`).
  - [x] Every scenario on Hardware MPV, Software MPV and VLC: **all 77 pass** (`external_audio_jump` the known VLC bug),
    on Copy and again on Shared. The first run failed 13, none of them MPV's:
    - **VLC Software showed no picture of a file that says to turn it.** On a Mac with a hardware decoder VLC 3 decodes
      H.264 with VideoToolbox, a decoder of its own beside avcodec that `avcodec-hw=none` doesn't reach. Its frames
      (`CVPN`) can't go through the `transform` filter the turn needs, so the video output failed to open. The VM has no
      hardware decoder and never showed it. VLC Software takes `no-videotoolbox` too on macOS now
      (`software_decoding_options`).
    - The drags of 8 layout scenarios: Qt's `QCursor.setPos` on macOS posts a mouse move of its own, with no button
      held, which ends the drag as let go of elsewhere. The driver moves the pointer with `CGWarpMouseCursorPosition`
      on cocoa, which posts nothing. `grid_lines` came back to the spot it had left from, and Qt drops a move to
      where the last one was: it comes from elsewhere now.
    - `mpv_basics` on Software MPV checked Picture quality, which Software MPV doesn't take (it scales on the CPU): a
      scenario bug since 10.34, never run on Software MPV before. Skipped there now.
  - [x] VideoToolbox, and **OpenGL 3.2 Core**. In Qt's default context, the legacy 2.1 profile, mpv has no VideoToolbox
    interop: `auto` lands on `videotoolbox-copy`, and `hwdec=videotoolbox` falls to the CPU altogether. In a 3.2 Core
    context `auto` takes `videotoolbox` with the frames kept on the GPU: H.264, HEVC, 10-bit HEVC (`p010`), 4K. The
    render thread's context is asked as 3.2 Core on macOS now (`macos_gl_format`), Qt's own if a Mac has no such
    context. HEVC goes through VideoToolbox too, which decodes it on the CPU on a GPU with no HEVC (Haswell).
    Colours: every hardware path gave the same frames, within 0.5 of Software MPV's on SMPTE bars (BT.709, limited).
  - [x] The bench in a real window, 1080p clips (fps a cell; `tests/real_app/bench` runs on macOS now, GPU load from
    `ioreg`):

    | | mix ×4 | mix ×9 | mix ×16 | H.264 60p ×4 | ×9 | ×16 |
    |---|---|---|---|---|---|---|
    | Hardware MPV, Copy, 2.1 (before) | 29 | 10 | 5 | 34 | 7 | — |
    | Hardware MPV, Copy, 3.2 Core | 39 | 27 | 14 | 50 | 30 | 10.5 |
    | **Hardware MPV, Shared, 3.2 Core** | **43** | **39** | **25** | **60** | **60** | 11 |
    | Software MPV | 44 | 38 | 21 | | | |
    | VLC Software (one process or many) | 43 | 25 | 15 | | | |
    | VLC Hardware | 44 | 29 | 18, 2 frozen | 60 | 32, slowest 13 | 11, 3 frozen |

    Copy is held up by reading frames back: at 16 cells a render round took 68 ms, 58 of them reading back (3.6 ms a
    frame). Shared reads none back and took the least CPU of all (130% at 9 cells against Software MPV's 593%). VLC
    Software filled all 8 threads by 9 cells, the GUI stalling up to 1.4 s at 16. VLC Hardware is as good at 4, on less
    CPU (it draws into a view of its own), and behind from 9; at 16 some of its videos showed no new frame at all (0 fps
    the whole measure). H.264 60p at 16 is the HD 4600's own limit. VLC Hardware's rate is VLC's own count of pictures
    shown, and no scenario sees its picture (its own view, out of `grab()`'s reach).
  - [x] **Shared output on macOS**, hidden till now: worth it, and **the default there** (`settings.py`). Qt's contexts
    are all 3.2 Core then (`QSurfaceFormat.setDefaultFormat`, as two profiles can't share), the share group takes Qt's
    context itself where Windows and Linux take WGL's and EGL's, and the render thread's context shares with it.
    Video output shows on macOS, with Copy and Shared (no Direct). **Your call:** Shared as macOS's default.
  - [x] Black rows or columns under the pictures, as NVIDIA's padding gave on Windows (13.8): none on macOS. 9 cells of
    a flat grey clip, filled, the window stepped through 45 sizes, captured from the screen right after each resize
    and settled: no dark edge in 90 captures on Shared, Copy, Software MPV, VLC Software or VLC Hardware.
  - Review fixes: the render thread's context is checked to really share with Qt's (Qt makes one of its own, saying
    nothing, when it can't), and takes the group's own format; no fallback to 2.1 while sharing. The window-size
    flush (`gl_window_size`) found no Qt on macOS and was off: it takes the framework PyQt5 carries now.
  - A stall that isn't the app's: `window.raise_()` on cocoa now and then takes 2-3 s in the window server, a bare Qt
    window too (1 in 6). It froze the GUI on opening a video and failed `mpv_transport`'s speed check (time not told
    for 2.6 s). Not seen in the night's four full runs; it came with a screen-sharing session on the Mac.
  - Found on the way, not MPV's:
    - **Media keys in the background are off on macOS** with Python 3.11 and up: pyobjc 13.0's CoreMedia (30 Oct, the
      latest) links `@rpath/libswiftCoreMedia.dylib` with no path to `/usr/lib/swift`, so it won't load, and the
      session gives up. Pinning pyobjc below 13 until a fixed one would do it. **Your call.**
      **Fixed 2026-11-15** (`e7091ea`) without pinning: MediaPlayer is loaded through pyobjc-core alone, its
      wrapper and CoreMedia's dropped. Checked on the Mac on Python 3.13: the session in 116 ms, play/pause and
      next sent through MediaRemote arrive.
      **And in the package (Python 3.14), 2026-11-15:** play/pause and next pressed as a keyboard does (a
      system-defined event posted with `CGEventPost`) reach the app's session every time, with Finder in front too.
      `MRMediaRemoteSendCommand`, used before, is no test: since macOS 15.4 MediaRemote's private calls are locked
      down, and its commands arrived now and then or not at all, the bare session's too. Media apps left open
      (QuickTime Player, Safari) take the keys as well.
    - VLC Software: a screenshot asked for just as a short clip loops round finds no frame, VLC's output being made
      again, and says so in a box. Seen once, in `aspect_ratio`.
    - `screencapture` over ssh brought up macOS's own question about `com.apple.sshd-session` recording the screen:
      left unanswered on the Mac.
  - Not run: a Retina screen (or a 4K one scaled): frames at the screen's pixels, cells, zoom and screenshots. Two GPUs
    (which one Qt's context draws on). Sleep and wake, a screen unplugged, the window moved between screens of different
    scales. Apple Silicon.
  - Video memory: Auto reads none on macOS, so it never decodes on the CPU. Metal says how much a GPU has, if that's needed.
  - **Open (2026-11-15): only what this Mac can't run**, the "Not run" above. Everything it can is done; Apple
    Silicon needs a real Mac of its own.

## Stage 12: Packaging and release

- [ ] 12.1 **Decided (2026-11-09): libmpv is bundled everywhere, with libVLC**, in every package; no split packages over some
  60 MB. Done after testing and fixing. Windows has no system libmpv and no standard installer for it. The DLL here is 117 MB, a
  smaller LGPL build may do. With libmpv always there, the `Get MPV` link and "How to fix" are only for running from source
  - **Your call (2026-11-14): the full build, not an LGPL one.**
  - Windows: `build_win.sh` takes shinchiro's `mpv-dev` build (the one mpv.io points to), x86_64 or i686, from the
    SourceForge mirror: GitHub keeps only the last 30 daily builds, SourceForge a weekly one back to 2020. Pinned to
    `20261108-git-55d3feb45c` with its SHA-256, unpacked with 7z (on the runner), `libmpv-2.dll` alone into
    `GridPlayer\libmpv`, where `find_libmpv` already looks. 116 MB on x64, 95 MB on x86, 30 MB as 7z. mpv needs Windows 10
    1607 or later: on 7 and 8 it won't load, and VLC stands in as for a missing libmpv.
  - **Your call (2026-11-14): AppImage on a newer base** rather than libmpv built by us. EL8 (`manylinux_2_28`) has libmpv 0.34
    only; `manylinux_2_34` (AlmaLinux 9) has EPEL's 0.39 (client API 2.3) with libplacebo6, and VLC 3.0.24 now comes from EPEL too,
    with RPM Fusion's `vlc-plugins-freeworld`. EPEL's ffmpeg leaves out H.264, HEVC and AAC: `dnf swap ffmpeg-free ffmpeg` puts RPM
    Fusion's 7.1 in its place, same sonames, both libraries take it. No Python AppImage is made for 2_34, 2_28's runs there.
    Drops Ubuntu 20.04, Debian 10 and 11, RHEL 8 (README says so). `build.sh` used to start a kept `appimage_build` container
    whatever its image: one of another image is now made anew. 124 MB to 210 MB.
  - linuxdeploy bundled EL9's libva, libvdpau, libvulkan, libwayland, libGLESv2, libpipewire and libpulse, which a system has with
    drivers and plugins of its own: EL9's libva looks for VAAPI drivers in `/usr/lib64/dri` only (Ubuntu's are elsewhere), and host
    Mesa would get EL9's libwayland. Nor will the system's alone do: RPM Fusion's ffmpeg 7.1 needs `vaMapBuffer2`, libva 2.21,
    and with Ubuntu 24.04's 2.20 libmpv won't load (VLC still did). They go in `usr/lib/fallback/<soname>/` under their full file
    names, and `AppRun` puts one on the path only when the system has none or an older one (`strverscmp` of the file names the
    two lead to), with `LIBVA_DRIVERS_PATH` set to the usual driver folders when the libva is ours.
  - Checked from the AppImage through its `AppRun`: Ubuntu 24.04 VM, libva, libvulkan and libpipewire ours, VLC and libmpv 0.39 play
    H.264 + AAC, VAAPI looks in Ubuntu's folder (no driver in the VM). Debian 13 on `test_gpu`, Intel i965: all the system's but
    libvulkan and libpipewire, `vaapi-copy` decoding. A bare Ubuntu container: all twelve ours.
  - **Your call (2026-11-14): Snap waits for Qt 6.** core22 has libmpv 0.34, and the kde-neon extension for Qt 5 is on core22
    only; with Qt 6 it moves to core24, whose libmpv2 is 0.37. Until then the Snap is VLC only.
  - **Your call (2026-11-15): an arm64 AppImage with Qt 6**, beside the Snap's move. PyPI has no Linux aarch64 wheel of
    PyQt5 or PyQt5-Qt5, of any version; on Qt 5 it would take PyQt5 built against EL9's Qt 5.15.9, a second Qt to keep up.
    PyQt6 and PyQt6-Qt6 have `manylinux_2_39_aarch64` wheels: glibc 2.39, so a newer base than x64's (Ubuntu 24.04+,
    Debian 13+, Fedora 40+), on GitHub's arm runners. Until then arm64 has the Flatpak: Flathub builds aarch64 too (no
    `flathub.json` holds it back), the libmpv module untried there before the next release.
  - **Your call (2026-11-14): macOS after its tests (11.4)**, on the real Mac.
  - **macOS's libmpv, looked for 2026-11-15:** Homebrew has no Intel bottles of mpv any more; IINA's and media-kit's
    builds have no Vulkan; mpv's own CI makes only the player app. **MPVKit** (GPL, mpv 0.41, FFmpeg 9.0.2, libplacebo,
    MoltenVK) has both architectures, macOS 12 and up, as static xcframeworks: 30 of them (pinned, SHA-256 from its
    `Package.swift`) linked by clang into one `libmpv.2.dylib`, 56 MB for x86_64, exporting only `mpv_*`, needing only
    the system's frameworks and Swift. `mpv_basics` passes on it, Copy and Shared, zero-copy `videotoolbox`.
  - **Bench, the real Mac, 1080p, fps a cell (CPU %, GPU busy %), MacPorts 0.42 against MPVKit 0.41:**

    | | mix ×4 | mix ×9 | mix ×16 | H.264 60p ×4 | ×9 | ×16 |
    |---|---|---|---|---|---|---|
    | Shared, MacPorts | 43 (60, 29) | 39 (123, 57) | 24 (177, 85) | 60 (83, 43) | 60 (149, 79) | 11 |
    | Shared, MPVKit | 43 (52, 23) | 39 (101, 38) | **36** (206, 63) | 60 (68, 27) | 60 (131, 47) | 12 |
    | Copy, MacPorts | 41 | 26 | (run cut short) | 52 | 29 | 11 |
    | Copy, MPVKit | 42 | 31 | 23 | 58 | 39 | 12 |
    | Direct (prototype), MPVKit | 44 (39) | 39 (82) | 37 (190) | 2 of 4 frozen | 2 of 9 frozen | 13 |

  - **Direct on macOS, prototype:** MPVKit's own `moltenvk` context (its patch) draws with Vulkan into a `CAMetalLayer`
    passed as `wid`; the layer in a plain `NSView` of our own inside the cell's native view (Qt draws over a layer set on
    its own view). It draws, `videotoolbox`, no drops, but never follows a resize: the context reads the layer's size
    only on reconfig, and nothing an app can set reconfigures it on macOS (`android-surface-size` and
    `d3d11-composition-size` aren't built there). It would take our own libmpv with a patch, or MPVKit taking one. As
    fast as Shared, a little less CPU, and two cells of 1080p60 froze. Proposed: not offered on macOS for now (your
    call open).
  - **Your call (2026-11-15): the Mac ships both, as Linux does,** MPVKit's libmpv bundled and Hardware MPV (Shared)
    the default there; **VLC leaves the Mac package in the release after with Linux's**, if nothing serious comes back
    from Mac users. Until then VLC is also what plays on macOS 10.15 and 11, where MPVKit's libmpv (macOS 12 and up)
    won't load.
  - **Built 2026-11-15:** `build_mac.sh` fetches what `libmpv_mac.txt` lists (each checked by its SHA-256), takes the
    target architecture's slice and links `libmpv.2.dylib` into `Contents/MacOS/libmpv`, failing if `mpv_create` isn't
    there or anything but the system is needed; licences in `Contents/Resources/licenses` (GridPlayer's, VLC's from
    its repository at the version, as the `.dmg` has none, mpv's and MPVKit's) with `SOURCES.txt`. The macOS default
    driver is Hardware MPV now (`settings.py`), as on Linux. Checked: the x86_64 `.app` built on the real Mac (438 MB,
    libVLC 107, libmpv 53) plays with its own libmpv on fresh settings; the arm64 link made there too (54 MB, signed
    ad hoc by the linker), not run.
  - Found by the built app: PyInstaller left out `PyQt5._QOpenGLFunctions_4_1_Core`, which `versionFunctions()`
    imports by name, so Shared crashed at start (Windows the same, with Shared picked). Both specs take every
    `_QOpenGLFunctions_*` now, and `qt_gl_functions` falls back to its ctypes calls on an `ImportError`. The AppImage
    and Snap had them taken out on purpose (`blacklist_pyqt.txt`); they keep them now, not yet built.
  - `get.videolan.org` sent the Mac to a mirror at 5 KB/s for the 63 MB `.dmg` (3 hours); VideoLAN's own server took
    7 s. Both builds take VLC from `download.videolan.org` now and check it against the SHA-256 VideoLAN publishes beside
    it, pinned in the script (the Windows zip: 8 s, matched).
  - The DMG (2026-11-15): `build_dmg.sh` on the x86_64 `.app`, by `hdiutil` as the Mac has no `create-dmg` (CI
    installs it): 204 MB. The app run from the mounted image on fresh settings loads its own libmpv and plays two
    clips through VideoToolbox, nothing in the log.
  - **Signed ad hoc** (2026-11-15, `codesign --force --deep --sign -`, no Apple account): PyInstaller signs the bundle
    before libVLC, libmpv and the licences go in, so its seal was broken ("a sealed resource is missing or invalid"),
    which macOS shows a downloaded app as "damaged" for: the README's `xattr` step. The 0.5.5 DMGs had it too, from
    libVLC. `build_mac.sh` signs it again at the end and verifies it (2 s). Quarantined, Gatekeeper's verdict went
    from the broken seal to a plain "rejected", an unknown developer's app that Open Anyway lets through. Not
    notarized, which takes a paid Apple account. The signed app plays as before.
  - The package's own (2026-11-15): a file opened from Finder (`open -a`) starts it and plays; one opened while it runs
    goes into the same window; the menu bar icon shows. macOS has no instance socket (none is set up there): it sends
    files to the running app itself, so the binary started a second time by hand is a second app, as by design.
    VLC stands in for a libmpv that won't load (a file that isn't one in its place, as macOS 10.15 and 11 will
    have): VLC Hardware, one process, both clips playing.
  - **The MPV scenarios on MPVKit's libmpv** (2026-11-15, the one shipped; the overnight run had MacPorts' 0.42): 38 of 42
    pass on Shared and on Copy, 14 minutes each. The 4 are `mpv_deinterlace` and `mpv_subtitles`, on Hardware and
    Software MPV: MPVKit's FFmpeg has 45 video filters, without `field`, `separatefields`, `convolution`,
    `fieldmatch` and `decimate`, so Discard, Blend, Bob, Linear and IVTC can't start (a log line each; Mean, X, Yadif,
    Yadif 2x and Phosphor can), and no VobSub demuxer, so an `.idx`/`.sub` pair can't be added (the scenario stops
    there, so what it checks after that went unchecked). MacPorts' build takes all of them. No `sofalizer` either,
    which Headphones already gives way for. **Your call (2026-11-15): grey them out.**
  - Built: `mpv_player/abilities.py` asks a libmpv once a run, with the first video's mpv, of an mpv of its own (70 ms
    on the Mac): its demuxers (`demuxer-lavf-list`), its filters (what it lists for `vf set lavfi=[help]`) and zimg
    (whether `zimg-scaler` is an option). The deinterlace modes whose filters it hasn't got are greyed out in the menu
    and in Settings (with "Not available in this MPV"), and not tried (Auto in their place, as for one refused). A
    subtitle file beside the video in a format it can't read is offered greyed out: MPVKit reads only `.srt`,
    `.ass`/`.ssa`, `.vtt` and `.mks` of the formats offered, not VobSub, MicroDVD `.sub`, SAMI and the rest. Not
    known yet, or not asked, is everything there, as before.
  - **Found on the way: Software MPV showed no subtitles with MPVKit's libmpv** ("osd: Failed rendering OSD" for
    every frame): with no zimg mpv can't draw them onto `bgra`. Software MPV takes `bgr0` there, which its libswscale
    fills the fourth byte of; `bgra` stays where zimg is, which leaves `bgr0`'s at 0. MPVKit, Software MPV: basics,
    view and subtitles pass with it.
  - "Add External Subtitles…" lists only the formats it reads, and one picked anyway through "All" is told of
    ("MPV can't read these subtitle files", VLC named as reading them) and left out.
  - Before macOS 12, where the package's libmpv won't load, VLC (one process) is the default: with MPV, a box said
    "libmpv won't load" at every launch. It also held up quitting by AppleScript, a box being open: seen in the VLC
    fallback check, not a fault of its own.
  - The README (12.5) says it: both libraries in every package, the Snap VLC only till Qt 6, Windows 10 and 11, both
    DMGs, MPV on macOS 12 and up, the Video output choices, libmpv only for UV and source installs, the attributions
    and Brick2892's fork.
  - **Your call (2026-11-15): the builds on Python 3.14**, from 3.10: Windows (x64 and x86), macOS, AppImage, the Flatpak's and
    PyPI's jobs. Not the Snap's, which stays on 22.04 until Qt 6. Windows 7 was gone already: Python 3.9 and later don't run
    there, and the builds have been on 3.10 since 0.5.4 (`763745c`), so the README's "Windows 7, 8" is stale (12.5).
    `requires-python` stays at 3.10, and `just build-requirements` resolves from 3.10 (`--python-version`), not from whatever
    runs it: run on 3.14 it had pinned what 3.10 can't install (`pycparser` 3.12, `websockets` 17), and the Flatpak's runtime and
    the Snap each have a Python of their own. The AppImage's base is kept by version (`base-3.14.AppImage`; a kept
    `base.AppImage` would have been 3.10), picked from the free-threaded `cp314t` one beside it, and a failed fetch stops the build.
  - **Your call (2026-11-15): Linux ships both, MPV the default there** (`settings.py`, Hardware MPV); from source without
    libmpv VLC stands in. Who never changed the driver moves to MPV, as a setting at its default isn't saved. **VLC leaves the
    Linux packages in the release after, if MPV holds up**, with the Snap's move to Qt 6; then Settings must hide VLC's choices
    where it can't be had, not offer "How to fix".
  - **Your call (2026-11-16): MPV the default on Windows too**, with Direct output; VLC stays in the Windows packages.
    From source without libmpv, VLC stands in, as on Linux.
  - Flatpak: `scripts/flatpak/libmpv/libmpv.yml`, after VLC's module (whose cache stays good): ffmpeg 7.1.5, libass 0.17.5,
    libplacebo v7.387.0 (OpenGL only), mpv v0.42.0 as libmpv alone, no Lua, JavaScript, discs or archives. Its own, though the
    runtime has ffmpeg 7.1: VLC's module leaves ffmpeg 4.4's headers and `libavcodec.so` in `/app`, which a build against the
    runtime's would take. Built after, its headers are the ones about, and each library has its own name (`.so.61` beside
    VLC's `.so.58`). Needs nothing of VLC's, so VLC's module can go as it is.
  - The build's requirements, from 3.10, have two of some packages (`curl-cffi` 0.16.3 below 3.11, 0.17.0 from it), and
    `flatpak-pip-generator` made a module of each, the first unfindable: `generate_dependencies.sh` compiles its own list
    for the Python of the runtime (3.13, asked of the SDK).
  - Built without Lua, mpv has no `ytdl` option, and the player set it whatever: "mpv option does not exist", no video
    started. `ytdl` is the hook script's switch, so it joined `_BUILT_IN_SCRIPTS`, set only where mpv has it; the readers
    (`_BuiltInScripts`, `check_conf`) no longer ask it. Any libmpv without Lua, a user's own too, works now.
  - Checked on the Ubuntu 24.04 VM, built with the module cache of the earlier build (VLC's modules cache hits): 63 MB
    bundle; inside, both libraries load from `/app/lib` and play H.264 + AAC in one process; the app with no settings
    starts on Hardware MPV, EGL on xcb, the picture on screen.
  - Checked: both Windows builds on 3.14 (x64 341 MB, x86 297 MB); the AppImage on 3.14 (217 MB) on the Ubuntu VM's desktop, VLC
    Hardware with its process started by `forkserver` (3.14's default on Linux) and Hardware MPV each playing two clips.
- [ ] 12.2 PyInstaller, AppImage, Flatpak, Snap, Chocolatey as decided. Fail loudly, keep the
  existing tools. Flatpak and Snap can't see a system libmpv, so the README's "How to fix" won't
  work there unless they ship it: check, and say so in the README
  - 2026-11-16: each package built is started once in `build.yml`, `GridPlayer --self-check tests/data/self_check.mp4`
    (`main/self_check.py`): Qt's platform, libVLC and libmpv found and loaded, a 1 s H.264 + AAC clip decoded by each,
    exit 1 otherwise. The Windows portable zip, the app in each DMG (with `codesign --verify --deep --strict` first) and
    the AppImage under Xvfb. Run on a local Windows PyInstaller build: all five checks pass, the windowed exe prints to
    redirected output. VLC on Windows refuses a `C:/` path, so the check passes it native.
- [x] 12.3 About box, licences (python-mpv and libmpv are GPL or LGPL, compatible)
  - MPV and python-mpv were in the About box already. Every libmpv shipped is a GPL build (shinchiro's, EPEL's, the
    Flatpak's), so MPV says "GPL 2.0 or later" rather than "or LGPL", and FFmpeg, inside both libraries, is listed too.
  - No package carried a licence: not GridPlayer's, VLC's nor mpv's. Windows: `licenses\` beside the exe, with GridPlayer's
    GPL 3, VLC's `COPYING.txt` from its zip, mpv's `Copyright` and `LICENSE.GPL` at the build's commit (GitHub takes the short
    one in the build's name), and `SOURCES.txt`: mpv's commit, shinchiro's build files, VLC's source tarball, each build's
    URL. AppImage: between two linuxdeploy runs, the package each bundled library came from (`rpm -qf`), their licence folders
    into `usr/share/licenses`, and `SOURCES.txt` listing them with their source RPMs and the three repositories (161
    folders, 215 packages). Flatpak: flatpak-builder copies each module's licence (`COPYING*`, `Copyright`, `LICEN*`) into
    `share/licenses/<id>/<module>`, and then the module's `cleanup` runs: VLC's, both ffmpegs' and mpv's took all of `/share`,
    their licences with it (`license-files` changed nothing). They now name what they leave out. macOS with its packaging,
    after 11.4.
- [x] 12.4 Real-app job in CI for mpv, if the runners can get a GL context
  - **Built 2026-11-15:** `real-app-mpv` in `test.yml`, beside the VLC job, which skips the MPV scenarios with no libmpv
    there. Ubuntu's `libmpv2` (0.37, the oldest taken) and Mesa's EGL and llvmpipe, `pytest -m real_app -k mpv`: Hardware
    MPV on software GL, Software MPV, and the VLC scenarios held to both. Checked in a bare `ubuntu:24.04` container on
    `test_ubuntu` with the job's packages only: 42 passed in 11 minutes. To tick once it has passed on GitHub.
  - 2026-11-16: passed on GitHub (14 minutes). The unit tests failed there, twice on Linux only: fixed, and the unit
    tests now run on Windows and macOS too.
  - 2026-11-16, next push: `ubuntu-latest` had become 26.04 (libmpv 0.41, Mesa 26), and `playback` on Hardware MPV and
    `mpv_audio` hung now and then. Caught in an `ubuntu:26.04` container on `test_ubuntu` with gdb: with no sound
    server, giving up on PipeWire's output, libmpv waits in `pw_thread_loop_stop` for a PipeWire thread idle in
    `epoll_wait`, for good. Hit when listing the audio devices (every video's load waited on its lock) and when a
    video opens its sound. Fixed: the list has 5 s and isn't asked again after, PipeWire's left out of `ao` with no
    PipeWire socket. 4 failures in 10 became 15 passes of 15 on 1.5 CPUs, and all 47 MPV scenarios passed there.
  - Then (your call): both real-app jobs run on `ubuntu-24.04` (libmpv 0.37) and `ubuntu-26.04` (0.41) side by side,
    and `real-app-desktop` runs every scenario on Windows (VLC and Software MPV: a runner has no OpenGL for Hardware
    MPV, `REAL_APP_MPV_DRIVERS=mpv_sw`; libmpv as the package has it, pins in `scripts/windows/libmpv_pins.sh`) and
    macOS (both MPVs, Homebrew's libmpv). It doesn't hold a release up (`continue-on-error`) until it has passed there.
  - Its first run: Windows passed (16 min) and holds releases up from now; macOS never started, GitHub had no arm64
    runner free. `real-app (ubuntu-26.04)` failed `cookies`, as it had once on Windows here: VLC is given 1 s to know a
    video's length before it's taken for a live stream, and an HLS video through the proxy took 0.2 to 1 s, now and
    then more. 3 s now (`LENGTH_WAIT_S`); every VLC scenario passed on 26.04 with it.
  - Second run: macOS's runner ran at last, and its unit tests passed. Its real-app job: every VLC scenario passed, and
    each of the 11 Hardware MPV ones hung till its 5 minutes were up, so the job ran out of its hour at 46% and nothing
    was kept. macOS runs Software MPV only now, as Windows does, and a cancelled run's files are kept. Why Hardware MPV
    hangs on a GitHub macOS VM (no GPU) is not known yet; on the real Mac it plays.
  - A run still going after 280 s now writes every thread's stack into `hung.txt` and ends (`REAL_APP_HANG_S`,
    faulthandler), which the test fails with; a job on trial stops at its third failure (`--maxfail=3`).
- [x] 12.5 README, CHANGELOG. Short trap list in `AGENTS.md`, rules only
  - 2026-11-16: CHANGELOG from `just changelog-since-last`, Brick2892's fork credited for Picture quality and
    `mpv.conf`; AGENTS.md: what a libmpv build lacks is asked of it (`abilities.py`), not assumed from the platform.
- [ ] 12.6 Remove this file, or keep it as you like

## Stage 13: GL output, a choice beside readback

**Your call (2026-11-08):** readback stays, as the default, and GL becomes a choice on MPV's row, the way Processes is on VLC's,
even if the shaking during a window resize can't be fixed. Why: `MPV_PERFORMANCE.md`, "Readback against GL", 20-35 points of a
core less while the decoder keeps up, at the same frame rates. Suggested words: "Video output", "Steady" and "Fast".

- [x] 13.1 Windows spike in the real app: a `QOpenGLWidget` a cell, the render thread's textures shared with Qt's contexts, nothing
  read back. Check the picture, the CPU against readback, and what happens when the first GL widget makes Qt make the window anew:
  its handle changes, and the tray, media keys and VLC's overlays hold it. Live driver switches both ways.
  - Built behind `GP_MPV_GL_OUTPUT=1` for now. `QtShareGroup` takes a context of Qt's share group, and the render thread's WGL context
    joins it with `wglShareLists`. Each video gets three textures instead of three pixel buffers, one `glFinish` a round before they go
    to the GUI. `MpvGLVideoSurface` draws with `QOpenGLTextureBlitter`, flips included. The placing is shared with the painted surface
    through `VideoSurfaceView`.
  - Needs `AA_ShareOpenGLContexts` and `AA_UseDesktopOpenGL` before the `QApplication`. With them the window keeps its handle: Qt
    doesn't make it anew. MPV to VLC Hardware and back works, VLC's output works in the window, and the cells' controls draw over the
    GL picture.
  - Real app, RTX 3060, real window on another desktop, 1080p60, app CPU with the bench's own 5.5 in both: 1 cell 51% to 19%, 4 cells
    55% to 36%, 9 cells 81% to 69%. Same frame rates. A `QPainter` each frame to fill the bars cost 10 points at 4 cells: the surface
    clears with GL instead.
  - Opening a cell holds the GUI up for about 70 ms more, Qt making a context for each `QOpenGLWidget`: 0.7 s at 9 cells. See 13.5.
    Found by the user as a freeze before the cells came up, opening a playlist, each time: `QOpenGLContext.create` takes
    38-40 ms on NVIDIA (a bare WGL context 12 ms), and as a cell's frame is shown only once it has loaded, every surface got
    its context at once as the frames appeared. The surfaces now start one at a time, 10 ms apart, as soon as they are in the
    window, shown or not (`_StartQueue` in `video_surface_gl.py`, the start Qt makes on a show or a resize held back), and a
    cell says it has loaded only once its surface draws, so the wait is part of its loading. 9 cells: the worst hold-up
    730 ms to 180-330 ms (readback has the same, making the cells), then one of 50-80 ms a cell; all on show in 1.9 s.
    Since replaced by one surface for the window, 13.5: one context made, not one a cell.
- [x] 13.2 Linux spike. Results on `test_gpu`:
  - Qt draws with EGL, `QT_XCB_GL_INTEGRATION=xcb_egl`. The render thread's EGL context is made on Qt's EGL display and shares with
    Qt's context. mpv keeps its own X connection for VAAPI, still `vaapi`, not a copy.
  - **VLC's forked processes break it.** MPV, then VLC Hardware multi-process, then MPV: the app aborts in libmpv's render or in
    Qt's compose, both runs. VLC Hardware single process, or MPV Software in between, doesn't; readback doesn't either. With the
    processes started by `forkserver`, which Python 3.14 makes the default on Linux anyway, it passes, twice. The app's process code
    already handles a start that isn't a fork, as on Windows.
  - Real app, 1080p60, app CPU: 1 cell 52% to 21%, 4 cells 68% to 37%, 9 cells 83% to 54%. The display server's CPU goes from 16-20%
    to 2%, so the whole machine from 75% to 29%, 90% to 46% and 113% to 52%. Same frame rates.
- [x] 13.3 The setting: default, field and page, restart where 13.1 and 13.2 say so. Unit tests, and the real-app scenarios on both
  outputs.
  - `player/mpv_output`, "Video output" with "Steady" and "Fast" as buttons under the Decoder, greyed out unless it's MPV, not shown
    on macOS. Read as the app starts, as Qt's GL can only be set up then, so a change asks for a restart on both systems.
    `init_app_env` sets up Qt for it only when it's on and MPV plays this session (not VLC picked, nor standing in for a
    missing libmpv): VLC users get nothing new, Fast kept or not. A switch the session didn't start with asks for a
    restart, one back to how it started doesn't. With it on, on Linux, VLC's processes start from `forkserver`. Should
    Qt's GL not come up, or the render thread's context not share with it (tried on the GUI thread before any cell is
    made), frames are read back as before.
  - When a video goes, a reload or a cell closing, the texture on show stays on show: the surface takes it from the renderer and
    deletes it once another comes, or as the surface goes, through the share group's own context: a hidden cell that never
    painted, or never had a context, deletes it all the same. A video that fails to render takes its frame off show, as the
    renderer has deleted it.
  - Qt 5.15 sizes a QOpenGLWidget's framebuffer rounded and sets paintGL's viewport cut down (101 px at 1.5: 152 and 151), so
    the surface sets the viewport to the whole framebuffer itself.
  - Bug found: `QOpenGLTextureBlitter.sourceTransform` with a top-left origin counts the part asked for from the bottom. The whole
    picture came out right, a zoomed or anchored part didn't: `mpv_view` caught it.
  - All 9 MPV scenarios pass on GL on `test_gpu`, and on Windows in a real window on another desktop, but `mpv_hidden_cells`
    there, as bringing a window back from minimized brings it to the front. `REAL_APP_MPV_OUTPUT=gl` runs any scenario on it,
    and the bench takes `--env MPV_OUTPUT=gl`. The real-app suite needs a real window for it, so its job runs on readback.
- [x] 13.4 Screenshots and the pause snapshot with GL: the pixels read from the texture when asked, not every frame.
  - `frame_image` draws the texture into a framebuffer of its own and reads that. The screenshot checks of `mpv_view`,
    `mpv_subtitles` and `mpv_deinterlace` pass on GL. The pause snapshot needed nothing: the last frame stays drawn.
- [x] 13.5 One GL surface for the whole window rather than one a cell. Built, in place of a surface a cell.
  - `widgets/video_surface_gl.py`: `GLGridSurface`, one `QOpenGLWidget` the size of the window under all of its other widgets,
    made as the first video in it has a frame, draws every cell's texture where the cell's `GLVideoSurface` is, lowest first,
    cut to what its parents leave in view (`placed_surfaces`, worked out again only once something in the way moves, changes
    size, shows, hides or is stacked differently). A cell's `GLVideoSurface` is a plain widget that clears its part of the
    window to see-through with `CompositionMode_Source`, as Qt does under a `QOpenGLWidget`: tiles over one another still hide
    what's under them, controls included. One context, one framebuffer, one blitter. The start queue is gone: a cell's surface
    draws once the grid surface is up, still part of the cell loading.
  - `grab()` of an MPV frame paints the picture into the surface (`GLVideoSurface.grabbing`): PyQt has no `backingStore()` to
    tell a grab from the window, and guessing by size failed on a cell as big as the window. A grab of the whole window has
    holes where the videos are; nothing in the app grabs.
  - Measured, RTX 3060, real window on another desktop, 1920x1061, 360p60 clips, 15 s (GUI thread / fps / dropped a second):
    16 cells readback 14.7% / 59.8 / 2.7, a surface a cell 27.3% / 59.8 / 3.0, one surface 6.4% / 59.7 / 4.9.
    36 cells readback 21.5% / 49.3 / 378, a surface a cell 51.0% / 43.2 / 612, one surface 14.5% / 59.7 / 10.9.
    Its paint takes 0.9 ms at 36 cells (1.7 ms when the prototype worked out the places each paint).
  - Resizing, each step waiting for the window to be swapped, 360p60 cells playing: 4 cells 71 sizes a second against 69, 16
    cells 66 against 38.
  - Adding and closing videos, the window read about every millisecond (BitBlt) for 2-5 s around each: no frame with a cell
    gone black or grey, either way. A new cell is black until its first frame, as before. The GUI is held up for 50-65 ms
    adding one, as before: the render thread making mpv's render context for it (61 ms), the driver holding GL meanwhile.
    Closing one holds it up 120-190 ms, either way.
  - Your report: the pointer over the cells, their controls coming up, and tiny videos lag. With GL, Qt puts all of the window
    together and swaps it for anything painted anew, and a cell's time and bar are painted apart from the frames: 110-120 swaps
    a second with the controls up, each waiting for the screen. A surface a cell had it too. 16 360p60 cells, frames reaching
    each cell a second (idle / pointer going over them / all controls up), three runs each: a surface a cell 53-55 / 34-52 /
    50-54, one surface 52-53 / 21-53 / 47-49, readback 55 / 56 / 56. Fix: the window's filter in `utils/gl_window_size.py`,
    beside the size fix, holds its update requests to one a screen refresh (`_is_too_soon`, the refresh read as the renderer
    reads it, `refresh_interval_s`), so the controls go with the next frames: 52-53 / 55 / 55-56, 65-70 swaps a second.
    Resizing isn't held (Qt paints for the system without a request): 79 and 70 sizes a second at 4 and 16 cells.
  - All 9 MPV scenarios pass on Windows (8: not `mpv_hidden_cells` on the away desktop) and on `test_gpu`. Free Tiles overlap
    checked by eye in both orders on both. Not done: macOS (Fast isn't offered there), Linux numbers, the real screen.
- [x] 13.6 The shaking during a window resize, Windows.
  - Cause: Qt takes a new window size from its own queue, and a paint can come before it: one asked for before, or the one it
    makes at once when the window shrinks. The whole window is then drawn at its old size into the new one, and with GL Windows
    shows that frame as it is, pinned to the bottom: everything jumps up by the difference, then back. Painted output is spared,
    as Windows keeps what was painted where it was. Not the video frames: paused, it was the same.
  - Fix: `utils/gl_window_size.py`, on a window once a GL surface in it comes up (`initializeGL`), Windows and Linux. Before Qt paints the window while
    its widgets are at an older size than the window's own (`QWindow.size()`, always the system's), it's made to take the new
    size first (`QWindowSystemInterface::flushWindowSystemEvents`, from `Qt5Gui.dll` or `libQt5Gui.so.5`, user input left
    queued), as Qt does itself before a paint the system asks for. Making all of Qt's window events synchronous worked as
    well, but that changes how input arrives everywhere.
  - Measured on the real screen, Windows' own resize with the pointer, 4 cells of a colour each, one column read about 110
    times a second and matched with what each height looks like when settled. Bottom edge: backward moves up to 11-12 px, and
    12% of frames matching no size the window had, to none past 1 px of rounding and 0%. Corner: up to 6-7 px to 2 px. Swaps
    at an old size: about 1 in 4 to none. Readback: none either way.
  - Left: between a new size and the next swap, Windows shows the last frame stretched or cut to it, for 5-15 ms, about 13% of
    frames in a corner drag. It never goes backward. Drawing and swapping inside `WM_SIZE` didn't change it, as Windows takes
    the size and GL's frame apart. GL also manages about 54 sizes a second against readback's 105, each `QOpenGLWidget` making
    its framebuffer anew: 13.5 would help there.
  - Linux, `test_gpu`, the window resized by sway about 45 times a second: 50 of 427 swaps at an old size without the fix,
    0 of 516 with it. All 9 MPV scenarios pass on both outputs there with it.
- [x] 13.7 A picture growing during a resize is drawn anew on the way, not blown up until the resize ends: every 100 ms
  while it's 10% or more past its frame (`RESIZE_CATCH_UP_MS`). Both outputs. Window enlarged over 3 s: frames at 42-57% of
  their cell's size on the way before, 90-95% after. Painted frames were already smoothed: the blockiness was the scale.
- [x] 13.8 NVIDIA, Windows: black rows at the bottom of the window with GL output, your report.
  - The driver pads the window's buffer height up to a multiple of 4 at some widths (1200, 1600, 1920; not 1100, 1300, 1500),
    and Windows squashes all of it, padding too, into the window: at 1920x1009 everything is 1006 rows tall with 3 black
    below. 1010 gives 2, 1011 gives 1, 1008 none. A bare `QOpenGLWindow` does it too. mpv's frames are fine. Not on AMD.
    Here the monitor is on the AMD GPU and NVIDIA renders for it.
  - The padding can't be drawn into. A window format with an alpha channel takes another way to the screen and has no black
    rows. It also resizes as cleanly as readback: no frames at a size the window didn't have, even in a corner drag, 59-64
    sizes a second. Not see-through: 22 pixels differ from readback's, the clock. It costs CPU, real screen, one run each
    in turn: 4 cells 49 to 57%, 9 cells 101 to 121%.
  - Your call: a setting, "Black line fix" under Experimental (`internal/gl_line_fix`), Auto, On or Off, Windows only,
    greyed out unless the output is Fast, restart to apply. Auto is on for NVIDIA, as other GPUs may turn out to need it.
  - Trap: the vendor can't be asked of a GL context made before the `QApplication`. Any such context, alpha or not, double
    buffered or not, makes NVIDIA's driver show the windows the black-line way for good (not DPI awareness, not COM). So
    Auto sets up the alpha channel before Qt starts, then asks once the app is up and takes it off for the windows to come
    unless it's NVIDIA (`init_app.settle_gl_line_fix`). Qt's share context keeps it: AMD plays fine that way. Asking costs
    about 130 ms, mostly loading the driver Qt loads next anyway.
  - The crash closing a cell, seen in `mpv_transport`, wasn't the fix's: fixed, see 13.9.
- [x] 13.9 A native crash closing a cell with GL output, about 1 in 90 runs of `mpv_transport`. Caught by a crash catcher of its
  own in the app (a vectored handler logging an unwound stack, the GUI thread): `~QOpenGLWidget` deletes its context, whose
  `aboutToBeDestroyed` has the blitter's vertex array free itself. With no context current, Qt makes a hidden window to make
  it current on, and Python can run meanwhile (event filters), the garbage collector with it. The surface was going and the
  blitter only Python's, so it could be freed right then, vertex array and all, under Qt's feet. A full collection at each new
  window surface made it crash 3 runs in 3, at the first cell closed. Now the context holds the blitter until it's gone
  (`_HeldTillContextGone`): 3 in 3 pass that way, every blitter let go. The surface's own slot can't do it, PyQt cuts a
  widget's bound methods off once it's being deleted. The earlier `PYTHONFAULTHANDLER` crash was the fault handler itself,
  printing from two threads.
- [x] 13.10 120 fps videos, your question: they showed about 64 frames a second, on both outputs. Three things, the first only
  in the measuring.
  - On the other desktop Windows 11 throttles the app as unseen, a few seconds in: every timer comes every 15.6 ms, 64 frames
    a second at most, and mpv's own late ones dropped (43 a second). A window moved off the screen on your desktop isn't
    throttled. The bench now opts out (`away._never_throttled`). Numbers taken there before, 13.5's among them, were throttled
    past the first seconds: fine for 60 fps clips, not for 120.
  - mpv on Windows 10 and up asks for 1 ms timers before each wait and lets the request go after it, and a process has just
    the one: the one Qt's precise timers rely on too. With two videos open, paused even, the app's timers came every 15.6 ms
    most of the time. VLC doesn't do it. Fix: `MPV_HRT=always` before libmpv starts, asking once and keeping it.
  - With timers on time, a picture held to a whole refresh misses one now and then: 105 swaps a second at 120 Hz. Both pacers,
    the renderer's and the window's, wait a refresh less 1 ms (`paint_interval_s`), the swap waiting out the rest: 119.
  - 360p120 clips, Fast, frames reaching each cell a second (before / after): 1 cell 119 / 119, 9 cells 97 / 111, 16 cells 89 /
    109; mpv now renders all 120 at 9. Readback at 16, 112 either way, the CPU's limit there. 36 360p60 cells: 58 fps at 14% of
    the GUI thread, now 60 at 18-23% (19% with the timer fix alone): 105 compositions a second for 60, the
    cells' frames falling on different refreshes.
  - `video_timing_offset=0` wasn't it: mpv's default played all 120 throttled, but shows frames up to 50 ms early, and with
    timers on time 0 drops none.

## Stage 14: mpv drawing into its own windows

**Your call (2026-11-11):** a third choice on "Video output" beside Steady and Fast, Windows first, then X11 on Linux.
Wayland and macOS keep Steady and Fast: on Wayland a surface is only its own client's to draw into, and mpv's Wayland
backend always opens a window of its own (`wid` takes an X11 window or a Windows handle).

Why, from Brick2892's fork (`docs/MPV_FORK_REVIEW.md`, not committed): mpv's own `vo=gpu` on Direct3D 11 into a native
child window a cell, with `wid`. A bare prototype against our outputs, the mix, one process, on the screen and off it:

- CPU a fifth to a half of ours on the RTX 3060 and the AMD iGPU (on screen at 16: 54% against Steady's 103% and Fast's
  117% on NVIDIA; 35% against 116% and 144% on AMD).
- On AMD and Intel our OpenGL path copies every frame GPU to CPU to GPU (`d3d11va-copy`): mpv's own output keeps them on
  the GPU. AMD at 16: 36.7 fps a video against 29.7 and 34.4, its 3D engine at 63% against 89% and 99%.
- On NVIDIA, less than half the video memory (+2.3 GB against +6.2 at 25).
- 25 swap chains cost the compositor no more than our one window: `dwm` at 5-12% of a core in every run.
- The same frames where the decoder is the limit (25 on either GPU).
- The prototype is bare: some of our CPU is the app around the video, which this output keeps.

How it goes in, by what's there already:

- **Windows, the overlay, the mouse:** VLC Hardware's native surface (`is_native_surface`): a clip window with the surface
  inside, kept out of the layout, the cell's overlay in a window of its own on top, which catches the mouse before mpv's
  window could. mpv makes its own window inside the surface, on a thread of its own.
- **The view:** the surface goes where the shown picture goes, and mpv is told what part of the frame that is with
  `video-crop` (0.38 and up) and `keepaspect=no`. A crop is whole pixels: it's grown out to them, the surface grown
  by as much, and the clip cuts it back, so a zoomed picture pans smoothly and never needs a window bigger than the cell.
  Turns by `video-rotate` as now, flips by the shader that's there for subtitles. Older libmpv: Steady instead.
- **Everything else** is `MpvPlayer` as it is, with no render context: time, tracks, audio, subtitles, deinterlacing,
  streams, errors.
- [x] 14.1 Spike in the real app, Windows: `MpvOutput.WINDOW`, a frame with a native surface and mpv drawing into it.
  Loads, plays, resizes, closes, the overlay over it, never takes focus. Real window on the other desktop. CPU against
  Steady and Fast in the bench.
  - Built (`widgets/video_frame_mpv_window.py`): `VideoFrameMpvWindow` on VLC Hardware's native surface, and
    `VideoDriverMpvWindow`, the mpv driver with no render thread: `MpvPlayer(wid=...)` takes `vo=gpu`,
    `gpu-api=d3d11`, mpv's own timing, and leaves the mouse to the overlay. mpv starts as soon as it's made. The surface
    goes over all of the picture for now, the clip cutting it to the cell (crops in 14.2). What every mpv frame has is in
    `MpvFrame`. Only through `REAL_APP_MPV_OUTPUT=window` until 14.7. Not for Software MPV, nor off Windows.
  - mpv can still be drawing as its video goes, so the clip with the surface is taken out of the frame then, hidden,
    and kept until mpv has terminated. Qt keeps a native child's window handle when it's taken out of its parent
    (checked); none are left kept a few seconds after closing.
  - A scenario in a real window on the other desktop: 3 cells play, follow two window resizes, the overlay over them,
    one closed, two opened again and loaded in 0.4 s, three closed, nothing left behind, never in the foreground.
  - Bench, real app, real window on the other desktop, the mix: frames a video · CPU of the process · video memory
    added. The bench counts frames for this output from mpv's clock and its drops, as the prototype did.

    | | 4 | 9 | 16 | 25 |
    |---|---|---|---|---|
    | RTX 3060 | 43.5 · 24% · +354 | 39.3 · 37% · +925 | 36.8 · 59% · +1454 | 27.6 · 71% · +2347 |
    | AMD iGPU | 43.5 · 17% | 39.4 · 27% | **36.8** · 45% | 21.6 · 48% |

    Against the off-screen numbers before (Steady · Fast): NVIDIA 71·53%, 71·80%, 96·115%, 118·114%; AMD 53·47%,
    100·96%, 116·148%, 116·133%, and 29.5 fps on Steady at 16. Close to the bare prototype's: the app around the video
    costs little. `d3d11va` on both GPUs, no copy.
  - Resizing, your report: tears around the videos, and on NVIDIA a black bar under each, the cells "wobbly" growing.
    - The black bar is Fast's NVIDIA black line again (13.8), a window at a time: drawing for a screen on the other GPU,
      NVIDIA's driver pads a Direct3D window's buffer to a multiple of 4 rows at some widths, squeezed in as 1-3 black
      rows. On the screen, the window resized in 24 steps: black rows under the pictures in 19 of 30 captures. The surface
      is now grown by 0-3 rows to whole blocks, the clip cutting them off: none in 30. (mpv was told to leave them out
      with `video-margin-ratio-bottom` too, but it leaves out no margins while it stretches the picture over its window,
      found in 14.2: the picture is 1-3 rows taller than it is, the rows past the cell cut off.) Only seen with NVIDIA rendering; on the other desktop it never shows (never drawn for a screen).
    - The surface followed the cell at most every 100 ms through a resize, as VLC's do: now every step, mpv's own window
      following ours within a millisecond by itself (measured). The clip and the surface are black once loaded, not
      Qt's light grey, where mpv's window hasn't caught up.
    - Edges still flash shrinking, you said: not seen resizing from code (no flashes, no light in 30 captures). A drag
      goes through Windows' own sizing loop, which can't be driven without the mouse. A trial by hand: the frame a native
      window as well (`GP_MPV_NATIVE_FRAME=1`), so the clip and mpv's window move with it in one go.
    - Your recording of a corner drag with about 20 cells (120 fps): mid-drag, light grey blocks with squashed dark
      marks between the cells. The window's own GDI picture (PrintWindow, no full render) still held every cell's
      "Opening..." card under the playing videos: the status is a native window over the frame while loading, and no
      paint reached under mpv's window after, the clip and the surface clipping out their children. Windows shows that
      picture, stretched, while a drag outruns the painting. Now both paint under their children too
      (`WS_CLIPCHILDREN` off, Windows), mpv's picture being a layer of its own above: all black under the videos.
      The native frame trial made no difference to you, and is gone.
- 2026-11-11, your call: the outputs are named for what they do, **Copy** (was Steady), **Shared** (was Fast) and
  **Direct**, with a ? button beside "Video output" that says what each does and when to pick it (Windows: all three;
  elsewhere Copy and Shared). Shared stays on Windows: smooth resizing with less CPU than Copy with a few videos, and
  on AMD. This plan keeps the old names where it was written with them.
- [x] 14.2 The view: zoom, pan, crop shapes, aspect ratios, view modes, turns and flips, the file's own rotation;
  `mpv_view` passing on it.
  - Not by `video-crop`, as planned: every change of it reconfigures mpv's output, and lands with the frames decoded
    after it, 70-600 ms later (measured). Its place under a file's own turn didn't come out the same twice either.
  - mpv's window goes over all of the picture, as in 14.1, mpv stretching it over the window, while that window stays
    small: at most 4 times the part on show, or 1920x1080 whatever that is, and 8192 a side. A pan or a resize moves
    the window, at once and to the pixel, with nothing to tell mpv. Fit, Stretch, Fill and zooms up to about 2x.
  - Past that, the window goes over the part on show, and mpv places the picture in it (`WindowPicture`): keepaspect,
    `video-unscaled`, aligned top left, `video-scale-x/y` for its size, `video-pan-x/y` for its place. mpv cuts the
    picture to its window in whole pixels of the picture and stretches that over the window, so an edge between two of
    them is up to one off: 5-23 px measured at 10x. So mpv's part of the window has its edges on the picture's pixels:
    worked out to the screen pixel as mpv's sums go (`_on_picture_pixels`), the window grown to them, the margins
    (`video-margin-ratio-*`) leaving out the rest, the clip cutting it off. A test runs mpv's sums from `aspect.c` over
    2000 random zooms and pans: the cut always where it was put.
  - Turns by mpv (`video-rotate`), flips by the shader that's there for subtitles, always on Direct. The shader flips
    mpv's picture area, not the whole window: the margins stay where they are.
  - Measured, the corners clip in one 1920x1061 cell, the middle lines against where the view puts them: within 0-2 px at
    1/2, 1/4 and 1/10 of the picture, plain, flipped and turned. Copy within 0-3 px. A pan shows after 20-50 ms paused,
    70-80 ms playing (the next frame mpv draws), against at once on Copy and Shared.
  - Needs `video-scale-x`, from 0.36: libmpv 0.37 is the oldest taken (see the Log, 2026-11-12).
  - `mpv_view` on Direct, on the other desktop: 87 checks pass. Its screenshots (14.4) left out, and the paused live
    stream's picture fails (14.4). `pixel_shape`: right but for the screenshots, and the phone clip (wide pixels, turned
    by the file) caught over all of the cell, stretched, as it's said to have loaded and before it's placed: 14.3.
  - The real-app driver's `shot` and the scenarios' `_grab` take a cell on Direct from what Windows composes
    (`tests/real_app/composed.py`): `grab()` can't see into mpv's window.
  - On the way: a video gone left its window as a top-level one, hidden, until mpv was done with it. Now hidden in the
    app's window: Windows can activate a window made a popup. Not seen to happen; what took the foreground in a run was
    the warning that there's no screenshot yet, which `mpv_view` asks for.
- [x] 14.3 Loading and the first picture: the cell says loaded once mpv has shown one, not a black window before it.
  Reloads, errors, a stream that ends.
  - Nothing to change: the load waits for mpv's playback-restart, which comes once mpv has its first picture up.
    Measured from what Windows composes every ~16 ms, the loading status coming off: the right picture in the next
    capture, never black or stretched between, for a local file and a 3-quality HLS stream, playing and paused,
    portrait or not. (`vo-configured` and the first `vo-passes` come with the video's size, 5-20 ms before.)
  - The phone clip "stretched over the cell" in 14.2 was the loading status: the scenario's capture from what Windows
    composes has it in, where Qt's `grab()` of the frame never did. Such a capture now takes the cells' overlays and
    statuses off for it, and `pixel_shape` waits for the status to go before it judges the picture.
  - On Direct, with message boxes logged rather than shown: `mpv_streams` and `mpv_transport` pass, `mpv_basics` too
    with its render-size checks only on Copy and Shared (Direct's picture follows the cell instead, checked by shape).
    `pixel_shape` but for its screenshots (14.4).
  - Found on the way, fixed 2026-11-12 (see below): a crash in NVIDIA's Direct3D 11 driver. Two videos opened and closed 60 times in a
    row, 8 runs: one access violation in `nvwgf2umx.dll`, on a thread of the driver's own, about half a second after
    two mpvs started together (read of 0x38). Copy, the same loops: none in 120. The test folder's clips are 4:4:4,
    decoded on the CPU. Caught by an in-process exception handler: `nvwgf2umx.dll+0x98cf4a`, on a thread the driver
    started, 0.5 s after two mpvs began together, one closed just before. With clips decoded on the GPU: one crash in
    3 runs, but that one in Python's own fault handler as it reported LuaJIT's exception from libmpv (code
    0xE24C4A02, which mpv's Lua raises and catches): the handler, not the app.
  - Fixed 2026-11-12: Direct's mpvs start one at a time (`MpvRenderService.add_own_window`), the next once the
    one before it plays, fails, or has had 1 s. Three videos a round, opened together and closed, 60 rounds a run,
    the same 24 seeds each time:

    | | runs that crashed | in the driver |
    |---|---|---|
    | as it was | 6 of 24 | 5 |
    | devices made without the driver's own threads | 4 of 24 | 4 |
    | `hwdec=d3d11va` instead of `auto` (no CUDA) | 4 of 24 | 4 |
    | the scenario opening them 0.4 s apart | 0 of 24 | |
    | started in turn by the app | 0 of 24 | |

    The crash comes 0.5-0.7 s after several mpvs start together, as their outputs come up, with every one closed
    before them already terminated: it's starting together, not one going as another comes. Each crash on a thread
    the driver started, all at `nvwgf2umx.dll+0x98cf4a`, the faulting stack all the driver's. Without the driver's
    threads: `D3D11_CREATE_DEVICE_PREVENT_INTERNAL_THREADING_OPTIMIZATIONS`, set by pointing libmpv's import of
    GetProcAddress at a stand-in that answered `D3D11CreateDevice` with one adding it (two threads a device fewer of
    21), changed nothing, so it went. The cost of taking turns, the test folder's clips: 9 videos loaded in 3.2 s
    rather than 2.1 s, 25 in 9.0 s rather than 5.8 s.
  - Not crashes of the app: an exit code 139 after the scenario was done came from the test wrapper ending with
    `sys.exit`, Python's finalizing meeting Qt's objects; `run.py` and the app end by `os._exit`.
- [x] 14.4 Screenshots (`screenshot-raw`, asked for without waiting) and a paused live stream's last picture (the
  pause snapshot over a hidden surface, as VLC Hardware).
  - `screenshot-raw video` asked for with a callback (`MpvPlayer.take_screenshot`), answered on mpv's event thread
    and handed to the GUI's: the picture as mpv draws it, turned and flipped already (the flip shader too), at the
    video's own size, no subtitles. It goes through the same cut to the view as Copy's frame.
  - A paused live stream: the picture asked for first, then the stream let go of (mpv's commands go in order), put up
    as the pause snapshot, cut to the view; mpv's window hidden under it, black once mpv has let go. Back from the
    pause, the snapshot stays until mpv's playback-restart says the stream is on show again. A screenshot while
    paused takes the snapshot's whole picture.
  - `mpv_view` on Direct passes whole, screenshots of every turn and flip on turned files and the live pause
    included: Windows (Direct3D 11) and X11 (OpenGL), 127 checks each.
- [x] 14.5 Hidden cells (Single Mode, minimized, the tray): what a hidden mpv window still costs, and taking it down if
  it's worth it.
  - Nothing to take down: hidden, a Direct video costs less than a Copy one does. The bench's new `EXP=single`, 9
    cells, the first in Single Mode:

    | | all on show | Single Mode |
    |---|---|---|
    | Windows, the mix, Direct | 26.9% CPU, decoder 67% | 3.6% CPU, decoder 14% |
    | Windows, the mix, Copy | 63.6% CPU | 24.0% CPU |
    | test_gpu, 720p30, Direct | 28.5% CPU, GPU 100% | 5.0% CPU, GPU 15% |
    | test_gpu, 720p30, Copy | 54.4% CPU | 64.6% CPU |

  - Hidden, they play on at their pace and are right on show again: Single Mode on Windows (4.08 s played in 4 s);
    `mpv_hidden_cells` on X11, minimized and in the tray too (it minimizes, so not on Windows' other desktop). mpv
    counts what it puts in a hidden window as shown, so the scenario leaves its draw counts to Copy and Shared.
- [x] 14.6 Subtitles drawn by mpv in its window: placement and style, `mpv_subtitles` passing.
  - The subtitle view is pushed as for Copy, by all of the picture, which mpv's window is over. Where mpv places the
    picture in a window over the part on show, it lays the line out in that window: the view is then that of a picture
    not cut at all. Found on X11, where mpv always places it: Copy's view there put the line out of sight once Fill cut
    a turned picture.
  - `mpv_subtitles` passes on Direct on Windows and X11; on X11 without the checks of how mpv's text shrinks with a
    zoom, which is Copy's way.
- [x] 14.7 The setting: a third button on "Video output", Windows only for now. Whether it needs a restart (no Qt GL to
  set up, so maybe not). Switching drivers live, MPV to VLC and back.
  - Built in 14.1 (Copy / Shared / Direct, with the ? box), on Linux too now (14.9). Copy and Direct switch with no
    restart, the videos open reloaded on the other; to or from Shared still restarts. Checked with two videos open on
    Windows: Direct to VLC Hardware (single process), back, to Copy and back, each in about half a second, both
    pictures on show each time.
  - Default (your call, 2026-11-12): Direct on Windows, the lightest there by every measure here (CPU, video memory,
    hidden cells); Copy on Linux, where it works on Wayland too. macOS has no Direct; Shared is its default since
    2026-11-15 (11.4). Direct with no window system to give mpv (offscreen) is Copy.
- [x] 14.8 All MPV real-app scenarios on it on Windows (`REAL_APP_MPV_OUTPUT=window`), and the bench against Steady and
  Fast, the real app this time.
  - On Windows, the other desktop, message boxes logged instead of shown: `mpv_view` (127 checks), `mpv_basics`,
    `mpv_transport`, `mpv_streams`, `mpv_seeking`, `mpv_audio`, `mpv_deinterlace`, `mpv_subtitles`,
    `mpv_low_video_memory`, `pixel_shape`: all pass. `mpv_hidden_cells` minimizes the window, so only on X11.
  - The bench, real app, the other desktop, RTX 3060, the mix: frames a video · CPU of the process · video memory
    added (MB).

    | | 4 | 9 | 16 | 25 |
    |---|---|---|---|---|
    | Direct | 43.4 · 15% · +353 | 39.2 · 27% · +925 | 36.7 · 49% · +1453 | 29.5 · 63% · +2346 |
    | Copy | 43.5 · 67% · +852 | 39.3 · 48% · +2321 | 36.7 · 74% · +3861 | 28.3 · 106% · +6182 |
    | Shared | 43.5 · 59% · +952 | 39.3 · 98% · +2418 | 36.7 · 111% · +3962 | 28.3 · 116% · +6277 |

    The same frames everywhere (the decoder is the limit), at a quarter to a half of the CPU and well under half the
    video memory.
- [x] 14.9 Linux X11 (and XWayland under the Window system setting): `wid` with an X11 window, `vaapi` on `test_gpu`.
  - Built: Direct on Linux where there's an X11 window (`is_hw_video_available`), Copy on Wayland. On `test_gpu`
    (XWayland under sway, libmpv 0.40): `vo=gpu` picks `x11egl`, VA-API with no copy.
  - Three things X11 needed: the cell isn't hidden while loading (mpv waits for its window to be mapped before
    drawing, and the load waits for its picture: they waited on each other); the surface isn't made transparent for
    input (mpv's window in one never got mapped, found by bisecting a bare Qt test); and mpv always places the picture
    in a window over the part on show (a GL window reaching past the screen's edge showed the picture moved by as
    much, under XWayland).
  - All MPV scenarios on X11 Direct pass but one check: `mpv_transport`'s random start, the picture at the moment it
    says it has loaded. For 50-150 ms after the loading status goes, mpv's window shows the old status card under it,
    not yet having drawn (X11 windows show what was under them until drawn). Left open.
  - CPU, 720p30 on `test_gpu`: 9 cells Direct 28%, Shared 40%, Copy 54%; 16 cells Direct 44%, Shared 40%. The help
    box's Linux table has Direct: "about the same as Shared, and works only with X11".
  - Test captures under XWayland come from the compositor by `grim` (installed on `test_gpu`): the X server has none of
    what GL draws. On GNOME, by asking GNOME Shell (`org.gnome.Shell.Screenshot`, for the owner of
    `org.gnome.Screenshot`).
  - Found by you on Ubuntu (GNOME, Wayland session, the app on XWayland), 2026-11-12: the screen black but for a small
    picture in the top left corner, the player's window glitching. mpv, left to pick, took its Wayland output, which
    knows nothing of an X11 window and made a surface of its own. Direct on Linux now says `gpu-context=x11egl`
    (libmpv 0.37 takes one name, not a list). The tests on `test_gpu` hadn't seen it: their runs had no
    `XDG_RUNTIME_DIR`, so mpv found no Wayland there; `x11_all.sh` now sets it.
  - Ubuntu VM (GNOME, libmpv 0.37, llvmpipe), Direct: all MPV scenarios pass but two checks. `mpv_transport`'s random
    start, as on `test_gpu` before. `mpv_subtitles`' turned video in Fill in a 1200x300 window: the line drawn tiny at
    the bottom, where 0.40 on sway shows it whole (Copy passes there). Fixed 2026-11-12, see the log.
  - Found by you on Ubuntu, 2026-11-12: after Reload All or a driver change, the first cell stayed on "Opening..."
    while it played. Its mpv window was there but never mapped. mpv takes the parent window being mapped for its own
    window being mapped (it watches the parent's StructureNotify), and the first player was started while the reload
    was still making the cells, before they were laid out and shown (100x30, hidden). The first start now waits for
    what's being done to finish: in 25 reloads and 12 Direct-Copy-Direct switches, every start found its cell shown,
    none stuck (before, about one reload in 12).
  - Found with it, on any driver: right-clicking after a reload from a menu, or a driver change in Settings, crashed
    (`wrapped C/C++ object of type VideoStatus has been deleted`). With a menu or dialog open the active video isn't
    updated, so it stayed the closed one; it's now dropped once closed.
  - Left open: glibc aborting (`malloc_consolidate(): unaligned fastbin chunk`) once in 30 runs of `pixel_shape` on
    `test_gpu`, as a closed mpv's `vo` thread ended and freed what it held, another mpv's `vo` thread starting its
    X11 EGL output at that moment. The heap was broken before; by what, not found. Copy, the Linux default, has no
    `vo` threads. Fixed 2026-11-12, see the log.
- [x] 14.10 Hand test by you: all fine on Windows (2026-11-12) once YouTube's AV1 and its slow downloads were fixed.
- [x] 14.11 **Done (2026-11-13): Direct's outputs made in turn, and none while one closed is going, on all of Windows;
  0 crashes in 48 runs on NVIDIA and on AMD (14.13).** Intel on Windows never tried (no machine).
  Overnight, on NVIDIA: the driver crash of Direct's mpvs starting together. Only Direct crashed: each of
  its mpvs makes a Direct3D 11 device and swap chain of its own, presenting from its own thread, while Copy and Shared
  draw into the app's OpenGL on one thread and make no output of their own. It crashed with 4:4:4 clips decoded on
  the CPU too, and `hwdec=d3d11va` changed nothing: the output coming up, not the decoder. Each run is the same hunt
  (3 videos opened together and closed, 60 rounds a run, 24 seeds, an in-process exception handler logging access
  violations), with clips decoded on the GPU, logging the time between starts. GPU-heavy: only while nobody's using
  the PC.
  - Does starting in turn hold with clips that play at once? The next mpv starts as the one before plays, which for a
    local file decoded on the GPU can be 50-150 ms after it started, well under the 0.4 s apart that never crashed
    (found by the review of all of Stage 14). The 0 of 24 above was the test folder's 4:4:4 clips, decoded on the
    CPU, slower to play. Any crash in `nvwgf2umx.dll` and the next starts no sooner than 0.4 s after the one before,
    as well as once it plays.
  - With the turns off (`OWN_WINDOWS_START_IN_TURN`), each of these, to fix the cause rather than wait: `d3d11-flip=no`
    (presented the older way: the flip model is where the driver sets up the most); `gpu-api=opengl` for Direct on
    NVIDIA (mpv's own window still, drawn with OpenGL, NVDEC's frames staying on the GPU); and, only if both crash,
    the devices made one at a time with playback started together. One at 0 of 24, against 6 of 24 as it was, and
    the turns go on NVIDIA too; the cost of each (GPU, VRAM, frame times) measured before it's kept.
  - The turns are only on Windows since 2026-11-12: AMD and Intel there never tried. Whether they crash, and if not,
    turns only with an NVIDIA GPU.
  - **Ready to run (2026-11-12).** 8 arms, taken in turn seed by seed so a drift over the night hits them all alike, 24
    runs each and 48 for the turns, 60 rounds a run of 3 H.264 clips of the bench media (1080p30, 720p30, 1080p60),
    decoded on the GPU, muted, on the other desktop: all at once as it was; in turn as it ships; at once with
    `d3d11-flip=no`; `gpu-api=opengl` + `gpu-context=win`; `gpu-api=vulkan`; `vo=gpu-next`; `d3d11va-zero-copy=yes`;
    and at once on the AMD iGPU. About 5-6 hours. A tally per arm: runs crashed, in `nvwgf2umx` or elsewhere, the time
    between starts, the time to play.
  - Seen in a 2-round check of each arm: in turn, the next mpv started **70-160 ms** after the one before with these
    clips, the very case above. `gpu-api=opengl` alone took mpv's ANGLE context and crashed at once in `libGLESv2.dll`
    (beside Qt's own), decoding `d3d11va-copy`; with `gpu-context=win` (WGL) it decodes with `nvdec` and frames stay on
    the GPU. Vulkan takes about 1.4 s to make its device, against about 0.1 s for D3D11, so it rarely plays before a
    round closes: it still tests the output coming up. `d3d11-flip=no` confirmed by "bitblt-model presentation",
    gpu-next by `vo/gpu-next/d3d11`, the AMD arm by "Device Name: AMD Radeon(TM) Graphics".
  - **Night of 2026-11-13, first part.** Seeds 101-119/120 (00:33-03:24), 60 rounds a run. After that every run froze
    at its start, in Windows' virtual desktop service (`MoveWindowToDesktop` of the test rig never returned), most likely
    held by the crashed runs' processes stuck in the driver: those runs are left out. Runs crashed of runs:

    | arm | crashed | where |
    |---|---|---|
    | all at once, NVIDIA | 1 / 20 | `nvwgf2umx.dll+0x98cf4a` |
    | in turn (as it ships) | 0 / 20 | next start 25 ms after the last at the least, 126 ms the median |
    | `d3d11-flip=no` | 0 / 20 | |
    | `vo=gpu-next` | 1 / 19 | `nvwgf2umx.dll+0x98cf4a` |
    | `d3d11va-zero-copy=yes` | 5 / 19 | `nvwgf2umx.dll+0x98cf4a`: worse |
    | `gpu-api=vulkan` | 0 / 19 | its device takes ~1.4 s, it rarely played before the round closed |
    | `gpu-api=opengl` (WGL) | 19 / 20 froze | the GUI held as the mpvs start: out |
    | **all at once, AMD iGPU** | **14 / 19** | a heap read in `ntdll.dll+0x279b6` under `d3d11.dll` from an mpv thread, 2 in `libmpv` |

  - So: **AMD crashes far more than NVIDIA** when Direct's mpvs start together, which keeps the turns on all of Windows,
    not only NVIDIA. Whether turns hold on AMD is not yet run. All at once on NVIDIA crashed far less with these clips
    than with the test folder's CPU-decoded ones (1 of 20 against 6 of 24), so `d3d11-flip=no`'s 0 says nothing yet.
  - Next run, after a reboot: AMD in turn, AMD with `d3d11-flip=no`, and NVIDIA all at once against `d3d11-flip=no`
    with the CPU-decoded clips that crashed more.
  - Explorer had died in the night (you restarted it in the morning), which is what held the window moves: no reboot
    needed, a run on the other desktop worked again at once. The runner now stops after two runs in a row that never
    start.
  - **Day run 2026-11-13** (10:55-12:11, 24 runs of 60 rounds an arm):

    | arm | crashed | where |
    |---|---|---|
    | AMD, in turn | 6 / 24 | heap corruption found by Windows (`ntdll.dll+0x118095`, 0xc0000374) in 5, `ntdll+0x279b6` in 1 |
    | AMD, all at once, `d3d11-flip=no` | 18 / 24 | the same, and once in `amdxx64.dll` |
    | NVIDIA all at once, CPU-decoded test clips | 2 / 24 | `nvwgf2umx.dll+0x98cf4a` |
    | NVIDIA all at once, CPU-decoded, `d3d11-flip=no` | 0 / 24 | |

  - **AMD:** turns cut it from about 3 in 4 runs to 1 in 4, but don't end it; no flip model doesn't help. Something
    else in AMD's D3D11 driver (32.0.21043.19003, June 2026) breaks the heap: whether with one video at a time too, and
    whether Copy (no D3D11 device of mpv's own) is spared, are the next questions.
  - **NVIDIA:** `d3d11-flip=no` 0 of 44 all at once, against 3 of 44 with the flip model (both nights' clips). A hint, not
    proof; the turns, 0 of 44 too, stay.
  - **AMD, 2026-11-13 afternoon** (13:40-14:12, 24 runs of 60 rounds each): Direct with **one video** opened and
    closed alone, **0 / 24**; **Copy** with 3 at once, `d3d11va-copy`, **0 / 24**. So AMD's crash takes several of
    Direct's mpvs, each with its D3D11 device, alive together: not one mpv's own, and not AMD's decoder. The turns only
    keep starts apart; a start can still meet another mpv closing, as the hunt closes all and opens again at once.
    Next: in turn and waiting for those closed to be gone first (what X11 does, `OWN_WINDOWS_WAIT_FOR_GONE`). If that
    isn't 0, Copy becomes the default on Windows without an NVIDIA GPU.
  - **Fixed (2026-11-13): no Direct mpv starts while one closed is still going, everywhere**, as under X11 since
    2026-11-12, at most 3 s. AMD, in turn and waiting: **0 / 48** (15:05-15:46), against 6 / 24 in turn alone; starts
    waited 2763 times, never as long as the 3 s. `OWN_WINDOWS_WAIT_FOR_GONE` is gone: the wait is in `_start_next`
    before either way of starting. The turns stay on Windows. Left open: Intel on Windows (no machine), and whether
    `d3d11-flip=no` is worth having on NVIDIA (0 of 44 against 3 of 44, a hint). All of it written up in
    `MPV_DIRECT_CRASHES.md`; what the turns cost, 14.13.
- [x] 14.12 **Closed (2026-11-15, your call): seen only by the test's screenshot, never on screen.** Parked
  2026-11-12; the notes are kept in case it turns up. X11, Direct, a GNOME screenshot taken as a video says it has loaded shows the
  loading card, the picture 0.3-0.7 s later. `mpv_transport`'s random start sees it, failing on the Ubuntu VM 5 runs of
  16, then 8 of 8 (2026-11-12), as often with mpvs starting together as in turn. Windows passes. You see no glitch
  opening videos on the VM, so it may be what the screenshot catches rather than what's on screen.
  - Found: the card's own window is unmapped at the load, mpv's mapped, on top and the cell's size (xwininfo): what
    shows is the card's pixels left in mpv's window. A screenshot of a video not loading shows the frame mpv is on.
  - Tried, no change (8 of 8 still): the card taken off once mpv says `vo-configured`; and as soon as mpv's X window is
    in the surface (XQueryTree every 2 ms), before its first frame.
  - Next, if it's ever seen: on `test_gpu` (sway, a real GPU, 50-150 ms there before), and mpv's X window given a black
    background so it's never the card's pixels; or mpv's drawing traced (Present, Damage) to see what holds it.
- [x] 14.13 **Direct's starts in turn, at less cost (your call, 2026-11-13; built 2026-11-13).** What crashes is mpvs making
  and letting go of their outputs at once (`MPV_DIRECT_CRASHES.md`), not opening files. The turns held all of a start, network
  and buffering too: the next waited for the last to play or 1 s. Rejected instead: a setting to start them together, crashes or
  speed (1 in 250-1200 opens of three on NVIDIA, about 1 in 50 on AMD, the whole app down each time).
  - Built: every mpv opens its file at once and is held at `on_preloaded`, tracks picked, nothing made
    (`MpvPlayer._hold_output`, `output_due`); the service lets them go on in turn (`let_output_start`), the next once the last's
    output is up (`vo-configured`, `output_up`), or it plays, fails or ends, or after 1 s. The wait for one closed to be gone
    stays. Under X11 all go on together, as before.
  - Not `vid=no`, as planned: mpv ends a file with no sound and no video track at once ("No video or audio streams
    selected"), and one with sound starts playing it, the picture joining later. Held at the hook, mpv makes no output (no
    `vo/gpu` line until let go on) and still takes a pause or a seek. Closed while held, mpv's quit waits for the hook, and
    let go on it made its output on the way out (41 lines of it): it's sent `stop` first, and ends at once, with none.
  - Timings, 3 runs each, before / after, until all play: 25 local files, NVIDIA 8.5-8.8 / 8.5-8.7 s, AMD 6.8-6.9 /
    6.7 s (a turn is mpv making its output and shaders, about 0.28 s at 1080p on NVIDIA, the part to keep apart); 16 test
    streams with each request held 0.15 s, NVIDIA 20.9-21.5 / 11.3-11.8 s, AMD 19.3-20.0 / 9.7-11.1 s. From the first stream
    playing to the last, 11.7 / 2.3 s on NVIDIA. Ubuntu VM, where they never took turns: 25 files 1.7-2.1 / 1.7-2.0 s,
    16 streams 5.0-5.1 / 4.9-5.0 s.
  - Crash hunt, 48 runs of 60 rounds each: NVIDIA 0 / 48, AMD 0 / 48 (14 / 19 all together, 6 / 24 in turn without the wait for
    those closed). About a quarter of the mpvs were closed while held. Outputs up in 125 ms (median), 356 ms at most.
  - All 10 MPV scenarios pass on Windows Direct; on the Ubuntu VM all 11 but `mpv_transport`'s random start, which is
    14.12's.
  - `d3d11-flip=no` needs no night of its own.
  - From `/code-review`: one closed as its file opens is stopped before it goes on too (`MpvPlayer._let_hook_go`, one place
    for every way a hook is let go of), and a live stream paused while it waits is let go of stopped, its turn passing at
    once. A paused live stream played again now waits its turn, as mpv makes its output again. Still outside the turns: a
    video track turned on again after being off, which makes an output at once (as before; in turn since, 14.15). After the fixes: all 10 MPV
    scenarios pass on Windows Direct, and the hunt 0 / 8 on NVIDIA and AMD. A slip in the hunt's script once let all go on
    at once: AMD crashed in 5 of 8 runs, as before the turns.
  - Seen on the way: on Windows, 16 test streams take 8-9 s to resolve before any mpv starts (2.6 s on the Ubuntu VM), before
    and after alike (fixed, 14.14).
- [x] 14.14 **Links slow to start on Windows (2026-11-13).** 16 test HLS links (each request held 0.15 s) took 8-9 s
  before any mpv started, 2.6 s on the Ubuntu VM. Not resolving itself, 0.7 s for all 16:
  - A `.m3u8` link is fetched first to tell a channel list from a stream, and the cells' links were fetched one after
    another, by one thread, which got short turns while the interface made the cells: 5.5 s for 16. Now 8 at a time
    (`CELLS_READ_AT_ONCE`): all 16 read in 1.2-1.5 s.
  - Each resolver asked both Streamlink and yt-dlp whether they take the link before trying Streamlink, which plays
    it. yt-dlp's answer compiles all of its sites' patterns the first time, 0.23 s alone, and 16 threads did it together
    before any had finished, seconds of it. Now each is asked only once those before it could not read the link.
  - Until all 16 play, 3 runs each on NVIDIA Direct: 10.8-12.7 s before, 7.1-7.6 s after. Most of what's left is the
    turns (about 0.2 s each), and the first import of yt-dlp and Streamlink, contended (0.5 s alone, about 1 s with
    16 threads and the cells being made; once a session). Neither part is MPV's: VLC's links go the same way (not
    measured there).
- [x] 14.15 **A video track turned on or off in Direct, in turn (2026-11-13).** mpv lets go of its output at `vid=no`
  and makes a new one, a Direct3D 11 device and swap chain, at `vid=1` (0.36 s on NVIDIA, seen with a probe), outside
  the turns until now: the tray's "stop decoding" turned every cell's off and on together. Now a track turned on with
  none shown, or off, is due as a file opening is (`MpvPlayer._select_video_track`, `output_due`), set in its turn
  (`let_output_start`), the next once its output is up, or gone (`output_done`, only the way it was asked for). Another
  track keeps the output and is set at once.
  - From `/code-review`: a track's turn waits only for its output (playing, a seek says it has restarted, which
    ended the turn early: the tray's return seeks every cell); passes at once where the output already is as wanted
    (a live stream stopped); one due as a live stream stops is set there and then. Waiting cells' lists read by one
    pool of 8 for all (`read_for_cell` started a thread each), and yt-dlp asked whether it takes a link one at a time,
    for the first to compile its patterns once (with yt-dlp first, all 16 compiled them together). mpv seeks a track
    turned on again to where it is itself (`lavf refresh seek`), so the tray's seek landing before it is harmless.

---

## Log

Newest first. What was finished and seen working, and anything that changed the plan.

- 2026-11-16: libmpv 0.41 with no sound server hung in PipeWire's output now and then: the audio device list is
  time-limited, PipeWire left out of `ao` with no server. Real-app jobs on Ubuntu 24.04 and 26.04, and on Windows and macOS (not blocking yet).
- 2026-11-16: `real-app-mpv` passed on GitHub (12.4). `--self-check` for packages, run in CI on each one built (12.2);
  unit tests on Windows and macOS as well.
- 2026-11-16: MPV the default on Windows too (your call), so Hardware MPV everywhere but macOS before 12. Every stream
  scenario passes on the Ubuntu VM as well. CHANGELOG written, AGENTS.md says libmpv builds differ (12.5).
- 2026-11-15: 10.36 Hardware VLC's slow live resizing measured with drags by hand: what feels like tar is VLC's pictures
  following late, not slow steps. Six ways tried, none kept (your call); MPV is the answer. Findings in `VLC.md`.
- 2026-11-15: 11.4 overnight on the real Mac: every scenario passes there. Fixed: VLC Software's picture of turned files
  (VideoToolbox), the cocoa harness's drags. MPV on macOS asks for OpenGL 3.2 Core (zero-copy VideoToolbox), and Shared
  output runs there, its default: 9 videos at 39 fps where Copy on 2.1 did 10.
- 2026-11-14: 10.35 built as "Use mpv.conf" (Experimental), not a typed-in box.
- 2026-11-14: 10.34 Picture quality built: Auto / Fast / High, no middle level (measured, see the item). The Ubuntu VM
  passed `mpv_audio`, `mpv_streams` and `mpv_basics` after 14.14/14.15's review fixes.
- 2026-11-13: 14.11 closed. 14.14: 16 HLS links play in 7.1-7.6 s on Windows, not 10.8-12.7 s: links to lists
  read 8 at a time, and yt-dlp not asked of links Streamlink plays. 14.15: a video track turned on or off in Direct
  waits its turn.
- 2026-11-13: 14.13 built: Direct's mpvs open their files at once and are held before making their outputs, let go on in
  turn. 16 streams all playing in about half the time on NVIDIA and AMD, local files as before; crash hunt 0 / 48 on each.
  Held at `on_preloaded` rather than `vid=no`, which ends a file with no sound.
- 2026-11-12: Added 10.34 (Picture quality Auto / Fast / High) and 10.35 (mpv options typed in), both ideas from
  Brick2892's fork, to be credited. Today's Linux Direct fixes seen on `test_gpu` (sway, libmpv 0.40, vaapi): all 11 MPV
  scenarios pass on Direct, `mpv_subtitles` 5 of 5 more under `MALLOC_CHECK_=3` with no heap abort.
- 2026-11-12: Under X11 a Direct mpv starts once every one closed is gone, or after 3 s
  (`MpvRenderService._is_waiting_for_gone`). glibc aborted the app on a broken heap (`corrupted size vs. prev_size`,
  `unsorted double linked list corrupted`, ...) in 3 of 7 runs of `mpv_subtitles` on Ubuntu Direct, whose reloads
  close one mpv as the next starts. With glibc's malloc checks (`libc_malloc_debug`, `malloc.check=3`) the first run
  aborted in the closing mpv's `mp_destroy`, freeing beside a chunk already overwritten, as the new mpv's `vo` thread
  was in `vo_x11_init` -> `XRRQueryExtension` -> libXext's `XextAddDisplay` (the X displays' lists those keep for
  the whole process). As on `test_gpu` before. With the wait: 6 runs of 6 with the malloc checks, no abort, and none
  waited the 3 s out. Starting together is as it was; Windows is untouched.
- 2026-11-12: Direct's subtitles laid out by all of the picture where mpv's window is over only the part on show
  (`sub-use-margins` and `sub-scale-with-window` off), as where it's over all of it: the same sums for both. With the
  picture past the window's edges, mpv up to 0.38 shrank the line as much again as the picture went past (fixed in
  mpv by 42e9f302df): on Ubuntu's 0.37, in Fill in a 1200x300 window, a line 40 px wide, and 14 px turned. Now as on
  0.41 there, and `mpv_subtitles` passes on Direct on Ubuntu and on Windows (once failing there on lines that never
  came, then passing twice, the same code).
- 2026-11-12: YouTube files asked of the host in pieces (yt-dlp's `http_chunk_size`, `Stream.piece_size`): mpv opens
  the picture and the sound as files, asking for each to its end, and YouTube gave an AV1 1080p file asked for that
  way at 266 KB/s, about its bit rate, and in pieces of 10 MB at 8 MB/s. Signed in, the video stopped every few
  seconds to wait for it. Now the proxy asks a piece at a time and answers as one: the same video's cache went from
  0-4 s, with two stops in 45 s, to 250 s in 2 s and none; seeks forward, back and past what was read play on.
- 2026-11-12: Direct keeps mpv's own 6 spare decoder frames (`hwdec_extra_frames`), Copy and Shared none. AV1 from
  YouTube on Direct froze and lagged for its first seconds: d3d11va decodes into a fixed pool, and with none spare
  AV1 ran out at once, mpv going to d3d11va-copy (missing the sequence header mid-stream), dxva2-copy, and once to
  the CPU after 7 s. A 1080p60 AV1 clip made by libaom: 0 spare falls back, 1 still runs out, 2 and up clean. VP9 and
  H.264 were clean with none; Copy's NVDEC took the AV1 clip with none.
- 2026-11-12: Direct's mpvs take turns starting only on Windows: under X11 they start together again, once their
  cells are shown, as no driver there crashed. Why NVIDIA's did, and three ways around it rather than waiting, go to
  14.11.
- 2026-11-12: libmpv 0.37 (Ubuntu 24.04) is the oldest taken, 0.35 (Debian 12) no longer: it had no `video-scale-x`, which
  Direct places the picture by, and with it unscaled Direct never fit the cell there (found by the review of all of
  Stage 14). The `fast` profile is a start option now, as 0.37 has it. Ubuntu 22.04's 0.34 was never taken. Ubuntu
  26.04 has 0.41, Debian 13 0.40.
- 2026-11-12: Direct the default on Windows, Copy on Linux. Ubuntu's Direct fixed (mpv took Wayland). The NVIDIA
  driver crash fixed by starting Direct's mpvs one at a time. Direct's scenarios run on the Ubuntu VM, GNOME
  screenshots for the tests.
- 2026-11-12: 14.3 to 14.9 overnight: Direct's first picture already right, screenshots and a paused live stream's
  picture, hidden cells cheaper than Copy's, subtitles kept on show, switching live, every MPV scenario passing on
  Windows, and Direct on Linux with X11. An NVIDIA driver crash, one in ~500 open-and-close, noted. Default left to
  you (14.7).
- 2026-11-12: 14.2, the view on Direct: zooms, pans, crops, view modes, turns and flips, the picture placed to the
  pixel at any zoom. mpv's window over all of the picture while that's small, mpv placing the picture in one over the
  part on show past that.
- 2026-11-11: Stage 14 planned, mpv drawing into its own windows, Windows first, from the fork review's bench. 10.21
  closed (libmpv's fence leak, worked around).
- 2026-11-10: the small ones of Stage 10. 10.2 tried by you, drags fine. 10.10 mpv's own scripts off, 5 threads a video.
  10.7 OpenGL ES on Linux where it's all there is, for both outputs. 10.19 measured: the placement kept and the time asked
  for while playing; the render round not worth changing. 10.6 bounded on Software MPV; Hardware MPV's growth on
  `test_gpu` is 10.21's Mesa. `stream_stalls` on `test_gpu` was the scenario's: there the
  proxy tells of the refusal at once, and the app's one reload came and went before the scenario saw the video stop. It
  now waits for the reload from the refusal on; passes there on both MPV drivers, and on Windows with VLC too.
- 2026-11-10: 10.11, "Decode on the CPU" has Auto, the default: a new video decodes on the CPU when there's no room left for
  it in video memory, read on Windows (DXGI) and Linux with NVIDIA (NVML). Fixed with it: Software MPV left a phone video
  unturned until a transform or reload.
- 2026-11-10: 10.17, Software MPV is fully software: libmpv's software renderer, no GL. On Windows less CPU, half the memory and the GPU idle; on `test_gpu` the same CPU and up to twice the frames past the limit. The old mode is Hardware MPV's new "Decode on the CPU", Off / On, Auto to come with 10.11.
- 2026-11-10: 10.22, a setting to turn off MPV's direct rendering, "Hand frames straight to the GPU", on by default. Off, Software MPV on Windows with NVIDIA no longer keeps about 1.5 MB per video closed: 6-minute churn, all closed, 471 MB against 1229.
- 2026-11-09: 10.26, VLC in a single process on Windows no longer burns up to 13 cores with 15 videos: VLC 3's waits pointed at Windows' own (`VLC_WAITS.md`). Checked in the 32-bit app too; found there 10.27, 32-bit single process out of address space with many videos, and fixed Hardware VLC's window check failing in 32-bit.
- 2026-11-09: 10.28, VLC single process against multi-process on Windows with 10.26 in: the same frame rate and CPU, a little less memory single, slower loading of many videos. Processes tooltip and README no longer warn of freezes past 4-6 videos.
- 2026-11-09: 10.16, the overnight run. An MPV crash closing a video as it loads, fixed (10.1). New: 10.21 Mesa's memory on `test_gpu`, 10.22 Software MPV's direct rendering on Windows, 10.23 VLC. The limits held over 3 runs, and VLC's freeze at 36 cells is Linux's only.
- 2026-11-09: 13.10, 120 fps videos play at 120 again with a few cells, 110 at 9: mpv let go of the app's 1 ms timers after each wait, now asked once and kept (`MPV_HRT`), and the pacing waits a millisecond less. The 64 a second measured before was Windows throttling the bench's window on the other desktop: the bench opts out now.
- 2026-11-08: 13.6 checked on Linux, the same cause there and fixed the same way. 13.7, a growing picture redrawn on the way. 13.8, NVIDIA's black rows: a Black line fix setting, on for NVIDIA by default. On a real screen Windows GL saves CPU only with a few videos, see `MPV_PERFORMANCE.md`.
- 2026-11-08: 13.6, the shaking of GL output during a window resize on Windows, fixed: frames drawn at the old size, as Qt took the new one too late. Backward jumps of up to 12 px down to 1-2 px of rounding.
- 2026-11-08: Stage 13, GL output, built: 13.1 to 13.4. "Fast" in Video output, after a restart. Same frame rates for 20-35 points of a core less, and on Linux the display server's share too. On Linux VLC's processes then have to start from `forkserver`.
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
