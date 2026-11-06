#!/bin/bash
# The long checks, run from Windows in Git Bash at the repo root, about 4.5 hours in all:
#
#   GP_LIBMPV_PATH='C:\path\to\libmpv-2.dll' bash tests/real_app/bench/overnight.sh
#
# Starts overnight_linux.sh on test_gpu, which then goes on by itself, and runs the Windows part here,
# about 3 hours. The machine has to stay awake. Real windows go on the other virtual desktop, and
# changing desktops stops those runs. Results: build/bench/overnight here, /opt/bench_out/overnight there.
: "${GP_LIBMPV_PATH:?Point GP_LIBMPV_PATH at libmpv-2.dll}"
cd "$(dirname "$0")/../../.." || exit 1
export BENCH_MEDIA=${BENCH_MEDIA:-build/bench-media}
O=build/bench/overnight
L=$O/log.txt
rm -rf "$O"
mkdir -p "$O" "$BENCH_MEDIA"

echo "-- test_gpu"
tar czf - --exclude='__pycache__' gridplayer tests pyproject.toml | ssh test_gpu 'cd /tmp/gp && tar xzf -' || exit 1
ssh -n test_gpu 'setsid nohup bash /tmp/gp/tests/real_app/bench/overnight_linux.sh > /tmp/overnight.out 2>&1 < /dev/null &'

# the clips come from test_gpu, which makes them; let it finish if it has to make any
echo "-- clips"
until ssh -n test_gpu 'grep -q "repeats" /opt/bench_out/overnight/log.txt 2>/dev/null'; do sleep 30; done
ssh -n test_gpu 'cd /opt/bench_media && tar cf - h264_1080p30.mp4 h264_1080p60.mp4 h264_2160p60.mp4 h264_360p60.mp4 mix*' | tar xf - -C "$BENCH_MEDIA" --skip-old-files || exit 1

say() { echo "### $(date +%H:%M:%S) $*" | tee -a "$L"; }
python_in_uv() { uv run --with psutil python "$@" </dev/null 2>&1 | grep -v "^warning\|Built\|Building\|Uninstalled\|Installed"; }

away() { # what run.py takes, on a real window
    python_in_uv tests/real_app/bench/run.py "$@" --env AWAY=1 --env REAL_APP_QT_PLATFORM=windows | cut -c1-280 | tee -a "$L"
    if grep -q "desktop changed" "$L"; then
        say "the desktop changed: the Windows part stops here"
        exit 77
    fi
}

scenario() { # name, script, env...
    name=$1; script=$2; shift 2
    out=$O/$name
    mkdir -p "$out"
    say "scenario $name"
    env "$@" PYTHONPATH="$(pwd -W);$(pwd -W)/tests/real_app/bench" uv run --with psutil python -m tests.real_app.run "tests/real_app/bench/$script" --out "$out" </dev/null > "$out/stdout.txt" 2>&1
    echo "$name rc=$?" | tee -a "$L"
    sleep 3
}

ALL=mpv_hw,vlc_hw_sp,vlc_hw

say "real window, what 2026-11-06 didn't get to"
away h264_360p60 --drivers $ALL --cells 16,36,64 --out "$O/p360"
away h264_1080p60 --drivers mpv_sw,vlc_sw_sp --cells 9,16,25 --out "$O/p1080_sw"
RUN_TIMEOUT=260 away h264_1080p30 --drivers $ALL --cells 36 --env LOAD_TIMEOUT=200 --env MEASURE=5 --out "$O/freeze"

say "the limits, three times each"
for round in 1 2 3; do
    for cells in 9 12 14 16; do
        away h264_1080p60 --drivers $ALL --cells $cells --out "$O/rep$round"
    done
    away h264_1080p60 --drivers mpv_hw --cells 16,20 --env EXP=skip --out "$O/rep${round}_skip"
done

say "a grid as it might be"
for cells in 9 16; do
    RUN_TIMEOUT=260 away mix --drivers $ALL,mpv_sw,vlc_sw_sp --cells $cells --env LOAD_TIMEOUT=120 --out "$O/mix"
    RUN_TIMEOUT=260 away mix --drivers mpv_hw --cells $cells --env EXP=skip --env LOAD_TIMEOUT=120 --out "$O/mix_skip"
done

# offscreen, so these stay clear of the desktop whatever happens
scenario hitch_hw_4 hitch.py DRIVER=mpv_hw CELLS=4
scenario hitch_hw_16 hitch.py DRIVER=mpv_hw CELLS=16
scenario churn_hw churn.py DRIVER=mpv_hw MINUTES=20 SEED=1
scenario churn_sw churn.py DRIVER=mpv_sw MINUTES=20 SEED=2
scenario soak_hw soak.py DRIVER=mpv_hw CELLS=9 MINUTES=30

say DONE
