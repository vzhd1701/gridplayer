import math
from dataclasses import dataclass
from fractions import Fraction
from typing import NamedTuple

from gridplayer.params.static import (
    MAX_SCALE,
    ROTATION_TRANSFORMS,
    SHIFT_STEP,
    VideoAnchor,
    VideoAspect,
    VideoCrop,
    VideoShift,
    VideoTransform,
    ViewParams,
)

# VLC 3 turns the aspect override into a sample aspect ratio, and places
# the picture with it, partly in 32-bit unsigned math: the SAR comes out
# as override_num * frame_height : override_den * frame_width, and then,
# reduced, is multiplied by the cropped width and height. Past 2^32 those
# wrap round, and the picture is placed at some other height altogether,
# a stretch that comes and goes with the crop. No product may get there,
# with a bit to spare.
_VLC_UINT_LIMIT = (1 << 31) - 1

# What float error a shift worked out to lie on a whole pixel can carry.
_ROUNDING_SLACK = 1e-6

# How big a picture VLC is asked to draw whole, see calc_whole_placement.
# Its window's buffer is the picture's size: no side past what Direct3D 11
# allows one, less a hidden margin, and no more pixels than a couple of
# such buffers can be spared for, a zoomed-in 4K picture being past both.
_WHOLE_MAX_SIDE = 16000
_WHOLE_MAX_PIXELS = 32_000_000

_NO_CROP = VideoCrop(0, 0, 0, 0)

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
    *,
    pixel_aspect: float = 1.0,
) -> ViewPlacement | None:
    """Where a frame goes in a pane: the one sum every driver draws from.

    The frame is what the video output gets, after the transform. The
    crop and the shift are in its pixels, the ones VLC crops in, and in
    the orientation the picture is shown in. Its pixels need not be
    square: pixel_aspect is how wide one is shown for its height, before
    the transform (see calc_frame_pixel_shape).

    Fit covers the pane, None fits inside it and Stretch fills it exactly;
    the zoom then scales that about the anchor. On each axis the picture
    sits at the anchor's place in the room between it and the pane, which
    picks what is cut off where it is bigger than the pane and where it
    stands where it is smaller, and the shift moves it on from there.
    It is held where no black shows beside a picture bigger than the pane
    and none of a smaller one is cut, or, where it may go past the edges,
    where half of it is still on show, or half the pane still covered by
    a picture bigger than that.

    None when there is nothing to place: no frame or no pane.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform, pixel_aspect)

    if fit is None:
        return None

    pane_w, pane_h = pane_size
    left, top = _picture_position(fit, pane_size, view)

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


def calc_whole_placement(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> ViewPlacement | None:
    """All of the frame and where it goes, past the pane where it is.

    For a video VLC turns or flips as it shows it, as the file says to: a
    phone recording, mostly. VLC 3 crops such a picture wrong, so the
    hardware drivers ask it for no crop at all and put its window over the
    whole frame, where calc_view_placement has the part of it on show,
    and cut that window down to the part on show. What the user's crop
    takes off is drawn with the rest, just never on show.

    None where that would take too big a window, and where there is
    nothing to place.
    """

    fit = _Fit.of(frame_size, pane_size, view, transform, pixel_aspect)

    if fit is None:
        return None

    frame_w, frame_h = frame_size
    whole_w, whole_h = frame_w * fit.per_x, frame_h * fit.per_y

    if max(whole_w, whole_h) > _WHOLE_MAX_SIDE:
        return None

    if whole_w * whole_h > _WHOLE_MAX_PIXELS:
        return None

    left, top = _picture_position(fit, pane_size, view)

    return ViewPlacement(
        source=(0, 0, frame_w, frame_h),
        target=(left - fit.x * fit.per_x, top - fit.y * fit.per_y, whole_w, whole_h),
    )


def calc_whole_geometry(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    is_turned: bool = False,
    *,
    pixel_aspect: float = 1.0,
) -> tuple[str, str] | None:
    """Aspect override and crop geometry for calc_whole_placement.

    The frame is as VLC has it, stored the way the file has it rather than
    shown; turned, when the file says to show it on its side, and its
    pixels with it, which pixel_aspect is not. The picture is placed as it
    is shown, and VLC told its shape the way it is stored.

    None where there is no whole picture to show.
    """

    frame_w, frame_h = frame_size
    shown_frame = (frame_h, frame_w) if is_turned else frame_size
    shown_pixel = 1 / pixel_aspect if is_turned else pixel_aspect

    placement = calc_whole_placement(
        shown_frame, pane_size, view, transform, pixel_aspect=shown_pixel
    )

    if placement is None:
        return None

    _, _, shape_w, shape_h = placement.target

    if is_turned:
        shape_w, shape_h = shape_h, shape_w

    override = _shape_override(
        max(round(shape_w), 1), max(round(shape_h), 1), frame_size, frame_size
    )

    return _format_view(override, _NO_CROP)


def calc_view_shift(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> VideoShift:
    """The shift the picture really stands at, in whole frame pixels.

    What was asked for where it is within the bounds calc_view_placement
    holds the picture in, the nearest shift that is where it would take
    the picture past them. A move goes from here, not from wherever past
    a bound the picture was held at, which would take presses to come
    back from without anything moving.

    The shift as it is where there is nothing to work it out from.
    """
    lowest, highest = calc_shift_range(
        frame_size, pane_size, view, transform, pixel_aspect=pixel_aspect
    )

    return VideoShift(
        min(max(view.shift.X, lowest.X), highest.X),
        min(max(view.shift.Y, lowest.Y), highest.Y),
    )


def calc_shift_range(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> tuple[VideoShift, VideoShift]:
    """The least and the most the shift can be, in whole frame pixels.

    As far as the bounds calc_view_placement holds the picture in let it
    go, from the anchor's place, left and up and then right and down. 0
    is always in it. Both the shift as it is where there is nothing to
    work it out from.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform, pixel_aspect)

    if fit is None:
        return view.shift, view.shift

    pane_w, pane_h = pane_size
    anchor_x, anchor_y = _ANCHOR_POSITIONS[view.anchor]

    lowest_x, highest_x = _shift_range(
        _bounds(pane_w, fit.picture_w, view.is_shift_past_edges),
        (pane_w - fit.picture_w) * anchor_x,
        fit.per_x,
    )
    lowest_y, highest_y = _shift_range(
        _bounds(pane_h, fit.picture_h, view.is_shift_past_edges),
        (pane_h - fit.picture_h) * anchor_y,
        fit.per_y,
    )

    return VideoShift(lowest_x, lowest_y), VideoShift(highest_x, highest_y)


def calc_picture_rect(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> Rect | None:
    """Where all of the picture goes in the pane, past its edges where it is.

    What the crop keeps, as calc_view_placement places it before the pane
    cuts it. None when there is nothing to place.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform, pixel_aspect)

    if fit is None:
        return None

    left, top = _picture_position(fit, pane_size, view)

    return left, top, fit.picture_w, fit.picture_h


def calc_view_step(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> tuple[int, int]:
    """What one move right and one move down add to the shift.

    A move goes the way it says. Where the picture is bigger than the pane
    that is looking further that way, so the picture slides the other way
    to bring more of that side in; where it is smaller, it is the picture
    that goes that way, across the room it has in the pane.

    A share of the part on show, so a press goes as far on screen however
    big the video is and however far it is zoomed: the part on show while
    the picture is within the edges, so a press goes as far wherever the
    picture is, past them included. (0, 0) where there is nothing to work
    it out from.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform, pixel_aspect)

    if fit is None:
        return 0, 0

    pane_w, pane_h = pane_size

    return (
        _step(
            min(fit.picture_w, pane_w) / fit.per_x,
            fit.picture_w > pane_w + _ROUNDING_SLACK,
        ),
        _step(
            min(fit.picture_h, pane_h) / fit.per_y,
            fit.picture_h > pane_h + _ROUNDING_SLACK,
        ),
    )


def calc_moved_shift(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    steps: tuple[int, int],
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> VideoShift:
    """The shift so many moves right and down take the picture to.

    Left and up are negative. From where the picture stands (see
    calc_view_shift), a whole step at a time (see calc_view_step), onto
    whole steps from the anchor: a move from between two goes as far as
    the next, so moving back comes back to where it was, the anchor's own
    place above all. Held within the bounds again after.
    """

    shift = calc_view_shift(
        frame_size, pane_size, view, transform, pixel_aspect=pixel_aspect
    )
    step_x, step_y = calc_view_step(
        frame_size, pane_size, view, transform, pixel_aspect=pixel_aspect
    )
    steps_x, steps_y = steps

    moved = view._replace(
        shift=VideoShift(
            _on_steps(shift.X, steps_x * step_x, abs(step_x)),
            _on_steps(shift.Y, steps_y * step_y, abs(step_y)),
        )
    )

    return calc_view_shift(
        frame_size, pane_size, moved, transform, pixel_aspect=pixel_aspect
    )


def calc_dragged_shift(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    moved: tuple[float, float],
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> tuple[VideoShift, tuple[float, float]]:
    """The shift the picture goes to, dragged along with the pointer.

    `moved` is how far the pointer went, right and down, in pane pixels.
    The picture goes the same way as far, whether it is bigger than the
    pane or not, from where it stands (see calc_view_shift), in whole frame
    pixels and held within the bounds after.

    Also what of the move is left over, less than a frame pixel each way,
    for the next move to go on from, so a slow drag of a zoomed in picture
    still gets somewhere. Nothing is left over where the picture was held:
    going back takes it back at once. The shift as it is, and nothing left
    over, where there is nothing to work it out from.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform, pixel_aspect)

    if fit is None:
        return view.shift, (0.0, 0.0)

    lowest, highest = calc_shift_range(
        frame_size, pane_size, view, transform, pixel_aspect=pixel_aspect
    )
    shift = calc_view_shift(
        frame_size, pane_size, view, transform, pixel_aspect=pixel_aspect
    )
    moved_x, moved_y = moved

    shift_x, left_x = _dragged(shift.X, moved_x, fit.per_x, lowest.X, highest.X)
    shift_y, left_y = _dragged(shift.Y, moved_y, fit.per_y, lowest.Y, highest.Y)

    return VideoShift(shift_x, shift_y), (left_x, left_y)


def calc_zoomed_shift(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    scale: float,
    focus: tuple[float, float],
    transform: VideoTransform | None = VideoTransform.NONE,
    kept: tuple[float | None, float | None] = (None, None),
    *,
    pixel_aspect: float = 1.0,
) -> tuple[VideoShift, tuple[float | None, float | None]]:
    """The shift that keeps what is under a pane point there, zoomed.

    `focus` is the point in pane pixels, and the part of the picture under
    it stays under it at the new scale: a zoom about that point rather
    than about the anchor's place. Over no picture, the nearest part of the
    picture on show is the one that stays.

    On an axis where the zoomed picture is no bigger than the pane, it goes
    to the anchor's place instead. Zoomed out about a point off to one side,
    it would otherwise be left against that side of the room it has. Not
    past the edges, where the picture stands wherever it is put.

    Held within the bounds after (see calc_view_shift), so near an edge the
    point slides out from under the focus rather than black coming in.

    Also the frame point kept on each axis, for the next zoom about the same
    focus to keep in its place, as `kept`: the shift is in whole frame
    pixels, and the point found under the focus again each time would
    wander by up to half of one a zoom, many screen pixels on a small video
    zoomed far in. None where none was kept, the picture having gone to the
    anchor's place or been held. The shift as it is, and nothing kept, where
    there is nothing to work it out from.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform, pixel_aspect)
    zoomed = view._replace(scale=scale)
    zoomed_fit = _Fit.of(frame_size, pane_size, zoomed, transform, pixel_aspect)

    if fit is None or zoomed_fit is None:
        return view.shift, (None, None)

    pane_w, pane_h = pane_size
    anchor_x, anchor_y = _ANCHOR_POSITIONS[view.anchor]
    left, top = _picture_position(fit, pane_size, view)
    focus_x, focus_y = focus
    kept_x, kept_y = kept

    wanted_x, kept_x = _zoomed_shift(
        pane_w,
        (left, fit.picture_w, fit.per_x),
        (zoomed_fit.picture_w, zoomed_fit.per_x),
        anchor_x,
        focus_x,
        kept_x,
        view.is_shift_past_edges,
    )
    wanted_y, kept_y = _zoomed_shift(
        pane_h,
        (top, fit.picture_h, fit.per_y),
        (zoomed_fit.picture_h, zoomed_fit.per_y),
        anchor_y,
        focus_y,
        kept_y,
        view.is_shift_past_edges,
    )

    shift = calc_view_shift(
        frame_size,
        pane_size,
        zoomed._replace(shift=VideoShift(wanted_x, wanted_y)),
        transform,
        pixel_aspect=pixel_aspect,
    )

    return shift, (
        kept_x if shift.X == wanted_x else None,
        kept_y if shift.Y == wanted_y else None,
    )


def calc_selection_zoom(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    selection: Rect,
    transform: VideoTransform | None = VideoTransform.NONE,
    max_scale: float = MAX_SCALE,
    room: tuple[float, float] | None = None,
    *,
    pixel_aspect: float = 1.0,
) -> tuple[float, VideoShift] | None:
    """The zoom and shift that fit a part of the picture into the pane.

    `selection` is (x, y, width, height) in pane pixels. What of it is over
    the picture on show is fitted whole into the pane, as big as it goes
    there, and put in its middle: a zoom about the middle of the pane that
    keeps the middle of the selection there. The picture is never zoomed
    out, the selection having been on show, so fitting already.

    `room` is how much of the pane the selection may take, all of it if not
    given: where the picture is drawn bigger than the view has it, as on
    a hardware surface, a little less of it is on show.

    Up to max_scale, where the selection is smaller in the pane then. The
    scale is in hundredths, down, which still fits the selection and reads
    as a number. On an axis where the picture fits the pane, it goes to
    the anchor's place, and it is held within the bounds after, as a zoom
    about a point is (see calc_zoomed_shift): by an edge, the selection
    goes off the middle rather than black coming in.

    None where nothing of the selection is over the picture, and where
    there is nothing to work it out from.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform, pixel_aspect)

    if fit is None:
        return None

    pane_w, pane_h = pane_size
    left, top = _picture_position(fit, pane_size, view)

    start_x, end_x = _over_picture(selection[0], selection[2], left, fit.picture_w)
    start_y, end_y = _over_picture(selection[1], selection[3], top, fit.picture_h)

    start_x, end_x = max(start_x, 0), min(end_x, pane_w)
    start_y, end_y = max(start_y, 0), min(end_y, pane_h)

    if end_x - start_x <= _ROUNDING_SLACK or end_y - start_y <= _ROUNDING_SLACK:
        return None

    room_w, room_h = room or pane_size
    by = min(room_w / (end_x - start_x), room_h / (end_y - start_y))
    scale = min(view.scale * by, max_scale)
    scale = max(math.floor(scale * 100 + _ROUNDING_SLACK) / 100, view.scale)

    zoomed = view._replace(scale=scale)
    zoomed_fit = _Fit.of(frame_size, pane_size, zoomed, transform, pixel_aspect)
    anchor_x, anchor_y = _ANCHOR_POSITIONS[view.anchor]

    # the selection's middle, kept at the pane's: the point is in frame
    # pixels from the picture's near edge, as _zoomed_shift has it
    wanted_x, _ = _zoomed_shift(
        pane_w,
        (left, fit.picture_w, fit.per_x),
        (zoomed_fit.picture_w, zoomed_fit.per_x),
        anchor_x,
        pane_w / 2,
        ((start_x + end_x) / 2 - left) / fit.per_x,
        view.is_shift_past_edges,
    )
    wanted_y, _ = _zoomed_shift(
        pane_h,
        (top, fit.picture_h, fit.per_y),
        (zoomed_fit.picture_h, zoomed_fit.per_y),
        anchor_y,
        pane_h / 2,
        ((start_y + end_y) / 2 - top) / fit.per_y,
        view.is_shift_past_edges,
    )

    shift = calc_view_shift(
        frame_size,
        pane_size,
        zoomed._replace(shift=VideoShift(wanted_x, wanted_y)),
        transform,
        pixel_aspect=pixel_aspect,
    )

    return scale, shift


class AxisPlace(NamedTuple):
    """Where a picture stands on one axis of its pane, see calc_shared_view."""

    # the point of the picture at the pane's middle, or where in the room
    # beside the picture it stands
    is_middle: bool
    # of the picture's length, or of the room's
    share: float


@dataclass(frozen=True)
class SharedView:
    """A video's view of its picture, for other videos to show theirs alike.

    See calc_shared_view; `view` is the video's own, its shift where the
    picture really stands.
    """

    view: ViewParams
    frame_size: tuple[int, int]
    pane_size: tuple[int, int]
    transform: VideoTransform | None
    place_x: AxisPlace
    place_y: AxisPlace
    pixel_aspect: float = 1.0


class SyncedView(NamedTuple):
    """A video's view, for the others to follow: see ViewControl.synced."""

    view: SharedView
    # where the picture stands is a zoom to a selection's doing, which a
    # reset of the zoom then undoes in the others too
    is_zoomed_to_selection: bool


def calc_shared_view(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> SharedView | None:
    """Where a picture is in its pane, for other videos to show the same part.

    The scale goes as it is, being one of the picture's fit already, and so
    does the anchor. On an axis where the picture is bigger than the pane,
    the point of it at the pane's middle, a share of the picture: another
    picture puts the same point there, whatever its size. Where it is
    smaller, where it stands in the room beside it, a share of the room:
    against one edge or the other, or anywhere between. Where it fits
    exactly, at the anchor's place, or the point at the middle where it has
    been moved past the edges.

    None where there is nothing to work it out from.
    """
    fit = _Fit.of(frame_size, pane_size, view, transform, pixel_aspect)

    if fit is None:
        return None

    pane_w, pane_h = pane_size
    anchor_x, anchor_y = _ANCHOR_POSITIONS[view.anchor]
    left, top = _picture_position(fit, pane_size, view)
    shift = calc_view_shift(
        frame_size, pane_size, view, transform, pixel_aspect=pixel_aspect
    )

    return SharedView(
        view=view._replace(shift=shift),
        frame_size=tuple(frame_size),
        pane_size=tuple(pane_size),
        transform=transform,
        place_x=_axis_place(pane_w, fit.picture_w, left, anchor_x),
        place_y=_axis_place(pane_h, fit.picture_h, top, anchor_y),
        pixel_aspect=pixel_aspect,
    )


def calc_followed_view(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    shared: SharedView,
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> ViewParams | None:
    """This video's view, showing the part of its picture another one shows.

    The scale and the anchor are the shared ones, the rest of the view this
    video's own: its crop, its aspect, whether it may go past the edges.
    The same video in a pane the same takes the shift as it is, every pixel
    where it is in the other. Any other puts its picture where the other's
    stands (see calc_shared_view), to the nearest whole frame pixel. Held
    within its own bounds either way (see calc_view_shift).

    None where there is nothing to work it out from.
    """
    followed = view._replace(scale=shared.view.scale, anchor=shared.view.anchor)
    fit = _Fit.of(frame_size, pane_size, followed, transform, pixel_aspect)

    if fit is None:
        return None

    is_same = (
        tuple(frame_size) == shared.frame_size
        and tuple(pane_size) == shared.pane_size
        and transform == shared.transform
        and pixel_aspect == shared.pixel_aspect
        and view.crop == shared.view.crop
        and view.aspect == shared.view.aspect
    )

    if is_same:
        shift = shared.view.shift
    else:
        pane_w, pane_h = pane_size
        anchor_x, anchor_y = _ANCHOR_POSITIONS[followed.anchor]

        shift = VideoShift(
            _followed_shift(pane_w, fit.picture_w, fit.per_x, anchor_x, shared.place_x),
            _followed_shift(pane_h, fit.picture_h, fit.per_y, anchor_y, shared.place_y),
        )

    followed = followed._replace(shift=shift)

    return followed._replace(
        shift=calc_view_shift(
            frame_size, pane_size, followed, transform, pixel_aspect=pixel_aspect
        )
    )


def calc_view_borders(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> VideoCrop:
    """What the view cuts off each side of the frame, in whole frame pixels.

    The crop the hardware drivers have VLC make, zoom and all, so what
    their snapshot keeps; frames drawn here get screenshots cut the same.
    Just the user crop where there is nothing to work it out from.
    """
    placement = calc_view_placement(
        frame_size, pane_size, view, transform, pixel_aspect=pixel_aspect
    )

    if placement is None:
        return view.crop

    return _source_borders(frame_size, placement.source)


def calc_view_geometry(
    frame_size: tuple[int, int],
    pane_size: tuple[int, int],
    view: ViewParams,
    transform: VideoTransform | None = VideoTransform.NONE,
    *,
    pixel_aspect: float = 1.0,
) -> tuple[str, str]:
    """Aspect override and crop geometry strings to pass to libvlc.

    VLC is told to crop the frame to exactly the part on show, zoom
    included, and to give that part the shape it has on screen. It then
    lands where calc_view_placement puts it as long as its window is over
    the target, which is what the hardware drivers see to. The override
    takes the place of the shape the video gives its pixels, so that
    shape is in the sums here instead.
    """
    placement = calc_view_placement(
        frame_size, pane_size, view, transform, pixel_aspect=pixel_aspect
    )

    if placement is None:
        # No usable geometry; show the user-cropped region letterboxed.
        return _format_view(
            _whole_override(frame_size, transform, pixel_aspect), view.crop
        )

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


def calc_vlc_picture(
    frame_size: tuple[int, int],
    geometry: tuple[str, str],
    window_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    """Where VLC 3 puts the picture in a window this size, told the geometry.

    vout_display_PlacePicture (src/video_output/display.c), filling the
    window with no zoom of VLC's own, as the hardware drivers have it: the
    override makes the frame's SAR num * frame_h : den * frame_w, reduced,
    the crop leaves the region, and the region goes in as large as it fits
    and in the middle, in VLC's whole-pixel sums. It matched VLC's own
    placement to the pixel everywhere it was measured.

    The geometry is calc_view_geometry's, not a turned file's: VLC turns
    those in placing them too. None where VLC goes by the file's own shape.
    """
    override, crop = geometry
    num, den = (int(part) for part in override.split(":"))
    frame_w, frame_h = frame_size
    window_w, window_h = window_size

    if min(num, den, frame_w, frame_h, window_w, window_h) <= 0:
        return None

    borders = VideoCrop(*(int(part) for part in crop.split("+")[1:]))
    _, _, region_w, region_h = calc_crop_region(frame_size, borders)

    sar_num, sar_den = num * frame_h, den * frame_w
    shared = math.gcd(sar_num, sar_den)
    sar_num, sar_den = sar_num // shared, sar_den // shared

    fill_w = region_w * window_h * sar_num // (region_h * sar_den)

    if fill_w <= window_w:
        width, height = fill_w, window_h
    else:
        width = window_w
        height = region_h * window_w * sar_den // (region_w * sar_num)

    return (window_w - width) // 2, (window_h - height) // 2, width, height


def calc_frame_pixel_shape(
    frame_size: tuple[int, int],
    transform: VideoTransform | None,
    pixel_aspect: float = 1.0,
) -> tuple[float, float]:
    """How wide and how tall a frame pixel is on screen, relatively.

    pixel_aspect is how wide the video's own pixels are for their height,
    its sample aspect ratio: 2 for a 320x360 frame of a 640x360 picture,
    64/45 for a 720x576 one shown 16:9. Under a rotation VLC 3 keeps the
    frame at its unrotated size and squeezes the turned picture into it:
    a 1920x1080 frame of square pixels then holds a picture 1080 wide and
    1920 tall.
    """
    if transform not in ROTATION_TRANSFORMS:
        return pixel_aspect, 1.0

    frame_w, frame_h = frame_size

    # the turned picture is as wide as the unturned one is tall
    return frame_h / frame_w, frame_w * pixel_aspect / frame_h


def _whole_override(
    frame_size: tuple[int, int], transform: VideoTransform | None, pixel_aspect: float
) -> tuple[int, int]:
    """The override that shows the whole frame in the shape it has.

    Its size on screen as far as whole pixels go, which VLC reduces. (0, 0),
    VLC's own shape, where there is no frame.
    """
    frame_w, frame_h = frame_size

    if min(frame_w, frame_h) <= 0:
        return 0, 0

    unit_x, unit_y = calc_frame_pixel_shape(frame_size, transform, pixel_aspect)

    return max(round(frame_w * unit_x), 1), max(round(frame_h * unit_y), 1)


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
        pixel_aspect: float,
    ) -> "_Fit | None":
        frame_w, frame_h = frame_size
        pane_w, pane_h = pane_size

        if min(frame_w, frame_h, pane_w, pane_h, view.scale, pixel_aspect) <= 0:
            return None

        x, y, region_w, region_h = calc_crop_region(frame_size, view.crop)
        unit_x, unit_y = calc_frame_pixel_shape(frame_size, transform, pixel_aspect)

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


def _picture_position(
    fit: "_Fit", pane_size: tuple[int, int], view: ViewParams
) -> tuple[float, float]:
    """Where the whole picture's top left corner goes in the pane."""

    pane_w, pane_h = pane_size
    anchor_x, anchor_y = _ANCHOR_POSITIONS[view.anchor]

    left = _hold(
        _place(pane_w, fit.picture_w, anchor_x, view.shift.X * fit.per_x),
        _bounds(pane_w, fit.picture_w, view.is_shift_past_edges),
    )
    top = _hold(
        _place(pane_h, fit.picture_h, anchor_y, view.shift.Y * fit.per_y),
        _bounds(pane_h, fit.picture_h, view.is_shift_past_edges),
    )

    return left, top


def _place(pane: float, picture: float, anchor: float, shift: float) -> float:
    return (pane - picture) * anchor + shift


def _bounds(
    pane: float, picture: float, is_shift_past_edges: bool
) -> tuple[float, float]:
    """How far along an axis the picture's near edge can go, both ways.

    Within the edges, as far as leaves no black beside a picture bigger
    than the pane and cuts none of a smaller one. Past them, as far as
    leaves half the picture on show, or half the pane covered by one
    bigger than that, which takes in every place within the edges too.
    """

    if is_shift_past_edges:
        overlap = min(pane, picture) / 2

        return overlap - picture, pane - overlap

    room = pane - picture

    return min(room, 0), max(room, 0)


def _hold(position: float, bounds: tuple[float, float]) -> float:
    lowest, highest = bounds

    return min(max(position, lowest), highest)


def _step(shown: float, is_bigger_than_pane: bool) -> int:
    step = max(round(shown * SHIFT_STEP), 1)

    return -step if is_bigger_than_pane else step


def _dragged(
    shift: int, moved: float, per: float, lowest: int, highest: int
) -> tuple[int, float]:
    """The shift moved so many pane pixels, and what is left over of them."""

    wanted = shift + moved / per
    whole = math.floor(wanted + 0.5)
    held = min(max(whole, lowest), highest)

    if held != whole:
        return held, 0.0

    return held, (wanted - held) * per


def _zoomed_shift(
    pane: float,
    before: tuple[float, float, float],
    after: tuple[float, float],
    anchor: float,
    focus: float,
    kept: float | None,
    is_shift_past_edges: bool,
) -> tuple[int, float | None]:
    """One axis of calc_zoomed_shift: the shift wanted, and the point kept.

    `before` is where the picture's near edge stands, how long it is and
    how many pane pixels a frame pixel takes; `after` the last two zoomed.
    The point is in frame pixels from the picture's near edge.
    """

    start, picture, per = before
    zoomed_picture, zoomed_per = after

    if not is_shift_past_edges and zoomed_picture <= pane + _ROUNDING_SLACK:
        return 0, None

    if kept is None:
        # the nearest part of the picture on show, which is not kept for
        # the next zoom where it is not the focus: it moves as it zooms
        at = min(max(focus, start, 0), start + picture, pane)
        point = (at - start) / per
        is_kept = abs(at - focus) <= _ROUNDING_SLACK
    else:
        at, point, is_kept = focus, kept, True

    near = at - point * zoomed_per
    wanted = (near - (pane - zoomed_picture) * anchor) / zoomed_per

    return math.floor(wanted + 0.5), point if is_kept else None


def _axis_place(pane: float, picture: float, start: float, anchor: float) -> AxisPlace:
    """One axis of calc_shared_view, the picture's near edge at `start`."""

    room = pane - picture

    if room > _ROUNDING_SLACK:
        return AxisPlace(is_middle=False, share=start / room)

    if room >= -_ROUNDING_SLACK and abs(start) <= _ROUNDING_SLACK:
        return AxisPlace(is_middle=False, share=anchor)

    return AxisPlace(is_middle=True, share=(pane / 2 - start) / picture)


def _followed_shift(
    pane: float, picture: float, per: float, anchor: float, place: AxisPlace
) -> int:
    """One axis of calc_followed_view: the shift that puts the picture there."""

    room = pane - picture

    if place.is_middle:
        start = pane / 2 - place.share * picture
    else:
        start = place.share * room

    return math.floor((start - room * anchor) / per + 0.5)


def _over_picture(
    start: float, length: float, picture_start: float, picture: float
) -> tuple[float, float]:
    """Where a stretch of one axis starts and ends over the picture."""

    return max(start, picture_start), min(start + length, picture_start + picture)


def _on_steps(shift: int, by: int, step: int) -> int:
    """The shift moved by so many whole steps, onto whole steps."""

    if not by or not step:
        return shift

    count = by // step

    if by > 0:
        return (shift // step + count) * step

    return (-(-shift // step) + count) * step


def _shift_range(
    bounds: tuple[float, float], anchored: float, per: float
) -> tuple[int, int]:
    # 0 is always within: no shift leaves the picture at the anchor's place
    # in the room, which is inside the bounds either way
    lowest = math.ceil((bounds[0] - anchored) / per - _ROUNDING_SLACK)
    highest = math.floor((bounds[1] - anchored) / per + _ROUNDING_SLACK)

    return lowest, highest


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
    """The aspect override that shows the region in the shape given.

    VLC shows the region with DAR = region_x * sar_num : region_y * sar_den,
    the SAR coming from the override A through the whole frame: sar =
    A_num * vid_y : A_den * vid_x. So the SAR is picked first, as near to
    what the shape takes as VLC can multiply without overflowing (see
    _VLC_UINT_LIMIT), and the override worked back from it exactly.
    """

    vid_x, vid_y = frame_size
    region_x, region_y = region_size

    sar = _bounded(
        Fraction(shape_w * region_y, shape_h * region_x),
        _sar_term_limit(frame_size, region_size),
    )

    if not sar:
        # Degenerate shape; "0:0" resets the override (native aspect).
        return 0, 0

    override = sar * Fraction(vid_x, vid_y)

    return override.numerator, override.denominator


def _sar_term_limit(frame_size: tuple[int, int], region_size: tuple[int, int]) -> int:
    """How big the SAR's terms can be for VLC's sums on them to fit.

    The override is the SAR times vid_x:vid_y, reduced by at least what
    the frame's sides have in common, and VLC multiplies its terms by the
    frame's sides; then it multiplies the SAR's own by the region's.
    """

    vid_x, vid_y = frame_size

    through_frame = _VLC_UINT_LIMIT * math.gcd(vid_x, vid_y) // (vid_x * vid_y)
    through_region = _VLC_UINT_LIMIT // max(region_size)

    return max(min(through_frame, through_region), 1)


def _bounded(value: Fraction, limit: int) -> Fraction:
    """The nearest fraction with neither of its terms past the limit."""

    # limit_denominator only bounds the denominator; above 1 it is the
    # numerator that has to be kept down, so bound the inverse instead
    if value >= 1:
        inverse = (1 / value).limit_denominator(limit)

        return 1 / inverse if inverse else inverse

    return value.limit_denominator(limit)
