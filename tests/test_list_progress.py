import threading

import pytest
from PyQt5.QtWidgets import QApplication

from gridplayer.utils import list_progress
from gridplayer.utils.list_progress import ReadingEnough, ReadingStopped, Throttled
from gridplayer.widgets import combo_box
from gridplayer.widgets.combo_box import ElidedComboBox


def test_told_once_and_then_not_for_a_while(mocker):
    times = iter([0.0, 0.1, 0.3])
    mocker.patch.object(
        list_progress.time, "monotonic", side_effect=lambda: next(times)
    )
    told = []
    tell = Throttled(lambda *said: told.append(said))

    tell("bytes", 1, 10)
    tell("bytes", 2, 10)
    tell("bytes", 3, 10)

    assert told == [("bytes", 1, 10), ("bytes", 3, 10)]


def test_what_comes_next_told_at_once(mocker):
    times = iter([0.0, 0.1, 0.2])
    mocker.patch.object(
        list_progress.time, "monotonic", side_effect=lambda: next(times)
    )
    told = []
    tell = Throttled(lambda *said: told.append(said[0]))

    tell("bytes", 1, 10)
    tell("items", 2000, 1)
    tell("comparing", 0)

    assert told == ["bytes", "items", "comparing"]


def test_stopped_where_asked_to():
    stop = threading.Event()
    tell = Throttled(lambda *said: None, stop=stop)
    tell("items", 1)

    stop.set()

    with pytest.raises(ReadingStopped):
        tell("items", 2)


def test_the_stop_is_no_error_any_reader_would_take_for_its_own():
    assert not issubclass(ReadingStopped, (OSError, ValueError))


def test_ended_where_asked_to():
    enough = threading.Event()
    tell = Throttled(lambda *said: None, enough=enough)
    tell("files", 1)

    enough.set()

    with pytest.raises(ReadingEnough):
        tell("files", 2)


def test_stopped_rather_than_ended_where_asked_to_do_both():
    stop, enough = threading.Event(), threading.Event()
    tell = Throttled(lambda *said: None, stop=stop, enough=enough)

    stop.set()
    enough.set()

    with pytest.raises(ReadingStopped):
        tell("files", 1)


def test_the_end_is_no_stop_and_no_error():
    assert not issubclass(ReadingEnough, (ReadingStopped, OSError, ValueError))


def test_a_folder_looked_through_said_by_its_files():
    assert list_progress.reading_txt("files", 12345) == (
        "Scanning folder… 12,345 files",
        0,
    )


class TestAComboNarrowerThanItsText:
    @pytest.fixture
    def combo(self):
        QApplication.instance() or QApplication([])
        combo = ElidedComboBox()
        combo.addItems(["Short", "A group with a name far longer than any box (12)"])
        combo.setMaximumWidth(120)
        combo.resize(120, combo.sizeHint().height())

        yield combo

        combo.hidePopup()
        combo.deleteLater()

    def test_drawn_without_trouble(self, combo):
        combo.setCurrentIndex(1)
        combo.show()

        assert not combo.grab().isNull()

    def test_opens_as_wide_as_its_longest_item(self, combo):
        combo.show()
        longest = combo.view().fontMetrics().horizontalAdvance(combo.itemText(1))
        screen = combo.screen().availableGeometry().width()

        combo.showPopup()

        # up to most of the screen
        assert combo.view().minimumWidth() == min(
            longest + combo_box.POPUP_ROOM_PX,
            int(screen * combo_box.POPUP_MAX_SCREEN_SHARE),
        )
        assert combo.view().minimumWidth() > combo.width()
