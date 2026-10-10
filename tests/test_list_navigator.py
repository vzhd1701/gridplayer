"""A cell going along the list it plays from: where it is on it, which item
comes next, and when the list has been played through."""

from pathlib import Path

import pytest
from PyQt5.QtCore import QSettings

from gridplayer.models.media_list import ListItem, MediaList
from gridplayer.models.video import Video
from gridplayer.params.static import ListEndAction
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.folder_navigator import FolderStep
from gridplayer.utils.list_navigator import (
    ListNavigator,
    ListPlace,
    list_neighbour,
    list_place,
)
from gridplayer.utils.next_file import MAX_MISSING_FILES

URL = "https://example.com/live/{}.m3u8"


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings
    PlaylistSettings().clear()


def _files(root: Path, *names: str) -> list[Path]:
    files = []

    for name in names:
        path = root / name
        path.touch()
        files.append(path)

    return files


def _list(*uris) -> MediaList:
    return MediaList(items=[ListItem(uri=uri) for uri in uris])


def _channels(count: int) -> MediaList:
    return _list(*(URL.format(n) for n in range(count)))


def _video(media_list: MediaList, index: int | None, **kwargs) -> Video:
    uri = media_list.items[index].uri if index is not None else URL.format("off")

    return Video(uri=uri, list_id=media_list.id, list_index=index, **kwargs)


class TestWhereTheVideoIsOnItsList:
    def test_at_the_place_it_was_put_in_from(self):
        media_list = _list(URL.format(1), URL.format(1), URL.format(1))

        assert list_place(media_list, _video(media_list, 2)) == ListPlace(2, True)

    def test_by_the_item_it_came_from_wherever_that_was_moved_to(self):
        media_list = _channels(3)
        moved = media_list.model_copy(
            update={"items": tuple(reversed(media_list.items))}
        )
        key = media_list.items[0].key

        place = list_place(moved, _video(media_list, 0), key)

        assert place == ListPlace(2, True)

    def test_by_its_file_where_the_place_is_another_files_now(self):
        media_list = _channels(3)
        video = _video(media_list, 2)
        video.list_index = 0

        assert list_place(media_list, video) == ListPlace(2, True)

    def test_a_file_known_whatever_the_case_of_its_letters_on_windows(
        self, tmp_path, mocker
    ):
        mocker.patch("os.path.normcase", str.lower)
        (movie,) = _files(tmp_path, "Movie.mp4")
        media_list = _list(Path(str(movie).upper()))

        place = list_place(media_list, Video(uri=movie, list_index=None))

        assert place == ListPlace(0, True)

    def test_where_it_was_once_taken_off(self):
        media_list = _channels(5)
        video = _video(media_list, 3)
        shorter = media_list.model_copy(
            update={"items": media_list.items[:3] + media_list.items[4:]}
        )

        assert list_place(shorter, video) == ListPlace(3, False)

    def test_past_the_end_of_a_list_cut_short(self):
        media_list = _channels(5)
        video = _video(media_list, 4)
        shorter = media_list.model_copy(update={"items": media_list.items[:2]})

        assert list_place(shorter, video) == ListPlace(2, False)


class TestTheNextItem:
    def test_after_this_one(self):
        media_list = _channels(3)

        assert list_neighbour(media_list, ListPlace(0, True), 1) == (1, False)

    def test_before_this_one(self):
        media_list = _channels(3)

        assert list_neighbour(media_list, ListPlace(2, True), -1) == (1, False)

    def test_round_the_end_to_the_start(self):
        media_list = _channels(3)

        assert list_neighbour(media_list, ListPlace(2, True), 1) == (0, True)

    def test_round_the_start_to_the_end(self):
        media_list = _channels(3)

        assert list_neighbour(media_list, ListPlace(0, True), -1) == (2, True)

    def test_a_list_of_one_goes_round_to_itself(self):
        media_list = _channels(1)

        assert list_neighbour(media_list, ListPlace(0, True), 1) == (0, True)

    def test_for_one_taken_off_the_item_in_its_place(self):
        media_list = _channels(3)

        assert list_neighbour(media_list, ListPlace(1, False), 1) == (1, False)
        assert list_neighbour(media_list, ListPlace(1, False), -1) == (0, False)

    def test_for_one_taken_off_the_end_the_start(self):
        media_list = _channels(3)

        assert list_neighbour(media_list, ListPlace(3, False), 1) == (0, True)
        assert list_neighbour(media_list, ListPlace(3, False), -1) == (2, False)

    def test_past_files_that_are_gone(self, tmp_path):
        files = _files(tmp_path, "a.mp4", "c.mp4")
        media_list = _list(files[0], tmp_path / "b.mp4", files[1])

        assert list_neighbour(media_list, ListPlace(0, True), 1) == (2, False)

    def test_going_round_past_them_is_going_round(self, tmp_path):
        files = _files(tmp_path, "a.mp4", "b.mp4")
        media_list = _list(files[0], files[1], tmp_path / "gone.mp4")

        assert list_neighbour(media_list, ListPlace(1, True), 1) == (0, True)

    def test_a_link_is_not_looked_for(self):
        media_list = _list("https://nowhere.invalid/a", "https://nowhere.invalid/b")

        assert list_neighbour(media_list, ListPlace(0, True), 1) == (1, False)

    def test_none_where_too_many_in_a_row_are_gone(self, tmp_path):
        gone = [tmp_path / f"{n}.mp4" for n in range(MAX_MISSING_FILES + 2)]
        media_list = _list(*gone)

        index, _is_round = list_neighbour(media_list, ListPlace(0, True), 1)

        assert index is None

    def test_none_on_an_empty_list(self):
        assert list_neighbour(_list(), ListPlace(0, False), 1) == (None, False)


class _Cell:
    """What a navigator is given by a cell, and what it hands back."""

    def __init__(self, media_list, index, open_elsewhere=(), **video_kwargs):
        self.media_list = media_list
        self.video = _video(media_list, index, **video_kwargs)
        self.key = media_list.items[index].key if index is not None else None
        self.played = []
        self.ended = []
        self.open_elsewhere = list(open_elsewhere)

        self.navigator = ListNavigator(
            video=lambda: self.video,
            media_list=lambda: self.media_list,
            item_key=lambda: self.key,
            switch=self._switch,
            end_of_list=self.ended.append,
            open_elsewhere=lambda: self.open_elsewhere,
        )

    def _switch(self, index):
        self.played.append(index)

        if index is None:
            return

        item = self.media_list.items[index]
        self.video.uri = item.uri
        self.video.list_index = index
        self.key = item.key

    def step(self, step, is_end=False):
        self.navigator.step(step, is_end=is_end)


class TestTheNavigator:
    def test_next_and_previous(self):
        cell = _Cell(_channels(3), 0)

        cell.step(FolderStep.NEXT)
        cell.step(FolderStep.NEXT)
        cell.step(FolderStep.PREVIOUS)

        assert cell.played == [1, 2, 1]

    def test_by_hand_it_goes_round_whatever_the_list_end_is_set_to(self):
        cell = _Cell(_channels(3), 2, list_end_action=ListEndAction.STOP)

        cell.step(FolderStep.NEXT)

        assert cell.played == [0]
        assert cell.ended == []

    def test_at_the_end_it_starts_over_by_default(self):
        cell = _Cell(_channels(3), 2)

        cell.step(FolderStep.NEXT, is_end=True)

        assert cell.played == [0]

    @pytest.mark.parametrize(
        "action", [ListEndAction.PAUSE, ListEndAction.STOP, ListEndAction.CLOSE]
    )
    def test_or_does_what_it_is_set_to_at_the_end(self, action):
        cell = _Cell(_channels(3), 2, list_end_action=action)

        cell.step(FolderStep.NEXT, is_end=True)

        assert cell.played == []
        assert cell.ended == [action]

    def test_going_backwards_the_start_is_its_end(self):
        cell = _Cell(_channels(3), 0, list_end_action=ListEndAction.STOP)

        cell.step(FolderStep.PREVIOUS, is_end=True)

        assert cell.ended == [ListEndAction.STOP]

    def test_before_the_end_the_list_goes_on(self):
        cell = _Cell(_channels(3), 1, list_end_action=ListEndAction.STOP)

        cell.step(FolderStep.NEXT, is_end=True)

        assert cell.played == [2]
        assert cell.ended == []

    def test_a_random_one_plays_every_item_once_before_it_ends(self):
        cell = _Cell(_channels(4), 0, list_end_action=ListEndAction.STOP)

        for _ in range(3):
            cell.step(FolderStep.RANDOM, is_end=True)

        assert sorted(cell.played) == [1, 2, 3]
        assert cell.ended == []

        cell.step(FolderStep.RANDOM, is_end=True)

        assert cell.ended == [ListEndAction.STOP]

    def test_a_random_one_starts_another_round_by_default(self):
        cell = _Cell(_channels(3), 0)

        for _ in range(5):
            cell.step(FolderStep.RANDOM, is_end=True)

        assert len(cell.played) == 5
        assert None not in cell.played

    def test_back_goes_to_the_one_played_before(self):
        cell = _Cell(_channels(5), 0)

        cell.step(FolderStep.RANDOM)
        first = cell.played[-1]
        cell.step(FolderStep.RANDOM)
        cell.step(FolderStep.BACK)

        assert cell.played[-1] == first

    def test_back_with_none_before_starts_this_one_over(self):
        cell = _Cell(_channels(3), 1)

        cell.step(FolderStep.BACK)

        assert cell.played == [1]

    def test_a_list_with_the_same_link_twice_plays_both(self):
        media_list = _list(URL.format(1), URL.format(2), URL.format(1))
        cell = _Cell(media_list, 0)

        cell.step(FolderStep.NEXT)
        cell.step(FolderStep.NEXT)
        cell.step(FolderStep.NEXT)

        assert cell.played == [1, 2, 0]

    def test_a_random_one_open_in_another_cell_is_put_off(self, mocker):
        media_list = _channels(3)
        cell = _Cell(media_list, 0, open_elsewhere=[media_list.items[1].uri])
        mocker.patch.object(
            PlaylistSettings(),
            "get",
            side_effect=lambda key: (
                key == "playlist/shuffle_avoid_open" or Settings().get(key)
            ),
        )

        cell.step(FolderStep.RANDOM)

        assert cell.played == [2]

    def test_the_list_edited_meanwhile_is_the_one_gone_along(self):
        media_list = _channels(3)
        cell = _Cell(media_list, 0)
        added = ListItem(uri=URL.format("new"))
        cell.media_list = media_list.model_copy(
            update={"items": (media_list.items[0], added, *media_list.items[1:])}
        )

        cell.step(FolderStep.NEXT)

        assert cell.video.uri == added.uri

    def test_nothing_to_play_on_a_list_of_gone_files(self, tmp_path):
        files = _files(tmp_path, "0.mp4", "1.mp4", "2.mp4")
        cell = _Cell(_list(*files), 0)

        for file in files:
            file.unlink()

        cell.step(FolderStep.NEXT)

        assert cell.played == [None]

    def test_nothing_is_done_without_a_list(self):
        cell = _Cell(_channels(2), 0)
        cell.media_list = None

        cell.step(FolderStep.NEXT)

        assert cell.played == []
        assert cell.navigator.place() is None

    def test_a_list_left_is_let_go_of(self):
        cell = _Cell(_channels(2), 0)
        cell.navigator.place()

        cell.media_list = None
        cell.navigator.place()

        assert cell.navigator._last_place is None
