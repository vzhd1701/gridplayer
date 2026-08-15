from gridplayer.player.managers.playlist import format_playlist_window_title
from gridplayer.version import __display_name__


def test_title_without_playlist():
    assert format_playlist_window_title(None) == __display_name__
    assert "[*]" not in format_playlist_window_title(None)


def test_title_with_playlist_uses_qt_modified_placeholder():
    assert (
        format_playlist_window_title("vacation") == f"vacation[*] - {__display_name__}"
    )


def test_title_placeholder_is_only_after_the_name():
    title = format_playlist_window_title("my*list*")
    assert title == f"my*list*[*] - {__display_name__}"
    assert title.startswith("my*list*")
    assert title.count("[*]") == 1
