import math
from dataclasses import dataclass
from fractions import Fraction

from gridplayer.params.static import (
    ROTATION_TRANSFORMS,
    SHIFT_STEP,
    VideoAnchor,
    VideoAspect,
    VideoCrop,
    VideoShift,
    VideoTransform,
    ViewParams,
)

# VLC converts the aspect override to a SAR with 32-bit unsigned math
# (sar = override_num * source_height : override_den * source_width, with
# source dims capped at 8192). Keep both terms of the reduced fraction
# at or below 2^19 - 1 so that product cannot overflow uint32; anything
# beyond is a degenerate stretch anyway.
_OVERRIDE_RATIO_LIMIT = (1 << 19) - 1

# What float error a shift worked out to lie on a whole pixel can carry.
_ROUNDING_SLACK = 1e-6

# Where the picture sits in the room it has to move in, per axis: 0 against
# the left or top edge, 1 against the right or bottom one.
_ANCHOR_POSITIONS = {
    VideoAnchor.CENTER: (0.5, 0.5),
    VideoAnchor.TOP: (0.5, 0.0),
    VideoAnchor.BOTTOM: (0.5, 1.0),
    VideoAnchor.LEFT: (0.0, 0.5),
    VideoAnchor.RIGHT: (1.0, 0.5),
    VideoAnchor.TOP_LEFT: (0.0, 0.0),
    VideoAnchor.TOP_RIGHT: (1.0, 0.0),
    VideoAnchor.BOTTOM_LEFT: (0.0, 1.0),
    VideoAnchor.BOTTOM_RIGHT: (1.0, 1.0),
}

Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class ViewPlacement:
    """What of a frame is on show, and where in the pane it goes.

    Both are (x, y, width, height). The source is in frame pixels, the
    target in pane pixels: the picture clipped to the pane, the source
    being exactly the part of the frame that lands in it.
    """

    source: Rect
    target: Rect


def calc_crop_region(
    video_dimensions: tuple[int, int], crop: VideoCrop
) -> tuple[int, int, int, int]:
    """Cropped region as (x, y, width, height), clamped to the video bounds."""
    vid_x, vid_y = video_dimensions

    x = min(crop.Left, max(vid_x - 1, 0))
    y = min(crop.Top, max(vid_y - 1, 0))

    width = max(vid_x - crop.Left - crop.Right, 1)
    height = max(vid_y - crop.Top - crop.Bottom, 1)

    return x, y, width, height


def calc_view_placement(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    is_beyond_edges: bool = False,
) -> ViewPlacement | None:
    """Where a frame goes in a pane: the one sum every driver draws from.

    The frame is what the video output gets, after the transform. The
    crop and the shift are in its pixels, the ones VLC crops in, and in
    the orientation the picture is shown in.

    Fit covers the pane, None fits inside it and Stretch fills it exactly;
    the zoom then scales that about the anchor. On each axis the picture
    sits at the anchor's place in the room between it and the pane, which
    picks what is cut off where it is bigger than the pane and where it
    stands where it is smaller, and the shift moves it on from there.
    Unless it may go past the edges, it is held where no black shows
    beside a picture bigger than the pane and none of a smaller one is cut.

    None when there is nothing to place: no frame, no pane, or a picture
    moved clear of the pane.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform)

    if fit is None:
        return None

    pane_w, pane_h = pane_size
    anchor_x, anchor_y = _ANCHOR_POSITIONS[view.anchor]

    left = _place(pane_w, fit.picture_w, anchor_x, view.shift.X * fit.per_x)
    top = _place(pane_h, fit.picture_h, anchor_y, view.shift.Y * fit.per_y)

    if not is_beyond_edges:
        left = _hold(left, pane_w - fit.picture_w)
        top = _hold(top, pane_h - fit.picture_h)

    target_x, target_w = _clip(left, fit.picture_w, pane_w)
    target_y, target_h = _clip(top, fit.picture_h, pane_h)

    if target_w <= 0 or target_h <= 0:
        return None

    return ViewPlacement(
        source=(
            fit.x + (target_x - left) / fit.per_x,
            fit.y + (target_y - top) / fit.per_y,
            target_w / fit.per_x,
            target_h / fit.per_y,
        ),
        target=(target_x, target_y, target_w, target_h),
    )


def calc_view_shift(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
) -> VideoShift:
    """The shift the picture really stands at, in whole frame pixels.

    What was asked for where it is within the edges, the nearest shift
    that is where it would take the picture past them. A move goes from
    here, not from wherever past an edge the picture was held at, which
    would take presses to come back from without anything moving.

    The shift as it is where there is nothing to work it out from.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform)

    if fit is None:
        return view.shift

    pane_w, pane_h = pane_size
    anchor_x, anchor_y = _ANCHOR_POSITIONS[view.anchor]

    return VideoShift(
        _held_shift(view.shift.X, pane_w - fit.picture_w, anchor_x, fit.per_x),
        _held_shift(view.shift.Y, pane_h - fit.picture_h, anchor_y, fit.per_y),
    )


def calc_view_step(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
) -> tuple[int, int]:
    """What one move right and one move down add to the shift.

    A move goes the way it says. Where the picture is bigger than the pane
    that is looking further that way, so the picture slides the other way
    to bring more of that side in; where it is smaller, it is the picture
    that goes that way, across the room it has in the pane.

    A share of the part on show, so a press goes as far on screen however
    big the video is and however far it is zoomed. (0, 0) where there is
    nothing to work it out from.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform)
    placement = calc_view_placement(frame_size, pane_size, view, transform)

    if fit is None or placement is None:
        return 0, 0

    pane_w, pane_h = pane_size
    _, _, width, height = placement.source

    return (
        _step(width, fit.picture_w > pane_w + _ROUNDING_SLACK),
        _step(height, fit.picture_h > pane_h + _ROUNDING_SLACK),
    )


def calc_view_borders(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
) -> VideoCrop:
    """What the view cuts off each side of the frame, in whole frame pixels.

    The crop the hardware drivers have VLC make, zoom and all, so what
    their snapshot keeps; frames drawn here get screenshots cut the same.
    Just the user crop where there is nothing to work it out from.
    """
    placement = calc_view_placement(frame_size, pane_size, view, transform)

    if placement is None:
        return view.crop

    return _source_borders(frame_size, placement.source)


def calc_view_geometry(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
) -> tuple[str, str]:
    """Aspect override and crop geometry strings to pass to libvlc.

    VLC is told to crop the frame to exactly the part on show, zoom
    included, and to give that part the shape it has on screen. Left to
    fill its window it then lands where calc_view_placement puts it, as
    long as that is the middle of the pane.
    """
    placement = calc_view_placement(frame_size, pane_size, view, transform)

    if placement is None:
        # No usable geometry; show the user-cropped region letterboxed.
        return _format_view(_display_size(frame_size, transform), view.crop)

    borders = _source_borders(frame_size, placement.source)
    _, _, region_w, region_h = calc_crop_region(frame_size, borders)
    _, _, target_w, target_h = placement.target

    override = _shape_override(
        max(round(target_w), 1),
        max(round(target_h), 1),
        frame_size,
        (region_w, region_h),
    )

    return _format_view(override, borders)


def _frame_pixel_shape(
    frame_size: tuple[int, int], transform: VideoTransform | None
) -> tuple[float, float]:
    """How wide and how tall a frame pixel is on screen, relatively.

    Square, but under a rotation VLC 3 keeps the frame at its unrotated
    size and squeezes the turned picture into it: a 1920x1080 frame then
    holds a picture 1080 wide and 1920 tall.
    """
    if transform not in ROTATION_TRANSFORMS:
        return 1.0, 1.0

    frame_w, frame_h = frame_size

    return frame_h / frame_w, frame_w / frame_h


def _display_size(
    frame_size: tuple[int, int], transform: VideoTransform | None
) -> tuple[int, int]:
    if transform in ROTATION_TRANSFORMS:
        return frame_size[1], frame_size[0]

    return frame_size


@dataclass(frozen=True)
class _Fit:
    """A frame sized for a pane: the region on show and its scale."""

    x: int
    y: int
    region_w: int
    region_h: int
    # pane pixels per frame pixel
    per_x: float
    per_y: float

    @property
    def picture_w(self) -> float:
        return self.region_w * self.per_x

    @property
    def picture_h(self) -> float:
        return self.region_h * self.per_y

    @classmethod
    def of(
        cls,
        frame_size: tuple[int, int],
        pane_size: tuple[int, int],
        view: ViewParams,
        transform: VideoTransform | None,
    ) -> "_Fit | None":
        frame_w, frame_h = frame_size
        pane_w, pane_h = pane_size

        if min(frame_w, frame_h, pane_w, pane_h, view.scale) <= 0:
            return None

        x, y, region_w, region_h = calc_crop_region(frame_size, view.crop)
        unit_x, unit_y = _frame_pixel_shape(frame_size, transform)

        fit_x = pane_w / (region_w * unit_x)
        fit_y = pane_h / (region_h * unit_y)

        if view.aspect == VideoAspect.FIT:
            fit_x = fit_y = max(fit_x, fit_y)
        elif view.aspect == VideoAspect.NONE:
            fit_x = fit_y = min(fit_x, fit_y)

        return cls(
            x=x,
            y=y,
            region_w=region_w,
            region_h=region_h,
            per_x=fit_x * unit_x * view.scale,
            per_y=fit_y * unit_y * view.scale,
        )


def _place(pane: float, picture: float, anchor: float, shift: float) -> float:
    return (pane - picture) * anchor + shift


def _hold(position: float, room: float) -> float:
    """Keep a picture from leaving black beside it, or being cut itself."""

    return min(max(position, min(room, 0)), max(room, 0))


def _step(shown: float, is_bigger_than_pane: bool) -> int:
    step = max(round(shown * SHIFT_STEP), 1)

    return -step if is_bigger_than_pane else step


def _held_shift(shift: int, room: float, anchor: float, per: float) -> int:
    # 0 is always within: no shift leaves the picture at the anchor's place
    # in the room, which is inside it
    lowest = math.ceil((min(room, 0) - room * anchor) / per - _ROUNDING_SLACK)
    highest = math.floor((max(room, 0) - room * anchor) / per + _ROUNDING_SLACK)

    return min(max(shift, lowest), highest)


def _clip(start: float, length: float, pane: float) -> tuple[float, float]:
    clipped_start = max(start, 0)

    return clipped_start, min(start + length, pane) - clipped_start


def _source_borders(frame_size: tuple[int, int], source: Rect) -> VideoCrop:
    """The borders that leave the source, rounded to whole pixels.

    At least one pixel is left each way, which a tiny region in a wildly
    mismatched pane could otherwise round away, sending VLC a 0-size crop.
    """
    frame_w, frame_h = frame_size
    x, y, width, height = source

    left = min(max(round(x), 0), frame_w - 1)
    top = min(max(round(y), 0), frame_h - 1)
    right = min(max(frame_w - round(x + width), 0), frame_w - left - 1)
    bottom = min(max(frame_h - round(y + height), 0), frame_h - top - 1)

    return VideoCrop(left, top, right, bottom)


def _format_view(override: tuple[int, int], borders: VideoCrop) -> tuple[str, str]:
    return (
        f"{override[0]}:{override[1]}",
        f"+{borders.Left}+{borders.Top}+{borders.Right}+{borders.Bottom}",
    )


def _shape_override(
    shape_w: int,
    shape_h: int,
    frame_size: tuple[int, int],
    region_size: tuple[int, int],
) -> tuple[int, int]:
    # VLC displays the visible region with DAR = region_x * sar_num :
    # region_y * sar_den, where the SAR comes from the override (A) via the
    # pre-crop source dims: sar = A_num * vid_y : A_den * vid_x. Solving
    # DAR == shape_w:shape_h for A gives the compensation below; without a
    # crop it reduces to the plain shape ratio.
    vid_x, vid_y = frame_size
    region_x, region_y = region_size

    override = Fraction(shape_w * region_y * vid_x, shape_h * region_x * vid_y)

    # limit_denominator only bounds the denominator; above 1 it is the
    # numerator that has to be kept down, so bound the inverse instead
    if override >= 1:
        inverse = (1 / override).limit_denominator(_OVERRIDE_RATIO_LIMIT)
        override = 1 / inverse if inverse else inverse
    else:
        override = override.limit_denominator(_OVERRIDE_RATIO_LIMIT)

    if not override:
        # Degenerate shape; "0:0" resets the override (native aspect).
        return 0, 0

    return override.numerator, override.denominator
