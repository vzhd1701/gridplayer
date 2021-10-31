import typing

from pydantic import BaseModel, Field, confloat

from gridplayer.params_static import VideoAspect, WindowState
from gridplayer.settings import Settings

MIN_SCALE = 1
MAX_SCALE = 3
MIN_RATE = 0.2
MAX_RATE = 12


class Video(BaseModel):
    file_path: typing.Optional[str]

    aspect_mode: VideoAspect = Field(
        default_factory=lambda: Settings().get("video_defaults/aspect")
    )
    is_start_random: bool = Field(
        default_factory=lambda: Settings().get("video_defaults/random_loop")
    )
    is_muted: bool = Field(
        default_factory=lambda: Settings().get("video_defaults/muted")
    )
    is_paused: bool = Field(
        default_factory=lambda: Settings().get("video_defaults/paused")
    )

    scale: confloat(ge=MIN_SCALE, le=MAX_SCALE) = 1.0
    rate: confloat(ge=MIN_RATE, le=MAX_RATE) = 1.0
    volume: float = 1.0
    current_position: int = 0

    loop_start: typing.Optional[int]
    loop_end: typing.Optional[int]

    class Config(object):
        json_encoders = {
            VideoAspect: lambda v: v.value,
            WindowState: lambda v: (v.x, v.y, v.height, v.width),
        }
