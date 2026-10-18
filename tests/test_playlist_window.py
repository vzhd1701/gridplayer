"""The Playlist window: the playlist's settings and those of new videos,
its bookmarks and its lists, as pages of one window; a playlist that keeps
all its settings; new videos' settings given to the videos already there."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QEvent, QPoint, QSettings, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget

from gridplayer.dialogs import playlist_settings
from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.playlist_settings import PlaylistSettingsDialog
from gridplayer.models.grid_state import GridState
from gridplayer.models.video import Video
from gridplayer.params.settings_bindings import (
    GRID_STATE_ATTR,
    PLAYLIST_ATTRS,
    VIDEO_DEFAULT_ATTRS,
    VIDEO_PARAM_ATTRS,
)
from gridplayer.params.static import (
    AudioChannelMode,
    VideoCellViewMode,
    VideoInitialState,
    VideoTransform,
)
from gridplayer.player.managers.playlist import PlaylistManager
from gridplayer.playlist_settings import (
    SAVE_ALL_KEY,
    PlaylistSettings,
)
from gridplayer.settings import _default_settings, _Settings
from gridplayer.widgets.video_block import VideoBlock
from tests.conftest import mock_block_parts

SHARING = "playlist/bookmarks_shared"
VOLUME = "video_defaults/volume"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """An ini of our own, so no test writes the one the user has."""

    store = _Settings.__new__(_Settings)
    store.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    monkeypatch.setattr(playlist_settings, "Settings", lambda: store)

    return store


class _Part(QWidget):
    """A page of what the playlist holds, as the window sees it."""

    sharing_asked = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.window_given = window
        self.calls = []

    def cancel(self):
        self.calls.append("cancel")

    def close_down(self):
        self.calls.append("close_down")

    def set_sharing_to_come(self, is_shared):
        self.calls.append(("sharing", is_shared))


@pytest.fixture
def parts():
    made = {}

    def _maker(part_id):
        def _make(window):
            made[part_id] = _Part(window)
            return made[part_id]

        return _make

    return SimpleNamespace(
        made=made, makers={"bookmarks": _maker("bookmarks"), "lists": _maker("lists")}
    )


@pytest.fixture
def make_window(settings, parts):
    made = []

    def _make(overrides=None, **kwargs):
        kwargs.setdefault("parts", parts.makers)
        window = PlaylistSettingsDialog(overrides or {}, GridState(), **kwargs)
        made.append(window)
        return window

    yield _make

    for window in made:
        window.deleteLater()

    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _shown(window):
    return window.section_page.currentWidget()


class TestThePages:
    def test_the_window_is_the_playlist(self, make_window):
        assert make_window().windowTitle() == "Playlist"

    def test_its_settings_then_what_it_holds(self, make_window):
        window = make_window()

        assert [item.text() for item in window.section_items] == [
            "Playlist",
            "New Videos",
            "Bookmarks",
            "Lists",
        ]

    def test_with_nothing_held_only_the_settings(self, make_window):
        window = make_window(parts=None)

        assert [item.text() for item in window.section_items] == [
            "Playlist",
            "New Videos",
        ]

    def test_what_it_holds_is_made_once_shown(self, make_window, parts):
        window = make_window()

        assert parts.made == {}

        window.show_page("lists")

        assert set(parts.made) == {"lists"}
        assert parts.made["lists"].window_given is window
        assert _shown(window) is window.pages["lists"]

    def test_opened_at_a_page(self, make_window, parts):
        window = make_window(page="bookmarks")

        assert _shown(window) is window.pages["bookmarks"]
        assert window.part("bookmarks") is parts.made["bookmarks"]

    def test_new_videos_say_what_they_are_for(self, make_window):
        window = make_window()

        assert "added from now on" in window.notes["video"].text()

    def test_no_reset_on_what_it_holds(self, make_window):
        window = make_window({"playlist/zoom_step": 30})

        assert not window.resetPage.isHidden()

        window.show_page("bookmarks")

        assert window.resetPage.isHidden()


class TestClosing:
    def test_cancel_puts_back_what_was_done_on_its_pages(self, make_window, parts):
        window = make_window()
        window.show_page("bookmarks")

        window.reject()

        assert parts.made["bookmarks"].calls[-2:] == ["cancel", "close_down"]

    def test_ok_keeps_it(self, make_window, parts):
        window = make_window()
        window.show_page("lists")

        window.accept()

        assert parts.made["lists"].calls == ["close_down"]


class TestTheBookmarksSharing:
    def test_the_page_says_what_the_switch_will_do(self, make_window, parts):
        window = make_window()
        window.show_page("bookmarks")
        part = parts.made["bookmarks"]

        window.widget(SHARING).setChecked(False)

        assert part.calls[-1] == ("sharing", False)

    def test_its_link_goes_to_the_switch(self, make_window, parts):
        # from a page other than the switch's, never shown till then
        window = make_window(page="bookmarks")
        window.resize(window.width(), 420)
        window.show()
        QApplication.processEvents()

        parts.made["bookmarks"].sharing_asked.emit()

        assert _shown(window) is window.pages["playlist"]
        assert QApplication.focusWidget() is window.widget(SHARING)

        form = window.forms["playlist"]
        viewport = form._scroll_area().viewport()
        row = form._rows[SHARING]
        top = row.mapTo(viewport, QPoint(0, 0)).y()
        # in the middle, give or take a little
        assert abs(top + row.height() // 2 - viewport.height() // 2) <= 2


class TestKeepingAllSettings:
    def test_saves_every_value(self, make_window):
        window = make_window()

        window.widget(SAVE_ALL_KEY).setChecked(True)
        result = window.result_overrides()

        for key in (*PLAYLIST_ATTRS, *VIDEO_DEFAULT_ATTRS, *GRID_STATE_ATTR):
            assert key in result, key
        assert result[SAVE_ALL_KEY] is True

    def test_says_so_at_the_top(self, make_window):
        window = make_window()

        assert "for this playlist only" in window.notes["playlist"].text()

        window.widget(SAVE_ALL_KEY).setChecked(True)

        assert "keeps all its settings" in window.notes["playlist"].text()

    def test_marks_only_what_differs_from_the_defaults(self, settings, make_window):
        overrides = {
            key: settings.get(key) for key in (*PLAYLIST_ATTRS, *VIDEO_DEFAULT_ATTRS)
        }
        overrides["playlist/zoom_step"] = settings.get("playlist/zoom_step") + 10
        overrides[SAVE_ALL_KEY] = True
        window = make_window(overrides)
        form = window.form_of("playlist/zoom_step")

        assert form.is_marked("playlist/zoom_step")
        assert not form.is_marked("playlist/view_sync")

    def test_let_go_of_keeps_only_what_differs(self, settings, make_window):
        overrides = {
            key: settings.get(key) for key in (*PLAYLIST_ATTRS, *VIDEO_DEFAULT_ATTRS)
        }
        overrides["playlist/zoom_step"] = settings.get("playlist/zoom_step") + 10
        overrides[SAVE_ALL_KEY] = True
        window = make_window(overrides)

        window.widget(SAVE_ALL_KEY).setChecked(False)

        assert window.result_overrides() == {
            "playlist/zoom_step": settings.get("playlist/zoom_step") + 10
        }


class TestNewVideos:
    def test_what_was_changed_for_them(self, make_window):
        window = make_window()

        window.widget(VOLUME).setValue(0.5)

        assert window.video_changes() == {VOLUME: 0.5}

    def test_how_they_start_is_for_them_only(self, make_window):
        window = make_window()
        combo = window.widget("video_defaults/initial_state")

        combo.setCurrentIndex(combo.findData(VideoInitialState.PAUSED))

        assert window.video_changes() == {}

    @pytest.mark.parametrize("answer", [True, False])
    def test_asked_on_ok_about_the_videos_here(self, make_window, monkeypatch, answer):
        window = make_window(has_videos=True)
        asked = []
        monkeypatch.setattr(
            window, "_ask_for_videos_here", lambda c: asked.append(c) or answer
        )
        window.widget(VOLUME).setValue(0.5)

        window.accept()

        assert asked == [{VOLUME: 0.5}]
        assert window.is_for_all_videos is answer
        assert window.result() == window.Accepted

    def test_cancel_in_the_question_goes_back(self, make_window, monkeypatch):
        window = make_window(has_videos=True)
        monkeypatch.setattr(window, "_ask_for_videos_here", lambda _changes: None)
        window.widget(VOLUME).setValue(0.5)
        window.show()

        window.accept()

        assert window.isVisible()
        window.reject()

    def test_not_asked_with_no_videos_here(self, make_window, monkeypatch):
        window = make_window(has_videos=False)
        asked = Mock()
        monkeypatch.setattr(window, "_ask_for_videos_here", asked)
        window.widget(VOLUME).setValue(0.5)

        window.accept()

        asked.assert_not_called()
        assert window.is_for_all_videos is False

    @pytest.mark.parametrize(
        ("clicked", "answer"),
        [("All videos", True), ("Only new", False), (None, None)],
    )
    def test_the_question(self, make_window, monkeypatch, clicked, answer):
        window = make_window(has_videos=True)
        seen = {}

        def _exec(box):
            seen["text"] = box.text()
            seen["info"] = box.informativeText()
            if clicked is None:
                box.reject()
            else:
                (button,) = [b for b in box.buttons() if b.text() == clicked]
                button.click()
            return 0

        monkeypatch.setattr(QCustomMessageBox, "exec_", _exec)

        assert window._ask_for_videos_here({VOLUME: 0.5}) is answer
        assert seen["text"] == "Change the videos already here too?"
        assert "Volume" in seen["info"]


def test_every_video_default_fills_a_field_of_a_video():
    assert set(VIDEO_PARAM_ATTRS) == set(VIDEO_DEFAULT_ATTRS)

    for key, field in VIDEO_PARAM_ATTRS.items():
        assert field in Video.model_fields, key


def test_each_video_default_is_where_a_video_takes_it_from():
    """A video made takes the default from the field named for it: a switch
    the other way from out of the box, to tell it from the rest."""

    wanted = {}
    for key, field in VIDEO_PARAM_ATTRS.items():
        if key.endswith("_track_mode") or key == "video_defaults/color":
            continue
        value = _default_settings[key]
        wanted[field] = not value if isinstance(value, bool) else value
        PlaylistSettings().set(key, wanted[field])

    video = Video(uri="http://example.com/a.mp4")

    assert {field: getattr(video, field) for field in wanted} == wanted


class _Blocks(list):
    pass


class TestGivenToTheVideosHere:
    def _manager(self, blocks):
        ctx = SimpleNamespace(commands=SimpleNamespace(), video_blocks=_Blocks(blocks))
        return PlaylistManager(context=ctx, parent=QWidget())

    def test_each_video_is_given_the_changes(self):
        block = Mock()
        block.video_params = Video(uri="http://example.com/a.mp4")
        manager = self._manager([block])

        manager._give_videos_here(
            {VOLUME: 0.5, "video_defaults/cell_view_mode": VideoCellViewMode.FIT}
        )

        block.adopt_defaults.assert_called_once_with(
            {"volume": 0.5, "cell_view_mode": VideoCellViewMode.FIT}
        )

    def test_checked_as_a_video_s_own(self):
        block = Mock()
        block.video_params = Video(uri="http://example.com/a.mp4")
        manager = self._manager([block])

        manager._give_videos_here({"video_defaults/color": "#ff0000"})

        (update,), _ = block.adopt_defaults.call_args
        assert update["color"].as_hex() == "#f00"

    def test_a_track_mode_is_the_pick_it_makes(self):
        block = Mock()
        block.video_params = Video(uri="http://example.com/a.mp4")
        manager = self._manager([block])

        manager._give_videos_here({"video_defaults/audio_track_mode": "x"})

        (update,), _ = block.adopt_defaults.call_args
        assert set(update) == {"audio_selection"}


def _block(initialized=True):
    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri="http://example.com/a.mp4")
    block.is_video_initialized = initialized
    block.video_tracks = [0]
    mock_block_parts(block)
    return block


class TestAVideoAdoptingThem:
    def test_shown_as_it_plays(self):
        block = _block()

        VideoBlock.adopt_defaults(block, {"volume": 0.5, "is_muted": True})

        block.audio.set_volume.assert_called_once_with(0.5)
        block.audio.set_muted.assert_called_once_with(True)
        block.reload.assert_not_called()
        assert block.video_params.volume == 0.5

    def test_one_not_opened_yet_takes_them_as_it_opens(self):
        block = _block(initialized=False)

        VideoBlock.adopt_defaults(block, {"volume": 0.5})

        block.audio.set_volume.assert_not_called()
        assert block.video_params.volume == 0.5

    def test_what_is_read_as_it_opens_has_it_opened_again(self):
        block = _block()

        VideoBlock.adopt_defaults(block, {"transform": VideoTransform.ROTATE_90})

        block.reload.assert_called_once()
        assert block.video_params.transform is VideoTransform.ROTATE_90

    def test_the_rest_read_when_next_needed(self):
        block = _block()

        VideoBlock.adopt_defaults(block, {"audio_channel_mode": AudioChannelMode.LEFT})

        assert block.video_params.audio_channel_mode is AudioChannelMode.LEFT


def test_the_question_has_cancel_to_go_back(make_window, monkeypatch):
    window = make_window(has_videos=True)
    roles = {}

    def _exec(box):
        roles.update({b.text(): box.buttonRole(b) for b in box.buttons()})
        box.reject()
        return 0

    monkeypatch.setattr(QCustomMessageBox, "exec_", _exec)

    window._ask_for_videos_here({VOLUME: 0.5})

    assert roles["All videos"] == QMessageBox.AcceptRole
    assert roles["Only new"] == QMessageBox.RejectRole
