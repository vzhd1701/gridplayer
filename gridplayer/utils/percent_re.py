"""Two libraries patching the one urllib3 internal, in either order.

Streamlink and yt-dlp each swap urllib3's percent-encoding regex for a
wrapper that leaves the case of a %-escape alone, and each wraps whatever
is there when it is imported. yt-dlp's wrapper passes everything else on
with ``__getattribute__``, which never reaches the ``__getattr__`` that
streamlink's relies on, so with streamlink imported first the pair
answers ``subn`` and nothing else. urllib3 2.8 calls ``sub`` on every
host name, and then not a single request gets made -- yt-dlp's, the
proxy's or a checkup's.

Which of the two comes first is down to whatever the viewer opened
first, so the pair is put right after yt-dlp arrives instead.
"""

import re

import urllib3.util.url

# urllib3's own, which both of them end up wrapping
_PERCENT_ESCAPE = re.compile(r"%[a-fA-F0-9]{2}")


class _KeepPercentCase:
    """What both wrappers set out to be: the regex, minus the upper-casing.

    Some sites compare a URL byte by byte, and urllib3 would otherwise
    rewrite "%2f" as "%2F" on the way out.
    """

    def __getattr__(self, item):
        return getattr(_PERCENT_ESCAPE, item)

    def subn(self, repl, string, count=0):
        return string, len(_PERCENT_ESCAPE.findall(string))


def untangle_percent_re() -> None:
    """Put a working regex back where the two wrappers broke each other.

    Called after importing yt-dlp, which wraps last whenever it comes
    second. Left alone where the pair still works: that is the order
    both of them expect.
    """

    try:
        urllib3.util.url._PERCENT_RE.sub  # noqa: B018
    except (AttributeError, TypeError):
        urllib3.util.url._PERCENT_RE = _KeepPercentCase()
