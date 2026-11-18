# Review: Brick2892's mpv fork

Looked at 2026-11-11: <https://github.com/Brick2892/gridplayermpv/commits/feat/mpv-prototype/>, branch
`feat/mpv-prototype`. Eight commits on top of master's `bf94368` (2026-11-04), made 2026-11-08 and 09. Read only: none
of its code was run.

What they made: GridPlayer playing everything through mpv on Windows 11 64-bit, with VLC removed. Linux and macOS
weren't built or tried.

## How it works

- **Hardware decoder:** mpv draws into a native child window of the cell (`wid`), with its own output: `vo=gpu` on
  Direct3D 11, `hwdec=auto-safe`. 4 videos per process, in the processes VLC Hardware uses
  (`widgets/video_frame_mpv_hw.py`, `mpv_player/instance.py`). The view (zoom, crop) goes to mpv as `video-crop` and
  `keepaspect`; the overlay is VLC Hardware's, as the surface is native.
- **Software decoder:** libmpv's `sw` render API into shared memory, the frame at the video's own size, scaled by Qt
  (`mpv_player/software.py`, `widgets/video_frame_mpv_sw.py`). Multi-process too.
- libmpv found from `GRIDPLAYER_MPV_DIR`, `.local-tools\mpv` or `libmpv\` beside the exe; put on `PATH` for the
  processes (`utils/libmpv.py`).
- No measurements kept. The quality presets "were picked by measuring grids of 1080p60 video on a Radeon 610M".

## Worth taking

1. **mpv drawing into its own window, a third MPV output on Windows.** Never tried here. On AMD and Intel our OpenGL
   path copies every frame GPU to CPU to GPU (`d3d11va-copy`; mpv hands D3D11 frames to desktop OpenGL only through
   ANGLE): on the AMD iGPU Steady falls to 28 fps at 16 videos of the mix (plan 10.4) while the CPU keeps up. mpv's own
   D3D11 output keeps them on the GPU (`d3d11va` zero-copy). On NVIDIA (`nvdec` already stays on the GPU) the gain is
   likely smaller. Costs: native windows with VLC Hardware's overlay ways (that code exists); X11 only on Linux, not
   Wayland; not macOS (libmpv's `wid` isn't supported there); screenshots and zoom through mpv. **Next: a bench in the
   scratchpad first** (being done, see the plan when it's in).
2. **Timeline drags.** Ours sends a key frame seek on each mouse move (`SeekAim.HAND`, `VideoBlock.seek`). They found
   each new seek makes mpv drop the one before it, so a drag faster than frames arrive shows nothing until it stops.
   Theirs: one seek in flight, then the latest asked for meanwhile (given up after 1 s), keyframes while dragging, an
   exact seek on release (`set_time_keyframe`, `_send_scrub`; a `scrub_changed` signal from the bar). Not checked
   whether ours has the trouble: a real-app test would tell.
3. **Packaging (Stage 12).** libmpv pinned by URL and SHA-256 from shinchiro's `mpv-winbuild-cmake` releases
   (`mpv-dev-x86_64-20261109-git-8bc468896e.7z`), checked before it's kept, `libmpv-2.dll` only, into `libmpv\` beside
   the exe (`scripts/pyinstaller/build_win.sh`: wget, `sha256sum -c`, 7z). Fits our tools. shinchiro also builds i686.
4. **Small features, your call:**
   - **Duplicate** (context menu): the active video again in the next cell, from where it is, muted, with a copy of
     its list and its own bookmarks where they aren't shared (`cmd_duplicate_video`).
   - **Volume above 100%:** "Maximum volume" 100-300%, default 150 (mpv's `volume-max`); the part past 100% amber on
     the bar, a snap at 100, the level as a number beside it. mpv's volume is cubic: 150% is about 3.4 times the
     signal. Would need VLC's side too.
   - **True Dark:** a black scheme beside Light and Dark; the overlay's colours follow the dark themes. Fits the
     grays-only rule.
5. **Scaling by how big a cell is.** We apply mpv's `fast` profile everywhere, soft on a big single video. Their Auto:
   Fast under 0.6 MP shown, Balanced (`catmull_rom` up, bilinear down, no dither) to 1.5 MP, High (mpv's defaults)
   above, and one step down when more than 10% of frames drop over 3 s (not when the video has more frames than the
   screen). All presets name every option so switching leaves nothing behind (`mpv_player/performance.py`).
6. **Maybe:**
   - **Graphics card:** Auto / High performance / Power saving / a card by name, from DXGI's adapter list, as
     `d3d11-adapter` (`utils/gpu_adapters.py`). Only works with mpv's own D3D11 output; for our OpenGL it would be
     Windows' per-app GPU preference for our exe. Laptops with two GPUs only.
   - **mpv Options** free text (`--name=value`), the last word over the settings, a typed `--profile` replacing the
     preset. Can fight the many options we manage.

## Nothing to take

- Multi-process mpv: measured here, no gain (`docs/findings/MPV_PERFORMANCE.md`).
- Their software driver: renders at the video's full size; ours at the cell's.
- Their fixes for live streams' length, default tracks, audio and subtitle files added while playing: ours has them.
- Their crash fix (python-mpv letting go of the update callback while mpv may still call it): ours sets it once.
- Their test harness against real libmpv: our real-app scenarios run on three systems.
- A drag on the timeline starting a cell drag, the overlay hiding mid-drag: ours is guarded (the bar keeps the moves;
  `OVERLAY_ACTIVITY_EVENT`).
- Removing VLC.

Code taken from it, rather than ideas, should credit its author as a co-author.

## Bench: mpv drawing into its own windows (2026-11-11)

A prototype in the scratchpad (`wid/wid_bench.py`): one process, a 1920x1080 window on the other virtual desktop with a
native child window a cell, one mpv each with `wid`, `vo=gpu`, `gpu-api=d3d11`, `hwdec=auto-safe`,
`hwdec-extra-frames=0`, the `fast` profile, muted, looping. Against our Hardware MPV, Steady and Fast, through
`tests/real_app/bench/run.py`, same clips (the mix), same window, same desktop. 8 s to settle, 20 s measured.

Frames a video, mean (the mix's own: 43.5 at 4, 39.3 at 9, 36.7 at 16, 37.7 at 25) · CPU of the process, 100% a core
· memory (USS, MB) · NVIDIA video memory added (MB):

**RTX 3060** (the prototype decodes `d3d11va`, ours `nvdec`):

| | 4 | 9 | 16 | 25 |
|---|---|---|---|---|
| mpv's own window | 43.5 · 19% · 391 · +342 | 39.3 · 38% · 881 · +920 | 36.7 · 55% · 1407 · +1445 | 27.1 · 66% · 3050 · +2340 |
| ours, Steady | 43.5 · 71% · 654 · +852 | 39.3 · 71% · 1353 · +2324 | 36.7 · 96% · 2190 · +3867 | 28.0 · 118% · 3402 · +6187 |
| ours, Fast | 43.5 · 53% · 697 · +963 | 39.3 · 80% · 1396 · +2429 | 36.7 · 115% · 2237 · +3973 | 28.0 · 114% · 3455 · +6284 |

**AMD iGPU** (the prototype `d3d11va`, zero-copy; ours `d3d11va-copy`):

| | 4 | 9 | 16 | 25 |
|---|---|---|---|---|
| mpv's own window | 43.5 · 15% · 409 | 39.3 · 27% · 1171 | 36.7 · 43% · 1949 | 19.4 · 44% · 3228 |
| ours, Steady | 43.5 · 53% · 596 | 39.2 · 100% · 1453 | **29.5** · 116% · 2361 | 18.4 · 116% · 3718 |
| ours, Fast | 43.5 · 47% · 758 | 39.3 · 96% · 1639 | 36.5 · 148% · 2539 | 20.4 · 133% · 3967 |

What it says:

- **CPU: a third to a quarter of ours**, on both GPUs, at every size. No frame read back or copied, nothing painted by
  Qt.
- **Video memory on NVIDIA: less than half** (+2.3 GB against +6.2 at 25), and less memory overall.
- **Frames: the same where the decoder is the limit** (25 videos on either GPU). Better only where ours spends its
  time copying: AMD at 16, 36.7 against Steady's 29.5 (Fast keeps up there, at 3.4 times the CPU).
- The AMD iGPU frames stay on the GPU, as expected.

Not fair to ours yet, and left out:

- The prototype is bare: no app around it, no overlays, no time read 5 times a second, no Python per frame. Part of
  the gap is the app itself, which would come back once it's in the app.
- The window is on the other desktop, where Windows doesn't put it on the screen: what composing 25 swap chains costs
  the compositor is missing, as is ours putting one window together. Only a window on a screen would tell.
- One run each.

What it would take in the app: a third output beside Steady and Fast, a native child window a cell as VLC Hardware has
(that code, its overlay windows included, exists). The view through mpv (`video-zoom`, `video-pan-x/y`, `video-crop`,
`video-rotate`), screenshots by `screenshot-raw`, cells not on show by `vid` off or a hidden window. Windows, and X11 on
Linux (`wid` takes an X11 window); not Wayland, not macOS.

## On the screen (2026-11-11)

The same runs with the window on the screen, 1920x1080 at the top left, never activated (`VISIBLE=1` for the
prototype, the bench's new `ON_SCREEN=1` for ours), so the compositor puts it together. The screen hangs off the AMD
iGPU at 120 Hz: on the RTX 3060 every frame crosses to the iGPU to be shown. Windows' counters, once every 1.7 s, for
`dwm.exe` (100% a core) and the busiest engine of each kind.

Frames a video, mean · CPU of the process · dwm · GPU engines:

**RTX 3060**, shown through the iGPU:

| | 4 | 9 | 16 | 25 |
|---|---|---|---|---|
| mpv's own window | 43.5 · 14% · 8% | 39.3 · 27% · 9% | 36.7 · 54% · 10% | 28.6 · 65% · 10% |
| ours, Steady | 43.4 · 71% · 6% | 39.3 · 84% · 7% | 36.7 · 103% · 8% | 28.2 · 110% · 9% |
| ours, Fast | 43.5 · 77% · 12% | 39.3 · 93% · 12% | 36.7 · 117% · 12% | 28.1 · 137% · 12% |

The iGPU's 3D engine, which composes: 24-28% with mpv's own windows, 26-29% Steady, 36% Fast. NVIDIA's decoder at
100% at 25 in all three: that's the limit there.

**AMD iGPU**, which shows them too:

| | 4 | 9 | 16 | 25 |
|---|---|---|---|---|
| mpv's own window | 43.5 · 11% · 5% · 3D 37% | 39.3 · 21% · 7% · 3D 51% | 36.7 · 35% · 11% · 3D 63% | 21.5 · 40% · 11% · 3D 57% |
| ours, Steady | 43.5 · 71% · 9% · 3D 55% | 39.2 · 81% · 11% · 3D 80% | **29.7** · 116% · 6% · 3D 89% | 18.7 · 114% · 6% · 3D 92% |
| ours, Fast | 43.5 · 34% · 9% · 3D 61% | 39.3 · 71% · 10% · 3D 89% | **34.4** · 144% · 6% · 3D 99% | 19.8 · 143% · 9% · 3D 99% |

The decoder (`videocodec0`) is the same in all three, 46% at 4 to 100% at 25.

What it says:

- **On the screen the gap holds.** 25 swap chains cost the compositor no more than our one window: dwm stays at
  5-12% of a core in every run, and the iGPU composing NVIDIA's frames is no busier for them.
- **CPU: a fifth to a half of ours**, as off the screen.
- **The iGPU's 3D engine is what runs out for ours**: 89-99% at 16 against 63% with mpv's own windows, which is
  why only those keep up there (36.7 against 29.7 and 34.4). At 25 the decoder is full whatever draws.
- Still bare against the whole app: ours at 4 videos takes 34% at the least (Fast on AMD), some of it the app
  around the video, which a third output keeps. The machine's own CPU is left out: something else was running.
- One run each.
