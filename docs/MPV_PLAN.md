# mpv driver: plan and progress

The findings and traps are in `C:\Projects\test_temp\test_mpv\HANDOFF.md`, and
`grid4.py` there is the working POC. That folder is reference only. This file is
what we build and how far it has got. Tick items only once they have been seen
working.

**Status: Stage 3 built (<https://claude.ai/artifact/8ngdeLCkVxmdQzSEnpxx1c>, real screenshots on its Built board). Open: macOS. Bundling libmpv (12.1) is for later. Stages 1-3 are committed on this branch.**

**Load tests against VLC: `MPV_PERFORMANCE.md`.** No multi-process mode for MPV. New items 10.13-10.16. **10.16 is a long run
still to be started, overnight, by you.**

| | Stage | State |
|---|---|---|
| 1 | Videos load, play and resize in the real grid, with zoom and pan | built, your hand test still open |
| 2 | Finding the libraries, no startup delay, runs with only one of VLC or mpv | **done, macOS not run** |
| 3 | Settings: unavailable drivers greyed out with a reason | **built, macOS still open** |
| 4 | Transport: seek, speed, frame step, looping, end of video | not started |
| 5 | View: rotate, flip, crop, aspect ratio, screenshots, sync | not started |
| 6 | Audio: tracks, files, devices, delay, channels | not started |
| 7 | Subtitles: tracks, files, delay, encoding, style | not started |
| 8 | Deinterlacing, chapters, bookmarks, SponsorBlock | not started |
| 9 | Streams, live video, errors and recovery, lists | not started |
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

- [ ] 4.1 Seeks: exact or not, many in a row from a bar drag, `_seek_target` logic works
  with mpv's time
- [ ] 4.2 `time_changed` throttled from `time-pos` to about what VLC sends. Measured: reading it 5
  times a second instead of every frame saves about 5% of the app's CPU, and plays no more
- [ ] 4.3 Frame step, playback rate, Loop A-B, random start, saved position
- [ ] 4.4 `loop-file=inf` against end-of-video actions, `is_loop_wrapped`, When Finished
- [ ] 4.5 Loaded paused: first frame shows, seeks work while paused
- [ ] 4.7 From the code review, not seen happen: `VideoDriverMpv.set_pause` compares with the last state mpv
  confirmed, not the last asked for, so a pause then an unpause in quick succession can leave it paused. Compare
  with what was last asked for
- [ ] 4.6 Scenario `playback` runs on mpv too, bugs in `KNOWN_BUGS` until fixed

## Stage 5: View and pictures

- [ ] 5.1 Rotate and flip. `video-rotate` for turns. Flips at paint time, since `vf` would
  knock out zero-copy
- [ ] 5.2 Files that say how to turn: track `orientation` from `demux-rotation`, and the
  `dw`/`dh` trap
- [ ] 5.3 Crop, crop shapes, aspect ratio, View Mode, anchors, shift past edges, SAR, list tags
- [ ] 5.4 Sync view, zoom to cursor, zoom to selection
- [ ] 5.5 Screenshots from the slot's pixels at a size worth saving: re-render at the picture's
  own size first, don't save a thumbnail of a small cell. `ScreenshotView` agrees
- [ ] 5.6 Pause on live video keeps the last frame
- [ ] 5.7 Real-app scenarios `aspect_ratio`, `crop_ratio`, `pixel_shape`, `list_shape` on mpv

## Stage 6: Audio

- [ ] 6.1 Mute, volume (scale matches VLC's), audio-only cells with their placeholder
- [ ] 6.2 Track list and selection, language picks, default track, ids that survive reloads
- [ ] 6.3 External audio: `audio-add`, which track came from which file
- [ ] 6.4 Devices from `audio-device-list`, mapped to `AudioDevice`, pick survives a reload
- [ ] 6.5 Channel mode (`audio-channels`, `af`), delay
- [ ] 6.6 Scenarios `tracks`, `external_audio_jump` on mpv
- [ ] 6.7 Linux audio outputs are limited to `pipewire,pulse,alsa` (see Stage 1 results). Decide
  about JACK users, and check on a machine with sound, which the test machines lack

## Stage 7: Subtitles

- [ ] 7.1 Track list, selection, language, default and forced, no subtitle
- [ ] 7.2 External files, `.idx`/`.sub`, what happens when a new file reloads tracks
- [ ] 7.3 Delay, encoding (`sub-codepage`)
- [ ] 7.4 Style settings mapped from `SUBTITLE_STYLE_SETTINGS`, applied live if possible
- [ ] 7.5 Size and sharpness: subtitles are drawn at render size, so check small cells and
  zoom, and whether they should stay the same size on screen

## Stage 8: Everything that hangs off time

- [ ] 8.1 Deinterlacing: map modes to `vf`/`deinterlace`. **Retest `hwdec_extra_frames=0`**,
  flagged as unsafe to assume in the handoff
- [ ] 8.2 Chapters from `chapter-list`, `chapters_changed`
- [ ] 8.3 Bookmarks, SponsorBlock: run their scenarios, fix timing assumptions written for VLC
- [ ] 8.4 Scenario `marks`, `navigation` on mpv

## Stage 9: Streams, errors, recovery

- [ ] 9.1 `MediaInput` with HTTP headers, cookies, stream proxy, `is_adaptive`. Keep
  `ytdl=no`, since the app resolves links itself
- [ ] 9.2 Live: `is_live`, no length, pause as stop, reconnects, `video-params` late
- [ ] 9.3 Sizes and dubs: scenario `streams`, `dubs`
- [ ] 9.4 Errors: `end-file` reason to `error`, mpv's log lines in place of "VLC errors:",
  `player/video_init_timeout`, no GL context, an mpv crash
- [ ] 9.5 `video_block_recovery`, When Video Fails, list cells moving on
- [ ] 9.6 `utils/item_info.py` reads lengths with VLC in a spawned process. With no VLC,
  use libmpv the same way
- [ ] 9.7 Log level setting for mpv, `hwdec-current` falling back mid-file surfaced in the log

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
- [ ] 10.9 Cells not on show, as in Single Mode, still render and read back every frame. Render
  them small or not at all
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
- [ ] 10.18 **Your decision:** a window minimized or in the tray still renders and reads back every frame of every video. MPV only: VLC Hardware
  has no readback. `render(skip_rendering=True)` could leave that out while the video goes on playing, with one real render on coming back. It
  needs trying, and isn't the rejected sleeping cells, as nothing stops
- [ ] 10.19 Small savings the review found, by reckoning and not yet measured, for when the CPU matters more than the code: each render round visits
  every video, not just those with a frame (at most about 4% of a core at 64 cells); the placement is worked out on each paint (about 1% at 9
  cells). 4.2: the time is still sent by mpv each frame, so the saving of `notime` isn't had yet
- [ ] 10.20 File lengths in lists are read by VLC. With only libmpv there, lists show none. libmpv could read them too, in a
  process of its own as now
- [ ] 10.14 Don't fill the cell black before drawing a picture that covers it: app CPU 61% to 47% at
  1x1080p. Applies to VLC's software drivers too, so test those
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
