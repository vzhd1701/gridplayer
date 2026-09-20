"""Audio files kept beside a video, to be played in place of its own sound.

A film ripped once and dubbed later arrives as a video and a pile of audio
files named after it, and the name is the only thing tying them together:
nothing in the container knows they exist, so they have to be looked for.

Looking is all this does. A file found here costs nothing until someone
picks it, which is what makes it safe to look on every video in the grid.
"""

import logging
from pathlib import Path

from gridplayer.params.extensions import SUPPORTED_AUDIO_EXT

_log = logging.getLogger(__name__)

# A directory of loose audio files is not a track list, and this is what
# keeps a video dropped into a music folder from offering all of it.
MAX_DISCOVERED = 8

# What libVLC can really play alongside a video, measured against the VLC
# the app ships with. A file plays as one of the video's own tracks only as
# far as its demuxer will follow the video about:
#
#   mp3 m4a aac flac ac3 wav   played all through, seeking included
#   ogg oga spx                played until the first seek, then silent
#   mka opus                   a track appears, no sound ever comes out
#
# The seek a saved position makes on load counts, so an Ogg file is silent
# from the start on any video that was not opened at the beginning.
UNPLAYABLE_SLAVE_EXT = frozenset({"mka", "opus"})
SEEK_SILENCES_SLAVE_EXT = frozenset({"oga", "ogg", "spx"})


def unplayable_as_audio_slave(file_paths) -> list[Path]:
    """Files that would bring a track no sound ever comes out of."""

    return _with_extension_in(file_paths, UNPLAYABLE_SLAVE_EXT)


def silenced_by_seeking(file_paths) -> list[Path]:
    """Files that play until the video is seeked, and not a sound after."""

    return _with_extension_in(file_paths, SEEK_SILENCES_SLAVE_EXT)


def _with_extension_in(file_paths, extensions) -> list[Path]:
    return [
        file_path
        for file_path in file_paths
        if file_path.suffix[1:].casefold() in extensions
    ]


# what may stand between the video's name and whatever the audio adds to it
SEPARATORS = frozenset(".-_ ")


def discover_audio_files(video_path: Path) -> list[Path]:
    """The audio files named after this video, in the order they are offered.

    The order is the directory's own, by name, so that the same video comes
    back with the same tracks in the same places every time it is loaded.
    """

    try:
        siblings = sorted(video_path.parent.iterdir(), key=lambda p: p.name.casefold())
    except OSError as exc:
        _log.debug(f"Cannot look beside {video_path}: {exc}")
        return []

    video_name = video_path.name.casefold()

    found = []

    for sibling in siblings:
        if len(found) == MAX_DISCOVERED:
            break

        if sibling.name.casefold() == video_name:
            continue

        if sibling.suffix[1:].casefold() not in SUPPORTED_AUDIO_EXT:
            continue

        if not _is_named_after(sibling, video_path):
            continue

        if not sibling.is_file():
            continue

        found.append(sibling)

    return found


def _is_named_after(audio_path: Path, video_path: Path) -> bool:
    """Whether this file was named after the video, rather than merely near it.

    "Movie.mkv" is answered by "Movie.mp3" and by "Movie.rus.ac3", since
    what a dub adds it adds to the end. "Movies Vol 2.mp3" answers nothing:
    a name that only begins the same way is a different name.
    """

    video_stem = video_path.stem.casefold()
    audio_stem = audio_path.stem.casefold()

    if audio_stem == video_stem:
        return True

    if not audio_stem.startswith(video_stem):
        return False

    return audio_stem[len(video_stem)] in SEPARATORS
