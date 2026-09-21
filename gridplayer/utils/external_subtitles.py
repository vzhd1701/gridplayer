"""Subtitle files kept beside a video, to be shown over it.

The same story as the audio files next to a video, and looked for the same
way: nothing in the container knows they exist, and the name is all that
ties them to it. What differs is how many there are. A dubbed film arrives
with one audio file per language, but a subtitled one can arrive with a
dozen, so the language a file is named for is worth reading off the name --
"Movie.en.srt" is English whatever is inside it.

Looking is all this does. A file found here costs nothing until someone
picks it, which is what makes it safe to look on every video in the grid.
"""

import logging
from pathlib import Path

from gridplayer.params.extensions import SUPPORTED_SUBTITLE_EXT
from gridplayer.utils.track_language import language_name, normalize

_log = logging.getLogger(__name__)

# A subtitled release can carry one file per language, which is a longer
# list than a folder of audio dubs ever runs to, so this sits higher than
# the audio side's. Still a limit: a video dropped into a folder of loose
# text files must not come back offering all of it.
MAX_DISCOVERED = 24

# what may stand between the video's name and whatever the subtitles add
SEPARATORS = frozenset(".-_ ")

# A VobSub pair is two files and one subtitle: the .idx carries the index
# and the timings, the .sub the pictures, and VLC has to be handed the .idx.
# Offering both would put a row in the menu that shows nothing.
INDEX_EXT = "idx"
INDEXED_EXT = "sub"


def discover_subtitle_files(video_path: Path) -> list[Path]:
    """The subtitle files named after this video, in the order they are offered.

    The order is the directory's own, by name, so that the same video comes
    back with the same files in the same places every time it is loaded.
    """

    try:
        siblings = sorted(video_path.parent.iterdir(), key=lambda p: p.name.casefold())
    except OSError as exc:
        _log.debug(f"Cannot look beside {video_path}: {exc}")
        return []

    video_name = video_path.name.casefold()

    found = []
    stems_with_index = {
        sibling.stem.casefold()
        for sibling in siblings
        if sibling.suffix[1:].casefold() == INDEX_EXT
    }

    for sibling in siblings:
        if len(found) == MAX_DISCOVERED:
            break

        if sibling.name.casefold() == video_name:
            continue

        extension = sibling.suffix[1:].casefold()

        if extension not in SUPPORTED_SUBTITLE_EXT:
            continue

        # the .idx of the pair is the one to hand over, and it is already
        # in the list under its own name
        if extension == INDEXED_EXT and sibling.stem.casefold() in stems_with_index:
            continue

        if not _is_named_after(sibling, video_path):
            continue

        if not sibling.is_file():
            continue

        found.append(sibling)

    return found


def subtitle_file_label(subtitle_path: Path, video_path: Path | None = None) -> str:
    """What to call this file in a menu.

    The name it has, unless the video's own name is the front of it and a
    language is what was added: "Movie.en.srt" beside "Movie.mkv" reads as
    "English", which is the thing actually worth telling apart in a list of
    a dozen files that begin the same way.
    """

    tag = subtitle_language_tag(subtitle_path, video_path)

    if tag is None:
        return subtitle_path.name

    return language_name(tag) or subtitle_path.name


def subtitle_language_tag(
    subtitle_path: Path, video_path: Path | None = None
) -> str | None:
    """The language this file's name claims, where it claims one.

    Only what was added to the video's own name is read, and only when it
    names a language on its own. "Movie.forced.srt" claims nothing, and
    saying so beats offering the viewer a language called Forced.
    """

    if video_path is None:
        return None

    video_stem = video_path.stem.casefold()
    subtitle_stem = subtitle_path.stem.casefold()

    if not subtitle_stem.startswith(video_stem):
        return None

    added = subtitle_stem[len(video_stem) :].strip("".join(SEPARATORS))

    if not added:
        return None

    # "en", "eng", and "en.forced" all lead with the language, where there
    # is one at all
    for part in added.replace("_", ".").replace("-", ".").split("."):
        if normalize(part) is not None and language_name(part) is not None:
            return part

    return None


def _is_named_after(subtitle_path: Path, video_path: Path) -> bool:
    """Whether this file was named after the video, rather than merely near it.

    "Movie.mkv" is answered by "Movie.srt" and by "Movie.en.srt", since what
    a subtitle track adds it adds to the end. "Movies Vol 2.srt" answers
    nothing: a name that only begins the same way is a different name.
    """

    video_stem = video_path.stem.casefold()
    subtitle_stem = subtitle_path.stem.casefold()

    if subtitle_stem == video_stem:
        return True

    if not subtitle_stem.startswith(video_stem):
        return False

    return subtitle_stem[len(video_stem)] in SEPARATORS
