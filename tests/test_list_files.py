"""Lists saved by other players and by channel providers, read for a cell
to play: M3U and M3U8, PLS and XSPF."""

import codecs
from pathlib import Path

import pytest

from gridplayer.models.media_list import HttpHeaders, ListItem
from gridplayer.utils import list_files
from gridplayer.utils.list_files import (
    NotAListError,
    decode_list_text,
    entry_uri,
    is_list_file_name,
    looks_like_list,
    m3u_text,
    parse_list,
    parse_m3u,
    parse_pls,
    parse_xspf,
    read_list_file,
)
from gridplayer.utils.list_progress import ReadingEnough

BASE = Path("/lists").absolute()


def _uris(read):
    return [item.uri for item in read.items]


class TestM3U:
    def test_a_plain_one_is_a_line_for_each(self):
        read = parse_m3u("a.mp4\n\n  b.mkv  \nhttps://host/c.mp4\n", BASE)

        assert _uris(read) == [BASE / "a.mp4", BASE / "b.mkv", "https://host/c.mp4"]

    def test_comments_are_left_out(self):
        read = parse_m3u("# made by hand\na.mp4\n#another\n", BASE)

        assert _uris(read) == [BASE / "a.mp4"]

    def test_an_extended_one_names_its_entries(self):
        read = parse_m3u(
            "#EXTM3U\n#EXTINF:123,Episode 1\na.mp4\n#EXTINF:-1,Live\nhttps://h/x\n",
            BASE,
        )

        first, live = read.items
        assert first.title == "Episode 1"
        assert first.duration_ms == 123000
        assert live.title == "Live"
        assert live.duration_ms is None

    def test_what_a_tag_says_is_only_for_the_entry_after_it(self):
        read = parse_m3u("#EXTINF:5,Named\na.mp4\nb.mp4\n", BASE)

        assert [item.title for item in read.items] == ["Named", None]

    def test_a_channel_list_says_its_group_and_name(self):
        read = parse_m3u(
            "#EXTM3U\n"
            '#EXTINF:-1 tvg-id="n.1" tvg-name="News, World" tvg-logo="l.png"'
            ' group-title="News, 24/7",News World HD\n'
            "http://iptv/1.ts\n",
            BASE,
        )

        (channel,) = read.items
        assert channel.title == "News World HD"
        assert channel.group == "News, 24/7"
        assert channel.uri == "http://iptv/1.ts"

    def test_a_channel_with_no_name_after_the_comma_goes_by_tvg_name(self):
        read = parse_m3u('#EXTINF:-1 tvg-name="Sport 1",\nhttp://iptv/2.ts\n', BASE)

        assert read.items[0].title == "Sport 1"

    def test_a_group_tag_of_its_own(self):
        read = parse_m3u("#EXTGRP:Movies\n#EXTINF:-1,One\nhttp://h/1\n", BASE)

        assert read.items[0].group == "Movies"

    def test_what_to_fetch_it_with_as_vlc_is_told(self):
        read = parse_m3u(
            "#EXTVLCOPT:http-user-agent=Agent/1.0\n"
            "#EXTVLCOPT:http-referrer=https://site/\n"
            "http://h/1\n",
            BASE,
        )

        assert read.items[0].http_headers == HttpHeaders(
            user_agent="Agent/1.0", referrer="https://site/"
        )

    def test_nothing_else_vlc_is_told_is_passed_on(self):
        read = parse_m3u("#EXTVLCOPT:sout=#file{dst=/etc/x}\nhttp://h/1\n", BASE)

        (item,) = read.items
        assert item.http_headers is None

    def test_what_to_fetch_it_with_as_json(self):
        read = parse_m3u(
            '#EXTHTTP:{"User-Agent": "Agent/2", "Referer": "https://r/"}\nhttp://h/1\n',
            BASE,
        )

        assert read.items[0].http_headers == HttpHeaders(
            user_agent="Agent/2", referrer="https://r/"
        )

    def test_what_to_fetch_it_with_after_the_link_kodi_style(self):
        read = parse_m3u("http://h/live.m3u8|User-Agent=Agent%2F3&Referer=r\n", BASE)

        (item,) = read.items
        assert item.uri == "http://h/live.m3u8"
        assert item.http_headers == HttpHeaders(user_agent="Agent/3", referrer="r")

    def test_channels_fetched_with_the_same_share_them(self):
        read = parse_m3u(
            "#EXTVLCOPT:http-user-agent=Agent/4\n"
            "http://h/1\n"
            "#EXTVLCOPT:http-user-agent=Agent/4\n"
            "http://h/2\n",
            BASE,
        )

        one, two = read.items
        assert one.http_headers is two.http_headers

    def test_what_to_fetch_it_with_written_out(self):
        headers = HttpHeaders(user_agent="Agent/5", referrer="https://w/")
        items = [ListItem(uri="http://h/1", title="One", http_headers=headers)]

        read = parse_m3u(m3u_text("TV", items, None), None)

        assert read.items[0].http_headers == headers

    def test_its_name_where_it_says_one(self):
        assert parse_m3u("#EXTM3U\n#PLAYLIST:My Shows\na.mp4\n", BASE).name == (
            "My Shows"
        )

    def test_an_hls_streams_playlist_is_no_list(self):
        hls = "#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nseg1.ts\n"

        with pytest.raises(NotAListError):
            parse_m3u(hls, BASE)

    def test_nor_is_a_master_playlist_of_one(self):
        hls = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nlow/index.m3u8\n"

        with pytest.raises(NotAListError):
            parse_m3u(hls, BASE)

    @pytest.mark.parametrize(
        "hls",
        [
            "#EXT-X-TARGETDURATION:6\nseg1.ts\n",
            "#EXTM3U\r\n  #EXT-X-TARGETDURATION:6\r\nseg1.ts\r\n",
            "#EXTM3U\r#EXT-X-TARGETDURATION:6\rseg1.ts\r",
        ],
    )
    def test_whichever_line_ends_it_has(self, hls):
        with pytest.raises(NotAListError):
            parse_m3u(hls, BASE)

    def test_a_tag_further_along_a_line_is_not_one(self):
        text = "#EXTM3U\n#EXTINF:-1,Not #EXT-X-STREAM\nhttp://tv/1\n"

        assert len(parse_m3u(text, BASE).items) == 1


class TestWhereAnEntryIs:
    def test_relative_to_the_list(self):
        assert entry_uri("sub/../a.mp4", BASE) == BASE / "a.mp4"

    def test_an_absolute_path_as_it_is(self, tmp_path):
        assert entry_uri(str(tmp_path / "a.mp4"), BASE) == tmp_path / "a.mp4"

    def test_a_file_url(self, tmp_path):
        url = (tmp_path / "My Movie.mp4").as_uri()

        assert entry_uri(url, BASE) == tmp_path / "My Movie.mp4"

    @pytest.mark.parametrize(
        "url", ["http://h/a", "https://h/a", "rtsp://cam/1", "udp://@239.0.0.1:1234"]
    )
    def test_a_link_one_can_play(self, url):
        assert entry_uri(url, BASE) == url

    @pytest.mark.parametrize(
        "url", ["javascript://alert(1)", "smb://share/a.mp4", "ftp://h/a.mp4"]
    )
    def test_not_a_link_of_another_kind(self, url):
        assert entry_uri(url, BASE) is None

    def test_nowhere_for_nothing(self):
        assert entry_uri("   ", BASE) is None


class TestPLS:
    def test_files_in_their_numbers_order_with_names_and_lengths(self):
        read = parse_pls(
            "[playlist]\n"
            "File2=b.mp4\nTitle2=Second\nLength2=-1\n"
            "File1=a.mp4\nTitle1=First\nLength1=60\n"
            "NumberOfEntries=2\nVersion=2\n",
            BASE,
        )

        assert _uris(read) == [BASE / "a.mp4", BASE / "b.mp4"]
        assert [item.title for item in read.items] == ["First", "Second"]
        assert [item.duration_ms for item in read.items] == [60000, None]

    def test_any_case_of_its_keys(self):
        read = parse_pls("[playlist]\nfile1=http://radio/1\n", BASE)

        assert _uris(read) == ["http://radio/1"]


class TestXSPF:
    XSPF = """<?xml version="1.0" encoding="UTF-8"?>
<playlist xmlns="http://xspf.org/ns/0/" version="1">
  <title>Saved by VLC</title>
  <trackList>
    <track>
      <location>file:///{folder}/a%20b.mp4</location>
      <title>First</title>
      <duration>61000</duration>
    </track>
    <track><location>https://host/c.mp4</location></track>
    <track><title>No location</title></track>
  </trackList>
</playlist>
"""

    def test_tracks_with_their_names_and_lengths(self, tmp_path):
        folder = tmp_path.as_posix().lstrip("/")

        read = parse_xspf(self.XSPF.format(folder=folder), BASE)

        assert read.name == "Saved by VLC"
        assert _uris(read) == [tmp_path / "a b.mp4", "https://host/c.mp4"]
        assert read.items[0].title == "First"
        assert read.items[0].duration_ms == 61000

    def test_one_that_is_not_xml_is_not_a_list(self):
        with pytest.raises(ValueError, match="XSPF"):
            parse_xspf("<playlist", BASE)


class TestTheText:
    def test_utf8_with_a_mark(self):
        assert decode_list_text(codecs.BOM_UTF8 + "Ä".encode(), False) == "Ä"

    def test_utf16(self):
        assert decode_list_text("Ä".encode("utf-16"), False) == "Ä"

    def test_utf8_without_one(self):
        assert decode_list_text("Ä".encode(), False) == "Ä"

    def test_an_old_m3u_in_the_systems_code_page(self, mocker):
        mocker.patch.object(
            list_files.locale, "getpreferredencoding", return_value="cp1252"
        )

        assert decode_list_text("Ä".encode("cp1252"), False) == "Ä"

    def test_an_m3u8_is_utf8_whatever_is_wrong_with_it(self):
        assert decode_list_text(b"a\xffb", True) == "a�b"


class TestLines:
    @pytest.mark.parametrize(
        ("text", "lines"),
        [
            ("a\nb\n", ["a", "b"]),
            ("a\r\nb", ["a\r", "b"]),
            ("a\rb\r", ["a", "b"]),
            ("a\n\nb", ["a", "", "b"]),
            ("", []),
        ],
    )
    def test_one_after_another_as_written(self, text, lines):
        assert list(list_files._lines(text)) == lines

    def test_a_list_with_old_mac_line_ends_is_read(self):
        read = parse_m3u("#EXTM3U\r#EXTINF:-1,One\rhttp://h/1\r", None)

        assert [(item.uri, item.title) for item in read.items] == [
            ("http://h/1", "One")
        ]

    def test_windows_line_ends_leave_nothing_behind(self):
        read = parse_m3u("#EXTM3U\r\n#EXTINF:-1,One\r\nhttp://h/1\r\n", None)

        assert [(item.uri, item.title) for item in read.items] == [
            ("http://h/1", "One")
        ]


class TestHowFarReadingHasGot:
    def test_told_every_so_many_items_and_how_far_through(self, mocker):
        mocker.patch.object(list_files, "PROGRESS_EVERY_ITEMS", 2)
        text = "#EXTM3U\n" + "".join(f"http://h/{n}\n" for n in range(6))
        told = []

        parse_m3u(text, None, lambda *said: told.append(said))

        assert [(what, count) for what, count, _percent in told] == [
            ("items", 2),
            ("items", 4),
            ("items", 6),
        ]
        percents = [percent for _what, _count, percent in told]
        assert percents == sorted(percents)
        assert percents[-1] == 100


class TestEndedEarly:
    def test_the_items_read_by_then(self, mocker):
        mocker.patch.object(list_files, "PROGRESS_EVERY_ITEMS", 2)
        text = "#EXTM3U\n" + "".join(f"http://h/{n}\n" for n in range(6))

        def progress(what, count, of=None):
            if count == 4:
                raise ReadingEnough

        read = parse_m3u(text, None, progress)

        assert [item.uri for item in read.items] == [f"http://h/{n}" for n in range(4)]


class TestManyItems:
    def test_a_groups_name_is_held_once(self):
        text = "#EXTM3U\n" + "".join(
            f'#EXTINF:-1 group-title="{"News" + ""}",C{n}\nhttp://h/{n}\n'
            for n in range(3)
        )

        groups = [item.group for item in parse_m3u(text, None).items]

        assert groups == ["News"] * 3
        assert groups[0] is groups[1] is groups[2]

    def test_items_given_the_same_fields_share_them(self):
        text = "#EXTM3U\n#EXTINF:-1,A\nhttp://h/1\n#EXTINF:-1,B\nhttp://h/2\n"

        first, second = parse_m3u(text, None).items

        assert first.model_fields_set is second.model_fields_set
        assert first.model_fields_set == {"uri", "title"}

    def test_one_changed_leaves_the_others_as_they_were(self):
        text = "#EXTM3U\n#EXTINF:-1,A\nhttp://h/1\n#EXTINF:-1,B\nhttp://h/2\n"
        first, second = parse_m3u(text, None).items

        changed = first.model_copy(update={"duration_ms": 5000})

        assert changed.duration_ms == 5000
        assert changed.key == first.key
        assert changed.model_fields_set == {"uri", "title", "duration_ms"}
        assert first.model_fields_set == second.model_fields_set == {"uri", "title"}

    def test_each_is_still_its_own_item(self):
        text = "#EXTM3U\nhttp://h/1\nhttp://h/2\n"

        first, second = parse_m3u(text, None).items

        assert first.key != second.key
        assert first.title is None
        assert not first.is_added


class TestAFile:
    def test_read_by_its_kind(self, tmp_path):
        path = tmp_path / "shows.m3u8"
        path.write_text("#EXTM3U\n#EXTINF:1,Ü\nep1.mkv\n", encoding="utf-8")

        read = read_list_file(path)

        assert _uris(read) == [tmp_path / "ep1.mkv"]
        assert read.items[0].title == "Ü"

    def test_one_larger_than_set_is_not_read(self, tmp_path):
        path = tmp_path / "huge.m3u"
        path.write_bytes(b"a.mp4\n" * 1024 * 1024)

        with pytest.raises(ValueError, match="larger than 5 MB"):
            read_list_file(path, max_bytes=5 * 2**20)

    def test_one_as_large_as_set_is(self, tmp_path):
        path = tmp_path / "list.m3u"
        path.write_bytes(b"a.mp4\n" * 10)

        assert len(read_list_file(path, max_bytes=60).items) == 10

    def test_larger_than_the_most_there_is_by_default(self, tmp_path, mocker):
        mocker.patch.object(list_files, "MAX_LIST_FILE_BYTES", 10)
        path = tmp_path / "huge.m3u"
        path.write_text("a.mp4\n" * 10, encoding="utf-8")

        with pytest.raises(ValueError, match="larger than"):
            read_list_file(path)

    @pytest.mark.parametrize(
        ("text", "kind"),
        [
            ("[playlist]\nFile1=http://h/1\n", "pls"),
            ('<?xml version="1.0"?><playlist><trackList/></playlist>', "xspf"),
            ("#EXTM3U\nhttp://h/1\n", "m3u"),
        ],
    )
    def test_with_no_extension_by_what_it_looks_like(self, text, kind):
        read = parse_list(text, "", None)

        assert isinstance(read.items, tuple)
        assert looks_like_list(text)

    @pytest.mark.parametrize(
        ("name", "is_list"),
        [
            ("a.m3u", True),
            ("a.M3U8", True),
            ("a.pls", True),
            ("a.xspf", True),
            ("a.mp4", False),
            ("m3u", False),
        ],
    )
    def test_told_by_its_name(self, name, is_list):
        assert is_list_file_name(name) is is_list

    def test_a_page_that_is_not_a_list(self):
        assert not looks_like_list("<!DOCTYPE html><html>")
