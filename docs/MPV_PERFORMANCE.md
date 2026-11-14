# VLC and MPV under load: findings

Measured 2026-11-06, on the `mpv` branch as of Stage 3. The bench is in `tests/real_app/bench`.
Plan items that come out of it are in `MPV_PLAN.md`, Stage 10.

## The answers

**Should MPV get a multi-process mode? No.** A prototype with the real renderer in 4 worker
processes played about the same on hardware decoding, at most 21% more in one overloaded case, for
20-50% more CPU. Software decoding gained more, but only once overloaded, and skipping frames gets
further for less. VLC's own multi-process mode plays about the same as its single-process mode too.
Crash isolation is the one reason left: a libmpv crash takes the whole app down. No MPV run crashed here.

**How much does the GIL matter? Very little for how many videos play.** The GPU's video decoder runs out
first: a C program with no Python hits the same wall at the same place, and changing Python's switch
interval changes nothing. Its share only shows far past that, at 64 small videos, and is at most about
20% there. Python costs some CPU and adds a few milliseconds of delay on the GUI thread, which nobody
will notice. Software VLC is the exception: the GUI thread holds the GIL most of the time there.

**What limits it, then?** On both machines the video decoder, then the GPU time left for drawing and for
being on screen. These are hardware limits, and they're close to the same for VLC and MPV.

**How does MPV compare with VLC?**

| | Better |
|---|---|
| Hardware decoding, how many videos hold full speed | Linux **VLC**, slightly: 12 against 9 at 1080p60. Windows level: both hold 9 and neither 16, 16-cell gap not narrowed down |
| Hardware decoding, CPU | **VLC**: 55-58% against 90% at 9x1080p60, MPV reads every frame back and paints it |
| Hardware decoding, memory | Depends on the machine. Linux **MPV**: about a third, 687 against 1907-2091 MB at 9x1080p60. Windows **VLC**: 794 MB VRAM against 2109, and less RAM |
| Past the limit, as MPV is now | **VLC**: 15 fps against MPV's 7 at 16x1080p60 |
| Past the limit, with MPV told to skip frames | **MPV**: 31 fps against VLC's 15, 25 cells 30 against 14 |
| Software decoding | **MPV**: half the CPU, half the memory, and the app stays responsive |
| Opening many videos | Level up to 16 cells. Past the decoder's limit **MPV**: 1.7 s against 107 s at 36x1080p30, on Linux |

**The biggest improvement found:** tell MPV to skip frames nothing else depends on, once the decoder
can't keep up. It's now the setting "Skip frames to play more videos". See [Past the limit](#past-the-limit).

## What was tested

| | `test_gpu` | Windows |
|---|---|---|
| CPU | i7-4790K, 4 cores, 8 threads | Ryzen 7 7700, 8 cores, 16 threads |
| GPU | Intel HD 4600, VAAPI, H.264 only | RTX 3060, NVDEC |
| Window | 1920x1080, real X11 through Xwayland under headless sway | 1920x1080, **offscreen**, so nothing reaches a screen |
| Software | Debian 13, libmpv 0.40, VLC 3.0.24, Python 3.13 | libmpv from the POC, VLC installed here, Python 3.14 |

The real app opened N cells of one clip, left them 8 s to settle, then was measured for 20 s. Clips are
60 s of real footage (Big Buck Bunny), 8-bit 4:2:0, re-encoded with x264 or x265 and no audio.

About 480 runs. The three controls were the same options and thread layout in **C with no Python**
(`native_bench`), raw **ffmpeg** with frames thrown away, and the real `VideoRenderer` in a **plain
window** (the prototype).

Frame rates are frames rendered or displayed per cell per second, the mean across cells. "Hold" means
at least 95% of the source's rate.

Limits of all this:

- Most points are one run. The 10-15 cell runs were done twice and agreed within about 10%, and three more times overnight, see
  [Overnight](#overnight-2026-11-09).
- Every cell plays the same file, with no audio, no subtitles and no overlay activity. The overnight run has a grid of different files too.
- Windows numbers include no display cost. Hardware VLC needs a real window, so it ran on another virtual desktop, where the compositor
  doesn't draw it. See [Windows: real window](#windows-rtx-3060-real-window).
- macOS wasn't run, nor AMD or NVIDIA on Linux.
- GPU "busy" on `test_gpu` is time out of its sleep state. It reads 100% with room to spare, so it isn't a
  utilisation figure. There's no per-engine counter in the container.

## How many videos play

### Linux: Intel HD 4600

1080p60 H.264, 12 Mbit:

| Cells | Hardware MPV | + skip | Hardware VLC SP | Hardware VLC | Software MPV | Software VLC SP | Software VLC |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 60 | | 60 | 61 | 59 | 61 | 60 |
| 4 | 60 | | 60 | 60 | 58 | 57 | 60 |
| 9 | 60 | 31 | 60 | 60 | 25-28 | 22 | 22 |
| 10 | 54 | | 60 | 60 | | | |
| 12 | 43 | | 60 | 60 | | | |
| 13 | 27 | | 35 | 36 | | | |
| 14 | 10 | | 17 | 17 | | | |
| 16 | 7 | 31 | 15 | 15 | 5 | | |
| 25 | | 30 | 14 | 14 | | | |
| 36 | | 8 | | | | | |

4K60 H.264, 50 Mbit:

| Cells | Hardware MPV | + skip | Hardware VLC SP | Hardware VLC | Software MPV | Software VLC SP | Software VLC |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 60 | | 60 | 60 | 54 | 37 | 36 |
| 2 | 59 | | 60 | 60 | 23-26 | 19 | 21 |
| 3 | 53 | | 59 | 60 | | | |
| 4 | 7 | 31 | 37 | 28 | 9 | | |
| 6 | | 31 | 19 | 19 | | | |
| 9 | | 6 | 13 | | | | |

1080p30 H.264, 8 Mbit:

| Cells | Hardware MPV | Hardware VLC SP | Hardware VLC | Software MPV | Software VLC SP | Software VLC |
|---:|---:|---:|---:|---:|---:|---:|
| 16 | 30 | 30 | 30 | 18 | 15 | 14 |
| 25 | 25 | 20 | 20 | 4 | 5 | 7 |
| 36 | 7 | 1, 35 of 36 loaded | 2, 24 of 36 loaded | | | |

HEVC 1080p60, which this GPU can't decode, so every driver is on the CPU. At 4 cells all are about
55-59 fps. At 9, Hardware MPV 12, Hardware VLC SP 28, Software VLC SP 14, Software VLC 18.

### What the hardware can do, with no player at all

ffmpeg decoding flat out, on `test_gpu`, all streams added up. Running in parallel doesn't add to it:

| | Frames a second | In cells at 60 fps |
|---|---:|---:|
| VAAPI, 1080p | 850 | 14 |
| VAAPI, 4K | 220 | 3.7 |
| CPU, 8 threads, 1080p | 787 | 13 |
| CPU, 8 threads, 4K | 196 | 3.3 |

So the cliff at 13-14 cells is the decoder running out. The players land just below it, with MPV a bit
earlier as drawing and reading back also take GPU time.

### Windows: RTX 3060, offscreen

1080p60:

| Cells | Hardware MPV | decoder busy | + skip | Software MPV | CPU | Software VLC SP | CPU |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 9 | 60 | 71% | | 60 | 377% | 59 | 685% |
| 12 | 60 | 95% | | | | | |
| 14 | 15 | 99% | | | | | |
| 16 | 16 | 99% | 31 | 59 | 565% | 59 | 1316% |
| 25 | | | 17 | 56 | 819% | 39, worst cell 18 | 1442% |
| 36 | | | | 34 | 1152% | 24 | 1444% |
| 49 | | | | 6, with skip 27 | 1451% | 16 | 1452% |

4K60:

| Cells | Hardware MPV | decoder busy | + skip | Software MPV | CPU | Software VLC SP | CPU |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 60 | 64% | | 60 | 155% | 60 | 195% |
| 3 | 60 | 86% | | | | | |
| 4 | 17 | 100% | 31 | 59 | 441% | 47 | 945% |
| 9 | | | 14 | 58 | 1102% | 20 | 1446% |
| 16 | | | | 7, with skip 30 | 1465% | | |

**On this machine software decoding plays far more than the GPU can.** 9x4K60 at full speed on the CPU,
against 3 on NVDEC. It costs CPU, of course, but it saves VRAM: 97 MB a cell against 233 at 1080p, 107
against 560 at 4K.

`d3d11va-copy` is no way out: the same decoder limit, and three times the CPU.

### Windows: RTX 3060, real window

The real app in a real window on a virtual desktop nobody was looking at. The compositor doesn't draw a window there, so reaching the
screen is still left out. Single runs of 20 s. These were cut short, so not every combination ran: the rest are in plan item 10.16.

| 1080p60 cells | Hardware MPV | + skip | Hardware VLC SP | Hardware VLC |
|---:|---:|---:|---:|---:|
| 1 | 59.7 | | 59.9 | 59.9 |
| 4 | 59.9 | | 59.7 | 60.3 |
| 9 | 59.9 | | 59.6 | 60.2 |
| 16 | 15.8 | 31.1 | 21.4 | 25.4 |
| 25 | | 17.2 | | 16.8 |

| 4K60 cells | Hardware MPV | + skip | Hardware VLC SP | Hardware VLC |
|---:|---:|---:|---:|---:|
| 1 | 59.9 | | 60.6 | 59.9 |
| 4 | 17.2 | | 19.8 | 19.9 |
| 6 | | 31.2 | | |
| 9 | | 13.5 | | |

The decoder is the limit here too, at 99-100% wherever the frame rate falls. What it costs:

| 9x1080p60 | Hardware MPV | Hardware VLC SP | Hardware VLC |
|---|---:|---:|---:|
| App CPU | 82% | 61% | 54% |
| VRAM added | 2109 MB | 794 MB | 794 MB |
| App memory, USS | 1338 MB | 977 MB | 1094 MB |
| GUI timer late, p95 | 6.3 ms | 6.7 ms | 7.0 ms |
| Load, GUI's worst stall | 0.9 s, 0.01 s | 0.7 s, 0.36 s | 0.9 s, 0.01 s |

So on this machine the two are level on how much plays and VLC costs less, the VRAM above all. Linux's memory result doesn't carry over.
VLC's freeze wasn't seen: 16 cells past the limit loaded with a worst stall of 0.85 s in single process and 0.04 s in multi-process, and 25 cells
on multi-process in 1.35 s. 36 cells, where it froze on Linux, wasn't reached.

## Past the limit

MPV's default when late is to throw away decoded frames. That saves no decoder work, so the decoder stays
flat out. Drawing then waits behind its queue: at 16x1080p60, 86% of the render thread's time is inside
`render()`. 850 frames a second are decoded and only about 115 shown, so a small overload costs nearly
everything. VLC falls less far.

`vd-lavc-skipframe=nonref` has the decoder skip frames nothing else depends on, which is about half with
x264's defaults. That frees the decoder:

| | As it is | `nonref` | VLC |
|---|---:|---:|---:|
| Linux, 16x1080p60 | 7 | **31**, no drops | 15 |
| Linux, 25x1080p60 | | **30**, 25 drops a second | 14 |
| Linux, 36x1080p60 | | 8, past it again | |
| Linux, 4x4K60 | 7 | **31**, no drops | 28-37 |
| Linux, 6x4K60 | | **31**, no drops | 19 |
| Linux, 9x4K60 | | 6, past it again | 13 |
| Windows, 16x1080p60 | 16 | **31**, decoder 69% | |
| Linux Software MPV, 9x1080p60 | 25 at 603% CPU | **31** at 376% | 22 at 760% |

Other options tried at 16x1080p60: `framedrop=decoder` and `vd-lavc-framedrop` dropped nothing at the decoder on
hardware decoding, `video-sync` modes did nothing, and `framedrop=no` gave 44-47 fps with the video running in slow
motion, at 73-79% speed, which won't do. `vd-lavc-skipframe=bidir` gave 17 fps with no drops, so it's a
second step.

**It can be switched on while playing:** `set vd-lavc-skipframe nonref` on a running video reached the
same 31 fps, on Linux and Windows.

**As it's built:** "Skip frames to play more videos" on the Video Decoder page, off by default, for both
MPV drivers, and it applies with no reload. Measured on `test_gpu` through the setting: 16x1080p60 Hardware 7.2
off and 31.1 on, 9x1080p60 Software 31.1 at 383% CPU. It's all or nothing: 4x1080p60, which plays at 60 without it,
plays at 31.1 with it. Turned on and off again on running videos, frames follow it both ways on both drivers.

**Switching shows, briefly.** On `test_gpu`, switching 12 times through the setting, the longest gap between finished frames:

| | Between switches | After a switch | A video's clock falls behind by |
|---|---:|---:|---:|
| Hardware, 4x1080p60 | 56 ms | 329 ms | 224-400 ms |
| Hardware, 4x1080p60, window resizing | 61 ms | 270 ms | 168-427 ms |
| Software, 4x1080p60 | 76 ms | 464 ms | 262-615 ms |
| Hardware, 16x1080p60, overloaded | 354 ms | 1077 ms | 282-1262 ms |

So a pause of about a third of a second for each video, and it recovers by itself. As a setting you change now and then that's fine; it counts against
switching automatically. Each switch also saved a picture on the GUI thread at that moment, which may add a little. Whether the pictures straight after
a switch are clean wasn't looked at; they're in that run's folder.

**On only as many cells as it takes.** A trial turned it on for more cells each 2-3 s while drops stayed
above 2%:

| 1080p60 cells | As it is | All skipping | As many as it takes | Cells it took |
|---:|---:|---:|---:|---:|
| 9 | 60 | 31 | 57 | 1, falsely, from the startup burst |
| 10 | 54 | | 51, no drops | 3 |
| 12 | 43 | | 48, no drops | 5 |
| 13 | 27 | | 40 | 9 |
| 14 | 10 | | 43 | 8 |
| 16 | 7 | 31 | 35 | 14 |
| 25 | | 30 | 27 | 25, still settling |

It works, with things still to solve:

- It takes up to 30 s to settle, and needs to ignore the first seconds.
- Each cell it switches pauses for about a third of a second, see above.
- Some cells play at 60 and others at 31, which you may or may not want.
- `frame-drop-count` went backwards after the switch, so mpv seems to restart something in the decoder. A
  visible hitch at that moment wasn't checked.
- **No B frames, nothing to skip.** With a clip encoded without them it makes no difference: 25 cells stay at
  8 fps against VLC's 16. That clip does cost less to decode: 16 cells gave 47.8 without skipping and 46.4 with it. Cameras and low-latency
  streams are often like this. Only `nonkey` is left there, which wasn't measured and would be nearly a slideshow.

## The GIL

### Measured directly

`py-spy --gil`, share of samples with a thread holding the GIL. It can count moments around ctypes calls, so
take these as upper limits:

| | Held | Mostly |
|---|---:|---|
| Hardware VLC SP, 25x360p60 | 1% | nothing, VLC never calls Python per frame |
| Hardware MPV, 9x1080p60 | 26% | painting |
| Hardware MPV, 1x1080p60 | 29% | painting, one big picture |
| Hardware MPV, 16x360p60 | 28% | painting, render thread |
| Hardware MPV, 64x360p60 | 43% | event threads, render thread, painting |
| Software VLC SP, 25x360p60 | 65% | painting, copying frames |
| Software VLC SP, 4x1080p60 | 76% | `FrameReader.read` 32%, painting 28% |

Painting counts because PyQt keeps the GIL through `QPainter.drawImage`. It can't be released from Python.

How late a sleeping Python thread wakes up, p95, next to the same sleep in C on a thread with no GIL. The gap is
about what the GIL adds:

| | Python | C |
|---|---:|---:|
| Hardware VLC SP, 9x1080p60 | 0.12 ms | 0.12 ms |
| Hardware MPV, 9x1080p60 | 2.1 ms | 0.09 ms |
| Hardware MPV, 64x360p60 | 0.45 ms | 0.08 ms |
| Software VLC SP, 9x1080p30 | 7.9 ms | 3.2 ms |
| Software VLC SP, 16x1080p30 | 19 ms | 3.5 ms |
| Software VLC, multi-process, 16x1080p30 | 28 ms | 3.3 ms |

Two things to see: MPV's GIL delay comes down to one paint at a time, and processes don't help Software VLC,
since the GUI process still copies and paints every frame.

### Does it limit how much plays?

Many small videos, 360p60, where decoding is easy and the player is what runs out. The real app stops well short of the
control, which looks like the GIL at first. Mostly it isn't: the control has no window. Here it is with a full-screen window
beside it in another process, which repaints a ready-made picture at 60 Hz, with no video and no Python in the control:

| | Control alone | Control with a window | Real app | Real app, painting nothing |
|---|---:|---:|---:|---:|
| 12x1080p60 | 60 | **43** | 43 | 48 |
| 36x360p60 | 60 | 60 | 46 | 56 |
| 64x360p60 | 57 | **41** | 31 | 37 |

- **12x1080p60:** being on screen is all of it. The compositor and Xwayland need the same GPU. VLC holds 60 here, as it reads
  nothing back.
- **64x360p60:** being on screen takes it from 57 to 41. Of the rest, the prototype with the GUI in another process, so no GIL shared with
  it, gets 34 against 28. That's the most the GIL was seen to cost, about 20%.
- **36x360p60:** the same split gets 52 against 48-50. Going from 60 to about 50 wasn't pinned down. More processes don't get it back, 51 at 4
  workers, so it isn't a lock inside a process.

Wayland instead of X11 is no different: 44 and 33.

And nothing done to Python moves it, at 36 and 64 cells:

| Change | fps at 36 | fps at 64 | App CPU at 36 |
|---|---:|---:|---:|
| As it is | 46 | 31 | 140% |
| Switch interval 0.2 ms, 1 ms or 20 ms | 46 | 30-31 | 139-145% |
| `time-pos` read 5 times a second, not every frame | 47 | 32 | 134% |
| Cached render parameters | 48 | 33 | 139% |
| Update callback with no Python, libc's `sem_post` | 45 | 30 | 124% |
| All three | 47 | 33 | **113%** |

So those save up to about 20% CPU, and play no more.

### Render threads and processes

The prototype, with the real renderer and player, in a plain window. 1 process is what the driver does now. "1 worker" has the
render thread away from the GUI:

| | 1 process | 1 worker | 2 workers | 4 workers | 2 threads | 4 threads |
|---|---:|---:|---:|---:|---:|---:|
| Hardware, 16x360p60 | 60 | 60 | 60 | 60 | | |
| Hardware, 36x360p60 | 48-50 | 52 | 51 | 51 | 47 | 49 |
| Hardware, 64x360p60 | 28 | 34 | 32 | 31 | 27 | |
| Hardware, 100x360p60 | 20 | 21 | 19 | 20 | | |
| Hardware, 12x1080p60 | 44-46 | 48 | | 53 | 46 | 47 |
| Hardware, 16x1080p60 | 7 | 7 | | 9 | | |
| Hardware, 4x4K60 | 7 | | 8 | | | |
| Software, 9x1080p60 | 25-27 | 26 | | 31 | 29 | 24 |
| Software, 16x1080p60 | 5 | 5 | | 10 | | |
| Software, 36x360p60 | 39 | | | 48 | 44 | |
| Software, 64x360p60 | 20 | | | 26 | | |

CPU at 4 workers against 1 process: 16x360p60 113% against 93%, 36x360p60 163% against 127%, Software 36x360p60
533% against 320%.

The C control says the same with no Python involved: at 16x1080p60, 2 render threads get 8 fps, 2 processes 8, 4 processes 9.

The gains are small and only where it's overloaded anyway, and skipping frames beats them at less cost: Software 9x1080p60 goes
to 31 fps on 376% CPU with skipping, against 31 fps on 751% with 4 workers. A real multi-process driver would also need all of
this per platform, and the commands, errors and settings carried across, as VLC's has.

## What each costs

Linux, the whole app and the system's change in available memory. On this GPU video memory is system memory, so this includes it.

| | Hardware MPV | Hardware VLC SP | Hardware VLC | Software MPV | Software VLC SP | Software VLC |
|---|---:|---:|---:|---:|---:|---:|
| **9x1080p60**, fps | 60 | 60 | 60 | 25-28 | 22 | 22 |
| App CPU | 90% | 58% | 55% | 590% | 762% | 777% |
| Memory | 687 MB | 1907 MB | 2091 MB | 888 MB | 1702 MB | 1802 MB |
| GUI timer late, p95 | 3.3 ms | 0.3 ms | 0.3 ms | 6.7 ms | 256 ms | 265 ms |
| **16x1080p30**, fps | 30 | 30 | 30 | 18 | 15 | 14 |
| App CPU | 65% | 48% | 53% | 635% | 774% | 781% |
| Memory | 1096 MB | 3252 MB | 3513 MB | 1402 MB | 2972 MB | 3064 MB |
| GUI timer late, p95 | 1.5 ms | 0.4 ms | 0.4 ms | 6.7 ms | 705 ms | 639 ms |
| **4x4K30**, fps | 30 | 30 | 30 | 22 | 12 | 12 |
| App CPU | 58% | 23% | 26% | 537% | 750% | 769% |
| Memory | 787 MB | 2959 MB | 2990 MB | 1141 MB | 2890 MB | 2644 MB |

Where it goes on Hardware MPV at 9x1080p60, percent of a core: GUI thread 27, render thread 27, mpv's `core` threads 19, `vo` 7, event
threads 6, demuxer 4. A single 1080p cell: 29 on the GUI thread, 18 rendering.

Windows, per 1080p cell: Hardware MPV 233 MB VRAM and 140 MB RAM, Software MPV 97 MB VRAM and 150 MB RAM.

**What Software MPV uses.** It decodes on the CPU, and still draws on the GPU through OpenGL: uploads each frame, converts its colours,
scales it, and reads it back. Unlike Software VLC, it needs a working GPU driver or a software OpenGL. Windows, RTX 3060, offscreen,
4x1080p60, one run each:

| | Hardware MPV | Software MPV | Software VLC SP |
|---|---:|---:|---:|
| Fps | 59.9 | 60.0 | 59.8 |
| `hwdec-current` | `nvdec` | `no` | |
| GPU decoder busy | 73% | 0% | 0% |
| GPU busy | 14% | 28% | 0.4% |
| VRAM added | 941 MB | 396 MB | 0 MB |
| App CPU, 100% is one core | 40% | 185% | 276% |

At 64 cells of 360p on NVDEC, some cells fell back to `d3d11va-copy` on their own, with VRAM at only about 5 GB of 12. That's probably
NVDEC running out of something, the cause wasn't looked into.

**Opening many videos:** level until the GPU is overloaded, then VLC freezes the whole window. 64x360p60 takes MPV 3 s against 12-13 s.
Hardware, 1080p30, last cell loaded, on `test_gpu`:

| Cells | Hardware MPV | Hardware VLC SP |
|---:|---:|---:|
| 4 | 0.6 s | 0.3 s |
| 16 | 0.8 s | 1.0 s |
| 25 | 1.3 s | 9.5 s |
| 36 | 1.7 s | 107 s, with the GUI frozen for 87 s |
| 36, starting paused | 1.6 s | 7.2 s, frozen for 5.8 s |
| 36x360p60 | | 4.7 s, frozen for 3.4 s |

In the bench's runs, multi-process VLC had 24 of 36 at its 60 s cutoff, and 25x4K30 had 24 of 25 by 131 s, with 22 GB in use. Those were
cut off, so they aren't load times.

While frozen, the GUI thread is in `xcb_wait_for_reply`, in `QXcbCursor::queryPointer` or `QXcbWindow::frameMargins`, in both VLC modes, and
Xwayland is in an ioctl into the Intel driver, sleeping at `i915_gem_ww_ctx_backoff` at about 3% CPU. So the app is waiting on the X server and the
X server on the GPU driver. Why VLC gets there and MPV doesn't wasn't proven. MPV's decoding is just as overloaded at 36 cells, 7 fps. The likely
difference is that VLC draws through the X server, one window a video, and MPV doesn't. Seen only on this machine, Xwayland under headless sway on
Intel; a real X server, other GPUs and Windows weren't checked.

**Failures:** every failed run was VLC. 100x360p60 on Hardware VLC SP segfaulted. These never finished within 200 s: both Software VLC modes at
64x360p60 on Linux, Hardware VLC SP at 25x4K30, and Software VLC at 49x1080p60 on Windows. No MPV run failed.

## Readback against GL

Measured 2026-11-08. The app reads each frame back from the GPU and paints it like any other widget. The POC also had GL: one
`QOpenGLWidget` a cell, drawing the frame's texture, with nothing read back. It found readback cheaper and rejected GL, as it shakes
while the window is being resized. That was measured with 6 and 16 small cells of 24 fps HEVC, with the GPU already 28% busy with
something else. Here is the same POC, `grid4.py` in its two modes, in a 1920x1080 window, two runs each, the means. CPU is the whole
app's, 100% is one core.

| | Fps, both | CPU, GL | CPU, readback |
|---|---:|---:|---:|
| **Linux, `test_gpu`, real screen through sway** | | | |
| 1x1080p60 | 60 | 14% | 48% |
| 4x1080p60 | 60 | 29% | 55% |
| 9x1080p60 | 60 | 43% | 77% |
| 1x4K60 | 60 | 16% | 55% |
| 4x4K60, past the decoder's limit | 7 | 29% | 35% |
| **Windows, RTX 3060, window on another virtual desktop** | | | |
| 1x1080p60 | 60 | 28% | 57% |
| 4x1080p60 | 60 | 46% | 71% |
| 9x1080p60 | 60 | 70% | 90% |
| 16x1080p60, past the decoder's limit | 15 | 56% | 54% |
| 1x4K60 | 60 | 21% | 44% |
| 4, 9, 16x4K60, past the decoder's limit | 15, 11, 9 | 26, 26, 40% | 23, 28, 34% |

- **Frame rates are the same everywhere.** Readback never decides how much plays.
- **Readback costs 20-35 points of a core while the decoder keeps up,** more the bigger the cells. Past the decoder's limit the two are level,
  and at 16 small cells readback is a little cheaper, which is where the POC measured.
- **The GPU:** on Linux, readback keeps it at full clock, 1200 against 400 MHz for one 1080p cell. On Windows GL keeps it a little busier
  from 4 cells, 25% against 18%, and a little less at 1 cell.
- **Not counted, both against readback:** on Linux each frame then goes through the X server, whose CPU isn't the app's. On Windows the
  window is cloaked, so the compositor does nothing for either mode.
- The POC's readback still filled each cell black before painting, which plan item 10.14 took out of the app: worth a few points at 1 cell
  on Linux, nothing on Windows.

**On a real screen, Windows** (measured later the same day, 1100x760 window on the main desktop, 1080p60 clips, app
CPU over 10 s, two or three runs each; the window on another desktop is cloaked, so Windows never puts it on screen):

| | GL, NVIDIA | Readback, NVIDIA | GL, AMD | Readback, AMD |
|---|---:|---:|---:|---:|
| 4 cells | 43-52% | 62-65% | 55% | 55-64% |
| 9 cells | 95-106% | 85-88% | 90-95% | 79-81% |

Here the monitor is on the AMD GPU, so NVIDIA's frames cross to it. GL composes and swaps the whole window for any cell's
new frame, 120 times a second here, where readback repaints only the cell. With few cells GL is still cheaper; at 9 it
costs more on both GPUs, and on AMD manages about 46 swaps a second. Linux, through sway, kept its saving at 9 cells.

So the choice was right for the shaking, and wrong about the cost: GL is cheaper at the sizes most grids have. Whether the shaking can be
dealt with any other way wasn't looked at again. Each run had 8 s to settle and 15 s measured, with the modes taking turns to go first.

**One GL surface for the window** (plan item 13.5, measured later the same day on Windows, RTX 3060, window on another desktop,
1920x1061, 360p60 clips so the decoder keeps up, 15 s; GUI thread CPU, fps, frames dropped a second):

| | Readback | GL, a surface a cell | GL, one surface |
|---|---:|---:|---:|
| 4 cells | 17% · 60 · 1 | 7% · 60 · 1 | 7% · 60 · 1 |
| 16 cells | 15% · 60 · 3 | 27% · 60 · 3 | 6% · 60 · 5 |
| 36 cells | 22% · 49 · 378 | 51% · 43 · 612 | 15% · 60 · 11 |

A surface a cell cost Qt a context switch, a framebuffer and a composed texture for each cell, each frame, on the GUI thread: at
36 cells it played the fewest frames of all. With one, a paint of all 36 takes 0.9 ms. The window also gets 66 sizes a second to
the screen during a resize at 16 cells, against 38. Not measured again on the real screen, where a surface a cell cost more than
readback at 9 cells.

These, and every number from a window on another desktop before 2026-11-09, were taken with Windows throttling the app as
unseen after its first few seconds: every timer 15.6 ms apart, 64 frames a second at most. Enough for 60 fps clips. The bench
opts out of it now, see plan item 13.10, which also has 120 fps numbers and two fixes found that way.

## Fully software MPV

Measured 2026-11-10, plan item 10.17. Software MPV now draws with libmpv's software renderer, scaling with swscale's fast
bilinear, and has no GL at all. The old Software MPV, CPU decoding drawn by OpenGL and read back, is now Hardware MPV with
"Decode on the CPU" On. The bench clips, `run.py`, 8 s to settle and 20 s measured, one run each. Windows offscreen, so the
compositor's share isn't in it; `test_gpu` on its X11 through sway. CPU is the app's, 100% is one core; GPU is how busy it is
(on `test_gpu` RC6's figure, which reads high).

| | Old: fps · CPU · memory · GPU | Fully software: fps · CPU · memory · GPU |
|---|---:|---:|
| **Windows, RTX 3060** | | |
| 1x1080p30 | 30 · 33% · 258 MB · 11% | 30 · 22% · 140 MB · 3% |
| 16x1080p30 | 30 · 388% · 2402 MB · 36% | 30 · 255% · 1118 MB · 1% |
| 16x1080p60 | 59.1 · 616% · 2425 MB · 24% | 59.9 · 470% · 1141 MB · 4% |
| 36 small (16 fps, 720x960) | 16 · 255% · 3878 MB · 32% | 16 · 147% · 1068 MB · 4% |
| 16 mixed | 36.7 · 371% · 2477 MB · 29% | 36.7 · 293% · 1189 MB · 1% |
| 1x2160p60 | 59.9 · 167% · 420 MB · 34% | 59.9 · 88% · 299 MB · 2% |
| 4x2160p60 | 59.6 · 398% · 1333 MB · 21% | 59.7 · 353% · 972 MB · 3% |
| **Linux, `test_gpu`, 4 cores** | | |
| 1x1080p30 | 30 · 90% · 280 MB · 80% | 30 · 105% · 244 MB · 22% |
| 9x1080p30 | 30 · 326% · 827 MB · 95% | 30 · 288% · 784 MB · 30% |
| 16x1080p30 | 20.4 · 580% · 1354 MB · 93% | 29.9 · 559% · 1262 MB · 28% |
| 9x1080p60 | 28.9 · 590% · 861 MB · 93% | 48.8 · 579% · 796 MB · 32% |
| 36 small | 16 · 244% · 1398 MB · 95% | 16 · 228% · 1333 MB · 20% |
| 16 mixed | 12.8 · 704% · 1488 MB · 86% | 24.9 · 679% · 1415 MB · 18% |
| 4x2160p60 | 10.0 · 763% · 1212 MB · 86% | 14.8 · 766% · 1117 MB · 14% |

- **On Windows it's cheaper everywhere,** a fifth to a half less CPU, with half the memory or less: the old mode's direct
  rendering buffers and textures are gone. NVIDIA's driver is what kept the old mode's memory, plan item 10.22.
- **On `test_gpu` it plays more past the limit,** up to twice the frames, for the same CPU. The old mode's GPU was full there.
- **The scaler decides the cost.** At zimg's defaults (lanczos, dithered), one 1080p30 video took 190% on `test_gpu`, zimg's
  workers 85% of it; swscale's bilinear held the render thread at 100% from 9x1080p30, all videos' scaling being on that one
  thread. Fast bilinear looks as the old mode's GL bilinear does.
- What it leaves out: HDR tone mapping, as Software VLC does.

## Picture quality

Measured 2026-11-14, plan item 10.34. What Hardware MPV's scaling costs: Fast is mpv's `fast` profile (bilinear,
no dither, nothing in linear light), what every video had until then; High is mpv's own defaults (`lanczos` up,
`hermite` down in linear light, dithered); "mid" is Fast with `catmull_rom` up; "mid+c" that with the colour
scaled bilinear (`cscale`, which otherwise follows `scale`). Copy output, a real 1920x1080 window on the other
virtual desktop (`AWAY=1`), one run each, `quality=` of the bench. NVIDIA is the RTX 3060 (nvdec), AMD the iGPU
(d3d11va-copy) through the scratchpad python copy. fps, and on NVIDIA how busy its GPU is.

| | Fast | mid | mid+c | High |
|---|---:|---:|---:|---:|
| **NVIDIA** | | | | |
| 1x1080p60, one cell over the window (2 MP) | 60 · 32% | 60 · 29% | 60 · 40% | 60 · 29% |
| 1x360p60, the same\* | 60 · 9% | 60 · 11% | 60 · 9% | 60 · 11% |
| 1x2160p60, the same | 60 · 17% | 60 · 17% | 60 · 14% | 60 · 20% |
| 4x1080p60 (0.5 MP a cell) | 60 · 16% | 60 · 24% | 60 · 19% | 60 · 28% |
| 4x2160p60 | 18 · 5% | 18 · 9% | 18 · 7% | 18 · 13% |
| **AMD iGPU** | | | | |
| 1x1080p60, one cell over the window | 60 | 60 | 60 | 60 |
| 1x360p60, the same\* | 60 | 60 | 60 | 60 |
| 1x2160p60, the same | 60 | 60 | 60 | **54** |
| 4x1080p60 | 60 | 60 | 60 | **49** |
| 4x2160p60 | 28 | **10** | **19** | **7** |

\* Rendered at 640x360 at every level, as Copy then did for a small picture (see below), so mpv's scaler had
nothing to make bigger: not what High costs now. The Auto run below is.

Offscreen first, where Qt holds the window to 764x572, the iGPU at 16x1080p60 (0.03 MP a cell): Fast 21.7 fps,
mid 11.2, High 6.9. NVIDIA was at its decoder's limit there whatever the level.

- **NVIDIA never lost a frame to it**: its decoder runs out first. Its GPU figures jump about from run to run.
- **The iGPU pays for anything past Fast where it shrinks pictures a lot**, many cells or 4K: a sixth of the frames at
  4 cells of 1080p, three quarters at 4 of 4K. `catmull_rom` alone cost as much there, so a middle level would save
  nothing.
- **One big video is free either way**, but 4K shrunk into the window cost the iGPU a tenth.
- So Auto: High for a picture shown at 1 MP or more, about a 720p screen's worth (one video over a 1080p window is
  2 MP, one of four 0.5), unless it's shrunk from over 2.5 times the pixels; Fast for the rest. Both go by the part
  of the picture on show, so a zoomed-in 4K video is made bigger, not smaller. Once High, it holds to 0.8 MP and 3.1
  times, so a window dragged to and fro over a line doesn't switch it, and mpv build its shaders, each time.
- **Copy renders a small picture at its own size**, which the GL surface makes bigger, bilinear: mpv's scaler never
  made it bigger. With High it renders at the size shown, as with subtitles on. For one 360p60 video over the window,
  on Auto: NVIDIA's CPU 37% to 88% (2 MP read back a frame against 0.2), the iGPU's 28% to 33%, both at 60 fps.
  Shared and Direct read nothing back.

## Overnight, 2026-11-09

Plan item 10.16, at commit 2c53c16: about 3 hours on `test_gpu` and 2 on Windows, the Windows part in a real window on another
desktop, no longer throttled (see plan item 13.10). The Windows screen is now at 120 Hz on the AMD iGPU, with decoding on the RTX 3060.

### Crashes and hangs

- **MPV crashed on Linux, closing a video as it loaded.** Both churns, about 2 minutes in, exit 139 with glibc's heap checks on: at file-loaded
  the event thread read the tracks while `terminate()` freed the handle. The Stage 7 notes in the plan saw this window and left it. Fixed: the event
  thread's reads now take the same lock as what's sent to mpv, and look at the closing flag inside it. Run again with
  the fix: both 20-minute churns pass, 2915 and 2819 videos opened, with everything closed at 2140 and 2383 MB from 80, see Memory.
- **Windows passes:** both 20-minute churns (3278 and 3371 videos opened, 455 broken files, about 1400 reloads, 6000 seeks), and 10 minutes on
  Linux under an address sanitizer, which doesn't show the crash.
- **Hardware VLC SP hung on Linux:** the GUI thread waited 42 s at load, in `_set_time_initial`, for VLC to say it had buffered after the
  start seek, and the churn's 45 s check killed it. That's VLC's driver, not changed.
- **Hardware VLC SP on Windows** didn't load 14x1080p60 in time in 2 rounds of 3.
- **Soaks:** no stall and no error. Windows Hardware MPV 30 minutes; Linux Hardware MPV 60, Software MPV and Hardware VLC SP 30.

### Memory

| | Grows |
|---|---:|
| Linux, Hardware MPV, 9 videos playing | **790 MB an hour**, in a straight line |
| Linux, Software MPV, 4 playing | 244 MB an hour |
| Linux, Hardware VLC SP, 9 playing | 48 MB an hour |
| Windows, Hardware MPV, 9 playing | 48 MB an hour |
| Windows churn, everything closed, Hardware MPV | 60 to 763 MB in 20 minutes |
| Windows churn, everything closed, Software MPV | **60 to 1838 MB** in 20 minutes |

**Linux: Mesa, on this GPU.** About 600 bytes a frame shown. Python's objects stay flat and glibc's heap grows. The C control,
`native_bench`, with no Python and none of the app, grows as fast: 8 MB a minute at 9x1080p30. `vaapi-copy` too, and less clearly software
decoding, which levels off. ffmpeg decoding with VAAPI on its own doesn't grow. `heaptrack` puts what grows in Mesa's `libgallium-25.0.7`,
the Haswell driver, and most of the growth isn't through malloc at all. So it's met through mpv's OpenGL, and not the app's to fix. A newer
Mesa and another GPU on Linux (10.4) would tell more.

Mesa 26.1.6, tried 2026-11-11 (plan 10.21): the same, 1387 MB an hour against 25.0.7's 1322 in 20-minute soaks of 9. Software MPV, fully
software since 10.17 and so with no OpenGL, now grows 26 MB an hour at 4, where it grew 244 drawing with OpenGL.

**Windows: Software MPV's direct rendering.** About 1.5 MB is kept per video closed. With `vd-lavc-dr=no` the same 6-minute churn stays at
340-400 MB, and falls back. Python holds none of it: one closed video stays alive, the same one, not more. Bare libmpv opening and closing players
with no rendering levels off at about 300 MB. So it's the decoder's buffers in GL that aren't given back. Hardware MPV keeps about 230 KB a video,
not looked into. Turning direct rendering off cost frames on Linux, 19 against 25 at 9x1080p60 in software (see below); on Windows it wasn't measured.

### How many play, three runs each

1080p60, frames per cell per second, the three runs:

| Cells | Linux MPV | VLC SP | VLC | Windows MPV | VLC SP | VLC |
|---:|---:|---:|---:|---:|---:|---:|
| 9 | 58-60 | 60 | 60 | 60 | 29 | 30 |
| 10 | 56-57 | 60 | 60 | | | |
| 12 | 44-48 | 60 | 60 | 60 | 28-29 | 29 |
| 13 | 27-29 | 39-42 | 36-41 | | | |
| 14 | 10-11 | 17-19 | 17-18 | 16-17 | 18, 2 not loaded | 19-20 |
| 16 | | | | 17 | 18-19 | 18-19 |
| 16, MPV skipping | 31.1 | | | 31.1 | | |
| 20, MPV skipping | | | | 31.1 | | |

Linux agrees with the first runs within 10%: MPV holds 9, VLC 12. Skipping gives 31.1 in every run, on both.

**VLC at 29 on Windows from 9 cells** is new: it held 60 on 2026-11-06. The commit measured then gives 29 too, and so does the bench without
opting out of throttling, so it's the machine as set up now, not the code. Its decoder is 91% busy there against MPV's 73%. Not looked into.

Windows, real window, also run:

| | MPV | VLC SP | VLC |
|---|---:|---:|---:|
| 16x360p60 | 60 | 60 | 60 |
| 36x360p60 | 53 | 32 | 33 |
| 64x360p60 | 29, worst cell 24, some on `d3d11va-copy` | 21 | 18 |
| 36x1080p30, decoder 99% | 13, clock at 70% speed | 13, worst cell 7 | 12 |

| Software, 1080p60 | MPV | CPU | VLC SP | CPU |
|---|---:|---:|---:|---:|
| 9 | 60 | 324% | 60 | 665% |
| 16 | 59 | 556% | 60 | 1318% |
| 25 | 52 | 824% | 42, worst cell 14, 5.9 s stall | 1480% |

### VLC's freeze at 36 cells

On Linux both rounds froze again: 36x1080p30 on Hardware VLC SP loaded its last cell at 94 and 81 s with the GUI stuck 81 and 78 s; multi-process
137 and 96 s, stuck 98 and 60 s. MPV loaded in 1.8-1.9 s. **Windows doesn't freeze:** every driver loaded 36 in 1.7-4.1 s, the worst stall
2.8 s on VLC SP. So it's the X server path, as thought.

### A real grid

The `mix` clips: 16 different files, H.264 at 24, 30 and 60 fps, phone clips, no B frames, 10-bit HEVC, HEVC 1080p60, 4K30, 540p60, in MP4
and MKV. Mean of the cells; every clip at its own rate is 39 for 9 cells and 37 for 16.

| | Windows 9 | Windows 16 | Linux 9 | Linux 16 |
|---|---:|---:|---:|---:|
| Hardware MPV | 39.3 | 36.7 | 39.3 | **30.3** |
| Hardware VLC SP | 39.3 | 36.6 | 39.1 | 36.5 |
| Hardware VLC | 39.5 | 36.7 | 39.3 | 36.4 |
| Software MPV | 39.3 | 36.7 | 26.6 | 10.3 |
| Software VLC SP | 39.4 | 36.7 | 25.6 | 15.4 |
| Hardware MPV, skipping | 24.3 | 22.1 | 24.2 | 22.1 |

On Windows everything plays it all. On Linux 16 mixed cells are past MPV's limit and not VLC's, as with one clip; this GPU decodes no HEVC,
which goes to the CPU. Skipping halves a grid that was keeping up, as known.

### Switching frame skipping, Windows

| | Between switches | After a switch | Clock behind by |
|---|---:|---:|---:|
| 4x1080p60 | 60 ms | 235-602 ms | 293-817 ms |
| 16x1080p60, overloaded | 275 ms | 879-2157 ms | 538-1407 ms |

Longer than on Linux (329 ms and 1077 ms). Overloaded, frames fall to 4-8 a second for a moment after turning it off.

## What's worth doing

In order of what it gets for the work:

1. **Skip frames when the decoder can't keep up.** Doubles or quadruples what plays past the limit, on both machines, on both MPV
   drivers. Built as a setting, see plan item 10.13. Automatic was left out.
2. **Say which is better when it's full.** On a good CPU software decoding plays much further than the GPU, 25x1080p60 and 9x4K60 at nearly
   full speed on the Ryzen. Worth a line in the README, and perhaps a step in the automatic route. New cells going to software
   past the decoder's limit wasn't tried.
3. **Don't fill the cell before drawing over it.** `paintEvent` fills the whole cell black, then draws the picture over it. Skipping the fill when
   the picture covers the cell: at 1x1080p, app CPU 61% to 47% and GUI timer p95 3.8 to 2.1 ms. No change at 9 cells. It also applies
   to VLC's software drivers. One run each. Done, filling only beside the picture: see plan item 10.14.
4. **`time-pos` less often, cached render parameters.** Small and simple, with about 5% less CPU. Stage 4.2 already has the first. `sem_post` saves
   more, but it changes how the render thread wakes, for CPU alone. Cached render parameters done, about 1% of it: see
   plan item 10.15.
5. **Software VLC's `FrameReader.read`,** 32% of the GIL at 4x1080p60. It copies each frame with the GIL held, on the GUI thread. A copy through
   `ctypes.memmove` lets go of it. Not tried, and not MPV's: it would be a change to VLC's drivers.

Plan item 10.16 ran overnight 2026-11-09, see [Overnight](#overnight-2026-11-09).

Tried and not worth it:

| | Result |
|---|---|
| Multi-process MPV | See above |
| More render threads | No gain on hardware. Software: +13% at 2, worse at 4 |
| PBO readback, batched, in C | Hardware: no change. Software 9x1080p60: 37 against 29 fps for 21% more CPU |
| `sys.setswitchinterval` | No change |
| Wayland instead of X11 | No change |
| No smooth scaling at 1:1 | No change, not even at 1x1080p |
| `vd-lavc-skiploopfilter=all`, software | +10%, and pictures look worse |
| `vd-lavc-fast` | Worse |
| `vd-lavc-dr=no` | Worse: 19 against 25 fps |
| `vd-lavc-threads` 2 or 8 | No fps change. 4 stays |
| `hwdec-extra-frames`, `vd-queue-enable`, at the limit | No change |

## Also found

**VLC's "single process" warning doesn't hold on these tests.** The README says the SP modes aren't recommended past 4-6 videos, and the
Processes tooltip says it can freeze. Up to 81 cells Hardware SP plays the same as multi-process, and uses less memory: 1907 against 2091 MB.
Software SP plays the same as multi-process and stays as responsive, until the CPU runs out. It does load slower when saturated on Windows,
14.6 s against 0.6 s at 25x1080p60, and it was the one that segfaulted at 100 cells. The warning may come from older VLC or other
kinds of files, so nothing was changed. It's worth a look. Changed 2026-11-09 (`VLC.md`, 10.28): the tooltip and README
no longer warn of it.

**Plan item 10.12, the fork abort, is settled for this machine.** With VLC now on `test_gpu`: started on MPV, live to Hardware VLC, multi-process, on a real
GPU, 2 rounds, all videos play. And this time a pass means something: with the old cause forced, `QT_XCB_GL_INTEGRATION=xcb_glx` or `xcb_egl`, decoder
processes do die with signal 6. So this machine can show the abort, and the app's setup avoids it, even with libmpv and EGL loaded in the parent.
Intel and Mesa only: NVIDIA on Linux isn't known.

**The control did worse than the app at light load:** 50 fps with drops at 9x360p60, where the app holds 60, and Software 44 fps at 4x1080p60 where the app holds 58. The GPU read 200
and 900 MHz in those runs, against 1250 in the app's, so it's probably clocking down with nothing on screen. Not proven. It doesn't touch the findings above, where the control does better than the app or the same.

**`test_gpu` has VLC now.** It was left without on purpose, to prove the app runs with only libmpv. `apt purge vlc* libvlc*` puts that back.

## Against the other project's numbers

[gridplayer-mpv](https://github.com/mjdelro/gridplayer-mpv), `MPV_BACKEND.md`, on an RTX 3080 Ti, with a shared GL context drawing directly into each cell
and a playlist that includes 4K60. It agrees where they can be compared:

| Theirs | Here |
|---|---|
| 16 cells stable, 22 at 100% decoder with EGL allocation failures, "cannot increase the GPU's physical decoder or memory capacity" | The same wall on other GPUs: decoder at 99-100% and frame rates falling off |
| Standalone mpv processes against one process: 16 cells 225% against 75% CPU, 8.4 against 3.7 GB RAM, 11.1 against 9.1 GB VRAM | Processes cost more here too, far less than that, since these workers are bare, not whole players |

They render with no readback, so their CPU isn't comparable with ours, and their notes have no VLC, no frame rates and nothing on the GIL. Their player code doesn't use `skipframe` either.
