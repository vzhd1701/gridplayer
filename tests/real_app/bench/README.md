# Load bench

Measures how many videos the real app plays and what that costs, for any video driver. It's what
`docs/MPV_PERFORMANCE.md` was measured with. Nothing here runs with `pytest`.

| File | What it is |
|---|---|
| `run.py` | Runs the real app at more and more cells, one process a run, and prints a line for each |
| `grid_bench.py` | The scenario `run.py` runs: frames shown, CPU by thread, memory, GPU, GUI lateness, sleep lateness |
| `sitecustomize.py` | Counts VLC's frames in every process, the forked players too. Off unless `GP_BENCH_DIR` is set |
| `native_bench.c` | Control: the same mpv path and options in C, with no Python |
| `mp_bench.py` | Prototype of a multi-process mpv driver on the real renderer |
| `bare_window.py` | Control: a full-screen window repainted at 60 Hz, with no video |
| `probe.c` | The sleep probe in C, for the gap that is the GIL. Optional |
| `spy_read.py` | What a `py-spy` file says |
| `make_media.sh` | Makes the clips, into `build/bench-media` |
| `churn.py` | Scenario: opens, closes, reloads and seeks as fast as it can, for crashes, hangs and leaks |
| `soak.py` | Scenario: a grid left playing for a long time, sampled once a minute |
| `hitch.py` | Scenario: whether switching frame skipping shows |
| `away.py` | Windows: a real window on another virtual desktop, never activated |
| `overnight.sh` | All the long checks, about 4.5 hours. Run on Windows, it starts `overnight_linux.sh` on `test_gpu` |
| `common.py` | What the scenarios share |

## Running it

Clips come from `BENCH_MEDIA`, `build/bench-media` by default. `ffmpeg` and `wget` make them, once:

```bash
bash tests/real_app/bench/make_media.sh
```

Linux, on a real X11 desktop or a machine with the `session` command, such as `test_gpu`:

```bash
python tests/real_app/bench/run.py h264_1080p60 --drivers mpv_hw,vlc_hw_sp --cells 4,9,16
```

Windows runs offscreen by default, so with no display cost and no VLC Hardware, and needs `psutil`:

```bash
uv run --with psutil python tests/real_app/bench/run.py h264_1080p60 --drivers mpv_hw --cells 4,9
```

To run on a real window instead, on a virtual desktop you aren't on, add
`--env AWAY=1 --env REAL_APP_QT_PLATFORM=windows`. The compositor doesn't draw a window there, so that still
leaves out what reaching the screen costs. Should your desktop change, the run stops.

The other scenarios run like any other, from the repo root, with this folder on the path:

```bash
PYTHONPATH=.:tests/real_app/bench DRIVER=mpv_hw MINUTES=20 python -m tests.real_app.run tests/real_app/bench/churn.py --out build/bench/churn
```

Any clip name below can be a list with commas, `mix` for the mixed clips of `make_media.sh`, or `small` for
its 15 small tall clips at 16 fps (many small videos).

A driver stops going up when it falls below 40% of the clip's frame rate or doesn't load, and each run
leaves `bench.json` under `--out`, `build/bench/out` by default. Build the C parts into `build/bench` on Linux:

```bash
gcc -O2 -shared -fPIC tests/real_app/bench/probe.c -o build/bench/probe.so
gcc -O2 tests/real_app/bench/native_bench.c -o build/bench/native_bench -lmpv -lEGL -lGL -lX11 -lpthread
```

```bash
build/bench/native_bench CLIP CELLS WIDTH HEIGHT SECONDS HWDEC RENDER_THREADS OBSERVE_TIME
PYTHONPATH=. python tests/real_app/bench/mp_bench.py CLIP CELLS PROCS   # 0 in-process, k workers, -k threads
python tests/real_app/bench/bare_window.py SECONDS
```

## Options

Pass them with `--env NAME=VALUE`:

- `SETTLE`, `MEASURE`, `LOAD_TIMEOUT`: seconds, 8, 20 and 60 by default.
- `PLAYERS`: videos per process for VLC's multi-process drivers.
- `SPY=gil`: record with `py-spy`, then read it with `spy_read.py FILE 200 SECONDS`.
- `EXP`: comma-separated changes to try.
  - `skip`: the "Skip frames to play more videos" setting.
  - `cpu`: Hardware MPV's "Decode on the CPU", what Software MPV was before it was fully software.
  - `opt.NAME=VALUE`: any mpv option, such as `opt.vd-lavc-skipframe=bidir`.
  - `liveskip=VALUE`: set `vd-lavc-skipframe` 3 s after loading.
  - `autoskip`: the trial of turning skipping on for more cells while frames drop.
  - `switch=SECONDS`: Python's switch interval.
  - `notime`, `fastrender`, `semwake`: less Python on the render path.
  - `nopaint`, `nofill`, `nosmooth`: less on the paint path.

## Traps

- Measure with the app's event loop, never the driver's `pump`, which sleeps.
- A control with no window flatters itself: the compositor needs the same GPU. Run `bare_window.py` beside it
  before blaming Python.
- mpv's `estimated-vf-fps` goes by the gaps between frames' timestamps. It says 60 at 16 cells while 7 a second
  are shown. `shown_fps` is what counts.
- Stopping a run's shell leaves `run.py` going on to the next run. Stop `python.exe` too, but match on the Python processes alone: a
  shell's own command line can hold the same words, and `pkill -f` or the like then kills that shell.
- Only one thing at a time on a machine: runs clean up with `pkill`, so a second run kills the first.
- On `test_gpu` the GPU "busy" figure comes from RC6, and reads 100% with room to spare.
