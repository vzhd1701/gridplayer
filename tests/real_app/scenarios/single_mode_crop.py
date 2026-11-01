"""Allow cropping when big: in Single Mode, the video shown big fills the
window where that cuts no more of it than the setting allows, 20% by
default, and is shown whole otherwise. A phone video fills its cell in the
grid, whatever that cuts, and is shown whole once big; a 16:9 one fills the
window big. With Any, in Settings or from the menu, the phone video fills
the window too."""

from gridplayer.params.static import NO_FILL_LIMIT
from gridplayer.settings import Settings
from tests.real_app.scenarios.pixel_shape import _grab, _picture, _picture_box, _ratio

SETTINGS = {"video_defaults/cell_view_mode": "fill"}

# to the pixel or so, on a few hundred
SLACK_PX = 3
SLACK = 0.03


def scenario(d):
    shapes = d.media.shapes
    d.open(shapes / "phone.mp4", shapes / "square.mp4")
    phone = d.wait_for_cell("phone.mp4")
    wide = d.wait_for_cell("square.mp4")
    d.wait_until(lambda: _picture_box(_grab(phone)) is not None, "a picture is on")

    cut = _fill_cut(phone)
    d.check("in the grid, Fill cuts more than 20% of it", cut > 0.2, cut)
    d.wait_until(
        lambda: _is_filled(phone), "in the grid, it fills its cell all the same"
    )
    _picture(d, phone, "grid")

    d.act(phone, "Single Mode ON / OFF")
    d.check("shown big", d.ctx.commands.single_mode_video() is phone)
    d.wait_until(lambda: _is_whole(phone), "big, it is shown whole")
    _picture(d, phone, "big_whole")

    d.act(phone, "Next Video")
    d.check("the 16:9 one shown big", d.ctx.commands.single_mode_video() is wide)
    d.wait_until(lambda: _is_filled(wide), "a 16:9 one big fills the window")

    d.act(wide, "Previous Video")
    d.wait_until(lambda: _is_whole(phone), "the phone one big again, whole")

    _set_crop(d, NO_FILL_LIMIT)
    d.wait_until(lambda: _is_filled(phone), "with Any in Settings, it fills")
    _set_crop(d, 20)
    d.wait_until(lambda: _is_whole(phone), "with 20% in Settings, whole again")

    d.act(phone, f"Crop When Big {NO_FILL_LIMIT}%")
    d.check(
        "Any is ticked in the menu",
        d.ctx.commands.is_single_mode_crop_set_to(NO_FILL_LIMIT),
    )
    d.wait_until(lambda: _is_filled(phone), "with Any from the menu, it fills")
    _picture(d, phone, "big_filled")

    d.act(phone, "Crop When Big 20%")
    d.wait_until(lambda: _is_whole(phone), "with 20% from the menu, whole again")

    d.act(phone, "Single Mode ON / OFF")
    d.wait_until(lambda: _is_filled(phone), "back in the grid, it fills its cell")


def _set_crop(d, value):
    # as the Settings dialog does on OK
    Settings().set("playlist/single_mode_crop", value)
    d.player._managers_inst["settings"].set_single_mode_crop.emit(value)
    d.pump()


def _fill_cut(b):
    """How much of the 9:16 picture Fill cuts in the cell as it is."""

    width, height = b.video_driver.width(), b.video_driver.height()
    fit_x, fit_y = width / 9, height / 16
    return 1 - min(fit_x, fit_y) / max(fit_x, fit_y)


def _is_filled(b):
    image = _grab(b)
    box = _picture_box(image)
    return box is not None and _near(box, (0, image.width(), 0, image.height()))


def _is_whole(b):
    image = _grab(b)
    box = _picture_box(image)
    return (
        box is not None
        and abs(box[3] - box[2] - image.height()) <= SLACK_PX
        and abs(_ratio(box) - 9 / 16) < SLACK
    )


def _near(box, expected):
    return all(abs(a - b) <= SLACK_PX for a, b in zip(box, expected))
