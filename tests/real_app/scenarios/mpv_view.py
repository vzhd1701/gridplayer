"""The picture on the mpv driver: every turn and flip comes out the way round the
VLC drivers have it, on files that say to turn it as well, with a crop and a zoom
going by the picture as shown. A screenshot has all the picture's pixels, however
small its cell. Many cells loaded paused all get their picture. Zooms and sync go
by the picture too, and a paused live stream stays up."""

import subprocess

from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtGui import QColor, QImage

from gridplayer.params.static import VideoAnchor, VideoCellViewMode, VideoTransform
from gridplayer.utils.screenshots import transformed_image
from tests.real_app.scenarios.pixel_shape import _grab

SETTINGS = {
    "player/video_driver": "mpv_hw",
    "video_defaults/cell_view_mode": "fit",
    "video_defaults/initial_state": "paused",
}

CLIP_W, CLIP_H = 640, 360

# what the file says to turn it by, and how to tell ffmpeg, anticlockwise
FILE_TURNS = {
    VideoTransform.ROTATE_90: "270",
    VideoTransform.ROTATE_180: "180",
    VideoTransform.ROTATE_270: "90",
}

# what's in each corner of the clip: the turns and flips only move these about
CORNERS = {
    "top_left": "red",
    "top_right": "green",
    "bottom_left": "blue",
    "bottom_right": "white",
}

# how close a corner's colour has to be, the video having been through a codec
COLOR_SLACK = 110

SMALL_CELLS = 16

LIVE_SECONDS = 30


def scenario(d):
    _turns_and_flips(d)

    _crop_on_a_flip(d)
    _zoom_on_a_flip(d)
    _view_modes_on_a_flip(d)

    _zoom_to_selection(d)
    _zoom_to_cursor(d)
    _sync_view(d)

    _screenshots(d)

    _live_pause(d)


def _corners_clip(d, file_turn=VideoTransform.NONE):
    plain = d.out / "corners.mp4"

    if not plain.exists():
        boxes = ",".join(
            f"drawbox=x={x}:y={y}:w={CLIP_W // 2}:h={CLIP_H // 2}:color={color}:t=fill"
            for (x, y), color in zip(
                (
                    (0, 0),
                    (CLIP_W // 2, 0),
                    (0, CLIP_H // 2),
                    (CLIP_W // 2, CLIP_H // 2),
                ),
                CORNERS.values(),
                strict=True,
            )
        )

        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                f"color=gray:size={CLIP_W}x{CLIP_H}:rate=30:duration=4",
                "-vf", boxes,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(plain),
            ],
            check=True,
        )  # fmt: skip

    if file_turn == VideoTransform.NONE:
        return plain

    turned = d.out / f"corners_{file_turn.name}.mp4"

    if not turned.exists():
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-display_rotation:v:0", FILE_TURNS[file_turn],
                "-i", str(plain), "-c", "copy", str(turned),
            ],
            check=True,
        )  # fmt: skip

    return turned


def _open(d, path):
    d.open(path)

    return d.wait_for_cell(path.name)


def _close(d, block):
    d.act(block, "Close")
    d.wait(0.3)


def _surface(block):
    return block.video_driver.video_surface


def _has_frame(block) -> bool:
    """Whether a frame is on show: mpv drawing into its own window (Direct) has
    one as soon as it says how big the picture is."""

    surface = _surface(block)

    if not hasattr(surface, "has_frame"):
        return block.is_video_initialized

    return surface.has_frame()


def _wait_for_transform(d, block, transform):
    block.set_transform(transform)

    d.wait_until(
        lambda: (
            block.is_video_initialized
            and block.video_params.transform == transform
            and _has_frame(block)
            and _corners_on_show(block) is not None
        ),
        f"it's shown {transform.name}",
    )
    # the frame at its new size
    d.wait(0.3)


def _picture_rect(block) -> QRect | None:
    placement = block.video_driver.view_placement()

    if placement is None:
        return None

    return QRect(*(round(side) for side in placement.target))


def _corners_on_show(block):
    rect = _picture_rect(block)

    if rect is None:
        return None

    return _corners_of(_grab(block), rect)


def _corners_of(image: QImage, rect: QRect):
    """The name of the colour nearest what's in each of the four corners."""

    left, top = rect.left(), rect.top()
    width, height = rect.width(), rect.height()

    spots = {
        "top_left": (left + width // 4, top + height // 4),
        "top_right": (left + width * 3 // 4, top + height // 4),
        "bottom_left": (left + width // 4, top + height * 3 // 4),
        "bottom_right": (left + width * 3 // 4, top + height * 3 // 4),
    }

    return {corner: _nearest(image.pixelColor(*spot)) for corner, spot in spots.items()}


def _nearest(color: QColor) -> str | None:
    def far(name):
        known = QColor(name)
        return (
            abs(known.red() - color.red())
            + abs(known.green() - color.green())
            + abs(known.blue() - color.blue())
        )

    # ffmpeg's green is half lit
    near = {
        name: far("#008000" if name == "green" else name) for name in CORNERS.values()
    }
    best = min(near, key=near.get)

    return best if near[best] < COLOR_SLACK else None


def _reference(transform, file_turn=VideoTransform.NONE):
    """Where the colours should be: the corners as an image, what's picked done to
    the frame as stored, and the file's turn after that, as the VLC drivers have
    it. A flip on a file on its side comes out the other way on screen."""

    image = QImage(2, 2, QImage.Format_RGB32)
    image.setPixelColor(0, 0, QColor("red"))
    image.setPixelColor(1, 0, QColor("green"))
    image.setPixelColor(0, 1, QColor("blue"))
    image.setPixelColor(1, 1, QColor("white"))

    image = transformed_image(image, transform)
    image = transformed_image(image, file_turn)

    def name(x, y):
        return QColor(image.pixelColor(x, y)).name()

    names = {
        "#ff0000": "red",
        "#008000": "green",
        "#00ff00": "green",
        "#0000ff": "blue",
        "#ffffff": "white",
    }

    return {
        "top_left": names[name(0, 0)],
        "top_right": names[name(1, 0)],
        "bottom_left": names[name(0, 1)],
        "bottom_right": names[name(1, 1)],
    }


def _turns_and_flips(d):
    for file_turn in (VideoTransform.NONE, *FILE_TURNS):
        block = _open(d, _corners_clip(d, file_turn))

        # before any transform is asked for, which opens it again with its track
        # known: the software renderer turns it by a filter set as it preloads
        d.wait_until(
            lambda block=block: (
                _has_frame(block) and _corners_on_show(block) is not None
            ),
            "it's shown",
        )
        d.wait(0.3)
        d.check(
            f"file {file_turn.name}: as first opened",
            _corners_on_show(block) == _reference(VideoTransform.NONE, file_turn),
            _corners_on_show(block),
        )

        for transform in (
            VideoTransform.NONE,
            VideoTransform.ROTATE_90,
            VideoTransform.ROTATE_180,
            VideoTransform.ROTATE_270,
            VideoTransform.HFLIP,
            VideoTransform.VFLIP,
            VideoTransform.TRANSPOSE,
            VideoTransform.ANTITRANSPOSE,
        ):
            what = f"file {file_turn.name}, {transform.name}"
            expected = _reference(transform, file_turn)

            _wait_for_transform(d, block, transform)

            rect = _picture_rect(block)
            is_tall = (transform in _SIDEWAYS) != (file_turn in _SIDEWAYS)

            d.check(
                f"{what}: the shape", (rect.height() > rect.width()) == is_tall, rect
            )
            d.check(
                f"{what}: the colours",
                _corners_on_show(block) == expected,
                (_corners_on_show(block), expected),
            )

            image = _take_screenshot(d, block)
            whole = QRect(0, 0, image.width(), image.height())

            d.check(
                f"{what}: the screenshot",
                _corners_of(image, whole) == expected,
                (_corners_of(image, whole), expected),
            )

        _close(d, block)


_SIDEWAYS = {
    VideoTransform.ROTATE_90,
    VideoTransform.ROTATE_270,
    VideoTransform.TRANSPOSE,
    VideoTransform.ANTITRANSPOSE,
}


def _crop_on_a_flip(d):
    block = _open(d, _corners_clip(d))

    _wait_for_transform(d, block, VideoTransform.HFLIP)

    # the left half of the picture as shown, which holds the clip's right half
    block.view.crop(CLIP_W // 2, 0, 0, 0)

    d.wait(0.3)

    colors = _corners_on_show(block)

    d.check(
        "a crop on a flip goes by the picture as shown",
        set(colors.values()) == {"red", "blue"},
        colors,
    )

    _close(d, block)


def _zoom_on_a_flip(d):
    block = _open(d, _corners_clip(d))

    _wait_for_transform(d, block, VideoTransform.VFLIP)

    rect = _picture_rect(block)
    # what's top left as shown is the clip's bottom left
    part = QRect(
        rect.left() + rect.width() // 10,
        rect.top() + rect.height() // 10,
        rect.width() // 4,
        rect.height() // 4,
    )
    block.view.zoom_to_selection(part.translated(block.video_driver.pos()))
    d.wait(0.5)

    colors = _corners_on_show(block)

    d.check(
        "a zoom on a flip goes by the picture as shown",
        set(colors.values()) == {"blue"},
        colors,
    )

    _close(d, block)


def _view_modes_on_a_flip(d):
    """On a picture turned and flipped: tall, in a wide cell, with red and blue on
    top and green and white below it, red and green on its left."""

    block = _open(d, _corners_clip(d))

    _wait_for_transform(d, block, VideoTransform.TRANSPOSE)

    whole = {
        "top_left": "red",
        "top_right": "blue",
        "bottom_left": "green",
        "bottom_right": "white",
    }

    def shown(what, expected):
        d.wait(0.3)
        colors = _corners_on_show(block)
        d.check(what, colors == expected, colors)

    rect = _picture_rect(block)
    d.check(
        "Fit: narrower than the cell", rect.width() < block.video_driver.width(), rect
    )
    d.check(
        "with black beside it",
        _nearest(_grab(block).pixelColor(rect.left() // 2, rect.height() // 2)) is None
        and _grab(block).pixelColor(rect.left() // 2, rect.height() // 2).value() < 30,
    )
    shown("Fit: all of it", whole)

    block.view.set_anchor(VideoAnchor.LEFT)
    d.wait(0.3)
    d.check("Fit, anchored left: against the left", _picture_rect(block).left() == 0)
    shown("and still all of it", whole)
    block.view.set_anchor(VideoAnchor.CENTER)

    block.view.set_shift_past_edges(True)
    block.view.shift_by(100, 0)
    shown(
        "past the edges: on its way off the right, its left half is left",
        {
            "top_left": "red",
            "top_right": "red",
            "bottom_left": "green",
            "bottom_right": "green",
        },
    )
    block.view.shift_reset()
    block.view.set_shift_past_edges(False)

    block.view.shift_by(100, 0)
    d.wait(0.3)
    d.check(
        "not past the edges: stays where all of it is on show",
        _picture_rect(block).right() < block.video_driver.width(),
        _picture_rect(block),
    )
    block.view.shift_reset()

    block.view.set_cell_view_mode(VideoCellViewMode.STRETCH)
    d.wait(0.3)
    d.check(
        "Stretch: the whole cell",
        _picture_rect(block).width() == block.video_driver.width(),
        _picture_rect(block),
    )
    shown("and all of the picture", whole)

    block.view.set_cell_view_mode(VideoCellViewMode.FILL)
    shown("Fill: the middle has a bit of all four", whole)

    block.view.set_anchor(VideoAnchor.TOP)
    shown(
        "Fill, anchored to the top: only the top",
        {
            "top_left": "red",
            "top_right": "blue",
            "bottom_left": "red",
            "bottom_right": "blue",
        },
    )

    block.view.set_anchor(VideoAnchor.BOTTOM)
    shown(
        "Fill, anchored to the bottom: only the bottom",
        {
            "top_left": "green",
            "top_right": "white",
            "bottom_left": "green",
            "bottom_right": "white",
        },
    )

    _close(d, block)


def _zoom_to_selection(d):
    block = _open(d, _corners_clip(d))
    d.wait_until(lambda: _picture_rect(block) is not None, "it's placed")

    rect = _picture_rect(block)
    part = QRect(
        rect.left() + rect.width() * 6 // 10,
        rect.top() + rect.height() * 6 // 10,
        rect.width() // 4,
        rect.height() // 4,
    )

    block.view.zoom_to_selection(part.translated(block.video_driver.pos()))
    d.wait(0.5)

    colors = _corners_on_show(block)

    d.check(
        "zoom to selection shows what was selected",
        set(colors.values()) == {"white"},
        colors,
    )

    _close(d, block)


def _zoom_to_cursor(d):
    block = _open(d, _corners_clip(d))
    d.wait_until(lambda: _picture_rect(block) is not None, "it's placed")

    d.act(block, "Zoom to Cursor")

    rect = _picture_rect(block)
    # over the green, top right, as a context menu would have opened
    spot = QPoint(rect.left() + rect.width() * 7 // 8, rect.top() + rect.height() // 8)

    block._ctx.context_menu_pos = block.video_driver.mapToGlobal(spot)
    for _ in range(12):
        d.act(block, "Zoom In")
    block._ctx.context_menu_pos = None
    d.wait(0.5)

    colors = _corners_on_show(block)

    d.check(
        "zoom to cursor stays on what's under it",
        colors["top_right"] == "green" and "white" not in colors.values(),
        colors,
    )

    d.act(block, "Zoom Reset")
    d.act(block, "Zoom to Cursor")

    _close(d, block)


def _sync_view(d):
    first = _open(d, _corners_clip(d))
    d.wait_until(lambda: _picture_rect(first) is not None, "the first is placed")

    d.open(_corners_clip(d))
    d.wait_until(lambda: len(d.cells) == 2, "both are there")
    second = next(cell for cell in d.cells if cell is not first)
    d.wait_until(lambda: _picture_rect(second) is not None, "the second is placed")

    rect = _picture_rect(first)
    part = QRect(
        rect.left() + rect.width() // 10,
        rect.top() + rect.height() * 6 // 10,
        rect.width() // 4,
        rect.height() // 4,
    )

    first.view.zoom_to_selection(part.translated(first.video_driver.pos()))
    d.wait(0.3)

    first.view.sync_others()
    d.wait(0.5)

    colors = _corners_on_show(second)

    d.check(
        "the other shows the same part of its picture",
        set(colors.values()) == {"blue"},
        colors,
    )

    _close(d, first)
    _close(d, second)


def _detailed_clip(d):
    path = d.out / "stripes.mp4"

    if not path.exists():
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                "color=gray:size=1280x720:rate=30:duration=4",
                "-vf", "geq=lum='if(mod(floor(X/2),2),220,30)':cb=128:cr=128",
                "-c:v", "libx264", "-qp", "4", "-pix_fmt", "yuv420p", str(path),
            ],
            check=True,
        )  # fmt: skip

    return path


def _sharpness(image: QImage) -> float:
    """How much next pixels differ, along a row out of the middle of the picture."""

    row = image.height() // 2
    width = image.width()

    total = sum(
        abs(image.pixelColor(x, row).red() - image.pixelColor(x + 1, row).red())
        for x in range(width // 4, width * 3 // 4)
    )

    return total / (width // 2)


def _take_screenshot(d, block) -> QImage:
    folder = d.out / "screenshots"
    before = set(folder.glob("*")) if folder.is_dir() else set()

    found = []

    def saved():
        for path in set(folder.glob("*")) - before if folder.is_dir() else ():
            image = QImage(str(path))
            if not image.isNull():
                found.append(image)
                return True
        return False

    d.act(block, "Take Screenshot")
    d.wait_until(saved, "the screenshot is saved")

    return found[0]


def _screenshots(d):
    path = _detailed_clip(d)

    # Small cells, each with a frame much smaller than the picture. Opened at
    # once they keep the render thread past what mpv waits for a frame, which
    # loaded paused is the only one coming.
    for _ in range(SMALL_CELLS):
        d.open(path)

    d.wait_until(
        lambda: (
            len(d.cells) == SMALL_CELLS
            and all(cell.is_video_initialized for cell in d.cells)
        ),
        "they're all in",
        60,
    )

    block = d.cells[0]
    surface = _surface(block)

    d.wait_until(
        lambda: 0 < surface.frame_size()[0] < 1280 / 2,
        "its frame is what the cell needs",
        5,
    )
    small = surface.frame_size()
    d.note(f"the frame in a small cell: {small}")

    for is_playing in (False, True):
        what = "playing" if is_playing else "paused"

        if is_playing:
            d.act(block, "Play / Pause")
            d.wait_until(lambda: not block.video_params.is_paused, "it plays")

        image = _take_screenshot(d, block)

        d.check(
            f"{what}: a screenshot is the picture's own size",
            (image.width(), image.height()) == (1280, 720),
            (image.width(), image.height()),
        )
        d.check(
            f"{what}: and has its detail",
            _sharpness(image) > 60,
            _sharpness(image),
        )
        # to within a pixel: the first size can be from before the cell had settled
        d.wait_until(
            lambda s=small: (
                abs(surface.frame_size()[0] - s[0]) <= 1
                and abs(surface.frame_size()[1] - s[1]) <= 1
            ),
            f"{what}: the frame goes back",
            5,
        )
        d.note(f"{what}: the frame is back at {surface.frame_size()}")

    d.act(block, "Play / Pause")

    # two at once both get theirs
    folder = d.out / "screenshots"
    before = set(folder.glob("*"))
    d.act(block, "Take Screenshot")
    d.act(block, "Take Screenshot")
    d.wait_until(lambda: len(set(folder.glob("*")) - before) == 2, "two are saved", 5)

    for cell in list(d.cells):
        _close(d, cell)

    # turned and flipped, a screenshot is as shown
    corners = _open(d, _corners_clip(d))

    for transform in (VideoTransform.ROTATE_90, VideoTransform.HFLIP):
        _wait_for_transform(d, corners, transform)

        image = _take_screenshot(d, corners)
        whole = QRect(0, 0, image.width(), image.height())

        d.check(
            f"{transform.name}: its screenshot is as shown",
            _corners_of(image, whole) == _reference(transform),
            _corners_of(image, whole),
        )

    # with a crop, what's left of what's shown
    corners.view.crop(CLIP_W // 2, 0, 0, 0)

    d.wait(0.3)

    image = _take_screenshot(d, corners)
    colors = _corners_of(image, QRect(0, 0, image.width(), image.height()))

    d.check(
        "a crop on a flip: its screenshot is what's left",
        set(colors.values()) == {"red", "blue"},
        colors,
    )

    _close(d, corners)


def _no_length_clip(d):
    """Plays as live does: bare H.264 has no length to tell, and moves all the time.

    A stream through the app's proxy doesn't do yet: mpv gives one a length, for
    Stage 9 of the plan.
    """

    path = d.out / "no_length.h264"

    if not path.exists():
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                f"testsrc2=size=320x180:rate=25:duration={LIVE_SECONDS}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "h264", str(path),
            ],
            check=True,
        )  # fmt: skip

    return path


def _live_pause(d):
    block = _open(d, _no_length_clip(d))

    d.wait_until(lambda: block.is_live, "it's live")

    if block.video_params.is_paused:
        d.act(block, "Play / Pause")

    d.wait_until(lambda: not block.video_params.is_paused, "it plays")
    d.wait(0.5)

    d.act(block, "Play / Pause")
    d.wait_until(lambda: block.video_params.is_paused, "it pauses")
    d.wait(0.3)

    picture = _grab(block)

    d.check("the last frame stays up", _has_frame(block))
    d.check(
        "nothing's put over it",
        not block.video_driver.pause_snapshot.isVisible(),
    )

    d.wait(1.5)
    d.check("and doesn't change", _grab(block) == picture)

    d.shot("live_paused", block)

    d.act(block, "Play / Pause")
    d.wait_until(lambda: not block.video_params.is_paused, "it plays again")
    d.wait_until(lambda: _grab(block) != picture, "and moves on", 5)

    _close(d, block)
