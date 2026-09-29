"""SponsorBlock: what it is asked, what comes back, and what is made of it."""

import hashlib
import threading
import time

import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication
from yt_dlp.postprocessor.sponsorblock import SponsorBlockPP

from gridplayer.models.sponsor_segment import SponsorSegment
from gridplayer.params.sponsorblock import (
    CATEGORY_COLORS,
    HIGHLIGHT_CATEGORY,
    SPONSORBLOCK_SETTINGS,
    allowed_modes,
    category_name,
    category_setting,
)
from gridplayer.params.static import SponsorBlockMode
from gridplayer.settings import Settings, _default_settings
from gridplayer.utils import sponsorblock
from gridplayer.utils.sponsorblock import (
    SKIP_JOIN_MS,
    SkipSpan,
    SponsorBlockFetcher,
    fetch_segments,
    parse_segments,
    skip_span_at,
    skip_spans,
)

VIDEO_ID = "dQw4w9WgXcQ"

SKIP_SPONSORS = {"sponsor": SponsorBlockMode.SKIP}


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


class TestTheCategories:
    def test_it_is_off_until_asked_for(self):
        assert Settings().get("sponsorblock/enabled") is False

    def test_only_sponsors_are_skipped_out_of_the_box(self):
        skipped = [
            category
            for category in CATEGORY_COLORS
            if Settings().get(category_setting(category)) is SponsorBlockMode.SKIP
        ]

        assert skipped == ["sponsor"]

    def test_every_one_has_a_setting(self):
        """The categories are listed twice, here and in the settings."""

        for key in SPONSORBLOCK_SETTINGS:
            assert key in _default_settings

    def test_every_setting_is_for_one(self):
        keys = {key for key in _default_settings if key.startswith("sponsorblock/")}

        assert keys == set(SPONSORBLOCK_SETTINGS)

    def test_every_one_has_a_name_of_its_own(self):
        names = [category_name(category) for category in CATEGORY_COLORS]

        assert len(set(names)) == len(names)
        assert not set(names) & set(CATEGORY_COLORS)

    def test_a_highlight_cannot_be_skipped(self):
        assert SponsorBlockMode.SKIP not in allowed_modes(HIGHLIGHT_CATEGORY)
        assert SponsorBlockMode.SKIP in allowed_modes("sponsor")


class TestWhatComesBack:
    def test_seconds_come_out_as_milliseconds(self):
        segments = parse_segments(
            [{"start_time": 61.5, "end_time": 90.25, "category": "sponsor"}]
        )

        assert segments == (SponsorSegment(61500, 90250, "sponsor"),)

    def test_they_come_out_in_order(self):
        segments = parse_segments(
            [
                {"start_time": 300, "end_time": 320, "category": "outro"},
                {"start_time": 0, "end_time": 15, "category": "intro"},
            ]
        )

        assert [s.category for s in segments] == ["intro", "outro"]

    def test_a_highlight_is_a_place_again(self):
        # yt-dlp makes it a second long, to mark it in a file
        segments = parse_segments(
            [{"start_time": 120, "end_time": 121, "category": HIGHLIGHT_CATEGORY}]
        )

        assert segments == (SponsorSegment(120000, 120000, HIGHLIGHT_CATEGORY),)

    @pytest.mark.parametrize(
        "raw",
        [
            {"start_time": 10, "end_time": 20, "category": "chapter"},
            {"start_time": 10, "end_time": 20, "category": "something_new"},
            {"start_time": None, "end_time": 20, "category": "sponsor"},
            {"start_time": float("nan"), "end_time": 20, "category": "sponsor"},
            {"start_time": 10, "end_time": float("inf"), "category": "sponsor"},
            {"start_time": -1, "end_time": 20, "category": "sponsor"},
            {"start_time": 20, "end_time": 20, "category": "sponsor"},
            {"start_time": 30, "end_time": 20, "category": "sponsor"},
        ],
    )
    def test_what_makes_no_sense_is_left_out(self, raw):
        assert parse_segments([raw]) == ()

    def test_nothing_is_nothing(self):
        assert parse_segments(None) == ()


class TestWhatIsSkipped:
    def test_only_what_is_set_to_be(self):
        segments = (
            SponsorSegment(10000, 20000, "sponsor"),
            SponsorSegment(50000, 60000, "selfpromo"),
        )

        assert skip_spans(segments, SKIP_SPONSORS) == (
            SkipSpan(10000, 20000, "sponsor"),
        )

    def test_ones_that_overlap_are_one(self):
        modes = {**SKIP_SPONSORS, "selfpromo": SponsorBlockMode.SKIP}
        segments = (
            SponsorSegment(10000, 20000, "sponsor"),
            SponsorSegment(18000, 30000, "selfpromo"),
        )

        assert skip_spans(segments, modes) == (SkipSpan(10000, 30000, "sponsor"),)

    def test_ones_all_but_touching_are_one(self):
        modes = {**SKIP_SPONSORS, "selfpromo": SponsorBlockMode.SKIP}
        segments = (
            SponsorSegment(10000, 20000, "sponsor"),
            SponsorSegment(20000 + SKIP_JOIN_MS, 30000, "selfpromo"),
        )

        assert skip_spans(segments, modes) == (SkipSpan(10000, 30000, "sponsor"),)

    def test_ones_further_apart_are_two(self):
        segments = (
            SponsorSegment(10000, 20000, "sponsor"),
            SponsorSegment(20000 + SKIP_JOIN_MS + 1, 30000, "sponsor"),
        )

        assert len(skip_spans(segments, SKIP_SPONSORS)) == 2

    def test_one_inside_another_leaves_it_as_it_was(self):
        segments = (
            SponsorSegment(10000, 30000, "sponsor"),
            SponsorSegment(15000, 20000, "sponsor"),
        )

        assert skip_spans(segments, SKIP_SPONSORS) == (
            SkipSpan(10000, 30000, "sponsor"),
        )

    @pytest.mark.parametrize(
        ("time_ms", "is_in"),
        [(9999, False), (10000, True), (19999, True), (20000, False)],
    )
    def test_a_time_is_in_one_from_its_start_up_to_its_end(self, time_ms, is_in):
        spans = (SkipSpan(10000, 20000, "sponsor"),)

        assert (skip_span_at(spans, time_ms) is not None) is is_in


class TestAskingYtDlp:
    """The lookup, down to the request yt-dlp would send."""

    @pytest.fixture
    def asked(self, monkeypatch):
        asked = []

        def _download_json(pp, url, **kwargs):
            asked.append(url)

            return [
                {"videoID": "someone_elses", "segments": []},
                {
                    "videoID": VIDEO_ID,
                    "segments": [
                        {
                            "segment": [60.0, 90.0],
                            "category": "sponsor",
                            "actionType": "skip",
                            "description": "",
                            "videoDuration": 600.0,
                        },
                        {
                            "segment": [120.0, 120.0],
                            "category": "poi_highlight",
                            "actionType": "poi",
                            "description": "",
                            "videoDuration": 600.0,
                        },
                        # marked on a cut of the video a minute shorter
                        {
                            "segment": [200.0, 230.0],
                            "category": "selfpromo",
                            "actionType": "skip",
                            "description": "",
                            "videoDuration": 540.0,
                        },
                    ],
                },
            ]

        monkeypatch.setattr(SponsorBlockPP, "_download_json", _download_json)

        return asked

    def test_it_finds_what_the_video_has(self, asked):
        segments = fetch_segments(VIDEO_ID, 600000)

        assert segments == (
            SponsorSegment(60000, 90000, "sponsor"),
            SponsorSegment(120000, 120000, HIGHLIGHT_CATEGORY),
        )

    def test_it_asks_by_a_piece_of_a_hash_not_by_the_id(self, asked):
        fetch_segments(VIDEO_ID, 600000)

        (url,) = asked
        prefix = hashlib.sha256(VIDEO_ID.encode()).hexdigest()[:4]

        assert f"/api/skipSegments/{prefix}?" in url
        assert VIDEO_ID not in url

    def test_it_asks_for_every_category_there_is_a_setting_for(self, asked):
        fetch_segments(VIDEO_ID, 600000)

        (url,) = asked

        for category in CATEGORY_COLORS:
            assert category in url


def _wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout

    while time.monotonic() < end:
        QApplication.processEvents()

        if predicate():
            return True

        time.sleep(0.005)

    return False


class _Lookups(list):
    """The videos looked up, in order, and the gate each one waits at."""

    def __init__(self):
        super().__init__()

        self.let_through = threading.Event()
        self.let_through.set()


class TestTheFetcher:
    @pytest.fixture
    def lookups(self, monkeypatch):
        """The lookups made, each held until a test lets it through."""

        lookups = _Lookups()
        let_through = lookups.let_through

        def _fetch_segments(video_id, duration_ms):
            lookups.append(video_id)
            let_through.wait(5)

            if video_id == "broken":
                raise OSError("no route to host")

            return (SponsorSegment(60000, 90000, "sponsor"),)

        monkeypatch.setattr(sponsorblock, "fetch_segments", _fetch_segments)

        return lookups

    @pytest.fixture
    def fetcher(self):
        fetcher = SponsorBlockFetcher()

        fetcher.answers = []
        fetcher.fetched.connect(
            lambda video_id, segments: fetcher.answers.append((video_id, segments))
        )

        return fetcher

    def test_the_answer_comes_later(self, fetcher, lookups):
        assert fetcher.fetch(VIDEO_ID, 600000) is None

        assert _wait_for(lambda: fetcher.answers)
        assert fetcher.answers == [
            (VIDEO_ID, (SponsorSegment(60000, 90000, "sponsor"),))
        ]

    def test_the_next_one_is_answered_at_once(self, fetcher, lookups):
        fetcher.fetch(VIDEO_ID, 600000)
        _wait_for(lambda: fetcher.answers)

        assert fetcher.fetch(VIDEO_ID, 600000) == (
            SponsorSegment(60000, 90000, "sponsor"),
        )
        assert lookups == [VIDEO_ID]

    def test_one_already_on_its_way_is_not_asked_twice(self, fetcher, lookups):
        lookups.let_through.clear()

        fetcher.fetch(VIDEO_ID, 600000)
        fetcher.fetch(VIDEO_ID, 600000)

        lookups.let_through.set()
        _wait_for(lambda: fetcher.answers)

        assert lookups == [VIDEO_ID]

    def test_a_failure_is_no_segments_and_is_asked_again(self, fetcher, lookups):
        fetcher.fetch("broken", 600000)
        _wait_for(lambda: fetcher.answers)

        assert fetcher.answers == [("broken", ())]

        fetcher.fetch("broken", 600000)
        _wait_for(lambda: len(fetcher.answers) == 2)

        assert lookups == ["broken", "broken"]
