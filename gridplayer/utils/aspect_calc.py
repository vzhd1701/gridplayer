from fractions import Fraction

from gridplayer.params.static import VideoAspect, VideoCrop

# VLC converts the aspect override to a SAR with 32-bit unsigned math
# (sar = override_num * source_height : override_den * source_width, with
# source dims capped at 8192). Keep both terms of the reduced fraction
# at or below 2^19 - 1 so that product cannot overflow uint32; anything
# beyond is a degenerate stretch anyway.
_OVERRIDE_RATIO_LIMIT = (1 << 19) - 1
_ZERO_CROP = VideoCrop(0, 0, 0, 0)


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


def calc_resize_scale(
    video_dimensions: tuple[int, int],
    size: tuple[int, int],
    aspect: VideoAspect,
    scale: float,
    crop: VideoCrop = _ZERO_CROP,
) -> float:
    scr_x, scr_y = size

    if scr_x <= 0 or scr_y <= 0:
        return 0

    vid_x, vid_y = _resize_dimensions(video_dimensions, size, aspect, crop)

    if vid_x <= 0 or vid_y <= 0:
        return 0

    if scale <= 1:
        return 0

    if aspect == VideoAspect.FIT:
        resize_scale = max(scr_x / vid_x, scr_y / vid_y) * scale
    else:
        resize_scale = min(scr_x / vid_x, scr_y / vid_y) * scale

    return resize_scale


def calc_crop(
    video_dimensions: tuple[int, int], size: tuple[int, int], aspect: VideoAspect
):
    scr_x, scr_y = size
    vid_x, vid_y = video_dimensions

    scaling = {
        VideoAspect.STRETCH: {"aspect": (scr_x, scr_y), "crop": (scr_x, scr_y)},
        VideoAspect.FIT: {"aspect": (vid_x, vid_y), "crop": (scr_x, scr_y)},
        VideoAspect.NONE: {"aspect": (vid_x, vid_y), "crop": (vid_x, vid_y)},
    }

    return scaling[aspect]["aspect"], scaling[aspect]["crop"]


def calc_view_geometry(
    video_dimensions: tuple[int, int],
    size: tuple[int, int],
    aspect: VideoAspect,
    crop: VideoCrop,
) -> tuple[str, str]:
    """Aspect override and crop geometry strings to pass to libvlc.

    Without a pixel crop this is the legacy ratio-form geometry (calc_crop).
    With a pixel crop the ratio-form slot is taken by the border geometry,
    so FIT folds the pane-ratio center-crop into the borders and STRETCH
    sends a compensated aspect override (VLC derives the override SAR from
    the pre-crop source dimensions, see _stretch_override).
    """
    if crop == _ZERO_CROP:
        crop_aspect, crop_geometry = calc_crop(video_dimensions, size, aspect)
        return (
            f"{crop_aspect[0]}:{crop_aspect[1]}",
            f"{crop_geometry[0]}:{crop_geometry[1]}",
        )

    scr_x, scr_y = size
    vid_x, vid_y = video_dimensions

    if scr_x <= 0 or scr_y <= 0 or vid_x <= 0 or vid_y <= 0:
        # No usable geometry; show the user-cropped region letterboxed.
        return _format_border_view((vid_x, vid_y), crop)

    _, _, region_x, region_y = calc_crop_region(video_dimensions, crop)

    if aspect == VideoAspect.STRETCH:
        override = _stretch_override(scr_x, scr_y, vid_x, vid_y, region_x, region_y)
        borders = crop
    elif aspect == VideoAspect.FIT:
        override = (vid_x, vid_y)
        borders = _fit_borders(video_dimensions, size, crop)
    else:
        override = (vid_x, vid_y)
        borders = crop

    return _format_border_view(override, borders)


def calc_view_borders(
    video_dimensions: tuple[int, int],
    size: tuple[int, int],
    aspect: VideoAspect,
    crop: VideoCrop,
) -> VideoCrop:
    """What the view cuts off each side of the frame, in video pixels.

    The same part calc_view_geometry has VLC crop to, which is where a
    screenshot on the hardware drivers ends up: FIT centers the pane's
    shape on what the user crop leaves, the others keep all of that. The
    zoom and the aspect override are not in it; VLC applies those later,
    where its snapshot doesn't see them.
    """
    scr_x, scr_y = size
    vid_x, vid_y = video_dimensions

    if aspect != VideoAspect.FIT or min(scr_x, scr_y, vid_x, vid_y) <= 0:
        return crop

    if crop == _ZERO_CROP:
        return _ratio_borders(video_dimensions, size)

    return _fit_borders(video_dimensions, size, crop)


def _ratio_borders(video_dimensions: tuple[int, int], size: tuple[int, int]):
    """The borders VLC takes off for the ratio-form geometry FIT sends.

    Its own rounding, which is not _fit_borders': the side that is cut is
    scaled and rounded down, and a pixel left over by centering it goes to
    the right or the bottom (VoutDisplayCropRatio in VLC 3).
    """
    scr_x, scr_y = size
    vid_x, vid_y = video_dimensions

    scaled_x = vid_y * scr_x // scr_y

    if scaled_x < vid_x:
        left = (vid_x - scaled_x) // 2
        return VideoCrop(left, 0, vid_x - scaled_x - left, 0)

    scaled_y = vid_x * scr_y // scr_x
    top = (vid_y - scaled_y) // 2
    return VideoCrop(0, top, 0, vid_y - scaled_y - top)


def _format_border_view(
    override: tuple[int, int], borders: VideoCrop
) -> tuple[str, str]:
    return (
        f"{override[0]}:{override[1]}",
        f"+{borders.Left}+{borders.Top}+{borders.Right}+{borders.Bottom}",
    )


def _center_extra(region: int, target: Fraction) -> int:
    """Pixels to take from each side so `region` matches `target`.

    Clamped so at least one pixel remains; without that, rounding on a
    tiny region in a wildly mismatched pane can send VLC a 0-size crop.
    """
    extra = round((region - target) / 2)
    return min(max(extra, 0), max(region - 1, 0) // 2)


def _fit_borders(
    video_dimensions: tuple[int, int],
    size: tuple[int, int],
    crop: VideoCrop,
) -> VideoCrop:
    """Extend the user borders around the cropped region center until the
    visible region matches the pane aspect ratio (center-fill crop)."""
    scr_x, scr_y = size
    _, _, region_x, region_y = calc_crop_region(video_dimensions, crop)

    if region_x * scr_y > region_y * scr_x:
        # Region is wider than the pane: crop the sides.
        extra = _center_extra(region_x, Fraction(region_y * scr_x, scr_y))
        return VideoCrop(crop.Left + extra, crop.Top, crop.Right + extra, crop.Bottom)

    # Region is taller than the pane: crop the top/bottom.
    extra = _center_extra(region_y, Fraction(region_x * scr_y, scr_x))
    return VideoCrop(crop.Left, crop.Top + extra, crop.Right, crop.Bottom + extra)


def _stretch_override(
    scr_x: int,
    scr_y: int,
    vid_x: int,
    vid_y: int,
    region_x: int,
    region_y: int,
) -> tuple[int, int]:
    # VLC displays the visible region with DAR = region_x * sar_num :
    # region_y * sar_den, where the SAR comes from the override (A) via the
    # pre-crop source dims: sar = A_num * vid_y : A_den * vid_x. Solving
    # DAR == scr_x:scr_y for A gives the compensation below; without a crop
    # it reduces to the plain pane ratio.
    override = Fraction(scr_x * region_y * vid_x, scr_y * region_x * vid_y)
    override = override.limit_denominator(_OVERRIDE_RATIO_LIMIT)

    if override.numerator > _OVERRIDE_RATIO_LIMIT:
        # Degenerate stretch; "0:0" resets the override (native aspect).
        return 0, 0

    return override.numerator, override.denominator


def _resize_dimensions(
    video_dimensions: tuple[int, int],
    size: tuple[int, int],
    aspect: VideoAspect,
    crop: VideoCrop,
) -> tuple[int, int]:
    if crop == _ZERO_CROP:
        return video_dimensions

    if aspect == VideoAspect.FIT:
        borders = _fit_borders(video_dimensions, size, crop)
        _, _, width, height = calc_crop_region(video_dimensions, borders)
        return width, height

    _, _, width, height = calc_crop_region(video_dimensions, crop)
    return width, height
