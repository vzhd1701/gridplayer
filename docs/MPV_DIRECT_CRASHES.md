# Direct's crashes: several mpv outputs coming and going at once

Found 2026-11-11 to 2026-11-13 on the `mpv` branch, with MPV's Direct output (each video an mpv drawing into a window of its
own). The app crashed, all of it, now and then as videos were opened, closed or reloaded. The causes are in graphics drivers and
libraries, not in mpv or GridPlayer; what sets them off is GridPlayer's way of using them. Avoided by
`MpvRenderService.add_own_window` and `_start_next` in `gridplayer/mpv_player/renderer.py`. Plan items 14.11 and 14.12 in
`MPV_PLAN.md` have the runs as they went.

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

1. **Starts in turn, on Windows** (`OWN_WINDOWS_START_IN_TURN`): the next mpv starts when the one before plays, fails or ends,
   or after 1 s (`OWN_WINDOW_START_TURN_MS`). NVIDIA: 0 in 44 runs, against 3 in 44 started together.
2. **No start while one closed is still going, everywhere**: until each mpv closed has said it's terminated, or 3 s
   (`OWN_WINDOW_GONE_WAIT_MS`). AMD in turn: 6 in 24 runs crashed without it, 0 in 48 with it. Linux: 0 in 6 runs checked under
   `MALLOC_CHECK_`, and every MPV scenario passes on Direct on Ubuntu (libmpv 0.37) and `test_gpu` (0.40).

The waits cost nothing while videos play: only opening and reloading. What they cost there:

- Local files: the next starts as the one before plays, about 0.1 s later (126 ms the median, 25 ms the least, with H.264 on
  NVIDIA). 25 cells loaded in 9.0 s in turn against 5.8 s together.
- Streams: a stream can take a second or more to play, so the next waits the full 1 s. 16 streams: up to about 16 s before the
  last one starts.
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
