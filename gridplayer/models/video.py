from pathlib import Path
from typing import Iterable, List, Optional, Union
from uuid import uuid4

from pydantic import (  # noqa: WPS450
    UUID4,
    AnyUrl,
    BaseModel,
    Field,
    FilePath,
    PydanticValueError,
    ValidationError,
    confloat,
)
from pydantic.color import Color

from gridplayer.params.extensions import SUPPORTED_MEDIA_EXT
from gridplayer.params.static import VideoAspect, VideoRepeat
from gridplayer.settings import default_field

MIN_SCALE = 1
MAX_SCALE = 3
MIN_RATE = 0.2
MAX_RATE = 12


class VideoURL(AnyUrl):
    allowed_schemes = {"http", "https", "rtp", "rtsp", "udp", "mms", "mmsh"}
    max_length = 2083


class PathNotAbsoluteError(PydanticValueError):
    code = "path.not_absolute"
    msg_template = 'path "{path}" is not absolute'


class PathExtensionNotSupportedError(PydanticValueError):
    code = "path.ext_not_supported"
    msg_template = 'path extension "{path}" is not supported'


class AbsoluteFilePath(FilePath):
    @classmethod
    def validate(cls, path: Path) -> Path:
        super().validate(path)

        if not path.is_absolute():
            raise PathNotAbsoluteError(path=path)

        if path.suffix[1:].lower() not in SUPPORTED_MEDIA_EXT:
            raise PathExtensionNotSupportedError(path=path)

        return path


VideoURI = Union[VideoURL, AbsoluteFilePath]


class Video(BaseModel):
    id: UUID4 = Field(default_factory=uuid4)
    uri: VideoURI

    # Presentation
    title: Optional[str]
    color: Color = Color("white")

    # Seekable video
    current_position: int = 0
    loop_start: Optional[int]
    loop_end: Optional[int]

    repeat_mode: VideoRepeat = default_field("video_defaults/repeat")
    is_start_random: bool = default_field("video_defaults/random_loop")
    rate: confloat(ge=MIN_RATE, le=MAX_RATE) = 1.0

    # Generic
    aspect_mode: VideoAspect = default_field("video_defaults/aspect")
    is_muted: bool = default_field("video_defaults/muted")
    is_paused: bool = default_field("video_defaults/paused")
    scale: confloat(ge=MIN_SCALE, le=MAX_SCALE) = 1.0
    volume: float = 1.0

    # Streamable
    stream_quality: str = default_field("video_defaults/stream_quality")
    auto_reload_timer_min: int = default_field("video_defaults/auto_reload_timer")

    @property
    def uri_name(self) -> str:
        if isinstance(self.uri, VideoURL):
            return str(self.uri)

        return self.uri.name

    @property
    def is_local_file(self):
        return isinstance(self.uri, AbsoluteFilePath)

    @property
    def is_http_url(self):
        return isinstance(self.uri, VideoURL) and self.uri.scheme in {"http", "https"}


class VideoBlockMime(BaseModel):
    id: str
    video: Video


def filter_video_uris(uris: Iterable[str]) -> List[Video]:
    valid_urls = []

    for uri in uris:
        try:
            video = Video(uri=uri)
        except ValidationError:
            continue

        valid_urls.append(video)

    return valid_urls
