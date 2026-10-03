"""Bookmarks as kept: by file, at the root of a playlist, and left out of
snapshots."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from gridplayer.models.bookmark import Bookmark, bookmark_color
from gridplayer.models.file_bookmarks import FileBookmarks
from gridplayer.models.grid_state import GridState
from gridplayer.models.playlist import Playlist, Snapshot
from gridplayer.models.video import Video
from gridplayer.utils.bookmarks import (
    BOOKMARK_AT_MS,
    BOOKMARK_BACK_MS,
    BOOKMARK_SAME_MS,
    bookmark_at,
    bookmark_on,
    bookmarks_txt,
    file_key,
    in_order,
    is_bookmarked,
    is_timestamp_bookmarked,
    merged,
    new_in_txt,
    next_bookmark_index,
    next_bookmark_round,
    parse_bookmarks_txt,
    previous_bookmark_index,
    with_bookmark,
)

URL = "https://example.com/watch?v=1"

BOOKMARKS = (Bookmark(time_ms=10000), Bookmark(time_ms=30000, name="Goal"))

LENGTH = 60000


def _times(bookmarks):
    return [bookmark.time_ms for bookmark in bookmarks]


class TestAdding:
    def test_one_goes_in_its_place_among_the_rest(self):
        added = with_bookmark(BOOKMARKS, Bookmark(time_ms=20000))

        assert _times(added) == [10000, 20000, 30000]

    def test_one_near_another_is_the_same_place(self):
        assert is_bookmarked(BOOKMARKS, 30000 + BOOKMARK_SAME_MS - 1)
        assert not is_bookmarked(BOOKMARKS, 30000 + BOOKMARK_SAME_MS)


class TestBeingAtOne:
    def test_near_enough_is_at_it(self):
        assert bookmark_at(BOOKMARKS, 30000 - BOOKMARK_AT_MS) == 1
        assert bookmark_at(BOOKMARKS, 30000 + BOOKMARK_AT_MS) == 1

    def test_further_off_is_at_none(self):
        assert bookmark_at(BOOKMARKS, 30000 + BOOKMARK_AT_MS + 1) is None

    def test_between_two_close_ones_it_is_the_nearer(self):
        close = (Bookmark(time_ms=10000), Bookmark(time_ms=10800))

        assert bookmark_at(close, 10500) == 1
        assert bookmark_at(close, 10300) == 0


class TestNext:
    def test_it_is_the_first_one_ahead(self):
        assert next_bookmark_index(BOOKMARKS, 0, 0, LENGTH) == 0
        assert next_bookmark_index(BOOKMARKS, 15000, 0, LENGTH) == 1

    def test_one_just_landed_on_a_hair_short_counts_as_passed(self):
        assert next_bookmark_index(BOOKMARKS, 10000 - 10, 0, LENGTH) == 1

    def test_past_the_last_there_is_none(self):
        assert next_bookmark_index(BOOKMARKS, 35000, 0, LENGTH) is None

    def test_one_outside_the_loop_is_passed_over(self):
        assert next_bookmark_index(BOOKMARKS, 0, 20000, LENGTH) == 1
        assert next_bookmark_index(BOOKMARKS, 20000, 0, 30000) is None


class TestPrevious:
    def test_well_past_one_it_is_that_one(self):
        assert previous_bookmark_index(BOOKMARKS, 35000, 0, LENGTH) == 1

    def test_just_past_one_it_is_the_one_before(self):
        time_ms = 30000 + BOOKMARK_BACK_MS - 1

        assert previous_bookmark_index(BOOKMARKS, time_ms, 0, LENGTH) == 0

    def test_before_the_first_there_is_none(self):
        assert previous_bookmark_index(BOOKMARKS, 10000, 0, LENGTH) is None

    def test_one_outside_the_loop_is_passed_over(self):
        assert previous_bookmark_index(BOOKMARKS, 35000, 20000, LENGTH) == 1
        assert previous_bookmark_index(BOOKMARKS, 25000, 20000, LENGTH) is None


class TestCloseTogether:
    """Marked a moment apart, each is still somewhere to go."""

    CLOSE = (Bookmark(time_ms=20000), Bookmark(time_ms=20600), Bookmark(time_ms=22000))

    def test_previous_from_one_is_the_one_just_before(self):
        assert previous_bookmark_index(self.CLOSE, 20600, 0, LENGTH) == 0

    def test_next_from_one_is_the_one_just_after(self):
        assert next_bookmark_index(self.CLOSE, 20000, 0, LENGTH) == 1

    def test_from_one_landed_on_a_hair_short_too(self):
        assert previous_bookmark_index(self.CLOSE, 20600 - 10, 0, LENGTH) == 0
        assert next_bookmark_index(self.CLOSE, 20000 - 10, 0, LENGTH) == 1

    def test_previous_while_playing_on_from_one_is_the_one_before(self):
        assert previous_bookmark_index(self.CLOSE, 20600 + 300, 0, LENGTH) == 0

    def test_a_pair_closer_than_a_seek_lands_short(self):
        """As a playlist written by hand may have them."""

        pair = (Bookmark(time_ms=20000), Bookmark(time_ms=20100))

        assert next_bookmark_index(pair, 20000, 0, LENGTH) == 1
        assert previous_bookmark_index(pair, 20100, 0, LENGTH) == 0


class TestForAFile:
    def test_they_come_first_to_last(self):
        entry = FileBookmarks(
            uri=URL,
            bookmarks=[{"time_ms": 30000}, {"time_ms": 10000, "name": "Start"}],
        )

        assert _times(entry.bookmarks) == [10000, 30000]

    def test_only_one_to_a_place(self):
        entry = FileBookmarks(
            uri=URL,
            bookmarks=[{"time_ms": 10000, "name": "A"}, {"time_ms": 10000}],
        )

        assert entry.bookmarks == [Bookmark(time_ms=10000, name="A")]

    @pytest.mark.parametrize(
        "broken", [{"time_ms": -5}, {"name": "no time"}, "0:30", None]
    )
    def test_a_broken_one_is_left_out_and_the_rest_kept(self, broken):
        entry = FileBookmarks(uri=URL, bookmarks=[broken, {"time_ms": 10000}])

        assert _times(entry.bookmarks) == [10000]

    def test_a_file_that_is_gone_is_kept_to_be_seen(self, tmp_path):
        gone = tmp_path / "gone.mkv"

        entry = FileBookmarks(uri=gone, bookmarks=list(BOOKMARKS))

        assert entry.uri == gone

    def test_they_cannot_be_changed_in_place(self):
        with pytest.raises(ValueError, match="frozen"):
            BOOKMARKS[0].name = "Changed"


class TestTheFileTheyAreIn:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            "https://youtube.com/watch?v=aqz-KE-bpKQ&t=30s",
            "https://www.youtube.com/watch?feature=share&v=aqz-KE-bpKQ",
            "https://youtu.be/aqz-KE-bpKQ?si=abc",
            "https://m.youtube.com/shorts/aqz-KE-bpKQ",
            "https://www.youtube.com/embed/aqz-KE-bpKQ",
        ],
    )
    def test_a_youtube_video_is_one_however_linked(self, url):
        assert file_key(url) == "youtube:aqz-KE-bpKQ"

    def test_other_links_are_their_own(self):
        assert file_key(URL) == URL

    def test_a_path_is_one_however_written(self, tmp_path):
        path = tmp_path / "Movie.mkv"
        written_otherwise = Path(str(tmp_path / "sub" / ".." / "Movie.mkv"))

        assert file_key(written_otherwise) == file_key(path)


class TestMerged:
    def test_every_place_once(self):
        assert _times(
            merged(
                (
                    [Bookmark(time_ms=10000), Bookmark(time_ms=30000)],
                    [Bookmark(time_ms=20000), Bookmark(time_ms=30200)],
                )
            )
        ) == [10000, 20000, 30000]

    def test_at_one_place_the_first_name_is_kept(self):
        assert merged(
            ([Bookmark(time_ms=10000, name="A")], [Bookmark(time_ms=10000, name="B")])
        ) == [Bookmark(time_ms=10000, name="A")]

    def test_a_name_is_not_lost_to_one_without(self):
        assert merged(
            ([Bookmark(time_ms=10000)], [Bookmark(time_ms=10100, name="B")])
        ) == [Bookmark(time_ms=10000, name="B")]

    def test_at_one_place_the_first_colour_is_kept(self):
        assert merged(
            (
                [Bookmark(time_ms=10000, color="#ff3d3d")],
                [Bookmark(time_ms=10000, color="#3d8bff")],
            )
        ) == [Bookmark(time_ms=10000, color="#ff3d3d")]

    def test_a_colour_is_not_lost_to_one_without(self):
        assert merged(
            (
                [Bookmark(time_ms=10000, name="A")],
                [Bookmark(time_ms=10100, name="B", color="#3d8bff")],
            )
        ) == [Bookmark(time_ms=10000, name="A", color="#3d8bff")]


def _saved(playlist, base_dir=None):
    return json.loads(playlist.dumps(base_dir=base_dir))


def _parsed(doc, base_dir=None):
    return Playlist.parse(json.dumps(doc), base_dir=base_dir)


class TestInAPlaylist:
    def test_they_are_saved_by_file_beside_the_videos(self):
        playlist = Playlist(
            videos=[Video(uri=URL)],
            bookmarks=[FileBookmarks(uri=URL, bookmarks=list(BOOKMARKS))],
        )

        saved = _saved(playlist)

        assert saved["bookmarks"] == [
            {
                "uri": URL,
                "bookmarks": [{"time_ms": 10000}, {"time_ms": 30000, "name": "Goal"}],
            }
        ]
        assert "bookmarks" not in saved["videos"][0]

    def test_and_come_back_with_it(self):
        cell = uuid4()
        playlist = Playlist(
            bookmarks=[FileBookmarks(uri=URL, cell=cell, bookmarks=list(BOOKMARKS))]
        )

        loaded = Playlist.parse(playlist.dumps())

        assert loaded.bookmarks == [
            FileBookmarks(uri=URL, cell=cell, bookmarks=list(BOOKMARKS))
        ]

    def test_a_file_is_written_as_the_videos_are(self, tmp_path):
        movie = tmp_path / "videos" / "movie.mkv"
        playlist = Playlist(
            save_paths_relative=True,
            bookmarks=[FileBookmarks(uri=movie, bookmarks=list(BOOKMARKS))],
        )

        saved = _saved(playlist, base_dir=tmp_path)

        assert saved["bookmarks"][0]["uri"] == "videos/movie.mkv"

    def test_and_read_back_where_the_playlist_is(self, tmp_path):
        loaded = _parsed(
            {
                "format": "gridplayer-playlist",
                "bookmarks": [
                    {"uri": "videos/movie.mkv", "bookmarks": [{"time_ms": 5000}]}
                ],
            },
            base_dir=tmp_path,
        )

        assert loaded.bookmarks[0].uri == tmp_path / "videos" / "movie.mkv"

    def test_a_file_without_any_is_not_saved(self):
        playlist = Playlist(bookmarks=[FileBookmarks(uri=URL, bookmarks=[])])

        assert "bookmarks" not in _saved(playlist)

    def test_a_broken_entry_is_left_out_and_the_playlist_kept(self):
        loaded = _parsed(
            {
                "format": "gridplayer-playlist",
                "videos": [{"uri": URL}],
                "bookmarks": [
                    "not an entry",
                    {"bookmarks": [{"time_ms": 5000}]},
                    {"uri": URL, "cell": "not an id", "bookmarks": []},
                    {"uri": URL, "bookmarks": [{"time_ms": 5000}]},
                ],
            }
        )

        assert len(loaded.videos) == 1
        assert loaded.bookmarks == [
            FileBookmarks(uri=URL, bookmarks=[Bookmark(time_ms=5000)])
        ]

    def test_a_colour_is_saved_with_one_given_it_only(self):
        playlist = Playlist(
            bookmarks=[
                FileBookmarks(
                    uri=URL,
                    bookmarks=[
                        Bookmark(time_ms=10000),
                        Bookmark(time_ms=30000, name="Goal", color="#3d8bff"),
                    ],
                )
            ]
        )

        assert _saved(playlist)["bookmarks"][0]["bookmarks"] == [
            {"time_ms": 10000},
            {"time_ms": 30000, "name": "Goal", "color": "#3d8bff"},
        ]

    def test_and_comes_back_with_it(self):
        bookmarks = [Bookmark(time_ms=30000, color="#3d8bff")]
        playlist = Playlist(bookmarks=[FileBookmarks(uri=URL, bookmarks=bookmarks)])

        loaded = Playlist.parse(playlist.dumps())

        assert loaded.bookmarks[0].bookmarks == bookmarks

    def test_a_colour_gone_wrong_costs_the_bookmark_its_colour_only(self):
        loaded = _parsed(
            {
                "format": "gridplayer-playlist",
                "bookmarks": [
                    {
                        "uri": URL,
                        "bookmarks": [
                            {"time_ms": 5000, "name": "A", "color": "reddish"},
                            {"time_ms": 9000, "color": 12},
                        ],
                    }
                ],
            }
        )

        assert loaded.bookmarks[0].bookmarks == [
            Bookmark(time_ms=5000, name="A"),
            Bookmark(time_ms=9000),
        ]

    def test_a_playlist_from_before_them_loads_with_none(self):
        loaded = _parsed({"format": "gridplayer-playlist", "videos": [{"uri": URL}]})

        assert loaded.bookmarks == []


class TestInASnapshot:
    def test_none_are_saved_in_one(self):
        video = Video(uri=URL)
        playlist = Playlist(
            videos=[video],
            bookmarks=[FileBookmarks(uri=URL, bookmarks=list(BOOKMARKS))],
            snapshots={1: Snapshot(grid_state=GridState(), videos=[video])},
        )

        saved = _saved(playlist)

        assert "bookmarks" not in saved["snapshots"]["1"]["videos"][0]

    def test_one_saved_with_some_by_hand_loads_without_them(self):
        loaded = _parsed(
            {
                "format": "gridplayer-playlist",
                "videos": [{"uri": URL}],
                "snapshots": {
                    "1": {
                        "grid_state": {},
                        "videos": [{"uri": URL, "bookmarks": [{"time_ms": 5000}]}],
                    }
                },
            }
        )

        assert "bookmarks" not in loaded.snapshots[1].videos[0].model_dump()


class TestInOrder:
    def test_first_to_last_the_first_of_those_at_one_place(self):
        bookmarks = [
            Bookmark(time_ms=50000),
            Bookmark(time_ms=20000, name="First"),
            Bookmark(time_ms=20000, name="Second"),
        ]

        assert in_order(bookmarks) == [
            Bookmark(time_ms=20000, name="First"),
            Bookmark(time_ms=50000),
        ]


class TestAsTimestamps:
    def test_one_to_a_line_the_time_then_the_name(self):
        assert bookmarks_txt(BOOKMARKS, LENGTH) == "0:10\n0:30 Goal"

    def test_an_hour_long_video_counts_hours(self):
        text = bookmarks_txt([Bookmark(time_ms=6000, name="Intro")], 3_600_000)

        assert text == "0:00:06 Intro"

    def test_they_come_back_as_they_went(self):
        bookmarks = [
            Bookmark(time_ms=0, name="Start"),
            Bookmark(time_ms=83000),
            Bookmark(time_ms=3_723_000, name="Goal & Run: the replay"),
        ]

        text = bookmarks_txt(bookmarks, 4_000_000)

        assert parse_bookmarks_txt(text) == bookmarks

    @pytest.mark.parametrize(
        ("line", "bookmark"),
        [
            ("0:00 Intro", Bookmark(time_ms=0, name="Intro")),
            ("1:23 - The chase", Bookmark(time_ms=83000, name="The chase")),
            ("1:23 \u2013 The chase", Bookmark(time_ms=83000, name="The chase")),
            ("[1:02:03] Outro", Bookmark(time_ms=3_723_000, name="Outro")),
            ("(12:05) Fight", Bookmark(time_ms=725_000, name="Fight")),
            ("Credits 9:41", Bookmark(time_ms=581_000, name="Credits")),
            (
                "\u2022 3:27 | Sword fight",
                Bookmark(time_ms=207_000, name="Sword fight"),
            ),
            ("7:45", Bookmark(time_ms=465_000)),
            ("  07:45  ", Bookmark(time_ms=465_000)),
        ],
    )
    def test_a_description_s_lines_are_read(self, line, bookmark):
        assert parse_bookmarks_txt(line) == [bookmark]

    @pytest.mark.parametrize(
        "line",
        [
            "no time here",
            "a number 42 is no time",
            "99:99 past a minute",
            "1:60:00 past an hour",
            "version 1.2:30",
            "",
        ],
    )
    def test_lines_without_a_time_are_passed_over(self, line):
        assert parse_bookmarks_txt(line) == []

    def test_copied_out_and_pasted_back_each_is_there_already(self):
        # the tenths dropped on the way out: 21:49.9 comes back as 21:49
        bookmarks = [Bookmark(time_ms=1_309_900), Bookmark(time_ms=3_063_020)]

        pasted = parse_bookmarks_txt(bookmarks_txt(bookmarks, 4_000_000))

        assert _times(pasted) == [1_309_000, 3_063_000]
        assert all(is_timestamp_bookmarked(bookmarks, b.time_ms) for b in pasted)

    @pytest.mark.parametrize(
        ("time_ms", "is_there"),
        [
            # the second it names, all of it
            (1_309_000, True),
            # near enough, as for any bookmark
            (1_310_000, True),
            (1_308_000, False),
            (1_311_000, False),
        ],
    )
    def test_a_timestamp_stands_for_all_of_its_second(self, time_ms, is_there):
        bookmarks = [Bookmark(time_ms=1_309_900)]

        assert is_timestamp_bookmarked(bookmarks, time_ms) == is_there

    def test_only_the_lines_with_times_count(self):
        text = "Chapters:\n0:00 Intro\n\nThanks for watching\n2:10 Outro"

        assert _times(parse_bookmarks_txt(text)) == [0, 130000]


class TestAsTimestampsToTheMillisecond:
    def test_each_time_has_its_milliseconds(self):
        assert bookmarks_txt(BOOKMARKS, LENGTH, is_precise=True) == (
            "0:10.000\n0:30.000 Goal"
        )

    def test_they_come_back_exactly_as_they_went(self):
        bookmarks = [
            Bookmark(time_ms=1, name="Start"),
            Bookmark(time_ms=83_450),
            Bookmark(time_ms=3_723_999, name="Goal & Run: the replay"),
        ]

        text = bookmarks_txt(bookmarks, 4_000_000, is_precise=True)

        assert parse_bookmarks_txt(text) == bookmarks

    @pytest.mark.parametrize(
        ("line", "bookmark"),
        [
            ("1:23.4 Intro", Bookmark(time_ms=83_400, name="Intro")),
            ("0:21.900 - Sword", Bookmark(time_ms=21_900, name="Sword")),
            ("[1:02:03.250] Outro", Bookmark(time_ms=3_723_250, name="Outro")),
            # past a millisecond, the rest is dropped
            ("0:21.90049", Bookmark(time_ms=21_900)),
            # the manager's list, as it shows them, and a tenth alone
            ("03:27.412", Bookmark(time_ms=207_412)),
            ("03:27.4", Bookmark(time_ms=207_400)),
        ],
    )
    def test_a_fraction_of_a_second_is_read(self, line, bookmark):
        assert parse_bookmarks_txt(line) == [bookmark]

    def test_a_full_stop_after_a_time_is_no_fraction(self):
        assert _times(parse_bookmarks_txt("Credits at 9:41.")) == [581_000]


class TestNewInTimestamps:
    def test_those_there_already_are_left_out(self):
        bookmarks = [Bookmark(time_ms=21_900)]

        new = new_in_txt(bookmarks, "0:21 Again\n0:40 New", LENGTH)

        assert new == [Bookmark(time_ms=40_000, name="New")]

    def test_one_in_whole_seconds_stands_for_all_of_its_second(self):
        bookmarks = [Bookmark(time_ms=21_900)]

        assert new_in_txt(bookmarks, "0:21", LENGTH) == []

    def test_one_to_the_millisecond_only_for_where_it_is(self):
        bookmarks = [Bookmark(time_ms=21_300)]

        new = new_in_txt(bookmarks, "0:21.900\n0:21.500", LENGTH)

        assert new == [Bookmark(time_ms=21_900)]

    def test_those_past_the_end_are_left_out(self):
        assert new_in_txt([], "0:59\n1:00\n1:30", LENGTH) == [Bookmark(time_ms=59_000)]

    def test_the_first_of_two_at_one_place_first_to_last(self):
        new = new_in_txt([], "0:30 Late\n0:10 First\n0:10 Again", LENGTH)

        assert new == [
            Bookmark(time_ms=10_000, name="First"),
            Bookmark(time_ms=30_000, name="Late"),
        ]


class TestRoundAMarker:
    """A marker standing for several bookmarks close together: clicked again
    and again, it goes to each in turn."""

    SHARED = [
        Bookmark(time_ms=30000),
        Bookmark(time_ms=30600),
        Bookmark(time_ms=31200),
    ]

    @pytest.mark.parametrize(
        ("time_ms", "on"),
        [
            (30000, 0),
            (30600, 1),
            # a hair short of it, as VLC reports a seek that landed there
            (30590, 1),
            # played on a little past it
            (30900, 1),
            (29000, None),
            (33000, None),
        ],
    )
    def test_the_one_the_video_is_on(self, time_ms, on):
        assert bookmark_on(self.SHARED, time_ms) == on

    @pytest.mark.parametrize(
        ("time_ms", "to"),
        [
            # on none of them: the first
            (5000, 0),
            (30000, 1),
            (30600, 2),
            # after the last, the first again
            (31200, 0),
        ],
    )
    def test_a_click_goes_to_the_one_after(self, time_ms, to):
        assert next_bookmark_round(self.SHARED, time_ms) == to

    def test_with_none_there_is_nowhere_to_go(self):
        assert next_bookmark_round([], 30000) is None


class TestAColour:
    def test_one_has_none_till_given_one(self):
        assert Bookmark(time_ms=0).color is None

    @pytest.mark.parametrize(
        ("given", "kept"),
        [
            ("#3d8bff", "#3d8bff"),
            # written by hand, any case, with room around it
            (" #3D8BFF ", "#3d8bff"),
            (None, None),
            ("blue", None),
            ("#38f", None),
            ("#3d8bff80", None),
            ("", None),
            (12, None),
        ],
    )
    def test_it_is_kept_as_rrggbb_or_not_at_all(self, given, kept):
        assert bookmark_color(given) == kept
        assert Bookmark(time_ms=0, color=given).color == kept
