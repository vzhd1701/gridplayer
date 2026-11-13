"""The resolvers tried on a link in turn, each asked whether it takes the
link only once those before it could not read it."""

import pytest

from gridplayer.params.static import URLResolver
from gridplayer.utils.url_resolve import url_resolve
from gridplayer.utils.url_resolve.static import NoResolverPlugin

URL = "http://cdn.example/live/master.m3u8"


def _resolver(asked, name, takes=True, result=None):
    class _Resolver:
        def __init__(self, url, headers=None, progress=None): ...

        @staticmethod
        def is_able_to_handle(url):
            asked.append(name)
            return takes

        def resolve(self):
            if result is None:
                raise NoResolverPlugin
            return result

    return _Resolver


@pytest.fixture
def resolvers(mocker):
    mocker.patch.object(url_resolve, "_is_match_youtube", return_value=False)

    def given(*made):
        mocker.patch.object(
            url_resolve,
            "_get_resolvers",
            return_value=dict(zip((URLResolver.STREAMLINK, URLResolver.YT_DLP), made)),
        )

    return given


def test_one_after_the_first_reads_the_link_is_not_asked(resolvers):
    asked = []
    resolvers(
        _resolver(asked, "first", result="resolved"),
        _resolver(asked, "second", result="other"),
    )

    assert url_resolve.resolve_url(URL) == "resolved"
    assert asked == ["first"]


def test_the_next_is_asked_once_the_first_cannot_read_it(resolvers):
    asked = []
    resolvers(
        _resolver(asked, "first"),
        _resolver(asked, "second", result="resolved"),
    )

    assert url_resolve.resolve_url(URL) == "resolved"
    assert asked == ["first", "second"]


def test_one_that_does_not_take_the_link_is_passed_over(resolvers):
    asked = []
    tried = []
    first = _resolver(asked, "first", takes=False, result="never")
    first.resolve = lambda self: tried.append("first")
    resolvers(first, _resolver(asked, "second", result="resolved"))

    assert url_resolve.resolve_url(URL) == "resolved"
    assert asked == ["first", "second"]
    assert tried == []
