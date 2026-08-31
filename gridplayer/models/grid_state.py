from pydantic import BaseModel, Field

from gridplayer.params.static import GridMode
from gridplayer.settings import default_field


class GridCell(BaseModel):
    video_id: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1


class GridState(BaseModel):
    mode: GridMode = default_field("playlist/grid_mode")
    is_fit: bool = default_field("playlist/grid_fit")
    size: int = default_field("playlist/grid_size")
    rows: int = default_field("playlist/grid_rows")
    cols: int = default_field("playlist/grid_cols")
    preallocate: bool = default_field("playlist/grid_preallocate")
    cells: list[GridCell] = Field(default_factory=list)
    video_order: list[str] = Field(default_factory=list)
