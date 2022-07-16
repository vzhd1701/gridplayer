from typing import Tuple

from gridplayer.params.static import VideoAspect


def calc_resize_scale(
    video_dimensions: Tuple[int, int],
    size: Tuple[int, int],
    aspect: VideoAspect,
    scale: float,
) -> float:
    scr_x, scr_y = size
    vid_x, vid_y = video_dimensions

    if vid_x == 0 or vid_y == 0:
        return 0

    if scale > 1:
        if aspect == VideoAspect.FIT:
            resize_scale = max(scr_x / vid_x, scr_y / vid_y) * scale
        else:
            resize_scale = min(scr_x / vid_x, scr_y / vid_y) * scale

    else:
        resize_scale = 0

    return resize_scale


def calc_crop(
    video_dimensions: Tuple[int, int], size: Tuple[int, int], aspect: VideoAspect
):
    scr_x, scr_y = size
    vid_x, vid_y = video_dimensions

    scaling = {
        VideoAspect.STRETCH: {"aspect": (scr_x, scr_y), "crop": (scr_x, scr_y)},
        VideoAspect.FIT: {"aspect": (vid_x, vid_y), "crop": (scr_x, scr_y)},
        VideoAspect.NONE: {"aspect": (vid_x, vid_y), "crop": (vid_x, vid_y)},
    }

    return scaling[aspect]["aspect"], scaling[aspect]["crop"]
