# Direct's crashes: several mpv outputs coming and going at once

Found 2026-11-11 to 2026-11-13 on the `mpv` branch, with MPV's Direct output (each video an mpv drawing into a window of its
own). The app crashed, all of it, now and then as videos were opened, closed or reloaded. The causes are in graphics drivers and
libraries, not in mpv or GridPlayer; what sets them off is GridPlayer's way of using them. Avoided by
`MpvRenderService.add_own_window` and `_start_next` in `gridplayer/mpv_player/renderer.py`. Plan items 14.11 and 14.12 in
`docs/archive/MPV_PLAN.md` have the runs as they went.

## The common ground

Direct runs several mpvs in one process, and each makes its own graphics output: on Windows a Direct3D 11 device and swap chain,
on Linux its own connection to the X server and an EGL context on it. Each is made and let go of on that mpv's own thread, as
its video starts and as it closes. A game or a player makes one output in a process, once; drivers are tested that way.
Several made and let go of at the same moment, in one process, on different threads, is what breaks, in three different ways.

Copy and Shared never crashed in any of this: there the app owns one OpenGL context and mpv makes no output of its own.

## NVIDIA, Windows

- An access violation reading address `0x38` at `nvwgf2umx.dll+0x98cf4a` (NVIDIA's Direct3D 11 driver, 32.0.16.1742), every
  time the same place, mostly on a thread of the driver's own. An empty pointer followed to a field 0x38 bytes into what it should
  point at: an object not made yet, or already freed, by another thread.
- Only when two or more mpvs make their outputs at the same moment. Started 0.4 s apart: none in 1440 starts.
- Not the decoder: clips decoded on the CPU crash as well, and `hwdec=d3d11va` against NVDEC changed nothing. Not the driver's
  own threading: devices made with `D3D11_CREATE_DEVICE_PREVENT_INTERNAL_THREADING_OPTIMIZATIONS` (by hooking libmpv's
  `D3D11CreateDevice`) crashed the same.
- How often, three videos opened together and closed, over and over: about once in 250 rounds with the test folder's
  CPU-decoded clips, once in 700-1200 with GPU-decoded ones. Each crash takes the whole app down.

## AMD, Windows

- The heap broken: Windows ends the app with 0xc0000374 (`ntdll.dll+0x118095`), or a read of a wild address at
  `ntdll.dll+0x279b6` under `d3d11.dll` on an mpv thread; once in `amdxx64.dll` itself (driver 32.0.21043.19003).
- Only with several mpvs alive and one's output let go of as another's is made. One video opened and closed alone: 0 in 24 runs
  of 60 rounds. Copy, three at once: 0 in 24.
- How often: 14 of 19 runs with all starting together, about once in 50 rounds of three.

## Linux, X11

- glibc aborting on a broken heap (`corrupted size vs. prev_size`, `malloc(): unsorted double linked list corrupted`,
  `corrupted double-linked list`), in 3 of 7 runs of the `mpv_subtitles` scenario on Ubuntu 24.04.
- The one understood to the end, from a core with `MALLOC_CHECK_`: one mpv closing its X connection (`XCloseDisplay`, through
  `mp_destroy`) while another's output thread opens one and asks for its extensions (`vo_x11_init` -> `xrandr_read` ->
  `XRRQueryExtension` -> `XextAddDisplay`). libXext and libXrandr keep process-wide lists of open connections with no lock.
- Wayland would avoid it, but mpv can only draw into a window given to it as an X11 one.

## What is done about it

1. **Outputs made in turn, on Windows** (`OWN_WINDOWS_START_IN_TURN`): every mpv opens its file at once, and is held at
   `on_preloaded`, its tracks known and nothing made yet (`MpvPlayer._hold_output`). The service lets one go on at a time,
   the next when the one before has its output up (`vo-configured`), plays, fails or ends, or after 1 s
   (`OWN_WINDOW_START_TURN_MS`). NVIDIA: 0 in 44 runs with whole starts in turn, against 3 in 44 started together; held,
   0 in 48. Until 2026-11-13 the whole start waited its turn, opening, network and buffering too.
2. **No start while one closed is still going, everywhere**: until each mpv closed has said it's terminated, or 3 s
   (`OWN_WINDOW_GONE_WAIT_MS`). AMD in turn: 6 in 24 runs crashed without it, 0 in 48 with it, 0 in 48 held. Linux: 0 in 6 runs checked under
   `MALLOC_CHECK_`, and every MPV scenario passes on Direct on Ubuntu (libmpv 0.37) and `test_gpu` (0.40).

A held mpv still takes what it's told (a pause, a seek). Closed while held, it's stopped first and then let go on
(`MpvPlayer._terminate`): mpv's quit waits on the hook, and let go on as it is, it made its output on its way out. With no
video track (`vid=no`) it would make no output either, but a file with no sound then has nothing to play and mpv ends it, and
one with sound starts playing it.

The waits cost nothing while videos play: only opening and reloading. What they cost there:

- Local files: a turn is mpv making its output and compiling its shaders, about 0.28 s for 1080p on NVIDIA, the part that has
  to be one at a time. 25 cells all playing in 8.5-8.7 s on NVIDIA, 6.7 s on AMD, the same as before holding (5.8 s all
  together, once).
- Streams: opening and buffering go on side by side now, and a turn ends once the output is up. 16 test streams (each request
  held 0.15 s): all playing in 11.3-11.8 s on NVIDIA, against 20.9-21.5 s with whole starts in turn; from the first playing to
  the last, 2.3 s against 11.7 s. AMD: 9.7-11.1 s against 19.3-20.0 s. The rest is the app resolving the links, before mpv.
- A reload: the new ones wait for the old ones to close, which took well under the 3 s in every run (2763 waits, none at the
  limit).

## Tried, and not the answer

All with every mpv starting together, on NVIDIA, 19-24 runs of 60 rounds each:

| | crashed | |
|---|---|---|
| `d3d11-flip=no` (copied into the window, not handed to the compositor) | 0 / 44 | against 3 / 44 with flips: a hint, not proof |
| `vo=gpu-next` | 1 / 19 | the same crash |
| `d3d11va-zero-copy=yes` | 5 / 19 | worse |
| `gpu-api=vulkan` | 0 / 19 | its device takes about 1.4 s to make, 0.1 s for D3D11, so it rarely played before a round closed |
| `gpu-api=opengl`, `gpu-context=win` | 19 / 20 froze | as the mpvs started; mpv's default `angle` context crashed at once in `libGLESv2.dll`, beside Qt's own |
| AMD, `d3d11-flip=no` | 18 / 24 | no help |

## What would end it rather than avoid it

- The vendors fixing their drivers. The repro is small: three mpvs with `vo=gpu`, `gpu-api=d3d11` and a `wid` each, in one
  process, loading at once and closed at once, over and over.
- One output device for all of them: mpv has no way to be given one for `vo=gpu`, so a patched libmpv.
- Each Direct mpv in a process of its own, which shares nothing in the driver: memory a process, and windows across processes.

## Not known

- Intel GPUs on Windows: never run.
- Whether other NVIDIA and AMD drivers do the same: one driver of each was run.
- How often with more than three videos at once. More outputs coming up together likely raises it, unmeasured.

## How it was hunted

A real-app scenario on the other virtual desktop opened three videos together, waited a random 0-1.2 s, closed them a random
0-0.1 s apart, and did it again, 60 rounds a run, many runs a variant taken in turn so a drift over a night hits all alike. An
in-process vectored exception handler logged each access violation's module and offset and the stack's modules before the crash
went on. Traps found on the way:

- A crashed run's process can be left stuck in the graphics driver, two threads, about 1 GB, and nothing ends it but a reboot. A
  run needs a short timeout, its own leftovers ended, and a stop when free memory runs low.
- Windows Explorer died once in the night; every move of a test window to the other desktop then hung (the virtual desktop
  service is Explorer's). A night run needs a stop when runs stop starting.
- Patching a method of the render service from a scenario misses the calls through a timer connected before the patch: patch
  what the method calls, or the module's constants.
