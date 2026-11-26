"""A live DASH manifest read for what's out now, as the proxy serves it to mpv as live
HLS: which segments, numbered so that each keeps its number from one reading to the
next and on into a new period, the picture and sound picked, and the playlist written
of them."""

from datetime import UTC, datetime, timedelta

import pytest

from gridplayer.utils.stream_proxy import dash_live
from gridplayer.utils.stream_proxy.dash_live import LiveManifest
from gridplayer.utils.stream_proxy.m3u8 import (
    LiveEntry,
    build_live_media_playlist,
    build_rendition_master_playlist,
)

STARTED = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)

URL = "https://cdn.example/live/manifest.mpd"


@pytest.fixture(autouse=True)
def _forget_numbers():
    dash_live._numbers_given.clear()


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


def _at(seconds: float, text: str = NUMBERED, now=None) -> LiveManifest:
    return LiveManifest(text, URL, now or STARTED + timedelta(seconds=seconds))


def _video(seconds: float, text: str = NUMBERED):
    """The 720p of NUMBERED."""

    return _at(seconds, text).window("video", max_height=800).segments


def _numbers(segments) -> list[int]:
    return [segment.sequence for segment in segments]


class TestNumbered:
    def test_only_what_has_ended_is_out(self):
        # 10 segments of 2 s have ended by 21 s, the 11th not yet
        assert _video(21)[-1].url == "https://cdn.example/live/v720/00010.m4s"

    def test_back_as_far_as_the_manifest_keeps(self):
        assert _numbers(_video(21)) == [6, 7, 8, 9, 10]

    def test_each_keeps_its_number_read_again(self):
        first = {s.url: s.sequence for s in _video(21)}
        later = {s.url: s.sequence for s in _video(25)}

        assert all(later[url] == first[url] for url in first.keys() & later.keys())

    def test_nothing_out_at_the_start(self):
        assert _video(1) == ()

    def test_its_init_segment(self):
        assert _video(21)[0].init_url == "https://cdn.example/live/v720/init.mp4"

    def test_its_lengths(self):
        sound = _at(21).window("audio:en").segments

        assert {s.duration for s in sound} == {2.0}

    def test_still_going(self):
        assert not _at(21).window("video").is_over

    def test_out_a_little_early_where_it_says_so(self):
        text = NUMBERED.replace(
            'duration="2000" startNumber="1"',
            'duration="2000" startNumber="1" availabilityTimeOffset="1.5"',
        )

        assert _video(20.6, text)[-1].sequence == 11
        assert _video(20.6)[-1].sequence == 10


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

    def test_every_language_s_best_the_main_first(self):
        assert [sound.id for sound in _at(21).sounds()] == ["a_en_hi", "a_es"]

    def test_a_sound_served_by_its_language(self):
        segments = _at(21).window("audio:es").segments

        assert segments[-1].url.endswith("/a_es/10.m4s")

    def test_nothing_of_a_kind_not_there(self):
        sound_only = NUMBERED.replace('contentType="video"', 'contentType="text"')

        assert _at(21, sound_only).window("video").segments == ()


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
        segments = _at(11, TIMED).window("video").segments
        urls = [s.url.rsplit("/", 1)[1] for s in segments]

        assert urls[:5] == [
            "seg-v-900000.mp4",
            "seg-v-1080000.mp4",
            "seg-v-1260000.mp4",
            "seg-v-1440000.mp4",
            "seg-v-1619000.mp4",
        ]

    def test_repeated_up_to_now(self):
        # 2 s each from the start: by 9 s, four have ended
        assert len(_at(9, TIMED).window("video").segments) == 4

    def test_numbered_on_read_again(self):
        first = {s.url: s.sequence for s in _at(9, TIMED).window("video").segments}
        later = {s.url: s.sequence for s in _at(15, TIMED).window("video").segments}

        assert all(later[url] == first[url] for url in first.keys() & later.keys())
        assert sorted(later.values()) == list(range(min(later.values()), 7))

    def test_their_lengths(self):
        lengths = [s.duration for s in _at(9, TIMED).window("video").segments]

        assert lengths == pytest.approx([2.0, 2.0, 2.0, 179000 / 90000])

    def test_numbered_where_the_template_takes_a_number(self):
        text = TIMED.replace("seg-$RepresentationID$-$Time$", "n-$Number$").replace(
            'presentationTimeOffset="900000"',
            'presentationTimeOffset="900000" startNumber="40"',
        )

        segments = _at(9, text).window("video").segments

        assert _numbers(segments) == [40, 41, 42, 43]
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

        segment = _at(5, text).window("video").segments[-1]

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

        segments = _at(9, text).window("audio:").segments

        assert segments[0].init_url == "https://cdn.example/live/init.mp4"
        assert [(s.url[-5:], s.sequence) for s in segments] == [
            ("a.mp4", 7),
            ("b.mp4", 8),
        ]

    def test_pieces_of_one_file(self):
        text = _mpd(
            """
            <AdaptationSet contentType="audio">
              <Representation id="a" bandwidth="1">
                <SegmentList timescale="10" duration="40">
                  <Initialization sourceURL="all.mp4" range="0-99"/>
                  <SegmentURL media="all.mp4" mediaRange="100-599"/>
                  <SegmentURL media="all.mp4" mediaRange="600-899"/>
                </SegmentList>
              </Representation>
            </AdaptationSet>
            """
        )

        segments = _at(9, text).window("audio:").segments

        assert segments[0].init_byterange == "100@0"
        assert [s.byterange for s in segments] == ["500@100", "300@600"]

    def test_the_lowest_level_that_says_how_wins(self):
        text = _mpd(
            """
            <SegmentList duration="2"><SegmentURL media="wrong.mp4"/></SegmentList>
            <AdaptationSet contentType="video">
              <Representation id="v" bandwidth="1" height="1">
                <SegmentTemplate duration="2" media="right-$Number$.mp4"/>
              </Representation>
            </AdaptationSet>
            """
        )

        assert _at(5, text).window("video").segments[-1].url.endswith("right-2.mp4")


class TestShortWindows:
    def test_at_least_one_however_short_it_keeps_them(self):
        text = NUMBERED.replace('"PT10S"', '"PT1S"')

        assert _numbers(_video(21, text)) == [10]

    def test_none_further_back_than_it_keeps_them(self):
        text = NUMBERED.replace('"PT10S"', '"PT4S"')

        assert _numbers(_video(21, text)) == [9, 10]

    def test_a_window_written_with_years_and_months(self):
        text = NUMBERED.replace('"PT10S"', '"P0Y0M0DT0H0M10S"')

        assert _numbers(_video(21, text)) == [6, 7, 8, 9, 10]

    def test_a_timeline_s_too(self):
        text = TIMED.replace("<MPD ", '<MPD timeShiftBufferDepth="PT1S" ')

        assert len(_at(15, text).window("video").segments) == 1


class TestOver:
    def test_by_the_manifest_s_length(self):
        text = NUMBERED.replace('type="dynamic"', 'type="static"').replace(
            "<MPD ", '<MPD mediaPresentationDuration="PT8S" '
        )

        window = _at(500, text).window("video", max_height=800)

        assert window.is_over
        assert _numbers(window.segments) == [1, 2, 3, 4]

    def test_by_its_period_s_where_that_s_all_it_says(self):
        text = NUMBERED.replace('type="dynamic"', 'type="static"').replace(
            '<Period id="0" start="PT0S">',
            '<Period id="0" start="PT0S" duration="PT8S">',
        )

        assert _numbers(_video(500, text)) == [1, 2, 3, 4]


class TestClock:
    def test_a_start_with_a_fraction_python_3_10_reads_too(self):
        text = NUMBERED.replace("12:00:00Z", "12:00:00.5Z")

        assert _video(21.5, text)[-1].sequence == 10

    def test_a_time_with_no_zone_is_utc(self):
        naive = (STARTED + timedelta(seconds=21)).replace(tzinfo=None)

        segments = _at(0, now=naive).window("video", max_height=800).segments

        assert segments[-1].sequence == 10


def test_a_timeline_repeated_for_days_is_counted_past():
    days = 3 * 86400
    text = TIMED.replace(
        """<S t="900000" d="180000" r="2"/>
          <S d="179000"/>
          <S d="181000" r="-1"/>""",
        """<S t="900000" d="180000" r="-1"/>""",
    )

    segments = _at(days, text).window("video").segments

    assert len(segments) == 15
    # named on from the start, as if every one had been gone through
    assert segments[-1].url.endswith(f"seg-v-{900000 + (days // 2 - 1) * 180000}.mp4")


class TestNumbersByTime:
    @staticmethod
    def _sound(seconds: float):
        """A sound whose segments take turns at two lengths, as AAC's do."""

        entries = "".join(
            f'<S t="{i * 191488}" d="96256"/><S d="95232"/>' for i in range(400)
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
        return _at(seconds, text).window("audio:").segments

    def _read(self, times) -> dict[str, int]:
        numbers = {}

        for seconds in times:
            for segment in self._sound(seconds):
                assert numbers.setdefault(segment.url, segment.sequence) == (
                    segment.sequence
                )

        return numbers

    @staticmethod
    def _in_order(numbers: dict[str, int]) -> list[int]:
        return [
            numbers[url]
            for url in sorted(numbers, key=lambda u: int(u[u.rindex("-") + 1 : -4]))
        ]

    def test_each_keeps_its_number_read_again_much_later(self):
        self._read(range(20, 700, 3))

    def test_one_after_another(self):
        ordered = self._in_order(self._read(range(20, 700, 3)))

        assert ordered == list(range(ordered[0], ordered[0] + len(ordered)))

    def test_counted_on_after_a_while_unread(self):
        # minimized a minute and a half, say: nothing in common with the last
        before = self._in_order(self._read([200]))
        after = self._in_order(self._read([300]))

        # 100 s on, segments of a little under 2 s
        assert after[-1] - before[-1] == pytest.approx(
            100 / (191488 / 2 / 48000), abs=1
        )


MULTI = """<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="dynamic"
     availabilityStartTime="2026-11-15T12:00:00Z" timeShiftBufferDepth="PT10S">
  <Period id="show" start="PT0S">
    <AdaptationSet contentType="video">
      <SegmentTemplate duration="2" startNumber="1"
          initialization="show/init.mp4" media="show/$Number$.m4s"/>
      <Representation id="show-v" bandwidth="1" height="720"/>
    </AdaptationSet>
  </Period>
  <Period id="ad" start="PT20S">
    <AdaptationSet contentType="video">
      <SegmentTemplate duration="2" startNumber="1"
          initialization="ad/init.mp4" media="ad/$Number$.m4s"/>
      <Representation id="ad-v" bandwidth="1" height="720"/>
    </AdaptationSet>
  </Period>
</MPD>"""


class TestPeriods:
    def test_into_the_next_its_own_representation(self):
        segments = _at(25, MULTI).window("video").segments

        assert [s.url.rsplit("live/", 1)[1] for s in segments] == [
            "show/8.m4s",
            "show/9.m4s",
            "show/10.m4s",
            "ad/1.m4s",
            "ad/2.m4s",
        ]

    def test_numbered_on_across_it(self):
        before = _numbers(_at(19, MULTI).window("video").segments)
        across = _at(25, MULTI).window("video").segments

        assert _numbers(across) == list(range(before[-2], before[-2] + 5))

    def test_the_break_marked(self):
        segments = _at(25, MULTI).window("video").segments

        assert [s.is_new_part for s in segments] == [False, False, False, True, False]

    def test_each_with_its_own_init_segment(self):
        segments = _at(25, MULTI).window("video").segments

        assert segments[-1].init_url.endswith("ad/init.mp4")

    def test_what_s_on_offer_is_of_the_one_it_is_in(self):
        assert _at(25, MULTI).pick("video").id == "ad-v"


class TestPlaylist:
    def test_live_has_no_end(self):
        playlist = build_live_media_playlist([LiveEntry("a", 2.0)], first_sequence=6)

        assert "#EXT-X-ENDLIST" not in playlist
        assert "#EXT-X-MEDIA-SEQUENCE:6" in playlist

    def test_its_init_segment_said_again_where_it_changes(self):
        playlist = build_live_media_playlist(
            [
                LiveEntry("a", 2.0, init_url="i1"),
                LiveEntry("b", 2.0, init_url="i1"),
                LiveEntry("c", 2.0, init_url="i2", is_discontinuity=True),
            ],
            first_sequence=1,
        )

        assert playlist.count("#EXT-X-MAP") == 2
        assert playlist.index("#EXT-X-DISCONTINUITY") < playlist.index('URI="i2"')

    def test_pieces_of_a_file(self):
        playlist = build_live_media_playlist(
            [LiveEntry("a", 2.0, byterange="500@100")], 1
        )

        assert "#EXT-X-BYTERANGE:500@100" in playlist

    def test_over_has_its_end(self):
        playlist = build_live_media_playlist([LiveEntry("a", 2.0)], 1, is_over=True)

        assert playlist.endswith("#EXT-X-ENDLIST")

    def test_every_language_to_switch_to(self):
        playlist = build_rendition_master_playlist(
            "video", [("en.m3u8", "en", True), ("es.m3u8", "es", False)]
        )

        assert 'LANGUAGE="en",DEFAULT=YES' in playlist
        assert 'LANGUAGE="es",DEFAULT=NO' in playlist
