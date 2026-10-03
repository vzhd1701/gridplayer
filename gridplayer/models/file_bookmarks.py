"""The bookmarks the playlist keeps for one file.

Kept at the playlist's root rather than with its videos, so that a cell gone
on to another file finds them again when it comes back, and so that a file
closed and opened again does. Shared by every cell playing the file, or one
cell's own, `cell` saying whose, where the playlist keeps them that way.
"""

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError, field_validator

from gridplayer.models.bookmark import Bookmark
from gridplayer.utils.bookmarks import in_order


def _valid_bookmark(bookmark: Any) -> Bookmark | None:
    try:
        return Bookmark.model_validate(bookmark)
    except ValidationError as e:
        logging.getLogger("FileBookmarks").debug(f"Bookmark left out: {e}")
        return None


class FileBookmarks(BaseModel):
    # a file that is gone stays a path, for its bookmarks to be seen and
    # cleared away, and a URL stays a URL
    uri: Path | str
    cell: UUID | None = None
    bookmarks: list[Bookmark]

    @field_validator("bookmarks", mode="before")
    @classmethod
    def _drop_broken_bookmarks(cls, bookmarks: Any) -> Any:
        """Leave out a bookmark that makes no sense, rather than the rest.

        A playlist is a text file anybody can edit, and one bookmark with a
        time gone wrong is no reason to lose the others of its file.
        """

        if not isinstance(bookmarks, list):
            return bookmarks

        kept = (_valid_bookmark(bookmark) for bookmark in bookmarks)

        return [bookmark for bookmark in kept if bookmark is not None]

    @field_validator("bookmarks")
    @classmethod
    def _sort_bookmarks(cls, bookmarks: list[Bookmark]) -> list[Bookmark]:
        """First to last, and only one to a place."""

        return in_order(bookmarks)
