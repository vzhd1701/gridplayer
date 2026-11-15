"""A live DASH manifest read for what's out now, as the proxy serves it to mpv as live
HLS: which segments, numbered so that each keeps its number from one reading to the
next, the representation picked, and the playlist written of them."""

from datetime import datetime, timedelta, timezone

import pytest

from gridplayer.utils.stream_proxy import dash_live
from gridplayer.utils.stream_proxy.dash_live import MIN_SEGMENTS, LiveManifest
from gridplayer.utils.stream_proxy.m3u8 import build_live_media_playlist

STARTED = datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc)

URL = "https://cdn.example/live/manifest.mpd"


def _mpd(body: str, kind="dynamic", extra="") -> str:
    return f"""<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="{kind}"
     availabilityStartTime="2026-11-15T12:00:00Z" {extra}>
  <Period id="0" start="PT0S">{body}</Period>
</MPD>"""


NUMBERED = _mpd(
    """
    <AdaptationSet contentType="video">
      <SegmentTemplate timescale="1000" duration="2000" startNumber="1"
          initialization="$RepresentationID$/init.mp4"
          media="$RepresentationID$/$Number%05d$.m4s"/>
      <Representation id="v720" bandwidth="3000000" height="720"/>
      <Representation id="v360" bandwidth="800000" height="360"/>
      <Representation id="v1080" bandwidth="6000000" height="1080"/>
    </AdaptationSet>
    <AdaptationSet contentType="audio" lang="es">
      <SegmentTemplate timescale="48000" duration="96000"
          initialization="$RepresentationID$/init.mp4"
          media="$RepresentationID$/$Number$.m4s"/>
      <Representation id="a_es" bandwidth="128000"/>
    </AdaptationSet>
    <AdaptationSet contentType="audio" lang="en">
      <Role schemeIdUri="urn:mpeg:dash:role:2011" value="main"/>
      <SegmentTemplate timescale="48000" duration="96000"
          initialization="$RepresentationID$/init.mp4"
          media="$RepresentationID$/$Number$.m4s"/>
      <Representation id="a_en" bandwidth="96000"/>
      <Representation id="a_en_hi" bandwidth="192000"/>
    </AdaptationSet>
    """,
    extra='timeShiftBufferDepth="PT10S"',
)


def _at(seconds: float, text: str = NUMBERED) -> LiveManifest:
    return LiveManifest(text, URL, STARTED + timedelta(seconds=seconds))


class TestNumbered:
    def test_only_what_has_ended_is_out(self):
        window = _at(21).window("v720")

        # 10 segments of 2 s have ended by 21 s, the 11th not yet
        assert window.segments[-1].url == "https://cdn.example/live/v720/00010.m4s"

    def test_back_as_far_as_the_manifest_keeps(self):
        window = _at(21).window("v720")

        assert [s.sequence for s in window.segments] == [6, 7, 8, 9, 10]

    def test_each_keeps_its_number_read_again(self):
        first = {s.url: s.sequence for s in _at(21).window("v720").segments}
        later = {s.url: s.sequence for s in _at(25).window("v720").segments}

        assert all(later[url] == first[url] for url in first.keys() & later.keys())

    def test_nothing_out_at_the_start(self):
        assert _at(1).window("v720").segments == ()

    def test_its_init_segment(self):
        assert (
            _at(21).window("v720").init_url == "https://cdn.example/live/v720/init.mp4"
        )

    def test_its_lengths(self):
        assert {s.duration for s in _at(21).window("a_en").segments} == {2.0}

    def test_still_going(self):
        assert not _at(21).window("v720").is_over

    def test_out_a_little_early_where_it_says_so(self):
        text = NUMBERED.replace(
            'duration="2000" startNumber="1"',
            'duration="2000" startNumber="1" availabilityTimeOffset="1.5"',
        )

        assert _at(20.6, text).window("v720").segments[-1].sequence == 11
        assert _at(20.6).window("v720").segments[-1].sequence == 10


class TestPicked:
    def test_the_best_video_that_fits(self):
        assert _at(21).pick("video", max_height=800).id == "v720"

    def test_the_best_with_nothing_said(self):
        assert _at(21).pick("video").id == "v1080"

    def test_the_smallest_where_none_fits(self):
        assert _at(21).pick("video", max_height=200).id == "v360"

    def test_the_first_language_asked_for_that_there_is(self):
        assert _at(21).pick("audio", languages=("fr", "es", "en")).id == "a_es"

    def test_the_sound_in_the_language_asked_for(self):
        assert _at(21).pick("audio", languages=("es-es",)).id == "a_es"

    def test_else_the_main_sound_the_best_of_it(self):
        assert _at(21).pick("audio", languages=("fr",)).id == "a_en_hi"

    def test_none_of_a_kind_not_there(self):
        assert _at(21).pick("text") is None

    def test_an_unknown_representation(self):
        with pytest.raises(LookupError):
            _at(21).window("v4k")


TIMED = _mpd(
    """
    <AdaptationSet mimeType="video/mp4">
      <SegmentTemplate timescale="90000" presentationTimeOffset="900000"
          initialization="init-$RepresentationID$.mp4"
          media="seg-$RepresentationID$-$Time$.mp4">
        <SegmentTimeline>
          <S t="900000" d="180000" r="2"/>
          <S d="179000"/>
          <S d="181000" r="-1"/>
        </SegmentTimeline>
      </SegmentTemplate>
      <Representation id="v" bandwidth="1000000" height="480"/>
    </AdaptationSet>
    """
)


class TestTimeline:
    def test_named_by_their_time(self):
        urls = [s.url.rsplit("/", 1)[1] for s in _at(11, TIMED).window("v").segments]

        assert urls[:5] == [
            "seg-v-900000.mp4",
            "seg-v-1080000.mp4",
            "seg-v-1260000.mp4",
            "seg-v-1440000.mp4",
            "seg-v-1619000.mp4",
        ]

    def test_repeated_up_to_now(self):
        # 2 s each from the start: by 9 s, four have ended
        assert len(_at(9, TIMED).window("v").segments) == 4

    def test_numbered_by_their_time_read_again(self):
        first = {s.url: s.sequence for s in _at(9, TIMED).window("v").segments}
        later = {s.url: s.sequence for s in _at(15, TIMED).window("v").segments}

        assert all(later[url] == first[url] for url in first.keys() & later.keys())
        assert sorted(later.values()) == list(range(min(later.values()), 7))

    def test_their_lengths(self):
        lengths = [s.duration for s in _at(9, TIMED).window("v").segments]

        assert lengths == pytest.approx([2.0, 2.0, 2.0, 179000 / 90000])

    def test_numbered_where_the_template_takes_a_number(self):
        text = TIMED.replace("seg-$RepresentationID$-$Time$", "n-$Number$").replace(
            'presentationTimeOffset="900000"',
            'presentationTimeOffset="900000" startNumber="40"',
        )

        segments = _at(9, text).window("v").segments

        assert [s.sequence for s in segments] == [40, 41, 42, 43]
        assert segments[0].url.endswith("/n-40.mp4")


class TestWhere:
    def test_each_level_s_base(self):
        text = """<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="dynamic"
     availabilityStartTime="2026-11-15T12:00:00Z">
  <BaseURL>https://other.example/root/</BaseURL>
  <Period start="PT0S">
    <BaseURL>period/</BaseURL>
    <AdaptationSet contentType="video">
      <BaseURL>set/</BaseURL>
      <Representation id="v" bandwidth="1" height="1">
        <BaseURL>rep/</BaseURL>
        <SegmentTemplate duration="2" media="$Number$.mp4"/>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""

        segment = _at(5, text).window("v").segments[-1]

        assert segment.url == "https://other.example/root/period/set/rep/2.mp4"

    def test_a_segment_list(self):
        text = _mpd(
            """
            <AdaptationSet contentType="audio">
              <Representation id="a" bandwidth="1">
                <SegmentList timescale="10" duration="40" startNumber="7">
                  <Initialization sourceURL="init.mp4"/>
                  <SegmentURL media="a.mp4"/>
                  <SegmentURL media="b.mp4"/>
                </SegmentList>
              </Representation>
            </AdaptationSet>
            """
        )

        window = _at(9, text).window("a")

        assert window.init_url == "https://cdn.example/live/init.mp4"
        assert [(s.url[-5:], s.sequence) for s in window.segments] == [
            ("a.mp4", 7),
            ("b.mp4", 8),
        ]


def test_over_once_the_manifest_is_static():
    text = NUMBERED.replace('type="dynamic"', 'type="static"').replace(
        "<MPD ", '<MPD mediaPresentationDuration="PT8S" '
    )

    window = _at(500, text).window("v720")

    assert window.is_over
    assert [s.sequence for s in window.segments] == [1, 2, 3, 4]


class TestPlaylist:
    def test_live_has_no_end(self):
        playlist = build_live_media_playlist([("a", 2.0)], first_sequence=6)

        assert "#EXT-X-ENDLIST" not in playlist
        assert "#EXT-X-MEDIA-SEQUENCE:6" in playlist

    def test_with_its_init_segment(self):
        playlist = build_live_media_playlist(
            [("a", 2.0)], first_sequence=1, init_url="init"
        )

        assert '#EXT-X-MAP:URI="init"' in playlist

    def test_over_has_its_end(self):
        playlist = build_live_media_playlist([("a", 2.0)], 1, is_over=True)

        assert playlist.endswith("#EXT-X-ENDLIST")


class TestShortWindows:
    def test_never_fewer_than_a_few_however_short_it_keeps_them(self):
        text = NUMBERED.replace('"PT10S"', '"PT1S"')

        assert len(_at(21, text).window("v720").segments) == MIN_SEGMENTS

    def test_a_window_written_with_years_and_months(self):
        text = NUMBERED.replace('"PT10S"', '"P0Y0M0DT0H0M10S"')

        assert [s.sequence for s in _at(21, text).window("v720").segments] == [
            6,
            7,
            8,
            9,
            10,
        ]

    def test_a_timeline_s_too(self):
        text = TIMED.replace("<MPD ", '<MPD timeShiftBufferDepth="PT1S" ')

        assert len(_at(15, text).window("v").segments) == MIN_SEGMENTS


def test_a_start_with_a_fraction_python_3_10_reads_too():
    text = NUMBERED.replace("12:00:00Z", "12:00:00.5Z")

    assert _at(21.5, text).window("v720").segments[-1].sequence == 10


def test_a_timeline_repeated_for_days_is_counted_past():
    days = 3 * 86400
    text = TIMED.replace(
        """<S t="900000" d="180000" r="2"/>
          <S d="179000"/>
          <S d="181000" r="-1"/>""",
        """<S t="900000" d="180000" r="-1"/>""",
    )

    segments = _at(days, text).window("v").segments

    assert len(segments) == 15
    # numbered on from the start, as if every one had been gone through
    assert segments[-1].url.endswith(f"seg-v-{900000 + (days // 2 - 1) * 180000}.mp4")


class TestNumbersByTime:
    @pytest.fixture(autouse=True)
    def _forget(self):
        dash_live._numbers_given.clear()

    @staticmethod
    def _sound(seconds: float):
        """A sound whose segments take turns at two lengths, as AAC's do."""

        entries = "".join(
            f'<S t="{i * 191488}" d="96256"/><S d="95232"/>' for i in range(200)
        )
        text = _mpd(
            f"""
            <AdaptationSet contentType="audio">
              <SegmentTemplate timescale="48000" media="a-$Time$.m4s">
                <SegmentTimeline>{entries}</SegmentTimeline>
              </SegmentTemplate>
              <Representation id="a" bandwidth="1"/>
            </AdaptationSet>
            """,
            extra='timeShiftBufferDepth="PT10S"',
        )
        return _at(seconds, text).window("a").segments

    def test_each_keeps_its_number_read_again_much_later(self):
        numbers = {}

        for seconds in range(20, 700, 3):
            for segment in self._sound(seconds):
                assert numbers.setdefault(segment.url, segment.sequence) == (
                    segment.sequence
                )

    def test_one_after_another(self):
        numbers = {}

        for seconds in range(20, 700, 3):
            for segment in self._sound(seconds):
                numbers[segment.url] = segment.sequence

        ordered = [
            numbers[url]
            for url in sorted(numbers, key=lambda u: int(u[u.rindex("-") + 1 : -4]))
        ]

        assert ordered == list(range(ordered[0], ordered[0] + len(ordered)))
