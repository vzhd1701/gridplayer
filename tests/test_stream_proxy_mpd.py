"""Pointing a live DASH manifest back at the proxy.

VLC follows a live manifest itself, so anything in it that still names
the host is a segment fetched without the cookies the manifest needed.
"""

import xml.etree.ElementTree as ET

import pytest

from gridplayer.utils.stream_proxy.mpd import MPD_NS, rewrite_manifest

MANIFEST_URL = "https://host/live/stream/Manifest.mpd"

PROXY = "http://127.0.0.1:9999/dash/"


@pytest.fixture
def proxify():
    """Stands in for the proxy handing out a URL per base it is given."""

    handed_out = {}

    def _proxify(url):
        base_id = handed_out.setdefault(url, f"b{len(handed_out)}")

        return f"{PROXY}{base_id}/"

    _proxify.handed_out = handed_out

    return _proxify


def _mpd(body, root_attrs=""):
    return (
        f'<?xml version="1.0"?>'
        f'<MPD xmlns="{MPD_NS}" type="dynamic"{root_attrs}>{body}</MPD>'
    )


def _find(manifest, tag):
    return ET.fromstring(manifest).iter(f"{{{MPD_NS}}}{tag}")


def _texts(manifest, tag):
    return [element.text for element in _find(manifest, tag)]


def _attrs(manifest, tag, attribute):
    return [element.get(attribute) for element in _find(manifest, tag)]


class TestWhereTheSegmentsAreLookedFor:
    def test_a_manifest_with_no_base_is_given_the_one_it_came_from(self, proxify):
        """Relative names would otherwise resolve against a URL of ours."""

        rewritten = rewrite_manifest(
            _mpd("<Period><AdaptationSet /></Period>"), MANIFEST_URL, proxify
        )

        assert _texts(rewritten, "BaseURL") == [f"{PROXY}b0/"]
        assert list(proxify.handed_out) == ["https://host/live/stream/"]

    def test_the_base_lands_where_a_base_belongs(self, proxify):
        """After the program information, which the schema puts first."""

        rewritten = rewrite_manifest(
            _mpd("<ProgramInformation /><Period />"), MANIFEST_URL, proxify
        )

        tags = [child.tag.rpartition("}")[2] for child in ET.fromstring(rewritten)]

        assert tags == ["ProgramInformation", "BaseURL", "Period"]

    def test_a_relative_base_is_resolved_before_it_is_handed_over(self, proxify):
        rewritten = rewrite_manifest(
            _mpd("<BaseURL>dash/</BaseURL><Period />"), MANIFEST_URL, proxify
        )

        assert _texts(rewritten, "BaseURL") == [f"{PROXY}b0/"]
        assert list(proxify.handed_out) == ["https://host/live/stream/dash/"]

    def test_an_absolute_base_is_replaced_outright(self, proxify):
        rewritten = rewrite_manifest(
            _mpd("<BaseURL>https://cdn/x/</BaseURL><Period />"), MANIFEST_URL, proxify
        )

        assert list(proxify.handed_out) == ["https://cdn/x/"]
        assert _texts(rewritten, "BaseURL") == [f"{PROXY}b0/"]

    def test_a_base_deeper_in_resolves_against_the_one_above_it(self, proxify):
        """An AdaptationSet may sit under a CDN of its own."""

        rewritten = rewrite_manifest(
            _mpd(
                "<BaseURL>https://cdn/x/</BaseURL>"
                "<Period><AdaptationSet><BaseURL>v/</BaseURL></AdaptationSet></Period>"
            ),
            MANIFEST_URL,
            proxify,
        )

        assert list(proxify.handed_out) == ["https://cdn/x/", "https://cdn/x/v/"]
        assert _texts(rewritten, "BaseURL") == [f"{PROXY}b0/", f"{PROXY}b1/"]

    def test_every_alternative_base_is_rewritten(self, proxify):
        """One host left alone is one host fetched from without a cookie."""

        rewritten = rewrite_manifest(
            _mpd(
                "<BaseURL>https://cdn1/</BaseURL><BaseURL>https://cdn2/</BaseURL>"
                "<Period />"
            ),
            MANIFEST_URL,
            proxify,
        )

        assert _texts(rewritten, "BaseURL") == [f"{PROXY}b0/", f"{PROXY}b1/"]


class TestTheNamesSegmentsAreBuiltFrom:
    def test_a_relative_template_is_left_for_the_base_to_answer(self, proxify):
        """It resolves against a BaseURL that points here already."""

        template = '<SegmentTemplate media="$RepresentationID$/$Number$.m4s" />'

        rewritten = rewrite_manifest(
            _mpd(f"<Period><AdaptationSet>{template}</AdaptationSet></Period>"),
            MANIFEST_URL,
            proxify,
        )

        assert _attrs(rewritten, "SegmentTemplate", "media") == [
            "$RepresentationID$/$Number$.m4s"
        ]

    def test_an_absolute_template_keeps_its_placeholders(self, proxify):
        """Only the player can fill them in, so only the host part moves."""

        template = (
            '<SegmentTemplate media="https://cdn/x/$RepresentationID$/$Number$.m4s" />'
        )

        rewritten = rewrite_manifest(
            _mpd(f"<Period><AdaptationSet>{template}</AdaptationSet></Period>"),
            MANIFEST_URL,
            proxify,
        )

        assert _attrs(rewritten, "SegmentTemplate", "media") == [
            f"{PROXY}b0/$RepresentationID$/$Number$.m4s"
        ]
        assert "https://cdn/x/" in proxify.handed_out

    def test_an_absolute_initialization_is_rewritten_too(self, proxify):
        template = '<SegmentTemplate initialization="https://cdn/x/init.mp4" />'

        rewritten = rewrite_manifest(
            _mpd(f"<Period><AdaptationSet>{template}</AdaptationSet></Period>"),
            MANIFEST_URL,
            proxify,
        )

        assert _attrs(rewritten, "SegmentTemplate", "initialization") == [
            f"{PROXY}b0/init.mp4"
        ]

    def test_a_segment_list_is_reached_though_it_sits_a_level_down(self, proxify):
        """SegmentURL hangs off SegmentList, not off the AdaptationSet."""

        segments = (
            "<SegmentList>"
            '<SegmentURL media="https://cdn/x/0.m4s" />'
            '<SegmentURL media="https://cdn/x/1.m4s" />'
            "</SegmentList>"
        )

        rewritten = rewrite_manifest(
            _mpd(f"<Period><AdaptationSet>{segments}</AdaptationSet></Period>"),
            MANIFEST_URL,
            proxify,
        )

        assert _attrs(rewritten, "SegmentURL", "media") == [
            f"{PROXY}b0/0.m4s",
            f"{PROXY}b0/1.m4s",
        ]


class TestWhatTheManifestSaysAboutItself:
    def test_the_offer_of_somewhere_else_is_taken_away(self, proxify):
        """A player that took it would ask the host for the updates."""

        rewritten = rewrite_manifest(
            _mpd("<Location>https://host/live/other.mpd</Location><Period />"),
            MANIFEST_URL,
            proxify,
        )

        assert _texts(rewritten, "Location") == []

    def test_how_often_to_come_back_is_left_alone(self, proxify):
        """Dropping it would leave VLC playing a window that never moves."""

        rewritten = rewrite_manifest(
            _mpd("<Period />", root_attrs=' minimumUpdatePeriod="PT2S"'),
            MANIFEST_URL,
            proxify,
        )

        assert ET.fromstring(rewritten).get("minimumUpdatePeriod") == "PT2S"

    def test_it_is_still_a_manifest_in_its_own_namespace(self, proxify):
        """Written back under a prefix, VLC would not know what it was."""

        rewritten = rewrite_manifest(_mpd("<Period />"), MANIFEST_URL, proxify)

        assert f'xmlns="{MPD_NS}"' in rewritten
        assert ET.fromstring(rewritten).tag == f"{{{MPD_NS}}}MPD"
