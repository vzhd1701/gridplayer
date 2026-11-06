#!/bin/bash
# The long checks on test_gpu, about 4.5 hours, one at a time so nothing measures another run's load.
# overnight.sh starts this. Results in /opt/bench_out/overnight, and all_done there when it's over.
export XDG_RUNTIME_DIR=/run/user/0 BENCH_MEDIA=/opt/bench_media PYTHONFAULTHANDLER=1
cd "$(dirname "$0")/../../.." || exit 1
PY=/opt/venv/bin/python
R=tests/real_app/bench/run.py
O=/opt/bench_out/overnight
L=$O/log.txt
rm -rf "$O"
mkdir -p "$O"
say() { echo "### $(date +%H:%M:%S) $*" | tee -a "$L"; }
run() { $PY $R "$@" 2>&1 | cut -c1-260 | tee -a "$L"; }

say media
PATH=/opt/venv/bin:$PATH bash tests/real_app/bench/make_media.sh 2>&1 | tail -30 | tee -a "$L"
session xcb swaymsg output HEADLESS-1 mode 1920x1080@60Hz > /dev/null

scenario() { # name, script, env...
  name=$1; script=$2; shift 2
  out=$O/$name
  mkdir -p "$out"
  say "scenario $name"
  env "$@" REAL_APP_QT_PLATFORM=xcb PYTHONPATH=$PWD:$PWD/tests/real_app/bench \
    timeout -k 10 "${LIMIT:-7500}" session xcb $PY -m tests.real_app.run tests/real_app/bench/$script --out "$out" > "$out/stdout.txt" 2>&1
  echo "$name rc=$?" | tee -a "$L"
  pkill -9 -f "tests.real_app.ru[n]" 2>/dev/null
  sleep 3
}

# the limits, three times each
say repeats
for round in 1 2 3; do
  for cells in 9 10 12 13 14; do
    run h264_1080p60 --drivers mpv_hw,vlc_hw_sp,vlc_hw --cells $cells --out "$O/rep$round"
  done
  for cells in 12 14 16; do
    run h264_1080p60 --drivers mpv_hw --cells $cells --env EXP=skip --out "$O/rep${round}_skip"
  done
done

# VLC's freeze at 36 cells, with room to finish
say freeze
for round in 1 2; do
  RUN_TIMEOUT=260 run h264_1080p30 --drivers mpv_hw,vlc_hw_sp,vlc_hw --cells 36 --env LOAD_TIMEOUT=200 --env MEASURE=5 --out "$O/freeze$round"
done

# a grid as it might be
say mix
for cells in 9 16; do
  RUN_TIMEOUT=260 run mix --drivers mpv_hw,vlc_hw_sp,vlc_hw,mpv_sw,vlc_sw_sp --cells $cells --env LOAD_TIMEOUT=120 --out "$O/mix"
  RUN_TIMEOUT=260 run mix --drivers mpv_hw --cells $cells --env EXP=skip --env LOAD_TIMEOUT=120 --out "$O/mix_skip"
done

# churn, with glibc's heap checks on, then an address sanitizer if it'll run at all
CHECKS="MALLOC_CHECK_=3 MALLOC_PERTURB_=165 GLIBC_TUNABLES=glibc.malloc.tcache_count=0"
LIMIT=1800 scenario churn_hw churn.py DRIVER=mpv_hw MINUTES=20 SEED=1 $CHECKS
LIMIT=1800 scenario churn_sw churn.py DRIVER=mpv_sw MINUTES=20 SEED=2 $CHECKS
LIMIT=1200 scenario churn_vlc churn.py DRIVER=vlc_hw_sp MINUTES=10 SEED=3
asan=$(gcc -print-file-name=libasan.so)
if [ -f "$asan" ]; then
  LIMIT=1200 scenario churn_asan churn.py DRIVER=mpv_hw MINUTES=10 SEED=4 LD_PRELOAD="$asan" ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:log_path=$O/asan
fi

# left playing
LIMIT=4200 scenario soak_hw soak.py DRIVER=mpv_hw CELLS=9 MINUTES=60
LIMIT=2400 scenario soak_sw soak.py DRIVER=mpv_sw CELLS=4 MINUTES=30
LIMIT=2400 scenario soak_vlc soak.py DRIVER=vlc_hw_sp CELLS=9 MINUTES=30

say DONE
touch "$O/all_done"
