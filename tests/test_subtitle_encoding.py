"""What a subtitle file is read as when it is not UTF-8.

VLC reads a subtitle file as UTF-8 wherever it is valid UTF-8 and falls
back to Windows-1252 where it is not, so a Cyrillic or Japanese file from
before UTF-8 was everywhere comes out as the wrong letters. Naming the set
it was written in is the only way to fix that, and it is settled when the
input opens.
"""

from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QApplication

from gridplayer.dialogs.subtitle_encoding import SetSubtitleEncodingDialog
from gridplayer.models.playlist import PlaylistVideoDefaults
from gridplayer.models.video import Video
from gridplayer.params.actions import ACTIONS
from gridplayer.params.defaults_fields import VIDEO_FIELDS, _subtitle_encodings
from gridplayer.params.menu import SECTIONS
from gridplayer.params.subtitle_encodings import DEFAULT_ENCODING, SUBTITLE_ENCODINGS
from gridplayer.player.managers.active_block import (
    LOADING_COMMANDS,
    _subtitle_encoding_menu_item,
)
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.settings import Settings
from gridplayer.utils.libvlc_options_parser import get_vlc_options
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.static import MediaInput
from gridplayer.widgets.combo_box import MAX_VISIBLE_COMBO_ITEMS
from gridplayer.widgets.defaults_form import DefaultsForm
from gridplayer.widgets.video_block import VideoBlock, _is_reopen_needed

URI = "http://example.com/a.mp4"

SETTING = "video_defaults/subtitle_encoding"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings


class _MinimalPlayer(VlcPlayerBase):
    def notify_snapshot_taken(self, snapshot_path): ...
    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def notify_load_video_done(self, media_track): ...
    def notify_tracks_changed(self, media_track): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...


class _FakeEventManager:
    def event_attach(self, event_type, callback): ...


class _FakeMedia:
    def __init__(self):
        self.options = []

    def event_manager(self):
        return _FakeEventManager()

    def add_options(self, *options):
        self.options.extend(options)

    def parse_with_options(self, parse_flag, timeout): ...

    def tracks_get(self):
        return []


class _FakeInstance:
    def __init__(self, media):
        self._media = media

    def media_new(self, uri):
        return self._media

    def media_new_path(self, uri):
        return self._media


class _FakeMediaPlayer:
    def add_slave(self, slave_type, uri, is_select):
        return 0


def _options_for(encoding):
    """The options the media is opened with, for a video set to `encoding`."""

    media = _FakeMedia()
    player = _MinimalPlayer(vlc_instance=_FakeInstance(media))
    player._media_player = _FakeMediaPlayer()

    player.load_video(
        MediaInput(
            uri=URI,
            is_live=False,
            is_audio_only=False,
            size=(640, 360),
            video=Video(uri=URI, subtitle_encoding=encoding),
        )
    )

    return media.options


def _block(encoding):
    """A video block that records what it was handed to open again."""

    block = Mock(spec=VideoBlock)
    block.video_params = Video(uri=URI, subtitle_encoding=encoding)
    block.set_subtitle_encoding = partial(VideoBlock.set_subtitle_encoding, block)

    return block


def _reopened_with(block):
    return [call.args[0].subtitle_encoding for call in block.set_video.call_args_list]


def _apply(blocks, encoding):
    manager = Mock(spec=VideoBlocksManager)
    manager._ctx = SimpleNamespace(video_blocks=blocks)

    VideoBlocksManager.apply_subtitle_encoding(manager, encoding)


class TestWhatGoesToVLC:
    def test_nothing_is_said_when_nothing_was_picked(self):
        assert not [o for o in _options_for("") if "subsdec-encoding" in o]

    def test_the_pick_is_handed_over_as_the_decoder_names_it(self):
        assert ":subsdec-encoding=Windows-1251" in _options_for("Windows-1251")

    def test_it_travels_with_the_media_rather_than_the_instance(self):
        """Instance options decide which VLC process a video is played in.

        Sending the encoding that way would fork the pool one process per
        encoding for a grid that mixes them, which is why it goes on the
        media instead -- and why video_block reopens on its own.
        """

        video = Video(uri=URI, subtitle_encoding="Windows-1251")

        assert not [o for o in get_vlc_options(video) if "subsdec" in o]


class TestWhatIsOffered:
    def test_leaving_it_alone_is_the_first_way_out(self):
        offered = list(_subtitle_encodings())

        assert offered[0] == DEFAULT_ENCODING

    def test_the_locales_own_set_is_not_among_them(self):
        """VLC offers a "system" entry; it is deliberately left out.

        It reads the file as the locale's character set, which on a UTF-8
        locale is the one already tried -- so a file that is not UTF-8
        converts to nothing at all and the subtitle is dropped without a
        word. Naming the set covers everything it would have served.
        """

        assert "system" not in _subtitle_encodings()

    @pytest.mark.parametrize(
        "encoding",
        ["UTF-8", "Windows-1251", "KOI8-R", "Shift_JIS", "Big5", "ISO-8859-7"],
    )
    def test_the_sets_people_actually_have_files_in_are_there(self, encoding):
        assert encoding in SUBTITLE_ENCODINGS

    def test_the_one_name_glibc_does_not_know_is_not_among_them(self):
        """VLC lists ISO-2022-TW where its own label says EUC-TW.

        glibc's iconv has no ISO-2022-TW, so asking for it on Linux converts
        nothing and the raw bytes are drawn as though they were UTF-8 -- the
        wrong letters, with nothing said. EUC-TW is what the label promises
        and what every iconv actually has.
        """

        assert "ISO-2022-TW" not in SUBTITLE_ENCODINGS
        assert "EUC-TW" in SUBTITLE_ENCODINGS

    def test_each_one_is_named_once(self):
        names = list(SUBTITLE_ENCODINGS.values())

        assert len(names) == len(set(names))

    def test_it_sits_with_the_rest_of_the_subtitle_defaults(self):
        spec = next(f for f in VIDEO_FIELDS if f.settings_key == SETTING)

        assert spec.video_attr == "subtitle_encoding"
        assert spec.combo_values is _subtitle_encodings
        # it has to apply to a track picked from the menu too, not only to
        # one a video opens with, so nothing gates it
        assert spec.enabled_by is None


class TestTakingHold:
    """It is settled at the open, so a change has to reopen the video."""

    def test_a_different_set_reopens(self):
        assert _is_reopen_needed(
            Video(uri=URI, subtitle_encoding=""),
            Video(uri=URI, subtitle_encoding="KOI8-R"),
        )

    def test_the_same_set_leaves_the_video_alone(self):
        assert not _is_reopen_needed(
            Video(uri=URI, subtitle_encoding="KOI8-R"),
            Video(uri=URI, subtitle_encoding="KOI8-R"),
        )

    def test_the_first_video_has_nothing_to_differ_from(self):
        assert not _is_reopen_needed(None, Video(uri=URI, subtitle_encoding="KOI8-R"))

    def test_a_change_reaches_the_videos_already_open(self):
        block = _block("")

        _apply([block], "Windows-1251")

        assert _reopened_with(block) == ["Windows-1251"]

    def test_a_video_already_on_it_is_left_where_it_is(self):
        block = _block("Windows-1251")

        _apply([block], "Windows-1251")

        assert _reopened_with(block) == []

    def test_the_menu_asks_the_video_the_same_way(self):
        """The menu row and the defaults both end at set_subtitle_encoding."""

        block = _block("")

        block.set_subtitle_encoding("KOI8-R")

        assert _reopened_with(block) == ["KOI8-R"]


class TestWhereItIsRemembered:
    def test_a_new_video_starts_on_what_the_defaults_say(self):
        Settings().set(SETTING, "KOI8-R")

        assert Video(uri=URI).subtitle_encoding == "KOI8-R"

    def test_a_playlist_can_carry_one_of_its_own(self):
        defaults = PlaylistVideoDefaults(subtitle_encoding="Shift_JIS")

        assert defaults.subtitle_encoding == "Shift_JIS"

    def test_a_playlist_that_says_nothing_leaves_it_to_the_defaults(self):
        assert PlaylistVideoDefaults().subtitle_encoding is None


class TestPickingItOnOneVideo:
    """The menu is where somebody looking at the wrong letters ends up."""

    def test_it_is_a_row_in_the_subtitle_list_not_a_menu_of_its_own(self):
        """Forty-odd sets is a list to scroll, not a column to walk."""

        subtitles = next(
            item
            for item in SECTIONS["video_active"]
            if isinstance(item, tuple) and item[0] == "Subtitles"
        )
        names = [i[0] if isinstance(i, tuple) else i for i in subtitles]

        assert "Subtitle Encoding" not in names
        assert "Subtitle Encoding" not in ACTIONS

    def test_the_row_reads_back_what_is_in_force_and_opens_the_box(self):
        row = _subtitle_encoding_menu_item()

        assert row["title"].endswith(": %v")
        assert row["func"] == ("active", "subtitle_encoding_dialog")
        assert row["value_getter"] == ("active", "get_subtitle_encoding")
        assert hasattr(VideoBlock, "subtitle_encoding_dialog")
        assert hasattr(VideoBlock, "get_subtitle_encoding")

    def test_the_readout_names_the_set_that_was_picked(self):
        assert VideoBlock.get_subtitle_encoding(_block("KOI8-R")) == "KOI8-R"

    def test_the_readout_says_default_where_none_was(self):
        assert VideoBlock.get_subtitle_encoding(_block("")) == "Default"

    def test_it_still_answers_while_the_video_is_reopening(self):
        """Picking one is what started the reload the next pick lands in."""

        assert {
            "subtitle_encoding_dialog",
            "get_subtitle_encoding",
            "set_subtitle_encoding",
        } <= LOADING_COMMANDS


class TestTheBox:
    """A combo, the same one the playlist settings offer, on its own."""

    def test_it_offers_leaving_it_alone_first_then_every_set(self):
        dialog = SetSubtitleEncodingDialog()

        assert dialog.combo.count() == len(SUBTITLE_ENCODINGS) + 1
        assert dialog.combo.itemData(0) == DEFAULT_ENCODING

    def test_it_opens_on_the_one_the_video_is_reading_by(self):
        dialog = SetSubtitleEncodingDialog(encoding="Shift_JIS")

        assert dialog.combo.currentData() == "Shift_JIS"

    def test_a_set_the_video_carries_that_is_not_offered_falls_to_default(self):
        dialog = SetSubtitleEncodingDialog(encoding="ISO-2022-TW")

        assert dialog.combo.currentData() == DEFAULT_ENCODING

    def test_dismissing_it_leaves_the_video_alone(self, monkeypatch):
        monkeypatch.setattr(SetSubtitleEncodingDialog, "exec_", lambda self: 0)

        assert SetSubtitleEncodingDialog.get_encoding(encoding="KOI8-R") is None

    def test_taking_it_hands_back_what_was_picked(self, monkeypatch):
        def _pick(dialog):
            dialog.combo.setCurrentIndex(dialog.combo.findData("Windows-1251"))
            return 1

        monkeypatch.setattr(SetSubtitleEncodingDialog, "exec_", _pick)

        assert SetSubtitleEncodingDialog.get_encoding() == "Windows-1251"


class TestTheListFitsOnScreen:
    def test_a_list_this_long_gets_a_scroll_bar_rather_than_the_screen(self):
        form = DefaultsForm(VIDEO_FIELDS)
        combo = form._widgets[SETTING]

        assert combo.count() > MAX_VISIBLE_COMBO_ITEMS
        assert combo.maxVisibleItems() == MAX_VISIBLE_COMBO_ITEMS
        # maxVisibleItems is ignored while the popup is the platform's own
        assert "combobox-popup: 0" in combo.styleSheet()
        # and a combo's list is built with its scroll bar off
        assert combo.view().verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded

    def test_the_box_the_menu_opens_is_capped_the_same_way(self):
        dialog = SetSubtitleEncodingDialog()

        assert dialog.combo.maxVisibleItems() == MAX_VISIBLE_COMBO_ITEMS
        assert "combobox-popup: 0" in dialog.combo.styleSheet()
        assert dialog.combo.view().verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded

    def test_the_short_lists_keep_the_popup_the_platform_draws(self):
        form = DefaultsForm(VIDEO_FIELDS)
        combo = form._widgets["video_defaults/subtitle_track_mode"]

        assert combo.count() <= MAX_VISIBLE_COMBO_ITEMS
        assert combo.styleSheet() == ""
