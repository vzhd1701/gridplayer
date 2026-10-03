"""The playlist's bookmarks, kept by file: shared by the cells playing one,
or each cell's own, and changed from one to the other."""

from pathlib import Path
from uuid import uuid4

import pytest

from gridplayer.models.bookmark import Bookmark
from gridplayer.models.file_bookmarks import FileBookmarks
from gridplayer.player.managers.bookmarks import BookmarksRegistry

MOVIE = Path("/videos/movie.mkv").absolute()
OTHER = Path("/videos/other.mkv").absolute()

FIRST = uuid4()
SECOND = uuid4()

A = (Bookmark(time_ms=10000), Bookmark(time_ms=30000, name="Goal"))
B = (Bookmark(time_ms=20000, name="Kick-off"), Bookmark(time_ms=30100))


def _times(bookmarks):
    return [bookmark.time_ms for bookmark in bookmarks]


@pytest.fixture
def registry():
    return BookmarksRegistry()


@pytest.fixture
def changes(registry):
    seen = []
    registry.changed.connect(lambda: seen.append(True))
    return seen


@pytest.fixture
def by_cell(registry):
    registry.set_shared(False, ())
    return registry


class TestShared:
    def test_a_file_has_the_same_in_every_cell(self, registry):
        registry.set(MOVIE, FIRST, A)

        assert registry.get(MOVIE, SECOND) == A

    def test_other_files_have_their_own(self, registry):
        registry.set(MOVIE, FIRST, A)

        assert registry.get(OTHER, FIRST) == ()

    def test_a_youtube_video_is_one_however_linked(self, registry):
        registry.set("https://www.youtube.com/watch?v=aqz-KE-bpKQ", FIRST, A)

        assert registry.get("https://youtu.be/aqz-KE-bpKQ", FIRST) == A

    def test_they_are_put_in_order_one_to_a_place(self, registry):
        registry.set(MOVIE, None, [A[1], A[0], Bookmark(time_ms=10000, name="Again")])

        assert registry.get(MOVIE, None) == A

    def test_a_file_left_without_any_has_no_entry(self, registry):
        registry.set(MOVIE, None, A)
        registry.set(MOVIE, None, [])

        assert registry.entries() == []

    def test_every_change_is_told_and_only_a_change(self, registry, changes):
        registry.set(MOVIE, None, A)
        registry.set(MOVIE, None, A)
        registry.set(OTHER, None, [])

        assert len(changes) == 1

    def test_those_from_elsewhere_are_added_to_its_own(self, registry):
        registry.set(MOVIE, None, A)

        registry.add(MOVIE, None, B)

        assert _times(registry.get(MOVIE, None)) == [10000, 20000, 30000]

    def test_the_file_is_kept_as_first_written(self, registry):
        registry.set(MOVIE, None, A)
        registry.set(Path(str(MOVIE.parent / "x" / ".." / MOVIE.name)), None, B)

        assert registry.entries()[0].uri == MOVIE


class TestByCell:
    def test_each_cell_has_its_own(self, by_cell):
        by_cell.set(MOVIE, FIRST, A)
        by_cell.set(MOVIE, SECOND, B)

        assert by_cell.get(MOVIE, FIRST) == A
        assert by_cell.get(MOVIE, SECOND) == B

    def test_a_file_left_from_sharing_goes_to_the_first_cell_to_open_it(self, by_cell):
        by_cell.load([FileBookmarks(uri=MOVIE, bookmarks=list(A))])

        by_cell.claim(MOVIE, FIRST)
        by_cell.claim(MOVIE, SECOND)

        assert by_cell.get(MOVIE, FIRST) == A
        assert by_cell.get(MOVIE, SECOND) == ()

    def test_a_cell_with_its_own_takes_none_of_those(self, by_cell):
        by_cell.set(MOVIE, FIRST, B)
        by_cell.put_entries([FileBookmarks(uri=MOVIE, bookmarks=list(A))])

        by_cell.claim(MOVIE, FIRST)

        assert by_cell.get(MOVIE, FIRST) == B

    def test_shared_nothing_is_taken(self, registry):
        registry.set(MOVIE, None, A)

        registry.claim(MOVIE, FIRST)

        assert registry.entries()[0].cell is None


class TestStoppingSharing:
    def test_each_cell_playing_a_file_gets_a_copy(self, registry):
        registry.set(MOVIE, None, A)

        registry.set_shared(False, [(MOVIE, FIRST), (MOVIE, SECOND)])

        assert registry.get(MOVIE, FIRST) == A
        assert registry.get(MOVIE, SECOND) == A

    def test_and_from_then_on_its_own(self, registry):
        registry.set(MOVIE, None, A)
        registry.set_shared(False, [(MOVIE, FIRST), (MOVIE, SECOND)])

        registry.set(MOVIE, FIRST, B)

        assert registry.get(MOVIE, SECOND) == A

    def test_those_of_a_file_not_open_wait_for_a_cell(self, registry):
        registry.set(OTHER, None, A)

        registry.set_shared(False, [(MOVIE, FIRST)])

        assert registry.entries() == [FileBookmarks(uri=OTHER, bookmarks=list(A))]


class TestSharing:
    def test_a_file_s_lists_are_made_one(self, by_cell):
        by_cell.set(MOVIE, FIRST, A)
        by_cell.set(MOVIE, SECOND, B)

        by_cell.set_shared(True, [(MOVIE, FIRST), (MOVIE, SECOND)])

        assert _times(by_cell.get(MOVIE, FIRST)) == [10000, 20000, 30000]
        assert by_cell.entries()[0].cell is None

    def test_at_one_place_the_first_cell_s_name_is_kept(self, by_cell):
        by_cell.set(MOVIE, SECOND, [Bookmark(time_ms=30000, name="Second's")])
        by_cell.set(MOVIE, FIRST, [Bookmark(time_ms=30000, name="First's")])

        by_cell.set_shared(True, [(MOVIE, FIRST), (MOVIE, SECOND)])

        assert by_cell.get(MOVIE, None) == (Bookmark(time_ms=30000, name="First's"),)

    def test_a_closed_cell_s_are_dropped(self, by_cell):
        by_cell.set(MOVIE, FIRST, A)
        by_cell.set(MOVIE, SECOND, B)

        by_cell.set_shared(True, [(MOVIE, FIRST)])

        assert by_cell.entries() == [FileBookmarks(uri=MOVIE, bookmarks=list(A))]

    def test_those_waiting_for_a_cell_are_kept(self, by_cell):
        by_cell.put_entries([FileBookmarks(uri=OTHER, bookmarks=list(A))])

        by_cell.set_shared(True, [(MOVIE, FIRST)])

        assert by_cell.get(OTHER, None) == A

    def test_what_would_be_merged_is_told_beforehand(self, by_cell):
        by_cell.set(MOVIE, FIRST, A)
        by_cell.set(MOVIE, SECOND, B)
        by_cell.set(OTHER, FIRST, A)
        by_cell.set(OTHER, SECOND, A)

        cells = [(MOVIE, FIRST), (MOVIE, SECOND), (OTHER, FIRST), (OTHER, SECOND)]

        assert by_cell.disagreeing(cells) == [(MOVIE, 2)]

    def test_a_closed_cell_s_are_not_counted(self, by_cell):
        by_cell.set(MOVIE, FIRST, A)
        by_cell.set(MOVIE, SECOND, B)

        assert by_cell.disagreeing([(MOVIE, FIRST)]) == []


class TestLoading:
    def test_those_of_a_playlist_take_the_place_of_any_there_were(self, registry):
        registry.set(OTHER, None, B)

        registry.load([FileBookmarks(uri=MOVIE, bookmarks=list(A))])

        assert registry.get(MOVIE, None) == A
        assert registry.get(OTHER, None) == ()

    def test_two_entries_for_one_file_are_merged(self, registry):
        registry.load(
            [
                FileBookmarks(uri=MOVIE, bookmarks=list(A)),
                FileBookmarks(uri=MOVIE, bookmarks=list(B)),
            ]
        )

        assert _times(registry.get(MOVIE, None)) == [10000, 20000, 30000]

    def test_by_cell_each_cell_the_playlist_opens_has_its_own(self, by_cell):
        by_cell.load(
            [
                FileBookmarks(uri=MOVIE, cell=FIRST, bookmarks=list(A)),
                FileBookmarks(uri=MOVIE, cell=SECOND, bookmarks=list(B)),
            ],
            cells=[FIRST, SECOND],
        )

        assert by_cell.get(MOVIE, FIRST) == A
        assert by_cell.get(MOVIE, SECOND) == B

    def test_by_cell_one_it_does_not_open_leaves_them_for_the_file(self, by_cell):
        # its video left out of the playlist, its file not found: saved now,
        # they would go as a closed cell's do
        by_cell.load(
            [FileBookmarks(uri=MOVIE, cell=SECOND, bookmarks=list(A))],
            cells=[FIRST],
        )

        assert by_cell.kept_entries({FIRST}) == [
            FileBookmarks(uri=MOVIE, bookmarks=list(A))
        ]

        by_cell.claim(MOVIE, FIRST)

        assert by_cell.get(MOVIE, FIRST) == A

    def test_two_it_does_not_open_are_left_merged(self, by_cell):
        by_cell.load(
            [
                FileBookmarks(uri=MOVIE, cell=FIRST, bookmarks=list(A)),
                FileBookmarks(uri=MOVIE, cell=SECOND, bookmarks=list(B)),
            ]
        )

        assert _times(by_cell.get(MOVIE, None)) == [10000, 20000, 30000]

    def test_each_cell_s_read_as_shared_are_merged(self, registry):
        registry.load(
            [
                FileBookmarks(uri=MOVIE, cell=FIRST, bookmarks=list(A)),
                FileBookmarks(uri=MOVIE, cell=SECOND, bookmarks=list(B)),
            ]
        )

        assert _times(registry.get(MOVIE, None)) == [10000, 20000, 30000]


class TestSaving:
    def test_a_closed_cell_s_are_left_out(self, by_cell):
        by_cell.set(MOVIE, FIRST, A)
        by_cell.set(MOVIE, SECOND, B)

        assert by_cell.kept_entries({FIRST}) == [
            FileBookmarks(uri=MOVIE, cell=FIRST, bookmarks=list(A))
        ]

    def test_and_forgotten_once_saved(self, by_cell):
        by_cell.set(MOVIE, FIRST, A)
        by_cell.set(MOVIE, SECOND, B)

        by_cell.forget_cells_gone({FIRST})

        assert by_cell.get(MOVIE, SECOND) == ()

    def test_those_waiting_for_a_cell_are_kept(self, by_cell):
        by_cell.put_entries([FileBookmarks(uri=MOVIE, bookmarks=list(A))])

        assert by_cell.kept_entries(set()) == by_cell.entries()
