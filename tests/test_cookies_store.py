import inspect
import io
import json
from http.cookiejar import LoadError, MozillaCookieJar

import pytest
from yt_dlp.cookies import YoutubeDLCookieJar
from gridplayer.utils.cookies import (
    CookieImportError,
    CookieJar,
    CookieStore,
    RewindingBuffer,
    domain_summary,
    parse_cookies,
    same_cookies,
)

NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"

SESSION = 0
FOREVER = 2000000000


def _line(domain, name, value, expires=SESSION, path="/"):
    includes_subdomains = "TRUE" if domain.startswith(".") else "FALSE"

    return (
        f"{domain}\t{includes_subdomains}\t{path}\tFALSE\t{expires}\t{name}\t{value}\n"
    )


def _write(path, *lines):
    path.write_text(NETSCAPE_HEADER + "".join(lines), encoding="utf-8")

    return path


def _store(tmp_path, *lines):
    path = tmp_path / "cookies.txt"

    if lines:
        _write(path, *lines)

    return CookieStore(path)


def _values(jar):
    return {(c.domain, c.name): c.value for c in jar}


class TestReadingTheJar:
    def test_it_reads_what_is_on_the_disk(self, tmp_path):
        store = _store(
            tmp_path,
            _line(".youtube.com", "SID", "abc"),
            _line(".bilibili.tv", "SESSDATA", "xyz"),
        )

        assert _values(store.jar) == {
            (".youtube.com", "SID"): "abc",
            (".bilibili.tv", "SESSDATA"): "xyz",
        }

    def test_no_file_is_no_cookies(self, tmp_path):
        store = _store(tmp_path)

        assert store.jar is None
        assert store.is_empty

    def test_a_file_of_nonsense_is_no_cookies_rather_than_an_error(self, tmp_path):
        """A damaged jar must never take a video down with it."""

        path = tmp_path / "cookies.txt"
        path.write_text("this is not a cookie file", encoding="utf-8")

        store = CookieStore(path)

        assert store.jar is None
        assert store.is_empty

    def test_an_empty_jar_counts_as_empty(self, tmp_path):
        store = _store(tmp_path, "")

        assert store.is_empty

    def test_a_file_edited_by_hand_is_picked_up(self, tmp_path):
        store = _store(tmp_path, _line(".youtube.com", "SID", "abc"))

        assert _values(store.jar) == {(".youtube.com", "SID"): "abc"}

        _write(
            tmp_path / "cookies.txt",
            _line(".youtube.com", "SID", "abc"),
            _line(".youtube.com", "HSID", "def"),
        )

        assert _values(store.jar) == {
            (".youtube.com", "SID"): "abc",
            (".youtube.com", "HSID"): "def",
        }


class TestTheBufferAJarIsSavedInto:
    """A jar saved back into the buffer it came from has to still parse.

    Driven with yt-dlp's own jar on purpose. The buffer exists because that
    is what yt-dlp saves into on close, so the thing worth pinning is how
    the real one behaves, not how ours does.
    """

    def test_truncating_to_nothing_rewinds(self):
        buffer = RewindingBuffer("some text")
        buffer.read()

        buffer.truncate(0)
        buffer.write("new")

        assert buffer.getvalue() == "new"

    def test_a_round_trip_leaves_no_padding_behind(self):
        """CookieJar.save truncates without seeking; plain StringIO NUL-pads."""

        buffer = RewindingBuffer(NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc"))

        jar = YoutubeDLCookieJar(buffer)
        jar.load(ignore_discard=True, ignore_expires=True)
        jar.save()

        assert "\x00" not in buffer.getvalue()

    def test_what_comes_back_out_can_be_read_again(self):
        buffer = RewindingBuffer(NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc"))

        jar = YoutubeDLCookieJar(buffer)
        jar.load(ignore_discard=True, ignore_expires=True)
        jar.save()

        reread = CookieJar()
        reread.load_text(buffer.getvalue())

        assert _values(reread) == {(".youtube.com", "SID"): "abc"}


class TestMergingBackWhatWasRefreshed:
    def test_a_new_value_for_a_cookie_we_hold_is_taken(self, tmp_path):
        store = _store(tmp_path, _line(".youtube.com", "SID", "old"))

        refreshed = store.merge(NETSCAPE_HEADER + _line(".youtube.com", "SID", "new"))

        assert refreshed == 1
        assert _values(store.jar) == {(".youtube.com", "SID"): "new"}

    def test_it_lands_on_the_disk_and_not_only_in_memory(self, tmp_path):
        store = _store(tmp_path, _line(".youtube.com", "SID", "old"))

        store.merge(NETSCAPE_HEADER + _line(".youtube.com", "SID", "new"))

        assert _values(CookieStore(tmp_path / "cookies.txt").jar) == {
            (".youtube.com", "SID"): "new"
        }

    def test_a_longer_life_counts_as_a_refresh(self, tmp_path):
        store = _store(tmp_path, _line(".youtube.com", "SID", "abc", expires=SESSION))

        refreshed = store.merge(
            NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc", expires=FOREVER)
        )

        assert refreshed == 1
        assert next(iter(store.jar)).expires == FOREVER

    def test_a_cookie_we_never_held_is_not_added(self, tmp_path):
        """Whatever a resolve followed on the way does not get to leave anything."""

        store = _store(tmp_path, _line(".youtube.com", "SID", "abc"))

        refreshed = store.merge(
            NETSCAPE_HEADER
            + _line(".youtube.com", "SID", "abc")
            + _line(".tracker.example", "UID", "666")
        )

        assert refreshed == 0
        assert _values(store.jar) == {(".youtube.com", "SID"): "abc"}

    def test_a_domain_deleted_meanwhile_does_not_come_back(self, tmp_path):
        """The resolve that is merging started before the deletion."""

        store = _store(
            tmp_path,
            _line(".youtube.com", "SID", "abc"),
            _line(".bilibili.tv", "SESSDATA", "xyz"),
        )
        in_flight = store.dump()

        store.save(_jar_of(_line(".youtube.com", "SID", "abc")))

        store.merge(in_flight)

        assert _values(store.jar) == {(".youtube.com", "SID"): "abc"}

    def test_nothing_worth_keeping_leaves_the_file_untouched(self, tmp_path):
        store = _store(tmp_path, _line(".youtube.com", "SID", "abc"))
        before = (tmp_path / "cookies.txt").read_bytes()

        refreshed = store.merge(NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc"))

        assert refreshed == 0
        assert (tmp_path / "cookies.txt").read_bytes() == before

    @pytest.mark.parametrize("dumped", ["", "   ", "not a cookie file"])
    def test_garbage_coming_back_changes_nothing(self, tmp_path, dumped):
        store = _store(tmp_path, _line(".youtube.com", "SID", "abc"))

        assert store.merge(dumped) == 0
        assert _values(store.jar) == {(".youtube.com", "SID"): "abc"}

    def test_merging_into_an_empty_store_adds_nothing(self, tmp_path):
        store = _store(tmp_path)

        assert store.merge(NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc")) == 0
        assert store.is_empty


class TestClearing:
    def test_it_takes_the_file_off_the_disk(self, tmp_path):
        store = _store(tmp_path, _line(".youtube.com", "SID", "abc"))

        store.clear()

        assert not (tmp_path / "cookies.txt").exists()
        assert store.jar is None

    def test_clearing_what_was_never_there_is_no_error(self, tmp_path):
        _store(tmp_path).clear()


def _jar_of(*lines):
    jar = CookieJar()
    jar.load_text(NETSCAPE_HEADER + "".join(lines))

    return jar


class TestReadingWhatWasHandedOver:
    """An export is whatever the browser or its add-on chose to produce."""

    def test_a_cookies_txt(self):
        jar = parse_cookies(NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc"))

        assert _values(jar) == {(".youtube.com", "SID"): "abc"}

    def test_lines_pasted_without_the_header(self):
        """What lands on the clipboard rarely brings the magic line along."""

        jar = parse_cookies(_line(".youtube.com", "SID", "abc"))

        assert _values(jar) == {(".youtube.com", "SID"): "abc"}

    def test_a_cookie_marked_http_only(self):
        jar = parse_cookies(
            NETSCAPE_HEADER + "#HttpOnly_" + _line(".youtube.com", "SID", "abc")
        )

        assert _values(jar) == {(".youtube.com", "SID"): "abc"}

    def test_what_a_browser_add_on_exports(self):
        exported = json.dumps(
            [
                {
                    "domain": ".youtube.com",
                    "name": "SID",
                    "value": "abc",
                    "path": "/",
                    "expirationDate": 1900000000.25,
                    "secure": True,
                }
            ]
        )

        jar = parse_cookies(exported)
        cookie = next(iter(jar))

        assert (cookie.domain, cookie.name, cookie.value) == (
            ".youtube.com",
            "SID",
            "abc",
        )
        assert cookie.expires == 1900000000
        assert cookie.secure

    def test_an_export_wrapped_in_an_object(self):
        jar = parse_cookies(
            json.dumps({"cookies": [{"domain": ".x.com", "name": "a", "value": "b"}]})
        )

        assert _values(jar) == {(".x.com", "a"): "b"}

    def test_entries_with_nothing_to_go_on_are_skipped(self):
        jar = parse_cookies(
            json.dumps(
                [
                    {"name": "no domain", "value": "b"},
                    {"domain": ".x.com", "value": "no name"},
                    "not even an object",
                    {"domain": ".x.com", "name": "a", "value": "b"},
                ]
            )
        )

        assert _values(jar) == {(".x.com", "a"): "b"}

    @pytest.mark.parametrize(
        "text", ["", "   ", "have some cookies", "[]", "[{}]", "{]"]
    )
    def test_anything_unusable_says_so_rather_than_half_importing(self, text):
        with pytest.raises(CookieImportError):
            parse_cookies(text)


class TestTellingTwoJarsApart:
    def test_the_same_cookies_are_the_same(self):
        text = NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc")

        assert same_cookies(parse_cookies(text), parse_cookies(text))

    def test_a_different_value_is_not(self):
        assert not same_cookies(
            parse_cookies(NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc")),
            parse_cookies(NETSCAPE_HEADER + _line(".youtube.com", "SID", "xyz")),
        )

    def test_an_extra_cookie_is_not(self):
        assert not same_cookies(
            parse_cookies(NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc")),
            parse_cookies(
                NETSCAPE_HEADER
                + _line(".youtube.com", "SID", "abc")
                + _line(".youtube.com", "HSID", "def")
            ),
        )

    def test_two_kinds_of_nothing_are_the_same(self):
        assert same_cookies(None, None)


NOW = 1700000000
PAST = NOW - 86400
SOON = NOW + 86400
LATER = NOW + 86400 * 365


class TestSummingUpAHost:
    """Which cookies count towards the span the settings page shows."""

    def _rows(self, *lines):
        return domain_summary(parse_cookies(NETSCAPE_HEADER + "".join(lines)), now=NOW)

    def test_the_span_runs_from_the_soonest_to_the_furthest(self):
        (row,) = self._rows(
            _line(".x.com", "a", "1", expires=SOON),
            _line(".x.com", "b", "2", expires=LATER),
        )

        assert (row.expires_from, row.expires_to) == (SOON, LATER)
        assert not row.is_expired

    def test_cookies_already_past_it_are_left_out_of_the_span(self):
        """A browser export routinely carries a few that lapsed on the way out.

        Counting them reported a login dead the moment it was imported.
        """

        (row,) = self._rows(
            _line(".x.com", "dead", "1", expires=PAST),
            _line(".x.com", "a", "2", expires=SOON),
            _line(".x.com", "b", "3", expires=LATER),
        )

        assert (row.expires_from, row.expires_to) == (SOON, LATER)

    def test_but_they_are_still_counted(self):
        (row,) = self._rows(
            _line(".x.com", "dead", "1", expires=PAST),
            _line(".x.com", "a", "2", expires=SOON),
        )

        assert row.count == 2

    def test_a_host_with_nothing_live_left_is_expired(self):
        (row,) = self._rows(_line(".x.com", "a", "1", expires=PAST))

        assert row.is_expired
        assert row.expires_from is None

    def test_a_session_cookie_keeps_it_from_being_expired(self):
        """It has no date to be past, so it is still worth something."""

        (row,) = self._rows(
            _line(".x.com", "dead", "1", expires=PAST),
            _line(".x.com", "tmp", "2", expires=0),
        )

        assert not row.is_expired
        assert row.expires_from is None

    def test_a_live_cookie_outranks_a_session_one(self):
        (row,) = self._rows(
            _line(".x.com", "tmp", "1", expires=0),
            _line(".x.com", "a", "2", expires=SOON),
        )

        assert (row.expires_from, row.expires_to) == (SOON, SOON)


class TestStandingOnTheStdlibParser:
    """What the jar keeps doing now that yt-dlp's version is out of the way."""

    def test_the_private_loader_still_takes_what_we_hand_it(self):
        """We call a private stdlib method, so notice loudly if it moves."""

        parameters = inspect.signature(MozillaCookieJar._really_load).parameters

        assert list(parameters) == [
            "self",
            "f",
            "filename",
            "ignore_discard",
            "ignore_expires",
        ]

    def test_one_broken_line_does_not_cost_the_whole_file(self):
        """The stdlib parser gives up on the file; an export can carry junk."""

        jar = CookieJar()
        jar.load_text(
            NETSCAPE_HEADER
            + _line(".youtube.com", "SID", "abc")
            + "this line is not a cookie\n"
            + _line(".bilibili.tv", "SESSDATA", "xyz")
        )

        assert _values(jar) == {
            (".youtube.com", "SID"): "abc",
            (".bilibili.tv", "SESSDATA"): "xyz",
        }

    def test_a_line_with_nonsense_where_the_date_goes_is_dropped(self):
        jar = CookieJar()
        jar.load_text(
            NETSCAPE_HEADER
            + ".x.com\tTRUE\t/\tFALSE\tsoonish\tbad\tv\n"
            + _line(".youtube.com", "SID", "abc")
        )

        assert _values(jar) == {(".youtube.com", "SID"): "abc"}

    def test_a_file_that_is_not_one_at_all_still_fails(self):
        """Line tolerance is not a reason to read a text file as cookies."""

        jar = CookieJar()

        with pytest.raises(LoadError):
            jar.load_text("this is not a cookie file at all")

    def test_a_zero_expiry_is_a_session_cookie_not_an_ancient_one(self):
        """Add-ons write 0 where the stdlib writes nothing.

        Read as a date, 0 is 1970, and every library we hand the jar to
        drops an expired cookie rather than sending it.
        """

        jar = CookieJar()
        jar.load_text(NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc", expires=0))

        (cookie,) = jar

        assert cookie.expires is None
        assert cookie.discard
        assert not cookie.is_expired()

    def test_a_session_cookie_survives_a_trip_through_the_file(self):
        jar = CookieJar()
        jar.load_text(NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc", expires=0))

        reread = CookieJar()
        reread.load_text(jar.dump())

        (cookie,) = reread

        assert cookie.expires is None
        assert not cookie.is_expired()

    def test_an_http_only_cookie_keeps_its_flag_across_a_round_trip(self):
        jar = CookieJar()
        jar.load_text(
            NETSCAPE_HEADER + "#HttpOnly_" + _line(".youtube.com", "SID", "abc")
        )

        assert "#HttpOnly_" in jar.dump()

    def test_a_dumped_jar_reads_back_the_same(self):
        jar = CookieJar()
        jar.load_text(
            NETSCAPE_HEADER
            + _line(".youtube.com", "SID", "abc", expires=FOREVER)
            + _line(".bilibili.tv", "SESSDATA", "xyz")
        )

        reread = CookieJar()
        reread.load_text(jar.dump())

        assert same_cookies(jar, reread)

    def test_what_it_writes_is_what_yt_dlp_reads(self):
        """The file format is the whole contract with yt-dlp."""

        jar = CookieJar()
        jar.load_text(
            NETSCAPE_HEADER + _line(".youtube.com", "SID", "abc", expires=FOREVER)
        )

        theirs = YoutubeDLCookieJar(io.StringIO(jar.dump()))
        theirs.load(ignore_discard=True, ignore_expires=True)

        assert _values(theirs) == {(".youtube.com", "SID"): "abc"}


class TestTheShapesAnExportActuallyArrivesIn:
    """What people paste and pick is rarely the tidy thing in the docs."""

    LINE = ".youtube.com\tTRUE\t/\tFALSE\t2000000000\tSID\tabc\n"

    def _one(self, text):
        return {(c.domain, c.name): c.value for c in parse_cookies(text)}

    def test_the_tidy_thing(self):
        assert self._one(NETSCAPE_HEADER + self.LINE) == {
            (".youtube.com", "SID"): "abc"
        }

    def test_lines_alone_off_the_clipboard(self):
        assert self._one(self.LINE) == {(".youtube.com", "SID"): "abc"}

    def test_an_export_that_leads_with_its_own_comment(self):
        """The stdlib parser takes the header line or nothing, and a file
        that says who wrote it first used to be refused outright."""

        text = "# Exported by Cookie-Editor\n" + NETSCAPE_HEADER + self.LINE

        assert self._one(text) == {(".youtube.com", "SID"): "abc"}

    def test_a_comment_that_is_nearly_but_not_quite_the_header(self):
        assert self._one("# Netscape-ish export\n" + self.LINE) == {
            (".youtube.com", "SID"): "abc"
        }

    def test_windows_line_endings(self):
        text = (NETSCAPE_HEADER + self.LINE).replace("\n", "\r\n")
        read = self._one(text)

        assert read == {(".youtube.com", "SID"): "abc"}

    def test_a_byte_order_mark_in_front(self):
        assert self._one("\ufeff" + NETSCAPE_HEADER + self.LINE) == {
            (".youtube.com", "SID"): "abc"
        }

    def test_trailing_blank_lines(self):
        assert self._one(NETSCAPE_HEADER + self.LINE + "\n\n") == {
            (".youtube.com", "SID"): "abc"
        }

    def test_something_that_is_not_cookies_at_all_is_still_refused(self):
        with pytest.raises(CookieImportError):
            parse_cookies("have some cookies")
