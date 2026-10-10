"""What a linked list's source had the last time it was read, kept in the
cache: for the list to be there at once as the playlist opens, before its
source is read again, and to be there at all where it cannot be read.

Only a link's: a list file or a folder on the disk is read again as soon
as it would be from here.
"""

import time
import zlib

from pydantic import BaseModel, TypeAdapter, ValidationError

from gridplayer.models.media_list import ListItem, ListSource
from gridplayer.params.static import ListSourceKind
from gridplayer.utils import cache

LISTS_DIR = "lists"

# items written out this many at a time, the interface thread getting its
# turn in between: a channel list's all at once kept it waiting a tenth of
# a second
_WRITTEN_AT_ONCE = 5000

_ITEMS = TypeAdapter(tuple[ListItem, ...])


class KeptRead(BaseModel):
    # when it was read, in seconds since the epoch
    at: int
    items: tuple[ListItem, ...]


def is_kept(source: ListSource) -> bool:
    return source.kind == ListSourceKind.URL


def keep_read(source: ListSource, items, at: int | None = None) -> None:
    """What was read from the source, and when, kept for the next time;
    compressed, a channel list of hundreds of thousands being tens of
    megabytes."""

    if not is_kept(source):
        return

    at = int(time.time()) if at is None else at

    cache.keep(LISTS_DIR, _key(source), _packed(at, tuple(items)))


def kept_read(source: ListSource) -> KeptRead | None:
    """What was read from the source last time, and when, if it is still
    kept."""

    if not is_kept(source):
        return None

    data = cache.cached(LISTS_DIR, _key(source))

    if data is None:
        return None

    try:
        return KeptRead.model_validate_json(zlib.decompress(data))
    except (zlib.error, ValidationError):
        cache.forget(LISTS_DIR, _key(source))
        return None


def _packed(at: int, items: tuple[ListItem, ...]) -> bytes:
    """A KeptRead as JSON, compressed: the items a few thousand at a time,
    a channel list's text being tens of megabytes."""

    packer = zlib.compressobj()
    packed = [packer.compress(b'{"at":%d,"items":[' % at)]

    for start in range(0, len(items), _WRITTEN_AT_ONCE):
        some = items[start : start + _WRITTEN_AT_ONCE]
        text = _ITEMS.dump_json(some, exclude_defaults=True)

        if start:
            packed.append(packer.compress(b","))

        # without the brackets around them
        packed.append(packer.compress(text[1:-1]))

    packed.append(packer.compress(b"]}"))
    packed.append(packer.flush())

    return b"".join(packed)


def _key(source: ListSource) -> str:
    return f"{source.kind.value}:{source.location}"
