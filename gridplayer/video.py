import typing

from pydantic import BaseModel, Field, confloat

from gridplayer.params_static import VideoAspect, WindowState
from gridplayer.settings import Settings


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

    scale: confloat(ge=1, le=3) = 1.0
    rate: confloat(ge=0.2, le=12) = 1.0
    volume: float = 1.0
    current_position: int = 0

    loop_start: typing.Optional[int]
    loop_end: typing.Optional[int]

    class Config(object):
        json_encoders = {
            VideoAspect: lambda v: v.value,
            WindowState: lambda v: (v.x, v.y, v.height, v.width),
        }
