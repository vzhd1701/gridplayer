"""What a video's sound was chosen to be, in one answer.

A choice of sound is one of six things, and only one of them at a time: let
the file put a track forward, go by the languages asked for, play nothing,
play a track of the video's own, play whichever track carries a language, or
play a file kept beside it. Each is remembered by the one key that outlives
a reload -- a stream renumbers its tracks, a file keeps its name -- so which
key it is says what was meant.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Choice(BaseModel):
    """Values, not records: two of the same choice are the same choice."""

    model_config = ConfigDict(frozen=True)


class AudioDefault(_Choice):
    """Whichever track the file itself marks as the one to play.

    Nothing is asked of libVLC, so it opens the video the way any player
    told nothing would. The languages asked for do not apply here: this is
    how to say "not for this one" without naming a track.
    """

    kind: Literal["default"] = "default"


class AudioPreferred(_Choice):
    """Whichever track answers the languages asked for, or the file's own."""

    kind: Literal["preferred"] = "preferred"


class AudioDisabled(_Choice):
    """No sound at all, which is not the same as muted."""

    kind: Literal["disabled"] = "disabled"


class AudioTrackId(_Choice):
    """One of the video's own tracks, where nothing steadier names it."""

    kind: Literal["track"] = "track"

    id: int


class AudioLanguage(_Choice):
    """The track in this language, for sources that renumber their tracks."""

    kind: Literal["language"] = "language"

    tag: str


class AudioExternal(_Choice):
    """The sound in a file of its own, named by that file.

    Most such files hold one track and ``track`` stays 0. Where one holds
    several, which of them was chosen is part of the choice: the file alone
    would bring the video back on the first of them after every reload.
    """

    kind: Literal["external"] = "external"

    file: Path
    track: int = 0


AudioSelection = Annotated[
    AudioDefault
    | AudioPreferred
    | AudioDisabled
    | AudioTrackId
    | AudioLanguage
    | AudioExternal,
    Field(discriminator="kind"),
]


def track_of_file(selection: AudioExternal, from_file) -> int | None:
    """Which of the tracks a file brought this choice names.

    The first of them where it names one that is not there: a file holding
    fewer tracks than it did is still the file that was chosen, and its
    sound is better than none.
    """

    if not from_file:
        return None

    if selection.track < len(from_file):
        return from_file[selection.track]

    return from_file[0]
