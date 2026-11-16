"""`--self-check`: whether GridPlayer has what it takes to play, for CI.

Run on each package as it was built. It starts Qt as the app does, without
a window, loads libVLC and libmpv, and plays each file given with each of
them, showing and sounding nothing. It prints a checkup report and exits
with 1 if anything failed.

A packaged app on Windows has no console, and nothing to print to unless its
output was redirected: then the report goes into self-check.txt in the user
data folder (portable_data in the portable zip).
"""

import sys
import time
from functools import partial
from pathlib import Path

from gridplayer.utils.checkup import Check, CheckResult, CheckStatus, report_text
from gridplayer.version import __app_name__, __version__

# from a file's start to its picture and sound being decoded, first run
# included: VLC on macOS reads its plugins the first time
PLAY_TIMEOUT_S = 30

REPORT_FILE = "self-check.txt"

_app = None


def run_self_check(files: list[str]) -> int:
    checks = [
        Check("Qt", _check_qt),
        Check("VLC", _check_vlc),
        Check("MPV", _check_mpv),
    ]

    for file in files:
        # native: VLC on Windows takes no C:/ path
        file = str(Path(file).resolve())
        name = Path(file).name
        checks.append(Check(f"VLC plays {name}", partial(_vlc_plays, file)))
        checks.append(Check(f"MPV plays {name}", partial(_mpv_plays, file)))

    rows = [(check.title, _run(check)) for check in checks]

    _write_report(report_text(f"{__app_name__} {__version__} self-check", rows))

    is_failed = any(result.status == CheckStatus.FAILED for _, result in rows)

    return 1 if is_failed else 0


def _run(check: Check) -> CheckResult:
    try:
        return check.run()
    # python-vlc exits by itself when the library it found won't load
    except (Exception, SystemExit) as e:
        return _failed(f"{type(e).__name__}: {e}")


def _passed(summary: str) -> CheckResult:
    return CheckResult(CheckStatus.PASSED, summary)


def _failed(summary: str) -> CheckResult:
    return CheckResult(CheckStatus.FAILED, summary)


def _write_report(text: str) -> None:
    if sys.stdout is not None:
        print(text, flush=True)
        return

    from gridplayer.utils.app_dir import get_app_data_dir

    report = get_app_data_dir() / REPORT_FILE
    report.write_text(f"{text}\n", encoding="utf-8")


def _check_qt() -> CheckResult:
    global _app

    from PyQt5.QtCore import QT_VERSION_STR

    from gridplayer.main.init_app import init_app

    # kept for the run, as Qt's platform plugin is what a package can lack
    _app = init_app()

    return _passed(f"Qt {QT_VERSION_STR}, {_app.platformName()}")


def _check_vlc() -> CheckResult:
    from gridplayer.params import env
    from gridplayer.utils.media_libs import (
        MediaLib,
        find_libvlc,
        lib_problem_text,
        load_lib,
    )

    if not load_lib(MediaLib.VLC):
        return _failed(lib_problem_text(MediaLib.VLC))

    return _passed(f"{env.VLC_VERSION}, {find_libvlc()}")


def _check_mpv() -> CheckResult:
    from gridplayer.utils.media_libs import (
        MediaLib,
        find_libmpv,
        lib_problem_text,
        load_lib,
    )

    if not load_lib(MediaLib.MPV):
        return _failed(lib_problem_text(MediaLib.MPV))

    from gridplayer.mpv_player.libmpv import load_mpv

    mpv = load_mpv()
    player = mpv.MPV(vo="null", ao="null", config=False)

    try:
        version, ffmpeg = player.mpv_version, player.ffmpeg_version
    finally:
        player.terminate()

    api = ".".join(map(str, mpv.MPV_VERSION))

    return _passed(f"{version}, FFmpeg {ffmpeg}, API {api}, {find_libmpv()}")


def _vlc_plays(file: str) -> CheckResult:
    from gridplayer.utils.media_libs import MediaLib, load_lib

    if not load_lib(MediaLib.VLC):
        return _failed("VLC didn't load")

    from gridplayer.vlc_player.instance import _is_plugin_cache_exists
    from gridplayer.vlc_player.libvlc import vlc

    options = [
        "--intf=dummy",
        "--quiet",
        "--vout=dummy",
        "--aout=dummy",
        "--no-lua",
        "--no-interact",
    ]

    # as the app starts it, which a stale or missing cache would trip
    if _is_plugin_cache_exists():
        options.append("--no-plugins-scan")

    instance = vlc.Instance(options)

    if instance is None:
        return _failed("VLC didn't start")

    media = instance.media_new_path(file)

    if media is None:
        instance.release()
        return _failed("VLC couldn't open it")

    player = instance.media_player_new()
    player.set_media(media)
    stats = vlc.MediaStats()

    try:
        player.play()

        deadline = time.monotonic() + PLAY_TIMEOUT_S

        while time.monotonic() < deadline:
            time.sleep(0.05)

            media.get_stats(stats)

            if stats.decoded_video and stats.decoded_audio:
                break

            if player.get_state() in {vlc.State.Error, vlc.State.Ended}:
                break
    finally:
        player.stop()
        player.release()
        media.release()
        instance.release()

    return _decoded(stats.decoded_video, bool(stats.decoded_audio))


def _mpv_plays(file: str) -> CheckResult:
    from gridplayer.utils.media_libs import MediaLib, load_lib

    if not load_lib(MediaLib.MPV):
        return _failed("libmpv didn't load")

    from gridplayer.mpv_player.libmpv import load_mpv

    errors = []

    def on_log(level, component, message):
        errors.append(f"{component}: {message.strip()}")

    mpv = load_mpv()
    player = mpv.MPV(
        vo="null",
        ao="null",
        config=False,
        idle=True,
        log_handler=on_log,
        loglevel="error",
    )

    frames, has_audio = 0, False

    try:
        player.play(file)

        deadline = time.monotonic() + PLAY_TIMEOUT_S

        while time.monotonic() < deadline:
            time.sleep(0.05)

            frames = player.estimated_frame_number or 0
            has_audio = player.audio_params is not None

            if frames and has_audio:
                break

            # back to idle: it ended, or never started
            if errors and player.idle_active:
                break
    finally:
        player.terminate()

    result = _decoded(frames, has_audio)

    if result.status == CheckStatus.FAILED and errors:
        return _failed(f"{result.summary}; {errors[-1]}")

    return result


def _decoded(frames: int, has_audio: bool) -> CheckResult:
    if frames and has_audio:
        return _passed("picture and sound decoded")

    return _failed(f"{frames} frames, {'' if has_audio else 'no '}sound decoded")
