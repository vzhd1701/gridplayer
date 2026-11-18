"""The mpv driver in the real grid: videos load and play, the picture follows
the cell through a resize, zoom and pan are the right part of the picture, and
cells close and come back."""

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QColor, QImage

from gridplayer.mpv_player.quality import FAST
from gridplayer.params.static import MpvPictureQuality
from tests.real_app.composed import has_direct_picture, is_direct
from tests.real_app.scenarios.pixel_shape import _grab, _picture_box, _ratio

SETTINGS = {
    "player/video_driver": "mpv_hw",
    "video_defaults/cell_view_mode": "fit",
    "video_defaults/initial_state": "paused",
}

# How long a video can take to be rendered at a new size, once settled
SETTLE_S = 5

# How far a pixel can be off a picture worked out by hand: scaled twice over,
# through smooth scaling, on a picture full of hard edges
PICTURE_SLACK = 40


def scenario(d):
    _playing(d)
    _resizing(d)
    _zoom_and_pan(d)
    _shapes(d)
    _closing(d)
    _broken_file(d)
    _reload_all(d)
    _skipping_frames(d)
    _picture_quality(d)


def _driver(block):
    return block.video_driver


def _rendered_size(block):
    return _driver(block).video_surface.frame_size()


def _has_picture(block) -> bool:
    if is_direct(block):
        return has_direct_picture(block)

    return _rendered_size(block)[0] > 0


def _picture_size(frame):
    if hasattr(frame.video_surface, "picture_size"):
        return frame.video_surface.picture_size()

    return frame._view_frame_size()


def _open_paused(d, path, name):
    d.open(path)
    block = d.wait_for_cell(name)
    d.wait_until(lambda: _has_picture(block), "a frame came")
    return block


def _playing(d):
    a, b = d.media.clips[:2]
    d.open(a, b)
    first = d.wait_for_cell("a.mp4")
    second = d.wait_for_cell("b.mp4")

    d.check(
        "it is the mpv driver",
        type(_driver(first)).__name__ in ("VideoFrameMpv", "VideoFrameMpvWindow"),
    )

    d.act(first, "Play / Pause")
    d.wait_until(lambda: not first.video_params.is_paused, "a plays")
    before = _grab(first)
    time_before = first.time
    d.wait(1.5)
    d.check("the time moves", first.time > time_before, (time_before, first.time))
    d.check("the picture moves", _grab(first) != before)
    d.check("b stays paused", second.video_params.is_paused)

    d.act(first, "Play / Pause")
    d.wait_until(lambda: first.video_params.is_paused, "a pauses")
    d.wait(0.3)
    paused_at = first.time
    still = _grab(first)
    d.wait(0.7)
    d.check("paused, it stays", _grab(first) == still and first.time == paused_at)

    d.act(first, "50%")
    d.wait_until(lambda: 9_000 <= first.time <= 11_000, "a seeks while paused")
    d.wait_until(lambda: _grab(first) != still, "and shows where it went")

    d.act(first, "Close")
    d.act(second, "Close")


def _resizing(d):
    # the source is 640x360: the frame goes down as the window does, and back
    block = _open_paused(d, d.media.shapes / "square.mp4", "square.mp4")

    if is_direct(block):
        # mpv draws at its window's size: the picture follows the cell
        for size in ((1280, 720), (320, 240), (1280, 720)):
            d.player.resize(*size)
            d.wait(0.5)
            _shaped(d, f"follows the cell at {size[0]}x{size[1]}", block, 16 / 9)

        d.act(block, "Close")
        return

    d.player.resize(1280, 720)
    d.wait_until(lambda: _rendered_size(block) == (640, 360), "own size", SETTLE_S)

    d.player.resize(320, 240)
    d.pump()
    frame_size = _rendered_size(block)
    d.check(
        "mid-resize the frame stays and is scaled",
        frame_size == (640, 360),
        frame_size,
    )
    _shaped(d, "scaled to the new size", block, 16 / 9)

    d.wait_until(
        lambda: _rendered_size(block)[0] < 640, "rendered for the new size", SETTLE_S
    )
    _shaped(d, "rendered for the new size", block, 16 / 9)
    d.shot("small", block)
    small = _rendered_size(block)

    # all it has if zoomed in far enough, and no more than the screen shows
    d.run(block, "active", "view.set_scale", 4.0)
    d.wait_until(lambda: _rendered_size(block) == (640, 360), "zoomed: all", SETTLE_S)
    d.run(block, "active", "view.set_scale", 1.0)
    d.wait_until(lambda: _rendered_size(block) == small, "not zoomed: small", SETTLE_S)

    d.player.resize(1280, 720)
    d.wait_until(lambda: _rendered_size(block) == (640, 360), "and back", SETTLE_S)

    d.act(block, "Close")


def _shaped(d, what, block, ratio):
    box = _picture_box(_grab(block))
    shape = _ratio(box)
    d.check(what, abs(shape - ratio) < 0.05 * ratio, (box, round(shape, 3)))


def _difference(one: QImage, other: QImage) -> float:
    """How far apart two pictures the same size are, per colour, on average."""

    step_x, step_y = max(one.width() // 40, 1), max(one.height() // 40, 1)
    total = count = 0

    for y in range(step_y // 2, one.height(), step_y):
        for x in range(step_x // 2, one.width(), step_x):
            a, b = QColor(one.pixel(x, y)), QColor(other.pixel(x, y))
            total += (
                abs(a.red() - b.red())
                + abs(a.green() - b.green())
                + abs(a.blue() - b.blue())
            ) / 3
            count += 1

    return total / count


def _expected_zoom(whole: QImage, part: QRect) -> QImage:
    return whole.copy(part).scaled(
        whole.size(),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _zoom_and_pan(d):
    block = _open_paused(d, d.media.shapes / "square.mp4", "square.mp4")

    # the cell the picture's own shape, for a zoom to fill it edge to edge
    d.player.resize(800, 450)
    d.wait(0.4)
    frame = _driver(block)
    d.wait_until(lambda: frame.picture_rect() is not None, "placed")
    whole = _grab(block)
    size = whole.size()
    width, height = size.width(), size.height()

    d.note(f"cell {width}x{height}, picture at {frame.picture_rect()}")

    d.run(block, "active", "view.set_scale", 2.0)
    d.wait(0.4)
    d.shot("zoomed", frame)

    middle = QRect(width // 4, height // 4, width // 2, height // 2)
    off = _difference(_grab(block), _expected_zoom(whole, middle))
    d.check("zoomed in, it is the middle of the picture", off < PICTURE_SLACK, off)

    shift_before = block.video_params.shift
    d.act(block, "Move Right")
    d.act(block, "Move Right")
    d.act(block, "Move Down")
    d.wait(0.2)
    d.check("moved", block.video_params.shift != shift_before, block.video_params.shift)

    source_x, source_y, source_w, source_h = frame.view_placement().source
    picture_w, picture_h = _picture_size(frame)
    part = QRect(
        round(source_x * width / picture_w),
        round(source_y * height / picture_h),
        round(source_w * width / picture_w),
        round(source_h * height / picture_h),
    )

    d.shot("moved", frame)
    off = _difference(_grab(block), _expected_zoom(whole, part))
    d.check(
        "moved, it is that part of the picture",
        off < PICTURE_SLACK,
        (off, part.getRect()),
    )

    d.act(block, "Zoom Reset")
    d.wait(0.4)
    off = _difference(_grab(block), whole)
    d.check("zoom reset, the whole picture again", off < PICTURE_SLACK, off)

    d.act(block, "Close")


def _shapes(d):
    shapes = d.media.shapes

    block = _open_paused(d, shapes / "wide_pixels.mp4", "wide_pixels.mp4")
    d.wait(0.3)
    d.shot("wide_pixels", _driver(block))
    _shaped(d, "pixels twice as wide, shown 16:9", block, 16 / 9)
    d.act(block, "Close")

    block = _open_paused(d, shapes / "phone.mp4", "phone.mp4")
    d.wait(0.3)
    d.shot("phone", _driver(block))
    _shaped(d, "a file that says to turn it, shown 9:16", block, 9 / 16)
    d.act(block, "Close")


def _closing(d):
    d.open(*d.media.clips)
    blocks = [d.wait_for_cell(name) for name in ("a.mp4", "b.mp4", "c.mp4")]

    d.act(blocks[1], "Close")
    d.wait_until(lambda: len(d.cells) == 2, "b is closed")

    for block in blocks[0], blocks[2]:
        d.act(block, "Play / Pause")
    before = blocks[0].time
    d.wait(1)
    d.check("the others play on", blocks[0].time > before, (before, blocks[0].time))

    d.open(d.media.clips[1])
    d.wait_for_cell("b.mp4")
    d.check("three again", len(d.cells) == 3)

    for block in list(d.cells):
        d.act(block, "Close")


def _broken_file(d):
    broken = d.out / "broken.mp4"
    broken.write_bytes(b"this is not a video" * 1000)

    d.open(broken)
    d.wait_until(lambda: d.cell("broken.mp4").is_error, "the cell says it failed")
    d.note("the broken file", d.cell("broken.mp4"))
    d.act(d.cell("broken.mp4"), "Close")


def _reload_all(d):
    d.open(*d.media.clips[:2])
    d.wait_for_cell("a.mp4")
    d.wait_for_cell("b.mp4")

    old = d.cell("a.mp4")
    d.act(old, "Reload [ALL]")
    d.wait_until(lambda: not old.is_playable or d.cell("a.mp4") is not old, "reloading")
    d.wait_for_cell("a.mp4")
    d.wait_for_cell("b.mp4")
    d.check("two again after Reload All", len(d.cells) == 2)
    d.wait_until(lambda: _has_picture(d.cell("a.mp4")), "pictures again")
    d.shot("reloaded")


def _skipping_frames(d):
    def asks_for(block):
        return _driver(block).video_driver._player.mpv.vd_lavc_skipframe

    block = d.cell("a.mp4")
    d.check("every frame to begin with", asks_for(block) == "default")

    d.change_setting("player/mpv_skip_frames", True)
    d.wait_until(lambda: asks_for(block) == "nonref", "skips, with no reload")

    d.act(block, "Reload [ALL]")
    d.wait_until(lambda: d.cell("a.mp4") is not block, "reloading")
    block = d.wait_for_cell("a.mp4")
    d.check("a video opened now skips too", asks_for(block) == "nonref")

    d.change_setting("player/mpv_skip_frames", False)
    d.wait_until(lambda: asks_for(block) == "default", "and back, with no reload")

    time_before = block.time
    d.act(block, "Play / Pause")
    d.wait_until(lambda: block.time != time_before, "it still plays")


def _picture_quality(d):
    """Auto goes by the cell's size, which the window this runs in decides: only
    the two that hold whatever the size are checked."""

    def player(block):
        return _driver(block).video_driver._player

    def scales_with(block):
        return player(block).mpv.scale

    block = d.cell("a.mp4")
    # Software MPV scales on the CPU, its own way whatever the setting
    if player(block)._is_software:
        d.note("Software MPV: no picture quality to check")
        return

    own = player(block)._high_quality["scale"]

    d.change_setting("player/mpv_picture_quality", MpvPictureQuality.HIGH)
    d.wait_until(lambda: scales_with(block) == own, "mpv's own, with no reload")

    d.change_setting("player/mpv_picture_quality", MpvPictureQuality.FAST)
    d.wait_until(lambda: scales_with(block) == FAST["scale"], "and the fast way")

    time_before = block.time
    d.wait_until(lambda: block.time != time_before, "it plays on")

    d.change_setting("player/mpv_picture_quality", MpvPictureQuality.AUTO)
