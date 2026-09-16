"""How a playlist entry refers back to the stream it was generated from.

A signed URL written into a playlist is there for good, and VLC asks for the
last segment of a long video hours after the first. Naming the position
instead leaves the proxy free to look up a URL that still works.
"""

from gridplayer.models.stream import Stream

# the stream itself rather than one of its fragments
FRAGMENT_SELF = "self"
FRAGMENT_INIT = "init"


def fragment_stream(stream: Stream, fragment: str) -> Stream:
    """Point a request at one fragment of a stream the proxy keeps track of."""

    url = fragment_url(stream, fragment)

    if url is None:
        raise LookupError(f"Stream has no fragment {fragment}")

    return Stream(url=url, protocol="http", session=stream.session)


def fragment_url(stream: Stream, fragment: str) -> str | None:
    if fragment == FRAGMENT_SELF:
        return stream.url

    if fragment == FRAGMENT_INIT:
        return stream.init_fragment.url if stream.init_fragment else None

    try:
        fragment_idx = int(fragment)
    except ValueError:
        return None

    fragments = stream.fragments or ()

    if not 0 <= fragment_idx < len(fragments):
        return None

    return fragments[fragment_idx].url
