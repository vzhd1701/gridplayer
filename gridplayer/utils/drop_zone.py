from enum import Enum, auto

from gridplayer.params.static import GridMode


class DropZone(Enum):
    BEFORE = auto()
    CENTER = auto()
    AFTER = auto()


class DropIndicator(Enum):
    NONE = auto()
    ARROW_LEFT = auto()
    ARROW_RIGHT = auto()
    ARROW_UP = auto()
    ARROW_DOWN = auto()
    SWAP = auto()
    DOT = auto()
    REPLACE = auto()
    SOURCE = auto()


def zone_at(
    x: float,
    y: float,
    width: float,
    height: float,
    grid_mode: GridMode,
) -> DropZone | None:
    """Return the drop zone for a point inside a block, or None if outside."""
    if width <= 0 or height <= 0:
        return None
    if not (0 <= x <= width and 0 <= y <= height):
        return None

    t = y / height if grid_mode == GridMode.AUTO_COLS else x / width

    if t < 1 / 3:
        return DropZone.BEFORE
    if t > 2 / 3:
        return DropZone.AFTER
    return DropZone.CENTER


def insert_index(dst_index: int, zone: DropZone) -> int:
    if zone == DropZone.AFTER:
        return dst_index + 1
    return dst_index


def indicator_for(
    zone: DropZone | None,
    is_internal: bool,
    grid_mode: GridMode,
    is_replace: bool = False,
) -> DropIndicator:
    if zone is None:
        return DropIndicator.NONE
    if is_replace:
        return DropIndicator.REPLACE
    if zone == DropZone.CENTER:
        return DropIndicator.SWAP if is_internal else DropIndicator.DOT
    if zone == DropZone.BEFORE:
        return (
            DropIndicator.ARROW_UP
            if grid_mode == GridMode.AUTO_COLS
            else DropIndicator.ARROW_LEFT
        )
    return (
        DropIndicator.ARROW_DOWN
        if grid_mode == GridMode.AUTO_COLS
        else DropIndicator.ARROW_RIGHT
    )
