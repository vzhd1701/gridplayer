from pydantic import RootModel, field_serializer

from gridplayer.params.static import TileSnap


class TileSnaps(RootModel):
    """What a tile moved or sized in Free Tiles snaps to, the rest left out
    (see TileSnap)."""

    root: frozenset[TileSnap] = frozenset()

    def __contains__(self, snap: TileSnap) -> bool:
        return snap in self.root

    def __iter__(self):
        # those on, as a settings form takes them (see FlagsField)
        return iter(self.root)

    def toggled(self, snap: TileSnap) -> "TileSnaps":
        """The same, with snap turned off if it was on, else on."""

        return TileSnaps(self.root ^ {snap})

    @field_serializer("root")
    def _in_order(self, root: frozenset[TileSnap]) -> list[TileSnap]:
        # saved in the order of the menu, the same every time
        return [snap for snap in TileSnap if snap in root]
