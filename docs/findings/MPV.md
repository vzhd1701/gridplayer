# MPV

What the MPV drivers are, why they are the way they are, what was turned down, and what's known and left. Built
2026-11-05 to 2026-11-16 on the `mpv` branch. The work log, stage by stage with every run, is
`docs/archive/MPV_PLAN.md`: commits and the findings name its items by number (10.11, 14.13). Measurements under load
are in `MPV_PERFORMANCE.md`, Direct's driver crashes in `MPV_DIRECT_CRASHES.md`, and what no machine here could run
in `docs/NEEDS_TESTING.md`.

## How it fits together

```text
gridplayer/mpv_player/
    mpv.py           vendored python-mpv, not edited
    libmpv.py        imports mpv.py against the library found; MPV_HRT
    gl_context.py    GL contexts with no Qt: EGL on Linux, WGL on Windows
    renderer.py      the render service: one render thread, the frame fences, Direct's turns
    player.py        one mpv: options, observers, commands, hooks
    abilities.py     what this libmpv has (demuxers, filters, zimg), asked once a run
    deinterlace.py   VLC's modes in what mpv has
    subtitles.py     the subtitle style and placement, what each libmpv takes
    quality.py       Picture quality
    conf.py          the user's mpv.conf
gridplayer/widgets/
    video_frame_mpv.py         the frame and driver of Copy and Shared
    video_frame_mpv_window.py  Direct: mpv in a window of its own
    video_surface_gl.py        Shared: one GL surface for the window
gridplayer/utils/
    media_libs.py      finds libVLC and libmpv without loading them
    video_memory.py    video memory left, for "Decode on the CPU" on Auto
    glibc_malloc.py    fewer malloc arenas, memory given back
    gl_window_size.py  a window drawn with GL takes its new size before it paints
```

- **Drivers.** Hardware MPV (`mpv_hw`) decodes on the GPU where it can and draws with OpenGL. Software MPV (`mpv_sw`)
  is software all the way: libmpv's software renderer, no GL at all, swscale's fast bilinear. Hardware MPV's "Decode on
  the CPU" (Auto / On / Off) is the old middle way, CPU decoding drawn on the GPU.
- **Outputs** (Hardware MPV's "Video output"):
  - **Copy:** frames read back and painted by Qt.
  - **Shared:** the render thread's textures drawn by one `QOpenGLWidget` under all of a window's widgets, nothing read
    back. Changing to or from it takes a restart, as Qt's GL is set up before the `QApplication`.
  - **Direct:** mpv's own `vo=gpu` into a native window a cell (`wid`), Direct3D 11 on Windows, `x11egl` under X11. Not
    on Wayland, where a surface is only its own client's, nor on macOS.
- **Defaults:** Hardware MPV everywhere; VLC before macOS 12, where the package's libmpv won't load. Direct on Windows,
  Copy on Linux (it works on Wayland too), Shared on macOS. From source without libmpv, VLC stands in.
- **One process.** Every video is an mpv in the app's process. A multi-process mode was measured and turned down: the
  decoder is the limit, not the GIL (`MPV_PERFORMANCE.md`). An mpv crash takes the app with it.
- **Threads.** The GUI thread never waits on mpv; the render thread never waits on the mpv core. A resize reaches mpv
  after 150 ms of quiet. Closing is: stop drawing, free on the render thread, terminate on another thread. Observers
  only store values. Everything sent to mpv takes one lock (`_telling`) and looks at `_is_closing` inside it, as
  `terminate()` frees the handle at once and mpv's event thread goes on.
- **Loading.** Finding a library is about 1 ms; loading it 7-11 ms on Windows, 35-94 ms on Linux. So only the
  library of the driver in use is loaded, and libmpv at the first video, on the GUI thread.

## Decisions

Each with why. "Your call" in the log marks the ones the user made.

- **Own GL contexts on Windows and Linux** (WGL, EGL by ctypes), Qt's on macOS. Qt's offscreen platform on Windows
  can't make a GL context, `QT_XCB_GL_INTEGRATION=none` stays for VLC, and switching to MPV needs no restart. Zero-copy
  `nvdec` and `vaapi` hold in them. OpenGL ES on Linux where it's all there is (read back BGRA where the driver has it,
  else RGBA).
- **macOS: OpenGL 3.2 Core.** In Qt's default 2.1 profile mpv has no VideoToolbox interop and copies every frame. In 3.2
  Core `videotoolbox` keeps frames on the GPU: 9 videos at 39 fps on Shared where Copy on 2.1 did 10 (HD 4600).
- **The view goes by the track's size**, not the rendered one, so crops and shifts stay put through resizes.
- **A cell is loaded at its first frame** (Direct: mpv's `playback-restart`, which comes once its picture is up), or at
  `file-loaded` for sound only. No black flash between the status and the picture.
- **A missing library:** the pick is kept and the other library stands in this session, of the same kind (Software
  for Software), said once. Neither: a box naming both.
- **libmpv 0.37 is the oldest taken** (Ubuntu 24.04, client API 2.2): Direct places the picture with `video-scale-x`,
  from 0.36. What a newer one adds is asked of mpv (`option_info`), never assumed from the version or platform.
- **libmpv in every package, a full GPL build:** shinchiro's on Windows, MPVKit linked into one dylib on macOS (12 and
  up), EPEL's 0.39 on the AppImage's EL9 base, our own module in the Flatpak (no Lua, so no `ytdl`), Ubuntu's 0.37 in the
  Snap.
- **Seeking: Exact by default** (Exact / Exact for bookmarks and chapters / Fast). Each seek says what it's for
  (`SeekAim`); frame steps, sync, loops, SponsorBlock skips and a place put back are always exact. A fast seek lands on
  the key frame at or before it; one forwards that would land behind goes on exactly.
- **The time 5 times a second while playing** (asked of mpv, not sent each frame), every change paused. `TimeAhead`
  times the loop's end and a skip's start to the frame between reports.
- **Turns by `video-rotate`, flips painted,** as `vf` would knock out zero-copy. Flips match VLC: of the frame as stored,
  so on a phone video Flip Horizontal is up and down on screen. While subtitles show, mpv flips by a shader (painting
  would mirror the text); Direct always does. Software MPV turns and flips by filters, its renderer ignoring both.
- **Tracks, the audio device, a random start and a file's turn go in at `on_preloaded`**, before anything is decoded:
  told later, mpv opens the default device and never says it plays, or shows the first frame first.
- **Sound on Linux: `pulse,pipewire,alsa`.** With no sound device mpv tries every output and JACK and SDL hang or crash;
  PipeWire's own output on a sleeping sink plays at three quarters speed for 5 s. PipeWire left out with no PipeWire
  socket: 0.41 hangs giving up on it. JACK stays out (your call). The device list is read by an mpv of its own,
  shared 5 s, as each mpv that reads it stays a client and PulseAudio takes 64.
- **Headphones on a surround track: VLC's room effect** (`sofalizer` with VLC's file, at VLC's levels). Without the
  filter or the file, the plain mix.
- **One-channel tracks and Mono go out on two channels**, as mpv's mix and PipeWire each take 3 dB going from one to two.
- **Subtitles stay on show and the same size on screen** in Fill and zoom, as on VLC Hardware (`sub-pos`, `sub-scale`,
  `sub-margin-x`), and change style with no reload. `sub-ass-override=yes`.
- **Deinterlacing:** Automatic is `deinterlace=auto` from 0.40, else asked of the frame. A mode by name is a filter, so
  decoding goes to `auto-copy` first, the filter added once `hwdec-current` says so; added at `file-loaded`, as one
  this libmpv lacks ends the file at open. X and Phosphor are `bwdif` stand-ins. Modes whose filters this libmpv lacks
  are greyed out (`abilities.py`).
- **Streams go to mpv as they come:** picture and sound as two links, a fragmented file as that file. Given as VLC's
  playlists, YouTube seeks took 6 s, and 0.40 went back to the start. `demuxer-seekable-cache=no` only where part is a
  fragmented file. Live DASH is served to mpv as live HLS by the proxy (`stream_proxy/dash_live.py`): FFmpeg's DASH
  reader can't follow a live manifest.
- **Software MPV is fully software** (your call): less CPU, half the memory or less, the GPU idle on Windows. swscale's
  fast bilinear, as zimg's defaults cost twice the CPU for a picture that looks much the same in a cell.
- **Picture quality Auto / Fast / High.** Auto: High (mpv's defaults) for a picture shown at 1 MP or more, unless
  shrunk from over 2.5 times its pixels; Fast below; a fifth either way before switching back. No middle level: it cost
  the AMD iGPU as much as High. No stepping down on dropped frames. Software MPV has its own scaler.
- **"Skip frames to play more videos"** off by default: 16x1080p60 from 7 to 31 fps, but half the frames at any load.
- **"Hand frames straight to the GPU"** on by default (mpv's direct rendering). Off is for NVIDIA's driver keeping
  1.5 MB of every video closed while the CPU decodes.
- **"Decode on the CPU" Auto:** a video decides once, at preload, by the video memory left (DXGI on Windows, NVML for
  NVIDIA on Linux; not read on Intel, AMD on Linux or macOS). A video counts 128 MB and 56 bytes a pixel, measured on an
  RTX 3060: 240 MB at 1080p, 570 at 2160p, 10-bit half as much again.
- **`hwdec_extra_frames`:** none on Copy and Shared (6 cost 130 MB a 1080p 10-bit video); mpv's 6 on Direct, whose
  d3d11va pool ran out at once on YouTube's AV1.
- **mpv's built-in scripts off** (5 threads a video), and users' scripts too: they would seek and change tracks behind
  the app's back. `mpv.conf` instead, as a file under Experimental (your call), with the app's own options skipped and
  every name checked with `option_info`.
- **Shared: one surface for the window**, not one a cell: at 36 cells the GUI thread 14.5% against 51%, 59.7 fps
  against 43. Its updates held to one a screen refresh. On Linux, VLC's processes then start from `forkserver`, as
  forked ones aborted.
- **Direct's mpvs make their outputs one at a time on Windows**, and none while one closed is still going, everywhere:
  several Direct3D 11 outputs coming up together crash NVIDIA's and AMD's drivers (`MPV_DIRECT_CRASHES.md`). Each mpv
  opens its file at once and is held at `on_preloaded` until its turn.
- **Black line fix** (Windows, Shared): NVIDIA pads a GL window's buffer to 4 rows at some widths, shown as black
  rows. An alpha channel avoids it, at some CPU; Auto is on for NVIDIA only. Direct grows its surfaces to whole blocks
  instead.
- **`MPV_HRT=always`:** mpv let go of Windows' 1 ms timer after each wait, and Qt's timers fell to 15.6 ms.
- **libmpv 0.40 and 0.41 leak a GL fence per frame** (fixed in 0.42): the last fence of each frame drawn is deleted by
  the app (`FrameFences`). 1479 MB an hour at 9 videos on Intel down to 20.
- **glibc: 8 malloc arenas and memory given back** 2 s after a video closes (Linux, every driver). 16 Hardware MPV videos
  985 MB to 810; a 10-minute churn, all closed, 2126 MB to 519.
- **Hidden cells** (Single Mode, minimized, the tray) take their frames without drawing them and are drawn again 50 ms
  after they show. On Direct a hidden window already costs less than Copy's.
- **A cleanup waits 5 s for the render thread**, then leaves it behind: one stuck in a GL driver would freeze the app.

## Turned down

- **Sleeping cells:** a video on the grid stays loaded.
- **A multi-process mode:** the decoder is the limit, not the GIL.
- **Direct's view by `video-crop`:** each change reconfigures mpv's output and lands 70-600 ms later. mpv's window is
  moved over the picture instead, or mpv places the picture in a window over the part on show.
- **Fast seeks by `relative+keyframes`:** with no key frame after, mpv went to the start.
- **Holding Direct's mpvs with `vid=no`:** mpv ends a file with no track at once, or plays its sound first.
- **For Direct's crashes:** a setting to start them together (1 in 250-1200 opens on NVIDIA, 1 in 50 on AMD, the whole
  app down each time); devices without the driver's threads (no change); `d3d11va-zero-copy` (worse); `gpu-api=opengl`
  (froze the GUI); Vulkan (1.4 s to make a device).
- **Direct on macOS:** MPVKit's MoltenVK output draws but never follows a resize; it would take a patched libmpv.
- **An LGPL libmpv**, and split packages with and without it.
- **A libplacebo settings page, rows for `gpu-api` / `vo`, a typed-in options box:** shaders take mpv off its fast path,
  and each default was picked for a bug found. `mpv.conf` covers the few who need it.
- **Automatic frame skipping:** a switch stops a video a third of a second, and it would flip up and down.
- **Per-frame time as a setting:** CPU everywhere for two features; `TimeAhead` does it for them.
- **mpv's stats script for playback stats:** needs mpv's key bindings and a thread a video. In `docs/ROADMAP.md` as a panel
  of our own, with surviving a GPU reset.
- **Streamlink's DASH reader for live DASH:** made for its own downloader.

## Known and left

- **Transport:** on a video under about 170 ms the end action never runs, no time report getting through. At 240 fps and
  up a frame step may land a frame short (mpv's 5 ms either side). The first pass after Set Loop End can be a report late.
- **View:** a pan shows on Direct with mpv's next frame, 20-80 ms; at once on Copy and Shared. Under X11, for 50-150 ms
  after the loading status goes, Direct's window can show the old card (seen only in test screenshots).
- **Subtitles:** up to 0.40 the side margin stops at 300, so a zoomed line can be wider than the view. Panned while zoomed,
  a line stays centred on the whole picture. In a zoomed picture a line is a little soft. Turned on its side the line
  goes by the frame's height and wraps sooner than VLC's. Several tracks added while playing lose their languages till the
  next load. ttml, dfxp, dks, psb and usf aren't read; UTF-16 with a mark gets a non-Latin line's first letter wrong, and
  without one doesn't open. MPVKit's libmpv (macOS) reads only srt, ass/ssa, vtt and mks; others are offered greyed out.
- **Sound:** Left and Right on a surround track take that side of the stereo mix. On PipeWire, WirePlumber remembers a
  device VLC moved a stream to for every stream after. A track that says one channel and decodes to two would come out
  3 dB up (not seen). Turning off the only track left says off while it plays on, as on VLC.
- **Deinterlacing:** made clips only; no broadcast, DVD or film, no PAFF or MBAFF H.264. Bob and Linear can't start on an
  odd height, only a log line saying so. Paused just after picking a mode, the frame on show can be from before the
  filter. A decoder change stops the picture 0.3-1 s. 9 cells of 1080i with On play at about half speed on an HD 4600.
  MPVKit lacks `field`, `separatefields`, `convolution`, `fieldmatch` and `decimate`: those modes are greyed out there.
- **Streams:** a live DASH picture's size is picked as it loads; a pane made bigger keeps it. FFmpeg's HLS reader asks for
  the init segment again with every playlist (about 1 KB each).
- **Software MPV:** no HDR tone mapping (flat, as on Software VLC). No subtitles without zimg on `bgra`, so `bgr0` there.
- **Memory:** mpv keeps the handles of deleted fences, 8 bytes a frame on 0.40 and 0.41. Intel's old i965 VA-API driver
  grows about 40 MB an hour on its own.
- **Windows:** between a new size and the next swap, Shared shows the last frame stretched for 5-15 ms. Direct on Intel
  never tried; `d3d11-flip=no` on NVIDIA was 0 of 44 crashes against 3 of 44, a hint not followed.
- **macOS:** `window.raise_()` sometimes takes 2-3 s in the window server, a bare Qt window too. Auto reads no video
  memory there.
- **CI:** Hardware MPV hangs on GitHub's macOS runners (no GPU); they run Software MPV only, as Windows' do (no OpenGL).

## Traps

What cost time to find, for whoever works on this next. The rules are in `AGENTS.md`.

- mpv waits 200 ms for a frame it announced to be rendered, then drops it without a word. A paused cell could lose its
  only frame: the renderer draws again when an update is over 150 ms old with no frame in it.
- mpv's log comes after its events: a failure waits 0.1 s for its reason.
- `keep-open` pauses at the end, which a reload then kept: `keep-open-pause=no`.
- Frames on the GPU stop a filter for good, only a log line saying so. A filter this libmpv lacks, added as the file
  opens, ends it; `set vf` then says nothing and leaves the dead filter in. Two decoder changes in a moment stopped the
  picture till the next key frame: every decoder change on an open file seeks to where it is.
- `sub-scale` grows `sub-margin-x` and `-y` too. `sub-back-color` only with the box on (0.35 and 0.37 go by it alone).
  On Windows an `.idx` asked for by URI doesn't find its `.sub`: by path. Left alone mpv takes a file over the track the
  file marks: `sid` is always said.
- The software renderer leaves `bgr0`'s fourth byte at 0 with zimg, which Qt paints as see-through: `bgra` there.
- `QOpenGLTextureBlitter.sourceTransform` with a top-left origin counted the part from the bottom (found on Qt 5.15). A
  blitter freed by Python while Qt deletes its context crashed: the context holds it till it's gone.
- Under X11 mpv maps its window only once the parent is mapped: a player started before its cell is shown never shows.
  Left to pick, mpv took its Wayland output under XWayland: Direct says `gpu-context=x11egl`.
- mpv counts what it puts in a hidden window as shown: draw counts only on Copy and Shared.
- A test machine's offscreen run has no sound server; an idle PulseAudio null sink starts sound 1.6 s late.

## Against VLC

- **Sound,** measured from null sinks: volume 100 / 75 / 50 within 0.001 of VLC's level; Reversed, Left, Right, Mono,
  Stereo, Dolby Surround and Headphones the same on a stereo track. Every audio file format tried plays beside a video on
  MPV, so VLC's warning about files it can't play isn't shown there. Device names match VLC's on Windows and
  PulseAudio, so a playlist's pick is found on either.
- **Subtitles:** `sub-font-size=50` gives VLC's width and height of text within 1%; the bottom gap is VLC Hardware's
  (4.4% of the height), where VLC Software's is 7%. VLC's text sits a little left of centre. A line picked part way
  through shows in 0.1 s with no seek, where VLC needs one. Raising lines (`subtitles/margin`) goes by the picture's
  pixels as on VLC Hardware.
- **Seeking:** VLC lands short of where it's asked, in about 2 s on YouTube; MPV Exact lands on the frame, YouTube in
  0.4-3 s.
- **Loops and skips** turn at the frame on both with `TimeAhead`; before it, up to 0.2 s late on MPV and 0.5 s on VLC.
