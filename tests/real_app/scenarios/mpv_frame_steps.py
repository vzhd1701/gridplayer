"""A frame step on MPV goes to the video's next frame or the one before, at whatever rate
they come (#305). The clip is 5 frames a second for 4 s, then 25, each frame a colour of
its own. Stepped by the average rate, 15, a press took three to move in the first part,
skipped frames in the second, and back stuck where the two meet.

A key held down steps a frame for every press, however fast they come. With seek sync,
the others go where the step landed and the one stepped stays on its frame. VLC still steps by the average rate: VLC 3 says no time with a step of its own.
"""

from PyQt6.QtGui import QColor

from tests.real_app.media import VFR_FRAMES, frame_shown
from tests.real_app.scenarios.pixel_shape import _grab

SETTINGS = {"player/video_driver": "mpv_hw"}

# mpv's time is said 1 ms on, see MpvPlayer._on_time
TIME_SLACK_MS = 2

HELD_PRESSES = 5


def _shown(b) -> int:
    image = _grab(b)
    return frame_shown(QColor(image.pixel(image.width() // 2, image.height() // 2)))


def _on_frame(b, frame) -> bool:
    return _shown(b) == frame and abs(b.time - VFR_FRAMES[frame]) <= TIME_SLACK_MS


def _settled(d, b, what) -> int:
    d.wait_until(
        lambda: 0 <= _shown(b) < len(VFR_FRAMES) and _on_frame(b, _shown(b)), what
    )
    return _shown(b)


def _step(d, b, action, frame, what) -> bool:
    d.act(b, action)
    d.wait_until(lambda: _on_frame(b, frame), f"{what}: frame {frame}", timeout=5)
    # and no further
    d.wait(0.2)
    return d.check(
        f"{what}: on frame {frame}", _on_frame(b, frame), (_shown(b), b.time)
    )


def _held(d, b, command, frame, what) -> bool:
    """A key held down: the presses come faster than the steps land, every one a
    frame all the same. mpv would add a seek to the one on its way, and turn a step
    back down."""

    d.ctx.active_block = b
    for _ in range(HELD_PRESSES):
        b.manual_seek(command)

    d.wait_until(lambda: _on_frame(b, frame), f"{what}: frame {frame}", timeout=10)
    d.wait(0.3)
    return d.check(
        f"{what}: on frame {frame}", _on_frame(b, frame), (_shown(b), b.time)
    )


def _paused(d, b):
    b.set_pause(True)
    d.wait_until(lambda: b.video_params.is_paused, f"{b.video_params.title}: paused")


def scenario(d):
    d.open(d.media.vfr)
    b = d.wait_for_cell("vfr.mp4")
    _paused(d, b)

    # by the frames' rate, across where it changes, and back
    b.seek(3_300)
    start = _settled(d, b, "before the change")

    for n in range(1, 9):
        _step(d, b, "Next frame", start + n, "on")
    for n in range(7, -1, -1):
        _step(d, b, "Previous frame", start + n, "back")

    # 3.5 s from the only key frame
    b.seek(7_500)
    far = _settled(d, b, "far from a key frame")
    _step(d, b, "Next frame", far + 1, "far on")
    _step(d, b, "Previous frame", far, "far back")
    _step(d, b, "Previous frame", far - 1, "far back")

    b.seek(3_300)
    start = _settled(d, b, "held")
    _held(d, b, "next_frame", start + HELD_PRESSES, "held on")
    _held(d, b, "previous_frame", start, "held back")

    _seek_synced(d, b)


def _seek_synced(d, b):
    d.open(d.media.clips[0])
    other = d.wait_for_cell("a.mp4")
    _paused(d, other)

    d.act(b, "Seek Sync (Timecode)")

    b.seek(4_500)
    start = _settled(d, b, "synced")

    for action, frame in (("Next frame", start + 1), ("Previous frame", start)):
        _step(d, b, action, frame, f"synced {action}")
        d.wait_until(
            lambda: abs(other.time - b.time) <= 40,
            f"synced {action}: the other goes where it landed",
            timeout=5,
        )
        d.check(
            f"synced {action}: it stays on its frame",
            _on_frame(b, frame),
            (_shown(b), b.time, other.time),
        )

    # followed to where the last landed
    _held(d, b, "next_frame", start + HELD_PRESSES, "synced held")
    d.wait_until(
        lambda: abs(other.time - b.time) <= 40,
        "synced held: the other goes where the last landed",
        timeout=5,
    )

    d.act(b, "Seek Sync (Disabled)")
