import typing

import pydantic
from pydantic import Field

from gridplayer.params_static import GridMode, VideoAspect, WindowState
from gridplayer.settings import settings


class PlaylistParams(pydantic.BaseModel):
    grid_mode: GridMode = Field(
        default_factory=lambda: settings.get("playlist/grid_mode")
    )
    window_state: typing.Optional[WindowState]


class VideoParams(pydantic.BaseModel):
    aspect_mode: VideoAspect = Field(
        default_factory=lambda: settings.get("video_defaults/aspect")
    )
    is_start_random: bool = Field(
        default_factory=lambda: settings.get("video_defaults/random_loop")
    )
    is_muted: bool = Field(default_factory=lambda: settings.get("video_defaults/muted"))
    is_paused: bool = Field(
        default_factory=lambda: settings.get("video_defaults/paused")
    )

    scale: pydantic.confloat(ge=1, le=3) = 1.0
    rate: pydantic.confloat(ge=0.2, le=12) = 1.0
    volume: float = 1.0
    current_position: int = 0

    loop_start: typing.Optional[int]
    loop_end: typing.Optional[int]

    class Config:
        json_encoders = {
            VideoAspect: lambda v: v.value,
            WindowState: lambda v: (v.x, v.y, v.height, v.width),
        }
