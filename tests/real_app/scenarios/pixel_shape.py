"""Videos whose pixels are not square, as they say: shown, turned and
screenshot the same as one of square pixels, whether VLC says how wide they
are on opening or only once the stream is decoded."""

from PyQt5.QtGui import QImage

from gridplayer.params.static import VideoTransform

SETTINGS = {"video_defaults/aspect": "none"}

# a picture worked out from a frame of other pixels lands a pixel or so off
SLACK_PX = 2


def scenario(d):
    shapes = d.media.shapes

    b = _play(d, shapes / "square.mp4")
    wide = _picture(d, b, "square")
    d.check("the square one is 16:9", _ratio(wide) > 1.7, wide)
    b = _turn(d, b)
    tall = _picture(d, b, "square_turned")
    d.act(b, "Close")

    b = _play(d, shapes / "wide_pixels.mp4")
    _same(d, "wide pixels", _picture(d, b, "wide_pixels"), wide)
    _same_size(d, "its screenshot", _screenshot(d, b), (640, 360))
    b = _turn(d, b)
    _same(d, "wide pixels turned", _picture(d, b, "wide_pixels_turned"), tall)
    d.act(b, "Close")

    b = _play(d, shapes / "wide_pixels.ts")
    d.wait_until(lambda: _track(b).sar is not None, "the stream says its pixels")
    _same(d, "a stream's wide pixels", _picture(d, b, "wide_pixels_ts"), wide)
    d.act(b, "Close")

    b = _play(d, shapes / "phone.mp4")
    _same(d, "wide pixels the file turns", _picture(d, b, "phone"), tall)
    _same_size(d, "its screenshot", _screenshot(d, b), (360, 640))


def _play(d, path):
    d.open(path)
    b = d.wait_for_cell(path.name)
    d.wait_until(lambda: _picture_box(_grab(b)) is not None, "a picture is on show")
    return b


def _turn(d, b):
    d.act(b, "Rotate 90")
    d.wait_until(
        lambda: (
            b.is_video_initialized
            and b.video_params.transform == VideoTransform.ROTATE_90
            and 0 < _ratio(_picture_box(_grab(b))) < 1
        ),
        "the picture is turned",
    )
    return b


def _track(b):
    return b.video_driver.media.cur_video_track


def _grab(b) -> QImage:
    return b.video_driver.grab().toImage()


def _picture(d, b, name):
    """Where the picture is in the cell: (left, right, top, bottom)."""

    box = _picture_box(QImage(str(d.shot(name, b.video_driver))))
    d.note(f"{name}: {box}, sar {_track(b).sar}")
    return box


def _picture_box(image: QImage):
    """The lit part, on a row and a column through the middle."""

    width, height = image.width(), image.height()

    def lit(x, y):
        color = image.pixelColor(x, y)
        return color.red() + color.green() + color.blue() > 90

    xs = [x for x in range(width) if lit(x, height // 2)]
    ys = [y for y in range(height) if lit(width // 2, y)]

    if not xs or not ys:
        return None

    return min(xs), max(xs) + 1, min(ys), max(ys) + 1


def _ratio(box) -> float:
    if box is None:
        return 0.0

    left, right, top, bottom = box
    return (right - left) / (bottom - top)


def _same(d, what, box, expected):
    d.check(
        f"{what} look as square ones do",
        box is not None
        and expected is not None
        and all(abs(a - b) <= SLACK_PX for a, b in zip(box, expected)),
        (box, expected),
    )


def _screenshot(d, b):
    folder = d.out / "screenshots"
    before = set(folder.glob("*")) if folder.is_dir() else set()

    def taken():
        if not folder.is_dir():
            return None
        for path in set(folder.glob("*")) - before:
            image = QImage(str(path))
            if not image.isNull():
                return image.width(), image.height()
        return None

    d.act(b, "Take Screenshot")
    d.wait_until(lambda: taken() is not None, "the screenshot is saved")

    return taken()


def _same_size(d, what, size, expected):
    d.check(f"{what} is {expected[0]}x{expected[1]}", size == expected, size)
