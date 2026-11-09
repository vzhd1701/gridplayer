# VLC notes

What was found and done about VLC itself while working on the `mpv` branch: freezes, CPU, 32-bit, single process against
multi-process. These were items 10.23-10.28 of `MPV_PLAN.md` and keep their numbers there, as commits and the plan's log name them.
The longer stories have files of their own: `VLC_WAITS.md` (10.26) and `VLC_HELPER.md` (the native log helper designed for 10.24, not
built).

- [x] 10.23 VLC, found by the overnight run, VLC's drivers not changed: Hardware VLC SP on Linux held the GUI thread 42 s at load waiting
  for VLC to buffer after the start seek (`_set_time_initial`). On Windows both VLC modes play 1080p60 at 29 from 9 cells, where they held 60
  on 2026-11-06; the 11-06 commit does the same now, so it's the machine as set up (120 Hz on the AMD iGPU?)
  - **Closed 2026-11-09:** the Linux freeze is 10.25's, fixed there (the 10-minute churn passes on `test_gpu` where it hung). The
    Windows frame rate isn't the code, as the 11-06 commit plays the same now; not chased further.
- [x] 10.24 **Hardware VLC in a single process freezes the app on Windows, for good.** You hit it opening a playlist (2026-11-08 22:41, twice).
  **Done your way (2026-11-09): VLC's log is off for that driver on Windows**, no native helper: building it for every architecture for the
  rest of the project's life isn't worth a log. The error card shows the error without VLC's own lines there. The "Log level (VLC)"
  tooltip says so. Reopen loop at debug: 50 of 50, where it froze within 0-9. The design below is kept in case it's ever wanted.
  Not this branch's: `master` freezes the same way, and v0.5.5 sets up the same callback.
  - **What happens:** two threads wait on each other, and both stop for good.
    - The GUI thread is inside a Qt call that moves or raises a native window: `raise()` in `activate_window`, which loading a playlist and
      opening files both do. PyQt5 keeps holding Python's lock (the GIL) through the call. Windows makes the call wait for every thread with
      a window under it to answer.
    - VLC's Direct3D 11 window thread is waiting for that same lock, inside our log callback (`InstanceVLC.libvlc_log_callback`). Every
      message VLC logs goes through that Python callback, whatever the log level, as it also catches VLC's errors for the error card.
  - **Seen:** caught with `py-spy`, the GUI in `QWidget::raise` → `NtUserSetWindowPos`, three VLC threads in `PyGILState_Ensure` under
    `vlc_Log`. Reopening a 3-video playlist: with VLC's log at debug it froze within 0-9 reopens, on this branch and on `master` alike; with
    the log off it passed 20. So logging only makes it likely.
  - **Not affected:** multi-process VLC, where VLC's threads wait on another process's lock; Software VLC in a single process, which has no
    VLC window; MPV, which owns no windows; Linux and macOS, as far as known (no cross-thread window messages like this on X11).
  - **Until fixed:** VLC's log level off, or multi-process VLC.
  - **The fix chosen: a native log helper, Windows only.** About 100 lines of C, a DLL loaded by ctypes:
    - VLC calls the helper instead of Python. It copies what the Python callback reads now: level, module, file and line, the object's id
      and type (`libvlc_log_get_context`, `libvlc_log_get_object`) and the text (`vsnprintf`), into a ring buffer behind a native lock
      held only for the copy. A full buffer drops and counts, never waits.
    - One Python thread per process drains it every few milliseconds and runs today's handling: log lines, errors kept for the error card,
      HTTP refusals. Split today's `_cb` into "decode one message" and that handling, so both paths share it.
    - It takes VLC's function addresses from Python at start, so building it needs no VLC headers or libraries.
  - **What it costs:**
    - The Windows build (`build.yml`, PyInstaller) gets one MSVC compile step, which GitHub's Windows runners already have, and one binary
      in the spec. Chocolatey takes that build.
    - A `just` recipe for running from source. Without the DLL the app falls back to today's callback.
    - The PyPI wheel is pure Python: ship the DLL in it as data, or leave pip users on Windows with today's callback.
    - Linux packages: nothing.
  - **Proof:** the reopen loop with VLC's log at debug, 50 reopens, no freeze. The loop is `hang_loop.py` in the 2026-11-09 session's
    scratchpad; it needs a real window (`REAL_APP_QT_PLATFORM=windows`).
  - **Rejected:**
    - Filtering in the callback: it runs in Python, so it has already waited for the lock.
    - VLC's own `--file-logging`: it writes nothing until 4 KB or exit, and leaves out which object said it.
    - Letting go of the lock on the GUI side: PyQt5 can't, and Qt makes these calls everywhere.
  - All of it, with the reopen loop, is in `VLC_HELPER.md`.
- [x] 10.25 **VLC in a single process waited for VLC on the GUI thread, up to the load timeout, twice.** Hardware and Software VLC single
  process (the default on macOS). The player object of `video_frame_vlc_hw_sp.py` / `_sw_sp.py` lives in the GUI thread; its `QThread`
  only makes and releases VLC. So every command and every load stage runs on the GUI, and the last stage, `load_video_st4_loaded`, waits
  there for VLC: the video output, buffering after the start seek, the pause, and a second seek for a paused video. Each wait goes up to
  what is left of the 120 s load timeout (`player/video_init_timeout`). Waiting lets go of the GIL, so it always ends.
  - **Measured, Windows, 4 videos served over HTTP, one whose server stops answering at its start seek:** single process froze the whole
    app 239 s, 119 s twice; multi-process 0.2 s, with only that cell waiting. It needs a start position or a paused start: a playlist
    saved with positions or play state (`playlist/save_position`, `save_state`, off by default), "start paused", a random start, or a
    reload. Opening from the start and playing, only the video output is waited for.
  - **In normal use it costs little:** 25 local 1080p60 videos 0.9 s against 0.5 s multi-process; 6 network videos with 300 ms of delay
    the same as multi-process. The 42 s GUI freeze on `test_gpu` overnight (10.23) is this, with the decoder overloaded.
  - **Fix:** do what multi-process does in its own process, in a thread: the player object moved to its `QThread`, which runs an event
    loop. Commands and load stages then run there, in order, as they do in a VLC process; the GUI only sends commands and hears signals.
    Cleanup aborts the waiter and quits the loop straight from the GUI, so a wait in progress doesn't hold it up; VLC is released on that
    thread after, as now. The re-applied view, chapters and time checks go to that thread rather than the GUI, still off libvlc's callback
    threads. Both single-process drivers. Maybe also "Event waiting hangs on init in MacOS", as the waits leave the main thread there.
  - **Done 2026-11-09 as above.** `moveToThread(self)` in each single-process player before anything connects, `exec_()` in `run()`,
    `cleanup()` connected direct: it aborts the waiter and quits the loop, and the release follows on the player's thread, Software VLC's
    too now. The waiter returns at once once aborted, so a load on its way out waits for nothing.
  - **Tested:**
    - The stalled seek, Windows: Hardware 0.19 s frozen (was 239 s), Software 0.15 s; closing the playlist while the stuck video still
      waits: 0.12 s and 0.03 s.
    - The real-app suite, offscreen on Software VLC single process: 34 passed and the known bug.
    - `test_gpu`, Hardware VLC single process on X11, the 10-minute churn twice: both pass, where overnight it hung.
    - Windows, Hardware VLC single process on real windows off the screen, 15 scenarios. 7 pass. The other 8 fail the same way without
      the change, so they come from the window being off the screen (no picture to measure, a double click) or the log being off
      there (`stream_errors`): `live`, `aspect_ratio`, `crop_ratio`, `pixel_shape`, `external_audio_jump`, `stream_errors`, `list_shape`,
      `single_mode_show_big`. Five got further with it.
  - **Not tested:** macOS, where it's the default driver (the VM was off, and it draws no video). Whether macOS's own init hang goes
    with it isn't known either.
- [x] 10.26 **VLC in a single process on Windows burns the CPU with many videos.** You saw Software VLC single process take about 80%
  of the CPU with a dozen small videos, where multi-process took 15-20%: the reason multi-process was made. VLC 3 looks
  `WaitOnAddress` up in `kernel32.dll`, which doesn't have it, and falls back to 32 wait slots for the whole process, where any wake
  wakes every thread in the slot. 15 videos in one process: up to 2.5 million context switches a second, 185-1370% of a core, uneven
  from run to run. All VLC drivers on Windows, kept small by multi-process. VLC 4 fixed the lookup in 2021; VLC 3 never got it. The
  whole story, and what didn't work: `VLC_WAITS.md`.
  - **Done 2026-11-09:** `gridplayer/utils/libvlc_waits.py`, run right after VLC loads in every process: finds VLC's three pointers in its
    own code and, only for VLC 3.0.x and only if they hold its stand-in, points them at `KernelBase.dll`'s. Renaming the
    DLL in the file doesn't work: the XP builds then crash in `DllMain`.
  - **Tested:** the same 15 clips, 6 runs: 141-221% of a core, about 7,000 switches a second, every run (before: 7 of 13 above 600%).
    Hardware VLC single process, 2 runs: 38-46%. Multi-process: its VLC processes wait the new way too. Every official build from
    3.0.0 to 3.0.24, 64-bit and 32-bit, read as data: the three pointers found and holding the stand-in (3.0.22's newer compiler stores
    before testing, now matched too). 32-bit GridPlayer with the official 32-bit 3.0.24, the same 15 clips, Software single process,
    4 runs each: 138-256% with the swap, 6,000-17,000 switches a second; 335-1402% without, 210,000 to 2.2 million. Official 3.0.20
    64-bit, one run each: 176% against 480%. Not tested: a packaged build, Windows 7.
- [x] 10.27 **32-bit single process runs out of address space with many videos.** Seen testing 10.26 with the 32-bit app (from source,
  `python.exe` not large-address-aware, so 2 GB): Hardware VLC single process, 8 cells peak at 1858 MB of address space, 12 and 15
  crash with nothing logged within 2 s of loading; Software, 15 cells, frame buffers now and then fail to allocate as they load. Not the
  swap: the same with it off. Multi-process (4 videos a process) keeps each process well under.
  - **Nothing to change:** the packaged 32-bit `GridPlayer.exe` (dev build from GitHub) is large-address-aware, so 4 GB on 64-bit
    Windows; only runs from source with a plain 32-bit `python.exe` get 2. With a 4 GB copy of that Python, 15 cells: Hardware single
    process peaks at 2645 MB and plays (38% of a core), Software at 2321 MB with no failed buffers (185%). 32-bit Windows itself still
    has 2 GB a process.
  - **Fixed on the way:** `win32_vlc_vout.py` called `GetWindowLongPtrW`, which 32-bit `user32` doesn't export (a macro for
    `GetWindowLongW` there), so Hardware VLC in the 32-bit app failed there; now falls back like `taskbar.py`. Checked in 32-bit.
- [x] 10.28 **VLC single process against multi-process on Windows, now that 10.26 is fixed.** Multi-process was made because a single
  process burned the CPU; is there still a reason for it? 64-bit VLC 3.0.24, window on the other desktop, 2 runs each, the bench's
  numbers for the whole app (all its processes). The default stays Hardware VLC multi-process for now.
  - Light, the 15 small clips without sound (4, 9, 16 cells): every run at the clips' full frame rate. CPU about the same for Software
    (4: 74-86% single against 43-60%; 9: 101-106 against 123-142; 16: 181-229 against 196-225, as noisy as it looks), lower in a single
    process for Hardware (16: 27-33% against 34-39%). Memory 7-12% less in a single process (16 Hardware: 1652 MB against 1858).
  - Heavy, past what the machine plays (1080p60 at 9 and 16 Software, 16 and 25 Hardware; the bench mix with 4K and HEVC 10-bit): the
    same frame rate and CPU both ways (Software 1080p60 16: 59.6-60.1 fps, about 1270%; Hardware 1080p60 16: 25 fps, the GPU's
    decoder the limit). Hardware 1080p60 25: multi-process a little ahead, 16.4-16.8 fps against 15.5-15.6. Memory within 3-10% either
    way. Single process loads slower with many videos: Hardware 25, 2.4-3.0 s against 1.4; Software 16, 1.4-2.0 against 0.8-0.9.
  - So no longer a performance question: what's left is a video crashing VLC taking one process (multi) or the whole app (single),
    and load time. **Done (2026-11-09):** the Processes tooltip and the README said a single process can freeze or load the CPU past
    4-6 videos, which 10.24, 10.25 and 10.26 made untrue; both now say what's left (crash takes one process or the app, load time).
