from pydantic import BaseModel, Field

from gridplayer.params.static import GridMode
from gridplayer.settings import default_field


class GridCell(BaseModel):
    video_id: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1


class GridTile(BaseModel):
    """A video's tile in Free Tiles: its edges as shares of the page,
    left, top, right and bottom."""

    video_id: str
    box: list[float]


class GridState(BaseModel):
    mode: GridMode = default_field("playlist/grid_mode")
    is_fit: bool = default_field("playlist/grid_fit")
    is_match_shapes: bool = default_field("playlist/grid_match_shapes")
    crop: int = default_field("playlist/grid_crop")
    is_reordered: bool = default_field("playlist/grid_reorder")
    is_linked: bool = default_field("playlist/grid_link")
    size: int = default_field("playlist/grid_size")
    rows: int = default_field("playlist/grid_rows")
    cols: int = default_field("playlist/grid_cols")
    preallocate: bool = default_field("playlist/grid_preallocate")
    cells: list[GridCell] = Field(default_factory=list)
    video_order: list[str] = Field(default_factory=list)
    # in Fit Shapes, how many steps bigger videos are made (smaller, less
    # than nought), by id
    sizes: dict[str, int] = Field(default_factory=dict)
    # the lines between the cells moved by hand: each column's share of the
    # width, each row's of the height, and of a row with lines of its own,
    # each video's share of it, by the row (see Weights)
    col_weights: list[float] = Field(default_factory=list)
    row_weights: list[float] = Field(default_factory=list)
    line_weights: list[list[float]] = Field(default_factory=list)
    # in Single Mode, the strip's share of the window, moved by hand
    strip_share: float | None = None
    # in Free Tiles, the videos' tiles, the one in front last; and the
    # page's width over its height (see FreeTiles)
    tiles: list[GridTile] = Field(default_factory=list)
    page_shape: float | None = None
