from enum import Enum, auto

from gridplayer.params.static import GridMode


class DropZone(Enum):
    BEFORE = auto()
    CENTER = auto()
    AFTER = auto()
    ABOVE = auto()
    BELOW = auto()


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

    if grid_mode == GridMode.FIXED:
        return _zone_at_fixed(x, y, width, height)

    t = y / height if grid_mode == GridMode.AUTO_COLS else x / width

    if t < 1 / 3:
        return DropZone.BEFORE
    if t > 2 / 3:
        return DropZone.AFTER
    return DropZone.CENTER


def _zone_at_fixed(x: float, y: float, width: float, height: float) -> DropZone:
    nx = x / width
    ny = y / height
    inner = 0.25

    if inner <= nx <= 1 - inner and inner <= ny <= 1 - inner:
        return DropZone.CENTER

    dist_left = inner - nx
    dist_right = nx - (1 - inner)
    dist_top = inner - ny
    dist_bottom = ny - (1 - inner)
    return max(
        (
            (dist_left, DropZone.BEFORE),
            (dist_right, DropZone.AFTER),
            (dist_top, DropZone.ABOVE),
            (dist_bottom, DropZone.BELOW),
        ),
        key=lambda item: item[0],
    )[1]


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
    if is_replace and zone is not None:
        return DropIndicator.REPLACE
    if zone == DropZone.CENTER:
        return DropIndicator.SWAP if is_internal else DropIndicator.DOT
    if zone == DropZone.ABOVE:
        return DropIndicator.ARROW_UP
    if zone == DropZone.BELOW:
        return DropIndicator.ARROW_DOWN
    if zone == DropZone.BEFORE:
        if grid_mode == GridMode.AUTO_COLS:
            return DropIndicator.ARROW_UP
        return DropIndicator.ARROW_LEFT
    if zone == DropZone.AFTER:
        if grid_mode == GridMode.AUTO_COLS:
            return DropIndicator.ARROW_DOWN
        return DropIndicator.ARROW_RIGHT

    return DropIndicator.NONE
