from pydantic import BaseModel

from gridplayer.params_static import GridMode
from gridplayer.settings import default_field


class GridState(BaseModel):
    mode: GridMode = default_field("playlist/grid_mode")
    is_fit: bool = default_field("playlist/grid_fit")
    size: int = default_field("playlist/grid_size")
