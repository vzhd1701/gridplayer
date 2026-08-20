from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, FilePath

URL_ALLOWED_SCHEMES = {"http", "https", "rtp", "rtsp", "rtmp", "udp", "mms", "mmsh"}
URL_MAX_LENGTH = 2083


def must_be_absolute(p: Path) -> Path:
    if not p.is_absolute():
        raise ValueError("path must be absolute")
    return p


def parse_uri(uri: str):
    if "://" in uri:
        return uri
    return Path(uri).absolute()


AbsoluteFilePath = Annotated[FilePath, AfterValidator(must_be_absolute)]


VideoURI = str | AbsoluteFilePath
