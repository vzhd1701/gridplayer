"""Streamlink and yt-dlp both wrapping urllib3's percent regex.

Each order they are imported in has to leave urllib3 a regex that works,
and no request a URL with its escapes upper-cased. Which order it is
depends on what was opened first, so each is tried in an interpreter of
its own: an import happens only once.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from gridplayer.utils.percent_re import _KeepPercentCase

PACKAGE_DIR = Path(__file__).parent.parent / "gridplayer"

URL = "https://rr1---sn-x.googlevideo.com/videoplayback?sig=a%2fb"

# asks urllib3 everything the two wrappers are there for
PROBE = f"""
import urllib3.util.url
import requests

percent_re = urllib3.util.url._PERCENT_RE

assert percent_re.sub(lambda m: m.group(0).upper(), "x%2fy") == "x%2Fy"
assert percent_re.subn(lambda m: m.group(0).upper(), "x%2fy") == ("x%2fy", 1)
assert requests.Request("GET", {URL!r}).prepare().url == {URL!r}
"""

YT_DLP_IMPORT = re.compile(r"^\s*(?:from|import) yt_dlp\b", re.MULTILINE)


def _run(imports: str):
    result = subprocess.run(
        [sys.executable, "-c", imports + PROBE],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "module",
    [
        "gridplayer.utils.js_runtime",
        "gridplayer.utils.url_resolve.resolver_yt_dlp",
        "gridplayer.utils.ytdlp_checkup",
    ],
)
def test_yt_dlp_arriving_after_streamlink_still_leaves_requests_working(module):
    """The checkup's own order: it imports streamlink on the line before."""

    _run(f"import streamlink.session\nimport {module}\n")


def test_telling_youtube_links_apart_leaves_requests_working():
    _run(
        "import streamlink.session\n"
        "from gridplayer.utils.url_resolve.url_resolve import _is_match_youtube\n"
        "_is_match_youtube('https://www.youtube.com/watch?v=aqz-KE-bpKQ')\n"
    )


def test_a_wrapper_that_works_is_left_alone():
    """yt-dlp's own, where nothing got to urllib3 before it."""

    _run(
        "import gridplayer.utils.js_runtime\n"
        "import urllib3.util.url\n"
        "from gridplayer.utils.percent_re import _KeepPercentCase\n"
        "assert not isinstance(urllib3.util.url._PERCENT_RE, _KeepPercentCase)\n"
    )


def test_every_import_of_yt_dlp_is_followed_by_the_repair():
    """One left out is enough to break every request after it runs."""

    missing = [
        path.relative_to(PACKAGE_DIR).as_posix()
        for path in PACKAGE_DIR.rglob("*.py")
        if YT_DLP_IMPORT.search(text := path.read_text(encoding="utf-8"))
        and "untangle_percent_re()" not in text
    ]

    assert missing == []


def test_the_repair_keeps_the_case_of_escapes():
    percent_re = _KeepPercentCase()

    assert percent_re.subn(str.upper, "a%2fb%3D") == ("a%2fb%3D", 2)
    assert percent_re.findall("a%2fb") == ["%2f"]
