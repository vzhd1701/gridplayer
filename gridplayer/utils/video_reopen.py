from gridplayer.models.video import Video
from gridplayer.params.static import VideoTransform


def is_reopen_needed(old: Video | None, new: Video) -> bool:
    """Whether a change needs the video opened again rather than adjusted.

    What the picture is turned or flipped by and what its subtitles are read
    as are both settled when the file opens.
    """

    if old is None:
        return new.transform != VideoTransform.NONE

    return old.transform != new.transform or (
        old.subtitle_encoding != new.subtitle_encoding
    )
