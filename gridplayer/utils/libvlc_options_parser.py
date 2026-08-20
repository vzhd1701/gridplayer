from gridplayer.models.video import Video
from gridplayer.params.static import VideoTransform

TransformMap = {
    VideoTransform.ROTATE_90: "90",
    VideoTransform.ROTATE_180: "180",
    VideoTransform.ROTATE_270: "270",
    VideoTransform.HFLIP: "hflip",
    VideoTransform.VFLIP: "vflip",
    VideoTransform.TRANSPOSE: "transpose",
    VideoTransform.ANTITRANSPOSE: "antitranspose",
}


def get_vlc_options(video_params: Video | None):
    vlc_options = []

    if video_params is None:
        return vlc_options

    if video_params.transform != VideoTransform.NONE:
        option_str = TransformMap[video_params.transform]
        vlc_options.append(f"--video-filter=transform{{type='{option_str}'}}")

    return vlc_options
