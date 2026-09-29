"""A chapter of a video, whether the file lists it or the site it came from."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chapter:
    """Where a chapter starts, and what it is called.

    Only where it starts: libVLC works out how long each one is from where
    the next one starts, so that is where its end is worked out here too.
    """

    start_ms: int
    name: str | None = None
