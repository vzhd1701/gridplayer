"""A place in a video the viewer marked, to come back to.

Kept by the playlist with the file it is in; see FileBookmarks.
"""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_COLOR = re.compile(r"#[0-9a-f]{6}")


def bookmark_color(color: Any) -> str | None:
    """A colour as a bookmark keeps it, #rrggbb, or None for one that is no
    colour."""

    if not isinstance(color, str):
        return None

    color = color.strip().lower()

    return color if _COLOR.fullmatch(color) else None


class Bookmark(BaseModel):
    """Where it is, what the viewer called it, and the colour they gave it,
    if anything.

    One with no colour is drawn in the bookmarks' own, and goes on being
    drawn in it whatever that comes to be.
    """

    model_config = ConfigDict(frozen=True)

    time_ms: int = Field(ge=0)
    name: str | None = None
    color: str | None = None

    @field_validator("color", mode="before")
    @classmethod
    def _readable_color(cls, color: Any) -> str | None:
        # A playlist is a text file anybody can edit: a colour gone wrong in
        # it costs the bookmark its colour, not the bookmark.
        return bookmark_color(color)
