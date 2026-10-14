"""A cell that plays a list: going along it, the end of it, an item that
will not play, naming an item, and a snapshot of another item."""

import dataclasses
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QWidget

from gridplayer.models.media_list import (
    HttpHeaders,
    ItemDetails,
    ListItem,
    MediaList,
)
from gridplayer.models.stream import Stream, Streams
from gridplayer.models.video import Video
from gridplayer.params.static import (
    ListEndAction,
    ListFailAction,
    VideoEndAction,
    VideoInitialState,
)
from gridplayer.player.managers.bookmarks import BookmarksRegistry
from gridplayer.player.managers.lists import MediaListsRegistry
from gridplayer.player.managers.video_blocks import VideoBlocksManager
from gridplayer.playlist_settings import PlaylistSettings
from gridplayer.settings import Settings
from gridplayer.utils.files import cell_mime_data, extract_mime_list
from gridplayer.utils.list_refresh import linked_items, refreshed, uri_key
from gridplayer.utils.url_resolve.static import ResolvedList, ResolvedVideo
from gridplayer.utils.url_resolve.url_resolve import VideoURLResolver
from gridplayer.utils.video_errors import ShownError
from gridplayer.widgets.video_block import NOT_ON_LIST_TXT, VideoBlock
from gridplayer.widgets.video_block_recovery import (
    MAX_NETWORK_FAILURES_IN_A_ROW as MAX_FAILED,
)
from gridplayer.widgets.video_frame_dummy import VideoFrameDummy
from gridplayer.widgets.video_overlay import OverlayBlock

URL = "https://example.com/live/{}.m3u8"


class _Frame(VideoFrameDummy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._fake_media_track = dataclasses.replace(
            self._fake_media_track, length=60000
        )


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    settings = Settings()
    real_settings = settings.settings

    settings.settings = QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)

    yield

    settings.settings = real_settings
    PlaylistSettings().clear()


@pytest.fixture(autouse=True)
def no_resolving(mocker):
    """Links are asked after on no network: the cell is left loading."""

    return mocker.patch.object(VideoURLResolver, "resolve")


def _context(lists, blocks):
    context = MagicMock()
    context.is_overlay_hide_on_timeout = False
    context.is_drag_ui = False
    context.is_disable_overlay = False
    context.is_show_overlay_border = False
    context.overlay_timeout = 1
    context.synced_view = None
    context.lists = lists
    context.bookmarks = BookmarksRegistry()
    context.video_blocks = blocks

    return context


def _touch(root: Path, *names: str) -> list[Path]:
    files = []

    for name in names:
        path = root / name
        path.touch()
        files.append(path)

    return files


@pytest.fixture
def lists():
    return MediaListsRegistry()


@pytest.fixture
def make_cell(lists):
    made = []

    def _make(media_list, index=0, **video_kwargs):
        parent = QWidget()

        block = VideoBlock(
            video_driver=_Frame, context=_context(lists, made_blocks), parent=parent
        )

        video_kwargs.setdefault("end_action", VideoEndAction.NEXT_FILE)
        video_kwargs.setdefault("playback_state", VideoInitialState.PAUSED)

        # a file gone kept, as a playlist reads one of a cell on a list
        uri = media_list.items[index].uri
        is_gone = isinstance(uri, Path) and not uri.exists()

        video = Video(
            uri=str(uri) if is_gone else uri,
            list_id=media_list.id,
            list_index=index,
            **video_kwargs,
        )
        video.uri = uri

        block.set_video(video)

        block.labels = []
        block.label_change.connect(block.labels.append)

        made.append((block, parent))
        made_blocks.append(block)

        return block

    made_blocks = []

    yield _make

    for block, _parent in made:
        block.cleanup()
        block.url_resolver.cleanup()


@pytest.fixture
def files(tmp_path):
    return _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4")


@pytest.fixture
def file_list(lists, files):
    return lists.add(MediaList(items=[ListItem(uri=file) for file in files]))


def _uri(block):
    return block.video_params.uri


class TestGoingAlongTheList:
    def test_next_is_the_next_on_the_list_not_in_the_folder(
        self, make_cell, lists, tmp_path
    ):
        a, _b, c = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4")
        media_list = lists.add(MediaList(items=[ListItem(uri=a), ListItem(uri=c)]))
        block = make_cell(media_list)

        block.next_video()

        assert _uri(block) == c
        assert block.video_params.list_index == 1

    def test_previous_goes_round_to_the_last(self, make_cell, file_list, files):
        block = make_cell(file_list)

        block.previous_video()

        assert _uri(block) == files[2]

    def test_links_are_gone_along_as_well(self, make_cell, lists, no_resolving):
        channels = lists.add(
            MediaList(items=[ListItem(uri=URL.format(n)) for n in range(3)])
        )
        block = make_cell(channels)

        block.next_video()

        assert _uri(block) == URL.format(1)
        no_resolving.assert_called_with(URL.format(1), {})

    def test_a_channel_that_does_not_answer_can_be_left(self, make_cell, lists):
        channels = lists.add(
            MediaList(items=[ListItem(uri=URL.format(n)) for n in range(3)])
        )
        block = make_cell(channels)
        block.network_error()

        block.next_video()

        assert _uri(block) == URL.format(1)

    def test_a_channel_left_takes_its_reload_with_it(self, make_cell, lists):
        channels = lists.add(
            MediaList(items=[ListItem(uri=URL.format(n)) for n in range(3)])
        )
        block = make_cell(channels)
        block.network_error()
        block.network_error()

        block.next_video()

        assert not block.recovery._retry_timer.isActive()

    def test_the_next_channel_reloaded_as_many_times_as_any(self, make_cell, lists):
        channels = lists.add(
            MediaList(items=[ListItem(uri=URL.format(n)) for n in range(3)])
        )
        block = make_cell(channels)
        block.network_error()
        block.network_error()
        block.next_video()

        block.network_error()

        assert block.video_status.status_text == "Reconnecting…"
        assert block.video_status.countdown == 1
        assert block.video_status.detail == "Try 1 of 3"

    def test_a_video_put_in_its_place_reloaded_as_many_times_as_any(
        self, make_cell, lists
    ):
        channels = lists.add(
            MediaList(items=[ListItem(uri=URL.format(n)) for n in range(3)])
        )
        block = make_cell(channels)
        block.network_error()
        block.network_error()

        block.set_video(Video(uri="https://example.com/other.mp4"))
        block.network_error()

        assert block.video_status.status_text == "Reconnecting…"
        assert block.video_status.countdown == 1
        assert block.video_status.detail == "Try 1 of 3"

    def test_the_same_file_twice_on_the_list_is_two_places(self, make_cell, lists):
        channels = lists.add(
            MediaList(
                items=[
                    ListItem(uri=URL.format(1)),
                    ListItem(uri=URL.format(2)),
                    ListItem(uri=URL.format(1)),
                ]
            )
        )
        block = make_cell(channels, index=2)

        block.next_video()

        assert block.video_params.list_index == 0

    def test_an_item_put_in_front_of_it_moves_it_along(
        self, make_cell, lists, file_list, files
    ):
        block = make_cell(file_list, index=1)

        lists.put(
            file_list.model_copy(
                update={"items": (ListItem(uri=files[2]), *file_list.items)}
            )
        )

        assert block.video_params.list_index == 2

    def test_a_list_the_playlist_does_not_have_is_no_list(self, make_cell, file_list):
        block = make_cell(file_list)
        video = block.video_params.model_copy(update={"list_id": MediaList().id})

        block.set_video(video)

        assert block.video_params.list_id is None
        assert block.media_list is None


class TestWhichItemItSays:
    """Over the video, "2/3": the item playing and how many there are."""

    @pytest.fixture
    def said(self):
        return []

    def _listened(self, block, said):
        block.list_place_change.connect(said.append)
        return block

    def test_from_the_start(self, make_cell, file_list):
        block = make_cell(file_list, index=1)

        assert block.list_place_txt == "2/3"

    def test_and_as_it_goes_along(self, make_cell, file_list, said):
        block = self._listened(make_cell(file_list), said)

        block.next_video()

        assert said[-1] == "2/3"

    def test_round_to_the_first(self, make_cell, file_list, said):
        block = self._listened(make_cell(file_list, index=2), said)

        block.next_video()

        assert said[-1] == "1/3"

    def test_with_an_item_more_on_the_list(
        self, make_cell, lists, file_list, files, said
    ):
        self._listened(make_cell(file_list), said)

        lists.put(
            file_list.model_copy(
                update={"items": (*file_list.items, ListItem(uri=files[0]))}
            )
        )

        assert said[-1] == "1/4"

    def test_the_one_playing_taken_off_it(self, make_cell, lists, file_list, said):
        self._listened(make_cell(file_list), said)

        lists.put(file_list.model_copy(update={"items": file_list.items[1:]}))

        assert said[-1] == f"{NOT_ON_LIST_TXT}/2"

    def test_nothing_for_a_cell_with_no_list(self, make_cell, file_list, files, said):
        block = self._listened(make_cell(file_list), said)

        block.set_video(Video(uri=files[0]))

        assert said[-1] == ""
        assert block.list_place_txt == ""

    def test_the_overlay_shows_it_only_for_a_list(self):
        overlay = OverlayBlock()

        overlay.set_list_place("3/12")
        assert not overlay.list_place_button.isHidden()
        assert overlay.list_place_button.text == "3/12"

        overlay.set_list_place("")
        assert overlay.list_place_button.isHidden()

    def test_as_wide_as_what_it_says_with_the_sign_in_front(self):
        overlay = OverlayBlock()
        button = overlay.list_place_button

        button.text = "3/12"
        short = button.width()
        button.text = "1843/18430"

        width = QFontMetrics(button.font()).horizontalAdvance("1843/18430")
        assert button.width() > width + button.margin * 2 + button.gap
        assert button.width() > short

    def test_clicked_for_the_list_window(self, make_cell, file_list):
        block = make_cell(file_list)
        block.overlay.set_list_place("1/3")

        QTest.mouseClick(block.overlay.list_place_button, Qt.LeftButton)

        block._ctx.commands.list_window_for.assert_called_once_with(block)

    def test_no_window_once_the_cell_has_left_the_list(self, make_cell, file_list):
        block = make_cell(file_list)

        block.leave_list()
        block.show_list_window()

        block._ctx.commands.list_window_for.assert_not_called()


class TestLeavingTheList:
    @pytest.fixture
    def picked(self, lists, files):
        """Two of the folder's three files, the first named on the list."""

        return lists.add(
            MediaList(
                items=[ListItem(uri=files[0], title="Pilot"), ListItem(uri=files[2])]
            )
        )

    def test_the_cell_plays_no_list(self, make_cell, picked, files):
        block = make_cell(picked)

        block.leave_list()

        assert block.media_list is None
        assert block.video_params.list_index is None
        assert _uri(block) == files[0]

    def test_next_goes_through_the_folder_again(self, make_cell, picked, files):
        block = make_cell(picked)

        block.leave_list()
        block.next_video()

        assert _uri(block) == files[1]

    def test_the_name_it_had_on_the_list_stays(self, make_cell, picked):
        block = make_cell(picked)

        block.leave_list()

        assert block.video_params.title == "Pilot"

    def test_nothing_said_over_the_video(self, make_cell, picked):
        block = make_cell(picked)
        said = []
        block.list_place_change.connect(said.append)

        block.leave_list()

        assert said == [""]

    def test_the_list_stays_for_the_playlist(self, make_cell, lists, picked):
        block = make_cell(picked)

        block.leave_list()

        assert lists.get(picked.id) is not None

    def test_a_cell_with_no_list_is_left_as_it_is(self, make_cell, picked, files):
        block = make_cell(picked)
        block.leave_list()
        block.video_params.title = "Mine"

        block.leave_list()

        assert block.video_params.title == "Mine"


class TestWithTheListWindowOpen:
    def test_the_overlay_stays_up(self, make_cell, file_list):
        block = make_cell(file_list)
        block._ctx.is_overlay_hide_on_timeout = True
        block.overlay.show()

        block.set_list_window_shown(True)
        block.hide_overlay()

        assert not block.overlay.isHidden()
        assert block.overlay.label_list_window.isVisibleTo(block.overlay)

    def test_gone_once_the_overlay_is_turned_off(self, make_cell, file_list):
        block = make_cell(file_list)
        block.overlay.show()
        block.set_list_window_shown(True)

        block._ctx.is_disable_overlay = True
        block.hide_overlay()

        assert block.overlay.isHidden()

    def test_not_brought_back_by_closing_it(self, make_cell, file_list):
        block = make_cell(file_list)
        block.overlay.show()
        block.set_list_window_shown(True)
        block._ctx.is_disable_overlay = True
        block.hide_overlay()

        block.set_list_window_shown(False)

        assert block.overlay.isHidden()

    def test_back_once_the_overlay_is_turned_on(self, mocker):
        manager = mocker.Mock()
        manager._ctx.is_overlay_hide_on_timeout = True
        marked = mocker.Mock(is_list_window_shown=True)
        other = mocker.Mock(is_list_window_shown=False)
        manager._ctx.video_blocks = [marked, other]

        VideoBlocksManager.set_disable_overlay(manager, False)

        marked.show_overlay.assert_called_once_with()
        other.show_overlay.assert_not_called()

    def test_and_goes_as_ever_once_it_is_closed(self, make_cell, file_list):
        block = make_cell(file_list)
        block._ctx.is_overlay_hide_on_timeout = True

        block.set_list_window_shown(True)
        block.set_list_window_shown(False)
        block.overlay.show()
        block.hide_overlay()

        assert block.overlay.isHidden()
        assert not block.overlay.label_list_window.isVisibleTo(block.overlay)


class TestHowLongAnItemIs:
    def _played(self, block):
        for _ in range(200):
            QTest.qWait(5)
            if block.is_video_initialized:
                return block

        raise AssertionError("never played")

    def test_is_learned_as_it_plays(self, make_cell, lists, files):
        media_list = lists.add(MediaList(items=[ListItem(uri=files[0])]))

        self._played(make_cell(media_list))

        assert lists.get(media_list.id).items[0].duration_ms == 60000

    def test_but_what_the_list_says_stays(self, make_cell, lists, files):
        media_list = lists.add(
            MediaList(items=[ListItem(uri=files[0], duration_ms=1234)])
        )

        self._played(make_cell(media_list))

        assert lists.get(media_list.id).items[0].duration_ms == 1234


class TestWhatTheSiteSaysOfAnItem:
    PICTURE = "https://i.ytimg.com/vi/a/mqdefault.jpg"

    def _looked_up(self, block, mocker, details):
        mocker.patch.object(block.stream, "load_quality")

        block.set_video_url(
            ResolvedVideo(title="A", is_live=False, streams=Streams(), details=details)
        )

    def _list(self, lists, details=None):
        return lists.add(
            MediaList(items=[ListItem(uri=URL.format("a"), details=details)])
        )

    def test_the_date_to_the_second_as_it_is_looked_up_to_play(
        self, make_cell, lists, mocker
    ):
        media_list = self._list(
            lists,
            ItemDetails(view_count=19000, published=1286582400, thumbnail=self.PICTURE),
        )
        block = make_cell(media_list)

        self._looked_up(
            block,
            mocker,
            ItemDetails(
                channel="Channel",
                view_count=92789,
                published=1273312425,
                is_published_exact=True,
            ),
        )

        details = lists.get(media_list.id).items[0].details
        assert details.published == 1273312425
        assert details.is_published_exact
        assert details.view_count == 92789
        # what the look-up did not say, as the list said it
        assert details.thumbnail == self.PICTURE

    def test_of_an_item_the_list_said_nothing_of(self, make_cell, lists, mocker):
        media_list = self._list(lists)
        block = make_cell(media_list)

        self._looked_up(block, mocker, ItemDetails(channel="Channel"))

        assert lists.get(media_list.id).items[0].details.channel == "Channel"

    def test_nothing_new_leaves_the_list_be(self, make_cell, lists, mocker):
        details = ItemDetails(channel="Channel", view_count=5)
        media_list = self._list(lists, details)
        block = make_cell(media_list)
        before = lists.get(media_list.id)

        self._looked_up(block, mocker, details)

        assert lists.get(media_list.id) is before

    def test_nothing_said_leaves_the_list_be(self, make_cell, lists, mocker):
        media_list = self._list(lists)
        block = make_cell(media_list)
        before = lists.get(media_list.id)

        self._looked_up(block, mocker, None)

        assert lists.get(media_list.id) is before


class TestTheEndOfTheList:
    def _at_the_end(self, make_cell, file_list, **kwargs):
        block = make_cell(file_list, index=2, **kwargs)
        block.loop_end_action()
        return block

    def test_starts_over_by_default(self, make_cell, file_list, files):
        block = self._at_the_end(make_cell, file_list)

        assert _uri(block) == files[0]

    def test_or_stops(self, make_cell, file_list, files):
        block = self._at_the_end(
            make_cell,
            file_list,
            list_end_action=ListEndAction.STOP,
            playback_state=VideoInitialState.PLAYING,
        )

        assert _uri(block) == files[2]
        assert block.is_stopped

    def test_or_pauses_at_the_start(self, make_cell, file_list, files):
        block = self._at_the_end(
            make_cell,
            file_list,
            list_end_action=ListEndAction.PAUSE,
            playback_state=VideoInitialState.PLAYING,
        )

        assert _uri(block) == files[2]
        assert block.video_params.is_paused

    def test_or_closes(self, make_cell, file_list):
        block = self._at_the_end(
            make_cell, file_list, list_end_action=ListEndAction.CLOSE
        )

        QTest.qWait(0)

        assert block._is_closing

    def test_before_the_end_the_list_goes_on(self, make_cell, file_list, files):
        block = make_cell(file_list, index=0, list_end_action=ListEndAction.STOP)

        block.loop_end_action()

        assert _uri(block) == files[1]

    def test_is_set_for_the_cell(self, make_cell, file_list):
        block = make_cell(file_list)

        block.set_list_end_action(ListEndAction.CLOSE)

        assert block.video_params.list_end_action is ListEndAction.CLOSE


class TestAnItemThatWillNotPlay:
    def test_is_skipped_where_the_list_plays_by_itself(
        self, make_cell, file_list, files
    ):
        block = make_cell(file_list)

        block.error()
        assert block.recovery.is_skip_counting

        block.recovery._skip_timer.timeout.emit()

        assert _uri(block) == files[1]

    def test_also_where_it_is_gone_through_by_hand(self, make_cell, file_list, files):
        block = make_cell(file_list, end_action=VideoEndAction.LOOP_FILE)

        block.error()
        block.recovery._skip_timer.timeout.emit()

        assert _uri(block) == files[1]

    def test_backwards_where_the_list_goes_so(self, make_cell, file_list, files):
        block = make_cell(file_list, index=1, end_action=VideoEndAction.PREVIOUS_FILE)

        block.error()
        block.recovery._skip_timer.timeout.emit()

        assert _uri(block) == files[0]

    def test_not_where_set_to_show_the_error(self, make_cell, file_list):
        block = make_cell(file_list, list_fail_action=ListFailAction.SHOW_ERROR)

        block.error()

        assert not block.recovery.is_skip_counting
        assert block.recovery.skip_note() == ""

    def test_after_the_wait_it_is_set_to(self, make_cell, file_list):
        block = make_cell(file_list, list_fail_wait_sec=5)

        block.error()

        assert block.recovery._skip_timer.interval() == 5000
        assert block.recovery.skip_note() == "Next file in 5 s"

    def test_at_once_with_no_count_said(self, make_cell, file_list, files):
        block = make_cell(file_list, list_fail_wait_sec=0)

        block.error()

        assert block.recovery._skip_timer.interval() == 0
        assert block.recovery.skip_note() == ""
        assert not block.recovery._note_timer.isActive()

        QTest.qWait(1)

        assert _uri(block) == files[1]

    def test_set_to_show_the_error_while_counting_calls_it_off(
        self, make_cell, file_list
    ):
        block = make_cell(file_list)
        block.error()

        block.recovery.set_fail_action(ListFailAction.SHOW_ERROR)

        assert not block.recovery.is_skip_counting
        assert block.video_status.note == ""

    def test_set_to_play_next_while_the_error_shows_starts_counting(
        self, make_cell, file_list
    ):
        block = make_cell(file_list, list_fail_action=ListFailAction.SHOW_ERROR)
        block.error()

        block.recovery.set_fail_action(ListFailAction.PLAY_NEXT)

        assert block.recovery.is_skip_counting
        assert block.video_status.note == "Next file in 2 s"

    def test_another_wait_counts_over_with_it(self, make_cell, file_list):
        block = make_cell(file_list)
        block.error()

        block.recovery.set_fail_wait(7)

        assert block.recovery._skip_timer.interval() == 7000
        assert block.video_status.note == "Next file in 7 s"

    def test_a_wait_set_while_it_plays_is_kept_for_later(self, make_cell, file_list):
        block = make_cell(file_list)

        block.recovery.set_fail_wait(7)

        assert not block.recovery.is_skip_counting
        assert block.video_params.list_fail_wait_sec == 7

    def test_the_wait_cancelled_is_left_as_it_was(self, make_cell, file_list, mocker):
        block = make_cell(file_list)
        block.error()
        mocker.patch(
            "gridplayer.widgets.video_block_recovery.QCustomSpinboxInput.exec",
            return_value=False,
        )

        block.recovery.fail_wait_dialog()

        assert block.video_params.list_fail_wait_sec == 2
        assert block.recovery._skip_timer.remainingTime() > 1000

    def test_not_for_a_cell_with_no_list(self, make_cell, file_list, files, lists):
        block = make_cell(file_list)
        block.set_video(Video(uri=files[0], end_action=VideoEndAction.NEXT_FILE))

        block.error()

        assert not block.recovery.is_skip_counting

    def test_not_round_a_list_where_none_will(self, make_cell, file_list):
        block = make_cell(file_list)

        for _ in range(len(file_list.items)):
            block.error()
            assert block.recovery.is_skip_counting
            block.recovery.stop_skip()

        block.error()

        assert not block.recovery.is_skip_counting
        assert block.video_status.note == "Stopped: nothing on the list plays"

    def test_on_past_a_long_stretch_of_files_that_will_not(
        self, make_cell, lists, tmp_path
    ):
        files = _touch(tmp_path, *(f"{n:02}.mp4" for n in range(MAX_FAILED + 5)))
        media_list = lists.add(MediaList(items=[ListItem(uri=f) for f in files]))
        block = make_cell(media_list)

        for _ in range(MAX_FAILED + 1):
            block.error()
            assert block.recovery.is_skip_counting
            block.recovery.stop_skip()

    def test_on_past_a_long_stretch_of_links_gone(self, make_cell, lists):
        block = _long_link_list(make_cell, lists)

        for _ in range(MAX_FAILED + 1):
            block.status.last_error = ShownError(title="Not found", is_retryable=False)
            block.error()
            assert block.recovery.is_skip_counting
            block.recovery.stop_skip()

    def test_not_on_and_on_with_no_network(self, make_cell, lists):
        block = _long_link_list(make_cell, lists)

        for _ in range(MAX_FAILED):
            block.status.last_error = ShownError(title="No connection", is_network=True)
            block.error()
            block.recovery.stop_skip()

        block.status.last_error = ShownError(title="No connection", is_network=True)
        block.error()

        assert not block.recovery.is_skip_counting
        assert block.video_status.note == f"Stopped: {MAX_FAILED + 1} failed in a row"

    def test_nor_with_a_site_turning_requests_away(self, make_cell, lists):
        refused = ShownError(
            title="Too many requests", is_retryable=False, is_refused=True
        )
        block = _long_link_list(make_cell, lists)

        for _ in range(MAX_FAILED):
            block.status.last_error = refused
            block.error()
            block.recovery.stop_skip()

        block.status.last_error = refused
        block.error()

        assert not block.recovery.is_skip_counting

    def test_links_gone_in_between_count_to_the_stop(self, make_cell, lists):
        """Said as the failures in a row, the network ones among them."""

        block = _long_link_list(make_cell, lists)
        gone = ShownError(title="Not found", is_retryable=False)
        lost = ShownError(title="No connection", is_network=True)

        for n in range(2 * MAX_FAILED + 1):
            block.status.last_error = gone if n % 2 else lost
            block.error()
            block.recovery.stop_skip()

        assert block.recovery._network_failures_in_a_row == MAX_FAILED + 1
        assert (
            block.video_status.note == f"Stopped: {2 * MAX_FAILED + 1} failed in a row"
        )

    def test_one_that_plays_starts_the_count_over(self, make_cell, file_list):
        block = make_cell(file_list)

        for _ in range(len(file_list.items)):
            block.error()
            block.recovery.stop_skip()

        block.next_video()
        block.error()

        assert block.recovery.is_skip_counting

    def test_set_to_show_the_error_it_is_not_counted_over(self, make_cell, file_list):
        """Failures counted all the same, so the list is not gone round for
        ever once set to play the next."""

        block = make_cell(file_list, list_fail_action=ListFailAction.SHOW_ERROR)

        for _ in range(len(file_list.items) + 1):
            block.error()

        assert block.video_status.note == ""

        block.recovery.set_fail_action(ListFailAction.PLAY_NEXT)

        assert not block.recovery.is_skip_counting
        assert block.video_status.note == "Stopped: nothing on the list plays"

    def test_the_viewer_doing_something_else_keeps_it(
        self, make_cell, file_list, files
    ):
        block = make_cell(file_list)
        block.error()

        block.set_end_action(VideoEndAction.LOOP_FILE)

        assert not block.recovery.is_skip_counting


def _long_link_list(make_cell, lists):
    links = [URL.format(n) for n in range(2 * MAX_FAILED + 5)]
    media_list = lists.add(MediaList(items=[ListItem(uri=link) for link in links]))

    return make_cell(media_list)


class TestNamingAnItem:
    def _rename(self, mocker, block, name):
        mocker.patch(
            "gridplayer.widgets.video_block.QVideoRenameDialog.get_edits",
            return_value=(name, (1, 2, 3)),
        )
        block.rename()

    def test_names_the_item_on_the_list(self, make_cell, lists, file_list, mocker):
        block = make_cell(file_list)

        self._rename(mocker, block, "Kickoff")

        assert lists.get(file_list.id).items[0].title == "Kickoff"
        assert block.video_params.title is None

    def test_every_cell_on_that_item_shows_it(self, make_cell, file_list, mocker):
        block = make_cell(file_list)
        other = make_cell(file_list)

        self._rename(mocker, block, "Kickoff")

        assert other.title == "Kickoff"

    def test_its_own_name_back_clears_it(self, make_cell, lists, file_list, mocker):
        block = make_cell(file_list)
        self._rename(mocker, block, "Kickoff")

        self._rename(mocker, block, block._default_title)

        assert lists.get(file_list.id).items[0].title is None

    def test_its_color_alone_changed_leaves_the_name_be(
        self, make_cell, lists, files, mocker
    ):
        media_list = lists.add(MediaList(items=[ListItem(uri=files[0], title="One")]))
        block = make_cell(media_list)

        self._rename(mocker, block, "One")

        item = lists.get(media_list.id).items[0]
        assert item.title == "One"
        assert not item.is_renamed
        assert block.video_params.color.as_rgb_tuple() == (1, 2, 3)

    def test_the_name_on_the_list_is_the_cells_title(self, make_cell, lists, files):
        media_list = lists.add(
            MediaList(
                items=[ListItem(uri=files[0]), ListItem(uri=files[1], title="Two")]
            )
        )
        block = make_cell(media_list)

        block.next_video()

        assert block.title == "Two"


class TestAChannelsOwnHeaders:
    """What a channel list says to fetch a channel with goes along with it."""

    HEADERS = {"User-Agent": "Box/1.0", "Referer": "https://portal.example/"}

    @pytest.fixture
    def channels(self, lists):
        return lists.add(
            MediaList(
                items=[
                    ListItem(
                        uri=URL.format(0),
                        http_headers=HttpHeaders(
                            user_agent="Box/1.0", referrer="https://portal.example/"
                        ),
                    ),
                    ListItem(uri=URL.format(1)),
                ]
            )
        )

    @pytest.fixture
    def handed(self, monkeypatch):
        """What the player is handed to fetch each link with."""

        handed = []
        load_video = _Frame.load_video

        def _load_video(frame, media_input):
            handed.append(media_input.http_headers)
            load_video(frame, media_input)

        monkeypatch.setattr(_Frame, "load_video", _load_video)

        return handed

    def _resolved(self, protocol):
        return ResolvedVideo(
            title="Channel",
            is_live=True,
            streams=Streams({"best": Stream(url=URL.format(0), protocol=protocol)}),
        )

    def test_the_link_is_resolved_with_them(self, make_cell, channels, no_resolving):
        make_cell(channels)

        no_resolving.assert_called_with(URL.format(0), self.HEADERS)

    def test_the_next_one_with_its_own(self, make_cell, channels, no_resolving):
        block = make_cell(channels)

        block.next_video()

        no_resolving.assert_called_with(URL.format(1), {})

    def test_a_link_the_player_fetches_itself_is_fetched_with_them(
        self, make_cell, channels, handed
    ):
        block = make_cell(channels)

        block.set_video_url(self._resolved("direct"))

        assert handed == [self.HEADERS]

    def test_one_the_proxy_fetches_is_not(self, make_cell, channels, handed):
        block = make_cell(channels)
        block._ctx.commands.add_stream.return_value = "http://127.0.0.1:1/stream"

        block.set_video_url(self._resolved("hls_proxy"))

        assert handed == [{}]

    def test_the_proxy_resolves_it_again_with_them(self, make_cell, channels):
        block = make_cell(channels)
        stream = Stream(url=URL.format(0), protocol="hls_proxy")

        origin = block.stream._with_origin(stream, "best").origin

        assert origin.headers == self.HEADERS

    def test_none_where_the_list_gives_none(self, make_cell, channels):
        block = make_cell(channels, index=1)
        stream = Stream(url=URL.format(1), protocol="hls_proxy")

        assert block.stream._with_origin(stream, "best").origin.headers is None

    def test_a_channel_on_its_own_with_its_own(
        self, make_cell, file_list, no_resolving
    ):
        block = make_cell(file_list)

        block.set_video(
            Video(
                uri=URL.format(0),
                http_headers=HttpHeaders(
                    user_agent="Box/1.0", referrer="https://portal.example/"
                ),
            )
        )

        no_resolving.assert_called_with(URL.format(0), self.HEADERS)

    def test_kept_once_the_cell_leaves_the_list(
        self, make_cell, channels, no_resolving
    ):
        block = make_cell(channels)

        block.leave_list()
        block.reload()

        no_resolving.assert_called_with(URL.format(0), self.HEADERS)


class TestASnapshotOfAnotherItem:
    def test_puts_that_one_back(self, make_cell, file_list, files, monkeypatch):
        block = make_cell(file_list)
        snapshot = block.video_params.model_copy()
        snapshot.current_position = 30000

        block.next_video()

        # where it is started from: the dummy player starts every one at 0
        started_at = []
        load_video = _Frame.load_video

        def _load_video(frame, media_input):
            started_at.append(media_input.video.current_position)
            load_video(frame, media_input)

        monkeypatch.setattr(_Frame, "load_video", _load_video)

        block.apply_snapshot(snapshot)

        assert _uri(block) == files[0]
        assert block.video_params.list_index == 0
        assert started_at == [30000]


class TestASnapshotsName:
    def _renamed(self, block, name):
        block.video_params.title = name
        block.title = name

    def test_the_one_it_had_then(self, make_cell, file_list):
        block = make_cell(file_list)
        block.leave_list()
        self._renamed(block, "Cam 1")
        snapshot = block.video_params.model_copy()
        self._renamed(block, "Cam A")

        block.apply_snapshot(snapshot)

        assert block.title == "Cam 1"
        assert block.video_params.title == "Cam 1"

    def test_on_a_list_the_items(self, make_cell, lists, file_list):
        block = make_cell(file_list)
        snapshot = block.video_params.model_copy()
        lists.rename_item(file_list.id, file_list.items[0].key, "Kickoff")

        block.apply_snapshot(snapshot)

        assert block.title == "Kickoff"


class TestACellTakingAList:
    def test_plays_from_it_from_where_it_is(self, make_cell, lists, files):
        media_list = lists.add(MediaList(items=[ListItem(uri=files[0])]))
        block = make_cell(media_list)
        block.set_video(
            Video(uri=files[0], title="Mine", end_action=VideoEndAction.LOOP_FILE)
        )
        grown = lists.add(
            MediaList(
                items=[ListItem(uri=files[0], title="Mine"), ListItem(uri=files[1])]
            )
        )

        block.take_list(grown.id, 0)

        assert block.media_list is grown
        assert block.video_params.list_index == 0
        # its name is the item's now
        assert block.video_params.title is None
        assert block.title == "Mine"
        # and it goes along the list at its end
        assert block.video_params.end_action is VideoEndAction.NEXT_FILE

        block.next_video()

        assert _uri(block) == files[1]

    def test_going_along_a_list_already_it_goes_on_so(self, make_cell, lists, files):
        media_list = lists.add(MediaList(items=[ListItem(uri=files[0])]))
        block = make_cell(media_list, end_action=VideoEndAction.SHUFFLE_FILE)

        block.take_list(media_list.id, 0)

        assert block.video_params.end_action is VideoEndAction.SHUFFLE_FILE


class TestChannelsGivenNewLinks:
    """A provider gives out its channels with a new token in each link each
    time the list is read: the cell is on the same channel still."""

    LINK = "https://provider.example/live/{}.m3u8?token={}"

    def _read(self, token):
        return [
            ListItem(uri=self.LINK.format(n, token), title=f"Channel {n}")
            for n in range(3)
        ]

    @pytest.fixture
    def channels(self, lists):
        return lists.add(MediaList(items=self._read("a"), is_linked=True))

    def _read_again(self, lists, channels, token):
        lists.put(refreshed(lists.get(channels.id), self._read(token)).media_list)

    def test_the_cell_stays_on_its_channel(self, make_cell, lists, channels):
        block = make_cell(channels, index=1)

        self._read_again(lists, channels, "b")

        assert block.list_place_txt == "2/3"
        assert block.list_item.title == "Channel 1"

    def test_and_has_its_new_link(self, make_cell, lists, channels):
        block = make_cell(channels, index=1)

        self._read_again(lists, channels, "b")
        self._read_again(lists, channels, "c")

        assert _uri(block) == self.LINK.format(1, "c")

    def test_without_being_reloaded_for_it(
        self, make_cell, lists, channels, no_resolving
    ):
        make_cell(channels, index=1)
        no_resolving.reset_mock()

        self._read_again(lists, channels, "b")

        no_resolving.assert_not_called()

    def test_kept_in_the_playlist_as_one_a_cell_plays(self, make_cell, lists, channels):
        block = make_cell(channels, index=1)

        self._read_again(lists, channels, "b")

        kept = linked_items(lists.get(channels.id), {uri_key(_uri(block))})
        assert [item.title for item in kept] == ["Channel 1"]

    def test_going_on_from_it_goes_to_the_next(self, make_cell, lists, channels):
        block = make_cell(channels, index=1)
        self._read_again(lists, channels, "b")

        block.next_video()

        assert _uri(block) == self.LINK.format(2, "b")


class TestAFileGoneAsThePlaylistOpens:
    """The file a cell was on gone as the playlist opens, its drive not
    plugged in: the cell goes on along its list from there."""

    @pytest.fixture
    def four(self, lists, tmp_path):
        files = _touch(tmp_path, "a.mp4", "b.mp4", "c.mp4", "d.mp4")

        return lists.add(MediaList(items=[ListItem(uri=file) for file in files]))

    def _gone(self, media_list, *indexes):
        for index in indexes:
            media_list.items[index].uri.unlink()

    def _as_saved(self, lists, media_list, *indexes):
        """A linked list as the playlist keeps it, with the items cells
        play, to be read again as it opens."""

        saved = lists.add(
            MediaList(
                items=[media_list.items[index] for index in indexes], is_linked=True
            )
        )
        lists.expect_reading([saved.id])

        return saved

    def test_the_next_one_on_its_list(self, make_cell, four):
        self._gone(four, 1)

        block = make_cell(four, index=1)

        assert _uri(block) == four.items[2].uri
        assert block.video_params.list_index == 2

    def test_round_to_the_start(self, make_cell, four):
        self._gone(four, 3)

        block = make_cell(four, index=3)

        assert _uri(block) == four.items[0].uri

    def test_past_others_gone_as_well(self, make_cell, four):
        self._gone(four, 0, 1, 2)

        block = make_cell(four)

        assert _uri(block) == four.items[3].uri

    def test_from_its_start(self, make_cell, four):
        self._gone(four, 1)

        block = make_cell(four, index=1, current_position=5000)

        assert block.video_params.current_position == 0

    def test_without_the_files_picked_for_the_one_gone(self, make_cell, four, tmp_path):
        subtitles = tmp_path / "b.srt"
        subtitles.touch()
        self._gone(four, 1)

        block = make_cell(four, index=1, external_subtitles=[subtitles])

        assert block.video_params.external_subtitles == []

    def test_nothing_there_on_it_is_said(self, make_cell, four):
        self._gone(four, 0, 1, 2, 3)

        block = make_cell(four)

        assert block.video_status.status_text == "Nothing on the list to play"

    def test_a_linked_list_is_read_again_first(self, make_cell, lists, four):
        self._gone(four, 1)
        # another cell plays the last one
        saved = self._as_saved(lists, four, 1, 3)

        block = make_cell(saved)

        assert _uri(block) == four.items[1].uri
        assert block.video_status.status_text == "Reading the list…"

        lists.mark_read(saved.id)
        lists.put(saved.model_copy(update={"items": four.items}))
        lists.finish_reading(saved.id)

        assert _uri(block) == four.items[2].uri

    def test_one_that_could_not_be_read_is_not_gone_along(self, make_cell, lists, four):
        self._gone(four, 1)
        saved = self._as_saved(lists, four, 1, 3)
        block = make_cell(saved)

        lists.finish_reading(saved.id)

        assert _uri(block) == four.items[1].uri
        assert block.video_status.status_text == "File not found"

    def test_one_back_by_then_is_played(self, make_cell, lists, four):
        self._gone(four, 1)
        saved = self._as_saved(lists, four, 1, 3)
        block = make_cell(saved)

        four.items[1].uri.touch()
        lists.finish_reading(saved.id)

        assert _uri(block) == four.items[1].uri
        assert block.is_video_initialized


class TestWaitingForItsList:
    @pytest.fixture
    def cell(self, lists):
        parent = QWidget()
        block = VideoBlock(
            video_driver=_Frame, context=_context(lists, []), parent=parent
        )

        yield block

        block.cleanup()
        block.url_resolver.cleanup()

    def test_saved_so_it_is_read_again(self, cell, no_resolving):
        video = Video(uri="http://tv/get.php?type=m3u_plus", read_as_list=True)

        cell.set_video(video)

        cell._ctx.commands.read_for_cell.assert_called_once_with(video)
        assert cell.video_status.status_text == "Reading the list…"
        no_resolving.assert_not_called()

    def test_closed_it_is_read_no_further(self, cell, lists):
        video = Video(uri="http://tv/get.php?type=m3u_plus")
        stop = lists.wait_for_list(video.id)
        cell.set_video(video)

        cell.close()

        assert stop.is_set()
        assert not lists.is_waiting(video.id)

    def test_nor_once_another_video_is_put_in_its_place(self, cell, lists, files):
        video = Video(uri="http://tv/get.php?type=m3u_plus")
        stop = lists.wait_for_list(video.id)
        cell.set_video(video)

        cell.set_video(Video(uri=files[0]))

        assert stop.is_set()

    def test_a_link_read_as_one_stream_plays_it(self, cell, no_resolving):
        url = "http://tv/live/index.m3u8"
        cell.set_video(Video(uri=url, read_as_list=True))
        cell.video_params.read_as_list = None

        cell.play_read(url)

        assert cell.video_params.uri == url
        no_resolving.assert_called_once()

    def test_a_folder_read_as_one_file_plays_it(self, cell, tmp_path, files):
        cell.set_video(Video(uri=str(tmp_path), read_as_list=True))
        cell.video_params.read_as_list = None

        cell.play_read(files[0])

        assert cell.video_params.uri == files[0]


class TestALinkThatTurnsOutToBeAList:
    SITE_LIST = ResolvedList(
        title="Site List",
        items=(ListItem(uri=URL.format("x")), ListItem(uri=URL.format("y"))),
    )

    def test_the_cell_plays_the_list(self, make_cell, file_list):
        block = make_cell(file_list)
        block.set_video(Video(uri="https://site/list", title=None))

        block._link_was_a_list(self.SITE_LIST)
        QTest.qWait(0)

        media_list = block.media_list
        assert media_list.name == "Site List"
        assert media_list.source.location == "https://site/list"
        assert _uri(block) == URL.format("x")
        assert block.video_params.end_action is VideoEndAction.NEXT_FILE

    def test_on_a_list_its_videos_take_its_place(self, make_cell, lists):
        media_list = lists.add(
            MediaList(
                items=[
                    ListItem(uri=URL.format("a")),
                    ListItem(uri="https://site/list"),
                    ListItem(uri=URL.format("c")),
                ]
            )
        )
        block = make_cell(media_list, index=1)

        block._link_was_a_list(self.SITE_LIST)
        QTest.qWait(0)

        assert [item.uri for item in block.media_list.items] == [
            URL.format("a"),
            URL.format("x"),
            URL.format("y"),
            URL.format("c"),
        ]
        assert _uri(block) == URL.format("x")
        assert block.video_params.list_index == 1

    def test_not_once_the_cell_is_closing(self, make_cell, file_list, files):
        block = make_cell(file_list)
        block._link_was_a_list(self.SITE_LIST)
        block._is_closing = True

        QTest.qWait(0)

        assert _uri(block) == files[0]


class TestDraggedToAnotherPlayer:
    def test_the_list_comes_along_apart(self, make_cell, file_list):
        block = make_cell(file_list)

        mime_data = cell_mime_data(block.drag_data, block.media_list)
        dragged = extract_mime_list(mime_data)

        assert dragged.id == file_list.id
        assert [item.uri for item in dragged.items] == [
            item.uri for item in file_list.items
        ]

    def test_not_with_the_cell(self, make_cell, file_list):
        block = make_cell(file_list)

        dragged = block.drag_data.model_dump_json()

        assert str(file_list.items[1].uri.name) not in dragged


class TestToldOfWhatIsAdded:
    def test_says_how_many_under_its_title(self, make_cell, file_list):
        block = make_cell(file_list)
        said = []
        block.info_change.connect(said.append)

        block.tell_added_to_list(3)

        assert said == ["Added to the list: 3"]
