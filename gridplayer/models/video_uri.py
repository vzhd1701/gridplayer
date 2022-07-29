from pathlib import Path
from typing import Union

from pydantic import AnyUrl, FilePath, PydanticValueError

from gridplayer.params.extensions import SUPPORTED_MEDIA_EXT


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
