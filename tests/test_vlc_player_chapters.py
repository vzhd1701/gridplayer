"""Chapters as the player reads them off libVLC.

The list is handed over through ctypes, a pointer level short in the
bindings, and has to be given back to libVLC to free. Faked here with real
ChapterDescription structs, laid out the way libVLC lays them out.
"""

import ctypes

import pytest

from gridplayer.models.chapter import Chapter
from gridplayer.models.video import Video
from gridplayer.vlc_player import player_base
from gridplayer.vlc_player.libvlc import vlc
from gridplayer.vlc_player.player_base import VlcPlayerBase
from gridplayer.vlc_player.player_event_manager import EventManager
from gridplayer.vlc_player.static import Media, MediaInput

ChapterDescription = vlc.ChapterDescription

URI = "movie.mkv"


class _Player(VlcPlayerBase):
    def __init__(self):
        super().__init__(vlc_instance=None)

        self.chapters_sent = []
        self.loaded = []

        self._media_player = object()

    def notify_chapters_changed(self, chapters):
        self.chapters_sent.append(chapters)

    def notify_load_video_done(self, media_track):
        self.loaded.append(media_track)

    def notify_snapshot_taken(self, snapshot_path): ...
    def notify_update_status(self, status, percent=0): ...
    def notify_error(self, error): ...
    def notify_time_changed(self, new_time): ...
    def notify_playback_status_changed(self, new_status): ...
    def loopback_load_video_st2_set_media(self): ...
    def loopback_load_video_st3_extract_media_track(self): ...
    def loopback_load_video_st4_loaded(self): ...


class _FakeLibVLC:
    """The two calls, answering with a list the way libVLC allocates one."""

    def __init__(self, chapters, count=None):
        self._structs = [
            ChapterDescription(time_offset=start, duration=0, name=name)
            for start, name in chapters
        ]
        self._array = (ctypes.POINTER(ChapterDescription) * len(self._structs))(
            *[ctypes.pointer(struct) for struct in self._structs]
        )
        self._count = len(chapters) if count is None else count

        self.released = []
        self.titles_asked = []

    def get_full_chapter_descriptions(self, media_player, title, descriptions_ref):
        self.titles_asked.append(title)

        if self._count > 0:
            # write the array's address where the caller's pointer lives
            address = ctypes.c_void_p(ctypes.addressof(self._array))
            ctypes.memmove(
                ctypes.addressof(descriptions_ref._obj),
                ctypes.byref(address),
                ctypes.sizeof(address),
            )

        return self._count

    def release(self, descriptions, count):
        address = ctypes.cast(descriptions, ctypes.c_void_p).value

        self.released.append((address, count))

    @property
    def array_address(self):
        return ctypes.addressof(self._array)


@pytest.fixture
def libvlc(monkeypatch):
    def _install(chapters, count=None):
        fake = _FakeLibVLC(chapters, count)

        monkeypatch.setattr(
            player_base.vlc,
            "libvlc_media_player_get_full_chapter_descriptions",
            fake.get_full_chapter_descriptions,
        )
        monkeypatch.setattr(
            player_base.vlc, "libvlc_chapter_descriptions_release", fake.release
        )

        return fake

    return _install


def _loaded_player(chapters=()):
    player = _Player()

    player.media_input = MediaInput(
        uri=URI,
        is_live=False,
        is_audio_only=False,
        size=(640, 360),
        video=Video(uri=URI),
    )
    player.media = Media(
        length=60000, video_tracks={}, audio_tracks={}, chapters=chapters
    )
    player.is_video_initialized = True

    return player


class TestReading:
    def test_starts_and_names_come_through(self, libvlc):
        libvlc([(0, b" Opening"), (25000, "Tom & Jerry — Ünïcødé".encode())])

        assert _Player()._read_chapters() == (
            Chapter(0, " Opening"),
            Chapter(25000, "Tom & Jerry — Ünïcødé"),
        )

    def test_a_chapter_with_no_name_has_none(self, libvlc):
        libvlc([(5000, None)])

        assert _Player()._read_chapters() == (Chapter(5000, None),)

    def test_a_name_that_is_not_utf8_still_leaves_the_chapter(self, libvlc):
        libvlc([(5000, b"caf\xe9")])

        assert _Player()._read_chapters() == (Chapter(5000, "caf�"),)

    def test_the_list_is_handed_back_to_libvlc_whole(self, libvlc):
        fake = libvlc([(0, b"A"), (5000, b"B"), (9000, b"C")])

        _Player()._read_chapters()

        assert fake.released == [(fake.array_address, 3)]

    def test_the_title_that_is_playing_is_asked_about(self, libvlc):
        fake = libvlc([(0, b"A")])

        _Player()._read_chapters()

        assert fake.titles_asked == [-1]

    @pytest.mark.parametrize("count", [-1, 0])
    def test_a_video_without_chapters_has_none_and_frees_nothing(self, libvlc, count):
        """-1 is what every video without chapters answers, not an error."""

        fake = libvlc([], count=count)

        assert _Player()._read_chapters() == ()
        assert fake.released == []

    def test_a_player_already_let_go_is_not_asked(self, libvlc):
        fake = libvlc([(0, b"A")])

        player = _Player()
        player._media_player = None

        assert player._read_chapters() == ()
        assert fake.titles_asked == []


class TestLateArrivals:
    """Chapters a file lists only as it plays, after the load is done."""

    def test_the_title_event_is_listened_to(self):
        assert (
            EventManager.player_events["title_changed"]
            == vlc.EventType.MediaPlayerTitleChanged
        )

    def test_chapters_that_turn_up_after_the_load_are_sent_on(self, libvlc):
        libvlc([(0, b"A"), (5000, b"B")])

        player = _loaded_player()

        player.cb_title_changed(event=None)

        expected = (Chapter(0, "A"), Chapter(5000, "B"))

        assert player.chapters_sent == [expected]
        assert player.media.chapters == expected

    def test_the_same_chapters_again_are_not_sent_again(self, libvlc):
        """An mkv sends a title event on every seek."""

        libvlc([(0, b"A"), (5000, b"B")])

        player = _loaded_player(chapters=(Chapter(0, "A"), Chapter(5000, "B")))

        player.cb_title_changed(event=None)

        assert player.chapters_sent == []

    def test_nothing_is_sent_before_the_load_is_done(self, libvlc):
        """The load reads them itself as it finishes."""

        libvlc([(0, b"A"), (5000, b"B")])

        player = _loaded_player()
        player.is_video_initialized = False

        player.cb_title_changed(event=None)

        assert player.chapters_sent == []

    def test_the_load_reads_them_as_it_finishes(self, libvlc, monkeypatch):
        libvlc([(0, b"A"), (5000, b"B")])

        player = _loaded_player()
        player.is_video_initialized = False

        monkeypatch.setattr(player, "_try_set_initial_state", lambda: True)
        monkeypatch.setattr(player, "_fill_missing_track_dimensions", lambda: False)

        player.load_video_st4_loaded()

        assert player.loaded[0].chapters == (Chapter(0, "A"), Chapter(5000, "B"))
