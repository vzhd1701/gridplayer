from gridplayer.models.video import Video
from gridplayer.params.static import (
    VideoDeinterlace,
    VideoDeinterlaceMode,
    VideoTransform,
)

TransformMap = {
    VideoTransform.ROTATE_90: "90",
    VideoTransform.ROTATE_180: "180",
    VideoTransform.ROTATE_270: "270",
    VideoTransform.HFLIP: "hflip",
    VideoTransform.VFLIP: "vflip",
    VideoTransform.TRANSPOSE: "transpose",
    VideoTransform.ANTITRANSPOSE: "antitranspose",
}

DeinterlaceModeMap = {
    VideoDeinterlaceMode.AUTO: "auto",
    VideoDeinterlaceMode.DISCARD: "discard",
    VideoDeinterlaceMode.BLEND: "blend",
    VideoDeinterlaceMode.MEAN: "mean",
    VideoDeinterlaceMode.BOB: "bob",
    VideoDeinterlaceMode.LINEAR: "linear",
    VideoDeinterlaceMode.X: "x",
    VideoDeinterlaceMode.YADIF: "yadif",
    VideoDeinterlaceMode.YADIF2X: "yadif2x",
    VideoDeinterlaceMode.PHOSPHOR: "phosphor",
    VideoDeinterlaceMode.IVTC: "ivtc",
}


def get_vlc_options(video_params: Video | None):
    vlc_options = []

    if video_params is None:
        return vlc_options

    if video_params.transform != VideoTransform.NONE:
        option_str = TransformMap[video_params.transform]
        vlc_options.append(f"--video-filter=transform{{type='{option_str}'}}")

    # A player left on auto takes its mode from the instance, and libVLC 3 has
    # no call to change it there without switching deinterlacing on for good.
    # Only a mode other than the instance's own is worth a process of its own.
    if (
        video_params.deinterlace == VideoDeinterlace.AUTO
        and video_params.deinterlace_mode != VideoDeinterlaceMode.AUTO
    ):
        option_str = DeinterlaceModeMap[video_params.deinterlace_mode]
        vlc_options.append(f"--deinterlace-mode={option_str}")

    return vlc_options


def is_reopen_needed(old: Video | None, new: Video) -> bool:
    """Whether a change needs the video opened again rather than adjusted.

    Instance options decide which VLC process a video is played in, so a
    change to one only takes hold in a new process. The subtitle encoding
    is a media option rather than an instance one -- as an instance option
    it would fork the process pool one way per encoding -- but it is settled
    when the input opens just the same, so it needs reopening too.
    """

    if get_vlc_options(old) != get_vlc_options(new):
        return True

    return old is not None and old.subtitle_encoding != new.subtitle_encoding


def is_deinterlace_reload_needed(
    current: Video, deinterlace: VideoDeinterlace, mode: VideoDeinterlaceMode
) -> bool:
    """Whether a deinterlace setting needs the video opened again.

    libVLC 3 switches a player's deinterlacing on or off, mode and all, while
    it plays; but it has no call to put a player back on auto, which is only
    where a player starts, and on auto the mode comes from the VLC instance.
    """

    if deinterlace != VideoDeinterlace.AUTO:
        return False

    return (
        current.deinterlace != VideoDeinterlace.AUTO or current.deinterlace_mode != mode
    )
