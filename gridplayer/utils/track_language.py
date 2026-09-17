"""Matching audio tracks against the languages a user asked for.

Every source spells a language its own way: libVLC reports whatever the
container says ("eng", "English", ""), yt-dlp reports BCP-47 ("en",
"es-419"), and an HLS manifest reports whatever the packager wrote. A
preference typed by hand is a fourth spelling again, so nothing can be
compared until it has all been reduced to one form.
"""

import re

from pycountry import languages

# what a source says when it has no language to report, which must never
# satisfy a preference: an untagged track is not a track in any language
UNDETERMINED = frozenset({"und", "zxx", "mis", "mul"})

# users separate their languages however they please
_SEPARATORS = re.compile(r"[,;/|]+|\s+")

# "en-US", "pt_BR" and "zh-Hant-TW" all name a language with trimmings
_SUBTAG = re.compile(r"[-_]")


def parse_preferences(preferences: str) -> tuple[str, ...]:
    """Read a preference list the way it was typed into a text box."""

    tags = (canonical_tag(tag) for tag in _SEPARATORS.split(preferences))

    return tuple(dict.fromkeys(tag for tag in tags if tag))


def canonical_tag(tag: str | None) -> str:
    """The tag as written, in the one casing and separator it is compared in."""

    if not tag:
        return ""

    return tag.strip().lower().replace("_", "-")


def normalize(tag: str | None) -> str | None:
    """Reduce a tag to the language it names, dropping region and script.

    Returns nothing for a tag that names no language, either because the
    source had none to give or because it is not a language code at all.
    """

    base = _SUBTAG.split(canonical_tag(tag), maxsplit=1)[0]

    if not base or base in UNDETERMINED:
        return None

    language = _lookup(base)

    if language is None:
        # not a code we know, but two spellings of the same unknown thing
        # still deserve to match each other
        return base

    if language.alpha_3 in UNDETERMINED:
        return None

    return getattr(language, "alpha_2", None) or language.alpha_3


def language_name(tag: str | None) -> str | None:
    """What to call this language on screen, where it can be named at all."""

    base = _SUBTAG.split(canonical_tag(tag), maxsplit=1)[0]

    if not base or base in UNDETERMINED:
        return None

    language = _lookup(base)

    return language.name if language is not None else None


def pick_by_language(
    preferences: tuple[str, ...], candidates: list[tuple[object, str | None]]
) -> object | None:
    """Choose the candidate the user would have picked themselves.

    Candidates are (key, language tag) pairs in the order the source
    offered them. The preference list is walked first, so that a later
    candidate in the user's favourite language beats an earlier one in
    their second choice.
    """

    # a tag written out in full outranks the language it belongs to, so
    # that "en-GB" is answered with British English where there is some
    exact = _index(candidates, canonical_tag)
    by_language = _index(candidates, normalize)

    for preference in preferences:
        for index, key in ((exact, canonical_tag), (by_language, normalize)):
            match = index.get(key(preference))

            if match is not None:
                return match

    return None


def pick_track(preferences: str, tracks: dict) -> object | None:
    """Choose a track out of a map of them, by the languages asked for.

    Tracks are anything with a ``language``: the ones libVLC found in a
    file, or the renditions a site offered alongside a video.
    """

    return pick_by_language(
        parse_preferences(preferences),
        [(key, track.language) for key, track in tracks.items()],
    )


def _index(candidates, key) -> dict:
    """Map each spelling to the first candidate that answers to it."""

    index = {}

    for candidate_key, tag in candidates:
        tag_key = key(tag)

        if tag_key:
            index.setdefault(tag_key, candidate_key)

    return index


def _lookup(code: str):
    """Find a language by any of the codes it is known by.

    pycountry's own ``lookup`` searches names as well, which makes it
    answer "en" with En, a language of Myanmar, instead of English.
    """

    return (
        languages.get(alpha_2=code)
        or languages.get(alpha_3=code)
        or languages.get(bibliographic=code)
        # containers sometimes carry the name where a code belongs
        or languages.get(name=code.title())
    )
