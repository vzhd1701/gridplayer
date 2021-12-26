import typing
from pathlib import Path

from pydantic import BaseModel, confloat
from pydantic.color import Color

from gridplayer.params_static import VideoAspect, VideoRepeat, WindowState
from gridplayer.settings import default_field

MIN_SCALE = 1
MAX_SCALE = 3
MIN_RATE = 0.2
MAX_RATE = 12


class Video(BaseModel):
    file_path: typing.Optional[Path]

    title: typing.Optional[str]
    color: Color = Color("white")

    aspect_mode: VideoAspect = default_field("video_defaults/aspect")
    repeat_mode: VideoRepeat = default_field("video_defaults/repeat")
    is_start_random: bool = default_field("video_defaults/random_loop")
    is_muted: bool = default_field("video_defaults/muted")
    is_paused: bool = default_field("video_defaults/paused")

    scale: confloat(ge=MIN_SCALE, le=MAX_SCALE) = 1.0
    rate: confloat(ge=MIN_RATE, le=MAX_RATE) = 1.0
    volume: float = 1.0
    current_position: int = 0

    loop_start: typing.Optional[int]
    loop_end: typing.Optional[int]

    class Config(object):
        json_encoders = {
            VideoAspect: lambda v: v.value,
            VideoRepeat: lambda v: v.value,
            WindowState: lambda v: (v.x, v.y, v.height, v.width),
        }
