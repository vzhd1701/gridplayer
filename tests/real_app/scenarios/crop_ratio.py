"""A crop shape picked from the menu is the shape the picture is cut to, as
it is shown: turned by the file, of wide pixels, or in the aspect ratio
picked. A nudge goes on from the margins that cut it so, and Off takes all
of it back. Its screenshot comes out the same shape."""

from tests.real_app.scenarios.aspect_ratio import _as_number, _shaped, _size_ratio
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
    _cut(d, b, "4:3")
    _shaped(d, "16:9 cut to 4:3", _picture(d, b, "square_4_3"), 4 / 3)
    _shaped(d, "its screenshot", _size_ratio(_screenshot(d, b)), 4 / 3)

    d.act(b, "Crop Top +")
    d.check(
        "a nudge is margins from then on",
        b.video_params.crop_ratio == "" and b.video_params.crop == (80, 1, 80, 0),
        (b.video_params.crop_ratio, b.video_params.crop),
    )

    d.act(b, "Crop Reset")
    d.check("Off cuts nothing", not any(b.video_params.crop))
    d.wait_until(
        lambda: abs(_ratio(_picture_box(_grab(b))) - 16 / 9) < SLACK, "all of it"
    )

    d.act(b, "Aspect Ratio 4:3")
    _cut(d, b, "16:9")
    _shaped(d, "shown 4:3, cut to 16:9", _picture(d, b, "square_4_3_16_9"), 16 / 9)
    d.act(b, "Close")

    b = _play(d, shapes / "phone.mp4")
    _cut(d, b, "1:1")
    _shaped(d, "a file turned cut to 1:1", _picture(d, b, "phone_1_1"), 1)
    d.act(b, "Close")

    b = _play(d, shapes / "wide_pixels.ts")
    d.wait_until(
        lambda: b.video_driver.media.cur_video_track.sar is not None,
        "the stream says its pixels",
    )
    _cut(d, b, "2.35:1")
    _shaped(d, "wide pixels cut to 2.35:1", _picture(d, b, "wide_pixels_2_35"), 2.35)


def _play(d, path):
    d.open(path)
    b = d.wait_for_cell(path.name)
    d.wait_until(lambda: _picture_box(_grab(b)) is not None, "a picture is on show")
    return b


def _cut(d, b, ratio):
    d.act(b, f"Crop {ratio}")
    d.check(f"{ratio} is ticked", b.video_params.crop_ratio == ratio)
    d.wait_until(
        lambda: abs(_ratio(_picture_box(_grab(b))) - _as_number(ratio)) < SLACK,
        f"the picture is {ratio}",
    )
