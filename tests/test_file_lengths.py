"""Reading how long files are, on a player that may not be on VLC."""

import os
from types import SimpleNamespace

from gridplayer.utils import item_info, libvlc
from gridplayer.utils.media_libs import LibProblem, MediaLib


def test_no_process_is_started_with_no_vlc_to_read_with(monkeypatch, tmp_path):
    monkeypatch.setattr(item_info, "lib_problem", lambda _lib: LibProblem.MISSING)
    reader = item_info.FileLengths()

    lengths = reader.lengths([tmp_path / "a.mp4", tmp_path / "b.mp4"])

    assert lengths == [None, None]
    assert reader._pool is None


def test_the_vlc_that_came_with_the_app_is_set_without_loading_it(
    monkeypatch, tmp_path
):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    library = tmp_path / "libvlc.dll"
    library.touch()
    monkeypatch.setenv("PYTHON_VLC_MODULE_PATH", "")
    monkeypatch.setenv("PYTHON_VLC_LIB_PATH", "")
    monkeypatch.setattr(libvlc, "get_embed_vlc_paths", lambda: (plugins, library))

    libvlc.set_embed_vlc_env()

    assert os.environ["PYTHON_VLC_MODULE_PATH"] == str(plugins)
    assert os.environ["PYTHON_VLC_LIB_PATH"] == str(library)


class _ReadsHere:
    """A pool that says what it was given to run."""

    run = []

    def __init__(self, **_kwargs): ...

    def submit(self, read, paths):
        self.run.append(read)

        return SimpleNamespace(result=lambda: [1] * len(paths))

    def shutdown(self, **_kwargs): ...


def _with_libs(monkeypatch, *missing):
    monkeypatch.setattr(
        item_info,
        "lib_problem",
        lambda lib: LibProblem.MISSING if lib in missing else None,
    )
    monkeypatch.setattr(item_info, "ProcessPoolExecutor", _ReadsHere)
    _ReadsHere.run = []


def test_vlc_reads_them_where_there_is_vlc(monkeypatch, tmp_path):
    _with_libs(monkeypatch)

    item_info.FileLengths().lengths([tmp_path / "a.mp4"])

    assert _ReadsHere.run == [item_info.lengths_in_process]


def test_libmpv_reads_them_with_no_vlc(monkeypatch, tmp_path):
    _with_libs(monkeypatch, MediaLib.VLC)

    item_info.FileLengths().lengths([tmp_path / "a.mp4"])

    assert _ReadsHere.run == [item_info.lengths_by_mpv_in_process]


class _FakeReader:
    """An mpv that answers a file by what it has been told of it."""

    def __init__(self, module, files, options):
        self._module = module
        self._files = files
        self._callback = None
        self.options = options
        self.duration = None
        self.stopped = 0
        # what a file given up on says once the next is asked for
        self._late = []
        self._entries = 0

    def register_event_callback(self, callback):
        self._callback = callback

    def _say(self, event_id, entry=None, reason=None):
        self._callback(
            SimpleNamespace(
                event_id=SimpleNamespace(value=event_id),
                data=SimpleNamespace(reason=reason, playlist_entry_id=entry),
            )
        )

    def command(self, name, *args):
        ids = self._module.MpvEventID

        if name == "stop":
            self.stopped += 1
            return

        for late in self._late:
            self.duration = late
            self._say(ids.FILE_LOADED)

        self._late.clear()

        # the one before being let go of says it has ended, with no error
        self._say(ids.END_FILE, entry=self._entries, reason=0)
        self._entries += 1
        self._say(ids.START_FILE, entry=self._entries)

        length = self._files.get(args[0], "nothing")

        if isinstance(length, tuple):
            self._late.append(length[1])
        elif length == "nothing":
            self.duration = None
            self._say(
                ids.END_FILE,
                entry=self._entries,
                reason=self._module.MpvEventEndFile.ERROR,
            )
        elif length != "silent":
            self.duration = length
            self._say(ids.FILE_LOADED)


def _length_reader(monkeypatch, files):
    module = SimpleNamespace(
        MpvEventID=SimpleNamespace(START_FILE=6, FILE_LOADED=8, END_FILE=7),
        MpvEventEndFile=SimpleNamespace(ERROR=4),
    )
    made = []

    def make_reader(**options):
        made.append(_FakeReader(module, files, options))

        return made[-1]

    module.MPV = make_reader

    monkeypatch.setattr("gridplayer.mpv_player.libmpv.load_mpv", lambda: module)
    monkeypatch.setattr(item_info, "FILE_PARSE_TIMEOUT_MS", 10)

    return item_info._MpvLengthReader(), made[0]


def test_libmpv_says_how_long_a_file_is(monkeypatch):
    reader, mpv = _length_reader(monkeypatch, {"a.mp4": 20.5})

    assert reader.length_of("a.mp4") == 20_500
    # let go of, or Windows wouldn't let it be moved
    assert mpv.stopped == 1


def test_libmpv_says_nothing_of_what_it_cannot_read(monkeypatch):
    reader, _mpv = _length_reader(monkeypatch, {})

    assert reader.length_of("junk.mp4") is None


def test_libmpv_taking_too_long_is_no_length(monkeypatch):
    reader, _mpv = _length_reader(monkeypatch, {"slow.mp4": "silent"})

    assert reader.length_of("slow.mp4") is None


def test_a_file_taking_too_long_is_let_go_of(monkeypatch):
    reader, mpv = _length_reader(monkeypatch, {"slow.mp4": "silent"})

    reader.length_of("slow.mp4")

    assert mpv.stopped == 1


def test_a_file_given_up_on_loading_late_is_not_taken_for_the_next(monkeypatch):
    reader, _mpv = _length_reader(
        monkeypatch, {"slow.mp4": ("late", 5.0), "next.mp4": "silent"}
    )

    assert reader.length_of("slow.mp4") is None
    assert reader.length_of("next.mp4") is None


def test_a_file_let_go_of_before_it_started_leaves_the_next_to_be_read(monkeypatch):
    reader, mpv = _length_reader(monkeypatch, {"a.mp4": 20.5})
    # numbered, but never started
    mpv._entries += 1
    reader._asked += 1

    assert reader.length_of("a.mp4") == 20_500


def test_a_file_with_no_length_has_none(monkeypatch):
    reader, _mpv = _length_reader(monkeypatch, {"live.ts": 0})

    assert reader.length_of("live.ts") is None


def test_libmpv_is_left_something_to_play(monkeypatch):
    # with no track it closes the file before it can be asked
    _reader, mpv = _length_reader(monkeypatch, {})

    assert "vid" not in mpv.options
    assert "aid" not in mpv.options
