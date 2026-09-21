"""What a video's subtitles were chosen to be, in one answer.

The same shape as a choice of sound, and for the same reason: a pick has to
survive a reload, and only the key it was made by can be trusted to carry it
there. A stream renumbers its tracks between one pass and the next, a file
keeps its name, so which key was used is what says what was meant.

Where this differs from sound is where it starts. Sound has to come from
somewhere, so "whichever track the file puts forward" is the sensible place
to begin; subtitles are off until someone asks for them, and every video
begins on ``SubtitleDisabled``.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Choice(BaseModel):
    """Values, not records: two of the same choice are the same choice."""

    model_config = ConfigDict(frozen=True)


class SubtitleDisabled(_Choice):
    """Nothing shown, which is where every video starts.

    Not the same as having nothing to show. A video with subtitles in it
    still offers them; this says they were not asked for.
    """

    kind: Literal["disabled"] = "disabled"


class SubtitlePreferred(_Choice):
    """Whichever track answers the languages asked for.

    Nothing where none of them does: a subtitle in a language that was not
    asked for is worse than none, unlike a sound track, where anything
    audible beats silence.
    """

    kind: Literal["preferred"] = "preferred"


class SubtitleDefault(_Choice):
    """Whichever track the container marks default or forced.

    What a player that was told nothing would show, and the only way to
    get the forced captions on a film that carries them for its subtitled
    passages alone.
    """

    kind: Literal["default"] = "default"


class SubtitleTrackId(_Choice):
    """One of the video's own tracks, where nothing steadier names it."""

    kind: Literal["track"] = "track"

    id: int


class SubtitleLanguage(_Choice):
    """The track in this language, for sources that renumber their tracks."""

    kind: Literal["language"] = "language"

    tag: str


class SubtitleExternal(_Choice):
    """The subtitles in a file of its own, named by that file.

    Most such files hold one track and ``track`` stays 0. Where one holds
    several, which of them was chosen is part of the choice: the file alone
    would bring the video back on the first of them after every reload.
    """

    kind: Literal["external"] = "external"

    file: Path
    track: int = 0


SubtitleSelection = Annotated[
    SubtitleDisabled
    | SubtitlePreferred
    | SubtitleDefault
    | SubtitleTrackId
    | SubtitleLanguage
    | SubtitleExternal,
    Field(discriminator="kind"),
]


def track_of_file(selection: SubtitleExternal, from_file) -> int | None:
    """Which of the tracks a file brought this choice names.

    The first of them where it names one that is not there: a file holding
    fewer tracks than it did is still the file that was chosen, and its
    subtitles are better than none.
    """

    if not from_file:
        return None

    if selection.track < len(from_file):
        return from_file[selection.track]

    return from_file[0]
