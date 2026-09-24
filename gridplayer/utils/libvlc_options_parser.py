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
