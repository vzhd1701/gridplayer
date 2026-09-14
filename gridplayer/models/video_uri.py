import os
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, FilePath

URL_ALLOWED_SCHEMES = {"http", "https", "rtp", "rtsp", "rtmp", "udp", "mms", "mmsh"}
URL_MAX_LENGTH = 2083


def must_be_absolute(p: Path) -> Path:
    if not p.is_absolute():
        raise ValueError("path must be absolute")
    return p


def parse_uri(uri: str, base_dir: Path | None = None):
    if "://" in uri:
        return uri

    path = Path(uri)

    if not path.is_absolute() and base_dir is not None:
        # Collapse ".." without resolve(), so symlinks stay portable.
        return Path(os.path.normpath(base_dir.absolute() / path))

    return path.absolute()


def relativize_uri(uri: Path | str, base_dir: Path) -> str:
    try:
        return Path(
            os.path.relpath(Path(uri).absolute(), base_dir.absolute())
        ).as_posix()
    except ValueError:
        return str(uri)


AbsoluteFilePath = Annotated[FilePath, AfterValidator(must_be_absolute)]


VideoURI = str | AbsoluteFilePath
