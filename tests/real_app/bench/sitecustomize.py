"""In every Python process of a bench run, the app's forked VLC players too: when the run
says so, write down what each VLC player has counted. Off unless GP_BENCH_DIR is set."""

import os

_dir = os.environ.get("GP_BENCH_DIR")


def _stats(players, vlc):
    rows = []
    for player in players:
        media = getattr(player, "_media_input_vlc", None)
        if media is None:
            continue
        stats = vlc.MediaStats()
        if media.get_stats(stats):
            rows.append(
                {
                    "player": id(player),
                    "displayed": stats.displayed_pictures,
                    "lost": stats.lost_pictures,
                    "decoded": stats.decoded_video,
                }
            )
    return rows


def _watch():
    import gc
    import json
    import sys
    import time

    seen = ""
    players = None
    phase_file = os.path.join(_dir, "phase")

    while True:
        time.sleep(0.25)
        try:
            with open(phase_file) as f:
                phase = f.read().strip()
        except OSError:
            continue

        if phase == seen:
            continue
        seen = phase

        module = sys.modules.get("gridplayer.vlc_player.player_base")
        libvlc = sys.modules.get("gridplayer.vlc_player.libvlc")
        if module is None or libvlc is None:
            continue

        if phase == "find" or players is None:
            players = [
                o for o in gc.get_objects() if isinstance(o, module.VlcPlayerBase)
            ]

        if phase != "find":
            rows = _stats(players, libvlc.vlc)
            out = os.path.join(_dir, f"vlc_{phase}_{os.getpid()}.json")
            with open(out, "w") as f:
                json.dump({"t": time.monotonic(), "rows": rows}, f)


def _start():
    import threading

    threading.Thread(target=_watch, name="bench-watch", daemon=True).start()


if _dir:
    _start()
    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=_start)
