# VLC's log in a single process: why it freezes, and a helper for later

Found 2026-11-09 on the `mpv` branch, from a freeze opening a playlist with Hardware VLC in a single process on Windows. Fixed for
now by not taking VLC's log there (item 10.24 in `VLC.md`). This keeps the analysis and the design of a native helper that
would bring the log back, perhaps as a library of its own, so this repository needs no compiler to build.

## What happens

Two threads wait on each other, and both stop for good:

1. The GUI thread is inside a Qt call that raises, activates, focuses or shows the main window: here `raise()` in
   `WindowStateManager.activate_window`, which loading a playlist and opening files both call. PyQt5 keeps holding Python's lock (the GIL)
   all through a Qt call.
2. Windows makes that call wait until every thread with a window under the main window has answered its messages. VLC's Hardware output
   makes a window of its own inside the cell's window, from a VLC thread (`direct3d11: Win32VoutCreateWindow`, "created video sub-window").
   Windows also links the input of a parent window and a child window owned by different threads, which adds to what waits.
3. That VLC thread is inside our log callback (`InstanceVLC.libvlc_log_callback`), waiting for the GIL.

The GUI holds the GIL and waits for the window thread; the window thread waits for the GIL.

**Seen:** a `py-spy dump --native` of the frozen app. The GUI is in `QWidget::raise` → `NtUserSetWindowPos`, and three VLC threads are in
`PyGILState_Ensure` under `vlc_Log`, from `libdirect3d11_plugin.dll`. The user's own log (2026-11-08 22:41, twice) stops dead right
after "created video sub-window", with not even VLC's other threads logging, as every thread that logs then waits for the GIL.

**How often:** a 3-video playlist closed and reopened again and again, VLC's log at debug: frozen within 0-9 reopens, on `master` as on
this branch. With the log level off, 20 of 20 passed, but the callback still runs for every message, so off only makes it rarer. v0.5.5
installs the same callback the same way, since 2022, so it isn't new. It took VLC's debug log, Hardware VLC in a single process and opening
files together to show up often.

## Where it happens

**Only Hardware VLC in a single process, on Windows.**

- **Windows** gives a window to the thread that made it, and only that thread can answer what is sent to it. Calls that change activation,
  focus or which window is on top send to the windows under the main window and wait. Moving and resizing the main window don't seem to:
  VLC's window notices its parent's new size on its own. That's from reading how Windows works, not tested call by call.
- **Linux (X11, and Wayland through XWayland, as VLC 3 can't embed in Wayland)**: a window belongs to the X server, not a thread. VLC
  reaches its window through its own connection to the server. When the GUI raises or resizes its window it sends the request and goes on;
  anything VLC's window is told waits in VLC's queue. The GUI never waits on VLC's thread. Not tested for this freeze.
- **macOS**: VLC's output waits on the app's main thread, as it hands its drawing work to that thread and waits. That's the other way round,
  and doesn't involve the GIL. `player_base.py` skips some waits there for it ("Event waiting hangs on init in MacOS"). Not tested.
- **Multi-process VLC** on Windows: VLC's window thread waits for the GIL of its own process, which nothing there holds while waiting on the
  GUI. Safe.
- **Software VLC in a single process**: VLC makes no window, it hands frames to us. Safe.
- **MPV**: mpv owns no windows (`vo=libmpv`). Safe.

## Why only the log callback

Every VLC or mpv callback into Python needs the GIL, but only the log is called on VLC's window thread:

| Callback | Runs on | Safe? |
|---|---|---|
| VLC events: playing, paused, time, buffering, vout, errors… (`player_base`, `player_event_waiter`) | VLC's input and event threads, which own no window | Yes. They hand work to the GUI through queued signals. None calls `stop`, `release` or sets a new media, the libvlc calls that deadlock from inside VLC's own callback: `stop` is only called from commands and the load stage |
| Software VLC's frames (`image_decoder`) | VLC's video output thread | Yes. No VLC window, and the frame lock gives up after 1 s when stopping |
| VLC's log (`instance.py`) | Every VLC thread that logs, the window thread too | **No**, for Hardware VLC in a single process on Windows. Off there now |
| MPV's events, property observers, log | python-mpv's event thread | Yes. No windows |
| MPV's `update_cb` | mpv's threads | Yes. It only sets a flag and wakes the render thread |
| MPV's GL address lookup | Our render thread, inside our own call | Yes |

Mouse and keyboard events are off for VLC (`--no-mouse-events`, `--no-keyboard-events`), so logging is the only way VLC's window thread
ever reaches Python. Calls into VLC and mpv go through ctypes, which lets go of the GIL for the whole call, so a thread waiting inside one
never holds a callback up.

## What doesn't work

- **A lock or a check in the callback.** ctypes takes the GIL before the first line of a callback runs; that's where it waits.
- **Taking the log on another thread.** `libvlc_log_set` doesn't attach to a thread: VLC calls it at once, on whichever thread wrote the
  message. Handing it on means queuing it on that thread first, which in Python needs the GIL.
- **Earlier thread splits** (`bc2d5e0` a thread per single-process player, `878b817` the view re-applied from the GUI, `d537b2d` the player
  released on its own thread) decide which of our threads calls VLC, not which VLC thread calls us.
- **VLC's own file log** (`--file-logging --logfile=…`): it buffers, nothing reached the file while playing, only at exit, and it leaves out
  which object said what, which the error card goes by.
- **Letting go of the GIL on the GUI side.** PyQt5 can't for a call. Making the risky calls through ctypes instead (`SetWindowPos` for
  `raise_()`) would let go of it, but any one missed, in the app or inside Qt, freezes it again: not provable.
- **Filtering by level in VLC.** libvlc hands every message to the callback, whatever `--quiet` or the level.

## Now

`video_frame_vlc_hw_sp.py` makes its `InstanceVLC` with `is_logged=not env.IS_WINDOWS`, so no callback is set there, and the app logs
"VLC's own log is off for this player" as each starts. The cost, there only: no VLC lines in the log, and the error card shows the error
without VLC's own lines under Details. "Log level (VLC)" says so in its tooltip. The reopen loop at debug: 50 of 50.

Anything else that gets VLC's window thread into Python brings the freeze back.

## The helper, if it's ever wanted

A small native library that takes VLC's messages without the GIL and hands them to Python later.

**Native side**, about 100 lines of C:

- `vlclog_attach(libvlc_instance_t *, fn_log_set, fn_log_get_context, fn_log_get_object)`: sets its own callback with `libvlc_log_set`.
  It takes VLC's functions as addresses from Python, so building it needs no VLC headers or libraries.
- The callback, on VLC's thread: level, then `libvlc_log_get_context` (module, file, line), `libvlc_log_get_object` (object type name and
  id) and the text through `vsnprintf`, copied into a ring buffer behind a native lock held only for the copy. A full buffer drops the
  message and counts it, never waits. It signals an event.
- `vlclog_read(buffer, size)`: hands over what's queued, as records. `vlclog_dropped()`, `vlclog_detach(instance)` before the instance is
  released.
- One buffer per instance, or one per process with the instance in each record. Strings copied in fixed fields (module 32, object type 32,
  file 64, text 1024 as now).

**Python side:**

- One drain thread per process, woken by the event or every 20-50 ms, turning records into what `_cb` reads now.
- Split today's `_cb` into decoding and handling, so both paths share the handling: level filter, `keep_vlc_error`, `note_vlc_object`,
  `http_refusal`, writing the log line. The handling is unchanged; it only runs a few milliseconds later and on the drain thread.
  `note_video_thread` goes by the thread a VLC object speaks on; a record would carry VLC's thread id for it.
- Fallback to today's callback where the library isn't there, except Hardware VLC in a single process on Windows, which stays without a log.

**As a library of its own:** wheels for Windows x64, arm64 and x86 at least, from a CI of its own (`cibuildwheel` or MSVC on GitHub's
runners), installed as an optional dependency. Linux and macOS don't need it for this freeze, though it would cost nothing to build there.

**Proof it works:** the reopen loop below at VLC's debug log, 50 reopens or more, no freeze, and the error card's Details still showing
VLC's lines on a broken file and a refused stream.

## The reopen loop

A scenario for `tests.real_app.run`, with `tests/real_app/bench` on the path for `common` and `away`. It needs real windows
(`REAL_APP_QT_PLATFORM=windows`): on the offscreen platform nothing can freeze, and on `master` the harness ignores that variable and runs
offscreen whatever it says. The user allowed it on their own desktop, with the window off the screen and never taking focus; `away.py`
puts it on another desktop instead. A frozen run shows as its `progress.txt` going quiet; take a `py-spy dump --native --pid` then.

```python
import os, time
from pathlib import Path
from common import clips_for, nested

SETTINGS = {
    "player/video_driver": "vlc_hw_sp",
    "playlist/warn_many_cells": False,
    "video_defaults/muted": True,
    "playlist/unsaved_changes": "discard",
    "logging/log_level_vlc": 10,  # debug
}


def scenario(d):
    progress = (d.out / "progress.txt").open("a")
    d.open(*clips_for("mix", 3))
    d.wait_until(
        lambda: len(d.cells) == 3 and all(c.is_playable for c in d.cells),
        "all play",
        120,
    )
    for i, cell in enumerate(d.cells):
        cell.seek(4_000 + 3_000 * i)
        if i % 2 == 0:
            d.act(cell, "Play / Pause")
    nested(2)
    playlists = d.player._managers_inst["playlist"]
    path = d.out / "saved.gpls"
    playlists._make_playlist().save(path)
    for round_ in range(50):
        playlists.cmd_force_close_playlist()
        d.wait_until(lambda: not d.cells, "closed", 30)
        nested(1)
        progress.write(f"{time.monotonic():.1f} round {round_}\n")
        progress.flush()
        d.player.process_arguments([str(path)])
        d.wait_until(
            lambda: len(d.cells) == 3 and all(c.is_playable for c in d.cells),
            "all play again",
            150,
        )
        nested(1)
```

On the user's desktop, before `scenario` runs: show the player at `(-4000, -4000)` with `Qt.WA_ShowWithoutActivating` and
`Qt.WindowDoesNotAcceptFocus`, and make `QWidget.activateWindow`, `showMaximized` and `showFullScreen` do nothing. Leave `raise_()` alone:
it's the call that freezes.

## Also found, not the log

VLC in a single process, Hardware and Software, runs every command and the last stage of loading a video on the GUI thread, and waits
there for VLC, up to the 120 s load timeout per wait. One network video that stalls at its start seek froze the whole app for 239 s,
where multi-process VLC kept the GUI free. See item 10.25 in `VLC.md`, with the fix: the player moved to its own thread.
