"""Deinterlacing on the mpv driver, through the app's own menus: the picture shows it.

A bar moving fast, made interlaced: what's combed has rows that differ from the ones
next to them. Each setting takes hold with no reload, comes back after one, and a mode
gets as many pictures a second as it should. A filter this libmpv hasn't got leaves it
playing on with its own, and a mode whose filters it hasn't got (MPVKit's on macOS)
shows greyed out.
"""

from unittest.mock import patch

from PyQt6.QtGui import qGray

from gridplayer.mpv_player import abilities, deinterlace, player
from gridplayer.params.actions import ACTIONS
from gridplayer.params.static import VideoDeinterlaceMode
from tests.real_app.media import _ffmpeg
from tests.real_app.scenarios.mpv_subtitles import _reload
from tests.real_app.scenarios.mpv_transport import _mpv
from tests.real_app.scenarios.mpv_view import _close, _open, _take_screenshot

SETTINGS = {
    "player/video_driver": "mpv_hw",
    "video_defaults/cell_view_mode": "fit",
    "video_defaults/initial_state": "playing",
}

# Light moves from the bar's two sides, 10 pixels per field, each edge in every row
COMBED = 2_000
CLEAN = 500

# of the picture's rows, a quarter of the way down
SAMPLED_ROWS = 60


def _moving_bar(rate: int, ending: str) -> str:
    return (
        f"color=black:s=640x360:r={rate}:d=20[bg];"
        f"color=white:s=80x360:r={rate}:d=20[bar];"
        f"[bg][bar]overlay=x='mod(n*10\\,560)':y=0,format=yuv420p,{ending}"
    )


_BAR = _moving_bar(60, "tinterlace=interleave_top")

_FLAGS = ("-flags", "+ildct+ilme", "-x264opts", "interlaced=1:tff=1")

# film at 24 frames a second, brought up to 30 by making some of two moments
_TELECINE = _moving_bar(24, "telecine=pattern=23")

FILM_SHOTS = 12

# how far a frame step goes on a clip of 30 frames a second, what's picked or not
FRAME_MS = 33
FRAME_STEP_SLACK_MS = 12

# what each should run at on a clip of 30 frames a second
MODE_RATES = {
    "Deinterlace Mode - Discard": 30,
    "Deinterlace Mode - Blend": 30,
    "Deinterlace Mode - Mean": 30,
    "Deinterlace Mode - Bob": 60,
    "Deinterlace Mode - Linear": 60,
    "Deinterlace Mode - X": 30,
    "Deinterlace Mode - Yadif": 30,
    "Deinterlace Mode - Yadif (2x)": 60,
    "Deinterlace Mode - Phosphor": 60,
    "Deinterlace Mode - Film NTSC (IVTC)": 24,
}


def scenario(d):
    flagged = _clip(d, "flagged.mkv", _BAR, *_FLAGS)
    unflagged = _clip(d, "unflagged.mkv", f"{_BAR},setfield=prog")

    _as_it_plays(d, flagged)
    _modes(d, flagged)
    _film(d)
    _automatic_goes_by_the_file(d, flagged, unflagged)
    _paused(d, flagged)
    _paused_to_automatic(d, flagged)
    _frame_steps(d, flagged)
    _a_filter_it_has_not_got(d, flagged)
    _hardware_keeps_up(d, flagged)


def _clip(d, name, graph, *flags):
    path = d.out / name

    if not path.exists():
        _ffmpeg(
            "-f",
            "lavfi",
            "-i",
            graph,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            *flags,
            name,
            cwd=d.out,
        )

    return path


def _comb(d, b) -> int:
    """How much rows differ from the next one, for each row of those looked at."""

    image = _take_screenshot(d, b)
    width, height = image.width(), image.height()
    first = height // 4

    def row(y):
        return [qGray(image.pixel(x, y)) for x in range(width)]

    total = 0
    above = row(first)
    for y in range(first + 1, first + SAMPLED_ROWS + 1):
        below = row(y)
        total += sum(abs(a - c) for a, c in zip(above, below))
        above = below

    return total // SAMPLED_ROWS


def _wait_for_motion(d, b):
    """Past where a filter changing has settled, with the bar on the move."""

    start = b.time
    d.wait_until(lambda: b.time > start + 400, "it plays on")


def _check_comb(d, b, what, is_combed):
    _wait_for_motion(d, b)
    comb = _comb(d, b)
    d.note(f"{what}: comb {comb}", b)

    if is_combed:
        d.check(f"{what}: combed", comb > COMBED)
    else:
        d.check(f"{what}: clean", comb < CLEAN)


def _as_it_plays(d, flagged):
    b = _open(d, flagged)

    _check_comb(d, b, "automatic, file says interlaced", is_combed=False)

    d.act(b, "Deinterlace Off")
    _check_comb(d, b, "off", is_combed=True)

    d.act(b, "Deinterlace On")
    _check_comb(d, b, "on", is_combed=False)

    d.act(b, "Deinterlace Off")
    _check_comb(d, b, "off again", is_combed=True)

    d.act(b, "Deinterlace Auto")
    _check_comb(d, b, "back to automatic", is_combed=False)
    d.check("none of that took a reload", b.is_video_initialized)

    d.act(b, "Deinterlace Off")
    _reload(d, b)
    _check_comb(d, b, "still off after a reload", is_combed=True)

    d.act(b, "Deinterlace On")
    d.act(b, "Deinterlace Mode - Yadif")
    _reload(d, b)
    _check_comb(d, b, "a mode after a reload", is_combed=False)

    _close(d, b)


def _wait_for_rate(d, b, rate, what, slack=4):
    d.wait_until(
        lambda: abs((_mpv(b).estimated_vf_fps or 0) - rate) < slack,
        f"{what}: {rate} pictures a second",
        timeout=8,
    )


def _modes(d, flagged):
    b = _open(d, flagged)
    d.act(b, "Deinterlace On")

    size = tuple(_mpv(b).video_out_params[key] for key in ("w", "h"))

    for action, rate in MODE_RATES.items():
        if _is_missing(action):
            d.check(f"{action}: greyed out", not d.ctx.actions[action].is_enabled)
            continue

        d.act(b, action)

        _wait_for_rate(d, b, rate, action)

        # This bar isn't film, which is all that one is for: it comes and goes, as it
        # stays on VLC. See _film.
        if "IVTC" not in action:
            _check_comb(d, b, action, is_combed=False)

        params = _mpv(b).video_out_params
        d.check(f"{action}: the same size", (params["w"], params["h"]) == size)

    _close(d, b)


def _most_comb_of_many(d, b) -> int:
    """Only 2 frames of film in 5 come out combed, so one picture tells nothing."""

    _wait_for_motion(d, b)

    most = 0
    for _ in range(FILM_SHOTS):
        most = max(most, _comb(d, b))
        d.wait(0.07)

    return most


def _is_missing(action: str) -> bool:
    """A mode whose filters this libmpv's FFmpeg hasn't got."""

    mode = ACTIONS[action]["func"][2]

    return mode in deinterlace.unavailable_modes(abilities.known())


def _film(d):
    if _is_missing("Deinterlace Mode - Film NTSC (IVTC)"):
        d.note("film: no IVTC in this libmpv")
        return

    b = _open(d, _clip(d, "film.mkv", _TELECINE, *_FLAGS))

    d.act(b, "Deinterlace Off")
    d.check("film, off: combed", _most_comb_of_many(d, b) > COMBED)

    d.act(b, "Deinterlace Mode - Film NTSC (IVTC)")
    _wait_for_rate(d, b, 24, "film, matched up", slack=2)
    d.check("film, matched up: clean", _most_comb_of_many(d, b) < CLEAN)

    _close(d, b)


def _automatic_goes_by_the_file(d, flagged, unflagged):
    b = _open(d, unflagged)
    _check_comb(d, b, "automatic, file says nothing", is_combed=True)
    d.act(b, "Deinterlace On")
    _check_comb(d, b, "on, file says nothing", is_combed=False)
    _close(d, b)

    # Only asked of a name once the file has said so, by its frames
    for clip, what, is_combed in (
        (flagged, "file says interlaced", False),
        (unflagged, "file says nothing", True),
    ):
        b = _open(d, clip)
        d.act(b, "Deinterlace Mode - Yadif")
        d.act(b, "Deinterlace Auto")
        _check_comb(d, b, f"automatic, by name, {what}", is_combed)
        _close(d, b)


def _paused(d, flagged):
    b = _open(d, flagged)
    d.act(b, "Deinterlace Off")
    b.set_pause(True)
    d.wait_until(lambda: b.video_params.is_paused, "it's paused")

    d.act(b, "Deinterlace Mode - Yadif")
    d.wait_until(lambda: _comb(d, b) < CLEAN, "paused, the picture goes clean")

    d.act(b, "Deinterlace Off")
    d.wait_until(lambda: _comb(d, b) > COMBED, "paused, the picture goes back")

    # by name, Automatic only hears of it from a frame, the one there's going to be
    d.act(b, "Deinterlace Mode - Yadif")
    d.act(b, "Deinterlace Auto")
    _reload(d, b)
    d.check("paused after the reload", b.video_params.is_paused)
    d.wait_until(lambda: _comb(d, b) < CLEAN, "automatic, by name, opened paused")

    _close(d, b)


def _paused_to_automatic(d, flagged):
    """Nothing's coming to say the file's interlaced, nor any time to go with it. A
    frame through a deinterlacer doesn't say, and looks clean until it's come off."""

    _paused_to_automatic_from(d, flagged, "Deinterlace Mode - Yadif", "Deinterlace Off")
    _paused_to_automatic_from(d, flagged, "Deinterlace Mode - Yadif")
    _paused_to_automatic_from(d, flagged, "Deinterlace On")


def _paused_to_automatic_from(d, flagged, *first):
    b = _open(d, flagged)
    loaded = b.video_driver.video_driver._player

    for action in first:
        d.act(b, action)

    # paused right after, the picture on show can be one from before the filter
    _wait_for_motion(d, b)

    b.set_pause(True)
    d.wait_until(lambda: b.video_params.is_paused, "it's paused")
    d.wait(0.5)

    d.act(b, "Deinterlace Auto")
    d.wait(1.5)

    d.check(f"from {first}: paused still", b.video_params.is_paused)
    d.check(f"from {first}: no reload", b.video_driver.video_driver._player is loaded)
    d.wait_until(lambda: _comb(d, b) < CLEAN, f"from {first}: goes by the file")

    _close(d, b)


def _frame_steps(d, flagged):
    """However many pictures a second a mode makes, a step is a frame of the video."""

    b = _open(d, flagged)
    b.set_pause(True)
    d.wait_until(lambda: b.video_params.is_paused, "it's paused")
    # by hand, so on the key frame before it, 8.3 s in, where seeks by hand are fast
    d.act(b, "50%")
    d.wait_until(lambda: 8_000 < b.time < 11_000, "at the middle")

    for picking in ("Deinterlace On", "Deinterlace Mode - Yadif (2x)"):
        d.act(b, picking)
        d.wait(0.5)

        # it can be showing the second field of a frame, half way to the next
        d.act(b, "Next frame")
        d.wait(0.3)

        for action, direction in (("Next frame", 1), ("Previous frame", -1)):
            for _ in range(3):
                wanted = b.time + direction * FRAME_MS

                d.act(b, action)
                d.wait_until(
                    lambda at=wanted: abs(b.time - at) <= FRAME_STEP_SLACK_MS,
                    f"{picking}: {action} goes to {wanted}",
                    timeout=5,
                )
                d.wait(0.1)

    _close(d, b)


def _a_filter_it_has_not_got(d, flagged):
    mode = VideoDeinterlaceMode.YADIF

    # not known to be missing beforehand, as where mpv can't be asked
    with (
        patch.dict(deinterlace._MODE_FILTERS, {mode: "nosuchfilter"}),
        patch.object(
            abilities, "_known", abilities.Abilities(frozenset(), frozenset())
        ),
    ):
        b = _open(d, flagged)
        d.act(b, "Deinterlace On")
        d.act(b, "Deinterlace Mode - Yadif")

        d.wait_until(lambda: mode in player._REFUSED_MODES, "it's refused")
        d.wait_until(lambda: not _mpv(b).vf, "the filter's gone")
        d.wait_until(lambda: _mpv(b).deinterlace is True, "mpv's own takes over")
        _check_comb(d, b, "a mode it hasn't got", is_combed=False)

        _reload(d, b)
        d.check("it isn't tried again", not _mpv(b).vf)
        _check_comb(d, b, "a mode it hasn't got, from the start", is_combed=False)
        _close(d, b)

    player._REFUSED_MODES.clear()


def _hardware_keeps_up(d, flagged):
    """The frames held for deinterlacing, with no extra frames to spare for them: see
    hwdec_extra_frames in player.py. It would show as mpv quietly going to -copy."""

    d.open(*[flagged] * 4)
    d.wait_until(
        lambda: len(d.cells) == 4 and all(b.is_playable for b in d.cells), "all play"
    )
    blocks = d.cells

    for b in blocks:
        d.act(b, "Deinterlace On")

    d.wait_until(
        lambda: all((_mpv(b).estimated_vf_fps or 0) > 40 for b in blocks),
        "each deinterlaced",
    )

    decoders = [_mpv(b).hwdec_current for b in blocks]
    d.note(f"decoding with {decoders}", blocks[0])

    for round_number in range(10):
        at = round_number * 1_500

        for b in blocks:
            b.seek(at)

        d.wait_until(
            lambda at=at: all(abs(b.time - at) < 1_500 for b in blocks),
            "the seeks have landed",
        )

        for b in blocks:
            b.set_pause(True)
            b.set_pause(False)

    d.check(
        "still the same decoder", [_mpv(b).hwdec_current for b in blocks] == decoders
    )

    for b in blocks:
        _close(d, b)
