"""Transport on the mpv driver: a frame step is one frame in any container, a bar
drag lands where it ends, and speed, the loop, a saved or random start and what
happens at the end of a video all work from mpv's time."""

import subprocess
import time
from itertools import pairwise
from pathlib import Path

from gridplayer.params.static import VideoEndAction
from tests.real_app.scenarios.pixel_shape import _grab

SETTINGS = {
    "player/video_driver": "mpv_hw",
    "video_defaults/cell_view_mode": "fit",
    "video_defaults/initial_state": "paused",
}

# Containers and rates where the time in whole milliseconds rounds differently:
# an mkv holds whole milliseconds, an mp4 a fraction, 30 fps lands on exact ones
STEPPED_CLIPS = (
    ("c30.mp4", "30"),
    ("ntsc.mp4", "24000/1001"),
    ("ntsc.mkv", "24000/1001"),
    ("c60.mkv", "60"),
)

FRAME_STEPS = 8

DRAG_SEEKS = 40
DRAG_GAP_S = 0.03


def scenario(d):
    _frame_steps(d)
    _bar_drag(d)
    _time_reports(d)
    _speed(d)
    _loop_ab(d)
    _saved_position(d)
    _random_start(d)
    _end_actions(d)
    _next_file_at_end(d)


def _clip(d, name: str, rate: str = "30", seconds: float = 10) -> Path:
    path = d.out / name

    if not path.exists():
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                f"testsrc2=size=320x180:rate={rate}:duration={seconds}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
            ],
            check=True,
        )  # fmt: skip

    return path


def _open(d, path, is_playing=False):
    d.open(path)
    block = d.wait_for_cell(path.name)

    if is_playing:
        d.act(block, "Play / Pause")
        d.wait_until(lambda: not block.video_params.is_paused, "it plays")

    return block


def _close(d, block):
    d.act(block, "Close")
    d.wait(0.3)


def _mpv(block):
    return block.video_driver.video_driver._player.mpv


def _frame_no(block):
    return _mpv(block).estimated_frame_number


def _frame_steps(d):
    for name, rate in STEPPED_CLIPS:
        block = _open(d, _clip(d, name, rate))

        d.act(block, "50%")
        d.wait_until(lambda b=block: _frame_no(b) > 0, "at the middle")
        d.wait(0.3)

        _step(d, block, name, "Next frame", 1)
        _step(d, block, name, "Previous frame", -1)

        _close(d, block)


def _step(d, block, name, action, direction):
    frame_no = _frame_no(block)

    for _ in range(FRAME_STEPS):
        picture = _grab(block)
        frame_no += direction

        d.act(block, action)
        d.wait_until(
            lambda n=frame_no: _frame_no(block) == n,
            f"{name}: {action} goes to frame {frame_no}",
            3,
        )
        d.wait_until(lambda p=picture: _grab(block) != p, "and shows it", 3)

    # none landed a frame off and only then came right
    d.wait(0.3)
    d.check(f"{name}: {action} stays there", _frame_no(block) == frame_no)


def _bar_drag(d):
    for is_playing in (False, True):
        block = _open(d, d.media.clips[0], is_playing=is_playing)
        surface = block.video_driver.video_surface
        # MPV's Direct output: mpv draws into its own window, nothing to count
        is_counted = hasattr(surface, "present_frame")

        shown = []
        present = getattr(surface, "present_frame", None)

        def counted(*args, present=present, shown=shown):
            shown.append(args)
            present(*args)

        if is_counted:
            surface.present_frame = counted

        for at in range(DRAG_SEEKS):
            percent = 0.1 + 0.8 * at / DRAG_SEEKS
            block.seek_percent(percent)
            d.pump(DRAG_GAP_S)

        # not the block's target, which is gone once the seek has been seen to land
        aim = percent * block.video_driver.length

        if is_counted:
            surface.present_frame = present

        what = "playing" if is_playing else "paused"

        d.wait_until(
            lambda a=aim, b=block: abs(_mpv(b).time_pos * 1000 - a) < 1000,
            f"{what}: the drag lands where it ended",
            5,
        )
        if is_counted:
            d.check(
                f"{what}: pictures came along", len(shown) > DRAG_SEEKS / 4, len(shown)
            )

        _close(d, block)


def _time_reports(d):
    block = _open(d, d.media.clips[0], is_playing=True)

    reports = []
    block.video_driver.time_changed.connect(reports.append)

    d.wait(2)

    # about what VLC sends, not one a frame
    d.check("the time is told a few times a second", 6 <= len(reports) <= 14, reports)

    _close(d, block)


def _speed(d):
    block = _open(d, d.media.clips[0], is_playing=True)

    for rate in (2.0, 0.5):
        block.set_rate(rate)
        d.wait(0.3)

        before, at = block.time, time.monotonic()
        d.wait(1.5)
        seen = (block.time - before) / 1000 / (time.monotonic() - at)

        d.check(f"plays at {rate}", abs(seen - rate) < 0.25 * rate + 0.15, seen)

    block.set_rate(2.0)
    block.reload()
    d.wait_until(lambda: block.is_playable, "it reloads")
    d.wait_until(lambda: _mpv(block).speed == 2.0, "the speed stays through a reload")

    _close(d, block)


def _loop_ab(d):
    block = _open(d, _clip(d, "loop.mp4"), is_playing=True)

    block.seek(3000)
    d.wait_until(lambda: block.time >= 3000, "at the loop's start")
    d.act(block, "Set Loop Start")
    d.wait_until(lambda: block.time >= block.loop_start + 1000, "a second on")
    d.act(block, "Set Loop End")

    start, end = block.loop_start, block.loop_end

    seen = []
    until = time.monotonic() + 3

    while time.monotonic() < until:
        seen.append(block.time)
        d.wait(0.1)

    d.check("it goes round", any(b < a for a, b in pairwise(seen)), seen)
    # a time is told every 200 ms: it can be that far past the end when it's seen
    d.check(
        "and stays in the loop",
        all(start - 100 <= at <= end + 300 for at in seen),
        (start, end, seen),
    )

    _close(d, block)


def _saved_position(d):
    block = _open(d, _clip(d, "saved.mp4", seconds=4), is_playing=True)

    block.seek(2500)
    d.wait_until(lambda: block.time >= 2500, "further on")

    block.reload()
    d.wait_until(lambda: block.is_playable, "it reloads")

    position = block.video_params.current_position
    d.check("it carries on from there", 2500 <= block.time <= 3500, block.time)

    # not back to where it started this time: that's only the saved position
    d.wait_until(lambda: block.time < position - 1000, "it goes round", 6)
    d.check("from the start of the video", block.time < 1000, block.time)

    _close(d, block)


def _random_start(d):
    path = _clip(d, "random.mp4", seconds=20)
    block = _open(d, path)

    d.act(block, "Random Loop")
    d.check("a random start is on", block.video_params.is_start_random)

    # nothing of the video's start on show once it says it has loaded
    block.video_params.current_position = 0
    block.reload()
    d.wait_until(lambda: block.is_playable, "it reloads")

    time_at_load, picture_at_load = block.time, _grab(block)
    d.check("it starts somewhere else", time_at_load > 0, time_at_load)

    d.wait(0.5)
    d.check("that's what it shows from the start", _grab(block) == picture_at_load)

    _close(d, block)


def _end_actions(d):
    path = _clip(d, "end.mp4", seconds=4)

    block = _open(d, path, is_playing=True)
    block.set_end_action(VideoEndAction.LOOP_FILE)
    block.seek(3600)
    d.wait_until(lambda: block.time < 1000, "looping, it goes round", 4)
    d.check("and keeps playing", not block.video_params.is_paused)
    _close(d, block)

    block = _open(d, path, is_playing=True)
    block.set_end_action(VideoEndAction.PAUSE)
    block.seek(3600)
    d.wait_until(lambda: block.video_params.is_paused, "it pauses at the end", 4)
    d.wait_until(lambda: _frame_no(block) == 0, "on the first frame", 3)
    _close(d, block)

    block = _open(d, path, is_playing=True)
    block.set_end_action(VideoEndAction.STOP)
    block.seek(3600)
    d.wait_until(lambda: block.is_stopped, "it stops at the end", 4)
    d.act(block, "Play / Pause")
    d.wait_until(lambda: block.is_playable and not block.is_stopped, "and plays again")
    _close(d, block)

    block = _open(d, path, is_playing=True)
    block.set_end_action(VideoEndAction.CLOSE)
    block.seek(3600)
    d.wait_until(lambda: not d.cells, "it closes at the end", 4)


def _next_file_at_end(d):
    block = _open(d, d.media.clips[0], is_playing=True)

    block.set_end_action(VideoEndAction.NEXT_FILE)
    block.seek(block.video_driver.length - 400)

    d.wait_until(lambda: block.video_params.uri.name == "b.mp4", "on to the next file")
    d.wait_until(lambda: block.is_playable, "which plays")

    _close(d, block)
