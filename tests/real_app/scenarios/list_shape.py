"""The aspect ratio and the crop shape a channel list says for a channel
show it so, where none is picked, and are never kept as picked. One picked
goes on to the list's next video, and Default lets the list's back."""

import shutil

from tests.real_app.scenarios.aspect_ratio import _as_number, _shaped
from tests.real_app.scenarios.pixel_shape import _grab, _picture, _picture_box, _ratio

SETTINGS = {"video_defaults/cell_view_mode": "fit"}

# a picture a few hundred pixels across, to the pixel or so
SLACK = 0.03


def scenario(d):
    # the same 16:9 clip three times over, for each to be a video of its own
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        shutil.copy(d.media.shapes / "square.mp4", d.out / name)

    channels = d.out / "channels.m3u"
    channels.write_text(
        "#EXTM3U\n"
        "#EXTINF:-1,Shown 4:3\n"
        "#EXTVLCOPT:aspect-ratio=4:3\n"
        "a.mp4\n"
        "#EXTINF:-1,Cut 1:1\n"
        "#EXTVLCOPT:crop=1:1\n"
        "b.mp4\n"
        "#EXTINF:-1,As it is\n"
        "c.mp4\n",
        encoding="utf-8",
    )

    d.open(channels)
    b = d.wait_for_cell("channels.m3u")
    _shown(d, b, "4:3", "the list's 4:3")
    d.check("not kept as picked", b.video_params.aspect_ratio == "")
    d.check(
        "Default says the list's",
        _title(d, b, "active_aspect_ratio_default_title") == "4:3 (list)",
    )

    _next(d, b, "b.mp4")
    _shown(d, b, "1:1", "the list's 1:1 crop")
    d.check("not kept as picked", b.video_params.crop_ratio == "")
    d.check(
        "Off says the list's", _title(d, b, "active_crop_off_title") == "1:1 (list)"
    )

    d.act(b, "Crop Top +")
    d.check(
        "a nudge goes on from the list's shape",
        b.video_params.crop_ratio == "" and b.video_params.crop.Left > 0,
        b.video_params.crop,
    )
    d.act(b, "Crop Reset")
    _shown(d, b, "1:1", "Off lets the list's back")

    _next(d, b, "c.mp4")
    _shown(d, b, "16:9", "nothing said, its own")

    d.act(b, "Aspect Ratio 16:10")
    _shown(d, b, "16:10", "picked")
    _next(d, b, "a.mp4")
    _shown(d, b, "16:10", "the pick over the list's 4:3")

    d.act(b, "Aspect Ratio Default")
    _shown(d, b, "4:3", "Default lets the list's back")
    d.shot("list_4_3", b.video_driver)


def _next(d, b, name):
    d.act(b, "Play Next File")
    d.wait_until(lambda: b.video_params.uri.name == name, f"on to {name}")
    d.wait_until(
        lambda: b.is_playable and _picture_box(_grab(b)) is not None,
        f"{name} plays",
    )


def _shown(d, b, ratio, what):
    d.wait_until(
        lambda: abs(_ratio(_picture_box(_grab(b))) - _as_number(ratio)) < SLACK,
        f"the picture is {ratio}",
    )
    _shaped(
        d, what, _picture(d, b, f"shown_{ratio.replace(':', '_')}"), _as_number(ratio)
    )


def _title(d, b, getter):
    d.ctx.active_block = b
    return d.ctx.commands.resolve(getter)()
