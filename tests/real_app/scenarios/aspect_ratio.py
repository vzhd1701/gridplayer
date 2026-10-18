"""An aspect ratio picked from the menu is the shape the picture is shown
in, as it is shown: turned by hand or by the file, and whatever shape the
video's own pixels are. Its screenshot comes out the same shape."""

from gridplayer.params.static import VideoTransform
from tests.real_app.scenarios.pixel_shape import (
    _grab,
    _picture,
    _picture_box,
    _ratio,
    _screenshot,
)

SETTINGS = {"video_defaults/cell_view_mode": "fit"}

# a picture a few hundred pixels across, to the pixel or so
SLACK = 0.03


def scenario(d):
    shapes = d.media.shapes

    b = _play(d, shapes / "square.mp4")
    _pick(d, b, "4:3")
    _shaped(d, "16:9 shown 4:3", _picture(d, b, "square_4_3"), 4 / 3)
    _shaped(d, "its screenshot", _size_ratio(_screenshot(d, b)), 4 / 3)

    d.act(b, "Rotate 90")
    d.wait_until(
        lambda: (
            b.is_video_initialized
            and b.video_driver._transform == VideoTransform.ROTATE_90
            and _picture_box(_grab(b)) is not None
        ),
        "the picture is turned",
    )
    _shaped(d, "turned, still 4:3", _picture(d, b, "square_turned_4_3"), 4 / 3)

    _pick(d, b, "")
    d.wait_until(lambda: 0 < _ratio(_picture_box(_grab(b))) < 1, "back to its own")
    _shaped(d, "Default, its own again", _picture(d, b, "square_turned"), 9 / 16)
    d.act(b, "Close")

    b = _play(d, shapes / "phone.mp4")
    _pick(d, b, "16:9")
    _shaped(d, "a file turned shown 16:9", _picture(d, b, "phone_16_9"), 16 / 9)
    _shaped(d, "its screenshot", _size_ratio(_screenshot(d, b)), 16 / 9)
    d.act(b, "Close")

    b = _play(d, shapes / "wide_pixels.ts")
    d.wait_until(
        lambda: b.video_driver.media.cur_video_track.sar is not None,
        "the stream says its pixels",
    )
    _pick(d, b, "1:1")
    _shaped(d, "wide pixels shown 1:1", _picture(d, b, "wide_pixels_1_1"), 1)


def _play(d, path):
    d.open(path)
    b = d.wait_for_cell(path.name)
    d.wait_until(lambda: _picture_box(_grab(b)) is not None, "a picture is on show")
    return b


def _pick(d, b, ratio):
    d.act(b, f"Aspect Ratio {ratio or 'Default'}")
    d.check(f"{ratio or 'Default'} is ticked", b.video_params.aspect_ratio == ratio)

    if ratio:
        d.wait_until(
            lambda: abs(_ratio(_picture_box(_grab(b))) - _as_number(ratio)) < SLACK,
            f"the picture is {ratio}",
        )


def _as_number(ratio):
    width, height = ratio.split(":")
    return float(width) / float(height)


def _size_ratio(size):
    if size is None:
        return None

    width, height = size
    return 0, width, 0, height


def _shaped(d, what, box, ratio):
    d.check(
        f"{what}",
        box is not None and abs(_ratio(box) - ratio) < SLACK,
        (box, round(_ratio(box), 3), round(ratio, 3)),
    )
