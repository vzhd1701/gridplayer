"""Minimal ISO-BMFF reader used to segment a single fragmented MP4 file.

VLC can only pair separate audio & video through HLS, and an HLS playlist
that points at a whole file as one segment makes every seek re-download it
from the start. Fragmented MP4 files published for DASH carry a ``sidx``
index, which maps playback time to byte ranges -- exactly what
``#EXT-X-BYTERANGE`` needs.
"""

import logging
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from typing import NamedTuple

from gridplayer.models.stream import StreamFragment

_log = logging.getLogger(__name__)

BOX_HEADER_SIZE = 8
LARGE_SIZE_HEADER = 16
LARGE_SIZE_MARKER = 1

# moov of a fragmented file holds no sample tables, so the index sits early on
INDEX_PROBE_SIZE = 256 * 1024
INDEX_PROBE_SIZE_MAX = 2 * 1024 * 1024

# a plain file keeps all of its samples in one mdat, a fragmented one
# announces its pieces up front
FRAGMENT_MARKERS = frozenset({b"sidx", b"styp", b"moof"})


class Box(NamedTuple):
    type: bytes
    offset: int
    size: int
    header_size: int


class Segment(NamedTuple):
    offset: int
    size: int
    duration: float


@dataclass(frozen=True)
class SegmentIndex:
    init_size: int
    segments: list[Segment]

    def as_fragments(self, url: str) -> tuple[StreamFragment, ...]:
        return tuple(
            StreamFragment(
                url=url,
                duration=segment.duration,
                byterange=f"{segment.size}@{segment.offset}",
            )
            for segment in self.segments
        )

    def as_init_fragment(self, url: str) -> StreamFragment:
        return StreamFragment(url=url, byterange=f"{self.init_size}@0")


def parse_segment_index(head: bytes) -> SegmentIndex | None:
    """Locate the ``sidx`` box in a file header and expand it into segments.

    Returns None when the header holds no usable index, in which case the
    caller has to fall back to treating the whole file as one segment.
    """

    try:
        return _parse_segment_index(head)
    except (struct.error, IndexError, ValueError, ZeroDivisionError) as err:
        _log.debug(f"Failed to parse segment index: {err}")
        return None


def is_fragmented(head: bytes) -> bool:
    """Tell whether a file is cut into fragments, judging by its header.

    VLC can only demux a fragmented file out of a playlist we build, so a
    plain one must not be offered as a segment.
    """

    try:
        return any(box.type in FRAGMENT_MARKERS for box in _iter_boxes(head))
    except struct.error as err:
        _log.debug(f"Failed to read file header: {err}")
        return False


def _iter_boxes(head: bytes) -> Iterator[Box]:
    offset = 0

    while offset + BOX_HEADER_SIZE <= len(head):
        box = _read_box_header(head, offset)

        yield box

        if box.size <= 0:
            return

        offset += box.size


def _parse_segment_index(head: bytes) -> SegmentIndex | None:
    for box in _iter_boxes(head):
        if box.type != b"sidx":
            continue

        if box.offset + box.size > len(head):
            return None

        return _parse_sidx(head, box)

    return None


def _read_box_header(data: bytes, offset: int) -> Box:
    box_size = struct.unpack_from(">I", data, offset)[0]
    box_type = data[offset + 4 : offset + 8]

    header_size = BOX_HEADER_SIZE

    if box_size == LARGE_SIZE_MARKER:
        box_size = struct.unpack_from(">Q", data, offset + 8)[0]
        header_size = LARGE_SIZE_HEADER

    return Box(type=box_type, offset=offset, size=box_size, header_size=header_size)


def _parse_sidx(data: bytes, box: Box) -> SegmentIndex | None:
    cursor = box.offset + box.header_size

    version = data[cursor]
    cursor += 4  # version + flags

    _reference_id, timescale = struct.unpack_from(">II", data, cursor)
    cursor += 8

    if not timescale:
        return None

    if version == 0:
        _earliest_pts, first_offset = struct.unpack_from(">II", data, cursor)
        cursor += 8
    else:
        _earliest_pts, first_offset = struct.unpack_from(">QQ", data, cursor)
        cursor += 16

    cursor += 2  # reserved
    reference_count = struct.unpack_from(">H", data, cursor)[0]
    cursor += 2

    # references are relative to the first byte after the sidx box
    segment_offset = box.offset + box.size + first_offset

    segments = []
    for _ in range(reference_count):
        reference, subsegment_duration, _flags = struct.unpack_from(
            ">III", data, cursor
        )
        cursor += 12

        is_reference_to_index = bool(reference >> 31)
        reference_size = reference & 0x7FFFFFFF

        if is_reference_to_index:
            # nested index, not worth chasing - fall back to a single segment
            return None

        segments.append(
            Segment(
                offset=segment_offset,
                size=reference_size,
                duration=subsegment_duration / timescale,
            )
        )
        segment_offset += reference_size

    if not segments:
        return None

    return SegmentIndex(init_size=box.offset, segments=segments)
