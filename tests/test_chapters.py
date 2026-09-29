"""Finding the way around a video by its chapters, away from any player."""

import pytest

from gridplayer.models.chapter import Chapter
from gridplayer.utils.chapters import (
    CHAPTER_RESTART_MS,
    CHAPTER_TOLERANCE_MS,
    chapter_index_at,
    chapter_span,
    chapter_stops,
    clean_chapters,
    is_site_length_playing,
    is_span_reachable,
    next_stop,
    previous_stop,
    span_at,
)

LENGTH = 60000

CHAPTERS = (
    Chapter(0, "Opening"),
    Chapter(10000, "Middle"),
    Chapter(25000, "Heist"),
    Chapter(40000, "Credits"),
)

# where VLC reports the time after a seek to 25000, measured on mkv, mp4 and
# m4a: the first update says 25000, every one after it 24990
LANDED_SHORT_MS = 10


class TestCleaning:
    def test_out_of_order_comes_back_in_order(self):
        cleaned = clean_chapters(tuple(reversed(CHAPTERS)), LENGTH)

        assert cleaned == CHAPTERS

    def test_a_start_listed_twice_is_kept_once_under_its_first_name(self):
        cleaned = clean_chapters(
            (Chapter(0, "A"), Chapter(5000, "B"), Chapter(5000, "C")), LENGTH
        )

        assert cleaned == (Chapter(0, "A"), Chapter(5000, "B"))

    def test_a_chapter_past_the_end_is_dropped(self):
        cleaned = clean_chapters((*CHAPTERS, Chapter(LENGTH, "After")), LENGTH)

        assert cleaned == CHAPTERS

    def test_a_chapter_before_the_start_is_dropped(self):
        cleaned = clean_chapters((Chapter(-5, "Before"), *CHAPTERS), LENGTH)

        assert cleaned == CHAPTERS

    def test_one_that_starts_a_moment_in_starts_at_the_beginning(self):
        cleaned = clean_chapters((Chapter(40, "A"), Chapter(9000, "B")), LENGTH)

        assert cleaned == (Chapter(0, "A"), Chapter(9000, "B"))

    def test_mkv_names_lose_the_space_in_front(self):
        cleaned = clean_chapters((Chapter(0, " Opening"), Chapter(5000, " ")), LENGTH)

        assert cleaned == (Chapter(0, "Opening"), Chapter(5000, None))

    def test_one_chapter_covering_the_whole_video_is_no_chapter(self):
        assert clean_chapters((Chapter(0, "Everything"),), LENGTH) == ()

    def test_one_chapter_that_starts_later_is_somewhere_to_go(self):
        cleaned = clean_chapters((Chapter(5000, None),), LENGTH)

        assert cleaned == (Chapter(5000, None),)

    def test_a_length_not_known_keeps_everything_past_the_start(self):
        cleaned = clean_chapters(CHAPTERS, 0)

        assert cleaned == CHAPTERS


class TestWhereTheVideoIs:
    def test_inside_a_chapter(self):
        assert chapter_index_at(CHAPTERS, 30000) == 2

    def test_a_seek_landing_a_hair_short_is_in_the_chapter_it_aimed_at(self):
        assert chapter_index_at(CHAPTERS, 25000 - LANDED_SHORT_MS) == 2

    def test_before_the_first_chapter_is_in_none(self):
        chapters = (Chapter(5000, "A"), Chapter(9000, "B"))

        assert chapter_index_at(chapters, 1000) is None

    def test_the_last_chapter_runs_to_the_end(self):
        assert chapter_span(CHAPTERS, 3, LENGTH) == (40000, LENGTH)

    def test_the_stretch_before_the_first_chapter_is_a_span_of_its_own(self):
        chapters = (Chapter(5000, "A"), Chapter(9000, "B"))

        assert span_at(chapters, 1000, LENGTH) == (0, 5000)

    def test_the_span_a_short_landing_is_in(self):
        assert span_at(CHAPTERS, 25000 - LANDED_SHORT_MS, LENGTH) == (25000, 40000)


class TestGoingForward:
    def test_to_where_the_next_chapter_starts(self):
        assert next_stop(CHAPTERS, 12000, 0, LENGTH) == 25000

    def test_twice_from_a_jump_that_landed_short_moves_on(self):
        """Not back onto the chapter the video is already at the start of."""

        assert next_stop(CHAPTERS, 25000 - LANDED_SHORT_MS, 0, LENGTH) == 40000

    def test_the_last_chapter_has_nowhere_to_go(self):
        assert next_stop(CHAPTERS, 45000, 0, LENGTH) is None

    def test_a_loop_ends_the_chapters_where_it_ends(self):
        assert next_stop(CHAPTERS, 12000, 5000, 20000) is None

    def test_a_chapter_the_loop_starts_past_is_skipped(self):
        assert next_stop(CHAPTERS, 16000, 15000, LENGTH) == 25000


class TestGoingBack:
    def test_well_into_a_chapter_starts_it_over(self):
        time_ms = 25000 + CHAPTER_RESTART_MS + 1

        assert previous_stop(CHAPTERS, time_ms, 0, LENGTH) == 25000

    def test_near_its_start_goes_to_the_one_before(self):
        time_ms = 25000 + CHAPTER_RESTART_MS - 1

        assert previous_stop(CHAPTERS, time_ms, 0, LENGTH) == 10000

    def test_from_a_jump_that_landed_short_goes_to_the_one_before(self):
        assert previous_stop(CHAPTERS, 25000 - LANDED_SHORT_MS, 0, LENGTH) == 10000

    def test_the_first_chapter_goes_back_to_its_own_start(self):
        assert previous_stop(CHAPTERS, 500, 0, LENGTH) == 0

    def test_inside_a_loop_the_loop_start_is_as_far_back_as_it_goes(self):
        assert previous_stop(CHAPTERS, 16000, 15000, LENGTH) == 15000

    def test_the_stretch_before_the_first_chapter_is_somewhere_to_go_back_to(self):
        chapters = (Chapter(5000, "A"), Chapter(9000, "B"))

        assert previous_stop(chapters, 5500, 0, LENGTH) == 0


class TestTheLoop:
    def test_the_loop_start_is_always_a_stop(self):
        assert chapter_stops(CHAPTERS, 15000, 50000) == [15000, 25000, 40000]

    @pytest.mark.parametrize(
        ("span", "reachable"),
        [
            ((0, 10000), False),  # before the loop
            ((10000, 25000), True),  # the loop starts inside it
            ((25000, 40000), True),  # inside the loop
            ((40000, 60000), False),  # the loop ends where it starts
        ],
    )
    def test_a_chapter_is_reachable_where_it_overlaps_the_loop(self, span, reachable):
        assert is_span_reachable(span, 15000, 40000) is reachable


HOUR_MS = 3600000


class TestTheSitesLength:
    def test_a_second_out_is_the_same_video(self):
        assert is_site_length_playing(LENGTH + 1000, LENGTH)

    def test_a_minute_out_is_some_other_cut_of_it(self):
        assert not is_site_length_playing(LENGTH + 60000, LENGTH)

    def test_a_long_video_is_given_room_in_proportion(self):
        # two percent of an hour is 72 seconds
        assert is_site_length_playing(HOUR_MS + 60000, HOUR_MS)
        assert not is_site_length_playing(HOUR_MS + 90000, HOUR_MS)

    @pytest.mark.parametrize(("length", "site_length"), [(-1, LENGTH), (LENGTH, 0)])
    def test_either_one_unknown_is_nothing_to_go_against(self, length, site_length):
        assert is_site_length_playing(length, site_length)


def test_the_tolerance_is_well_past_what_a_seek_was_measured_to_miss_by():
    assert CHAPTER_TOLERANCE_MS > LANDED_SHORT_MS * 10
