"""A track picked by its number, where nothing steadier names it."""

from pydantic import BaseModel, ConfigDict


class TrackNumber(BaseModel):
    """An id means nothing to another driver, the way each counts them. How many of
    the tracks of its kind come before it means the same to all: None in a playlist
    from before it was kept.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    position: int | None = None

    @classmethod
    def of(cls, track_id: int, tracks):
        """For this one of these tracks, which may not be listed yet."""

        track_ids = list(tracks)

        return cls(
            id=track_id,
            position=track_ids.index(track_id) if track_id in track_ids else None,
        )

    def track_in(self, tracks) -> int | None:
        """Which of these tracks this names, None if it's not one of them."""

        track_ids = list(tracks)

        if self.position is not None and self.position < len(track_ids):
            return track_ids[self.position]

        return self.id if self.id in track_ids else None
