"""Lists of files and links as players save them, read for a cell to play.

M3U (and M3U8, the same in UTF-8), PLS and XSPF, the ones players and
channel lists come in. A channel list says more of each channel than where
it is -- its name, its group, what to fetch it with -- and that is kept.

An HLS stream's playlist is an M3U8 file too, but it lists the pieces of one
video rather than videos to play one after the other; it is told apart and
left to be played as the one video it is.
"""

import codecs
import json
import locale
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from gridplayer.models.media_list import (
    ListItem,
    new_item_key,
    shared_http_headers,
    shared_item_shape,
)
from gridplayer.models.video_uri import URL_ALLOWED_SCHEMES, parse_uri
from gridplayer.params.extensions import (
    SUPPORTED_LIST_EXT,
    SUPPORTED_M3U_EXT,
    SUPPORTED_PLS_EXT,
    SUPPORTED_XSPF_EXT,
)
from gridplayer.utils.aspect_calc import parse_aspect_ratio
from gridplayer.utils.list_progress import ReadingEnough

_log = logging.getLogger(__name__)

M3U_EXT = SUPPORTED_M3U_EXT
PLS_EXT = SUPPORTED_PLS_EXT
XSPF_EXT = SUPPORTED_XSPF_EXT

LIST_FILE_EXT = SUPPORTED_LIST_EXT

# the largest list read where none is asked for: a channel list of a whole
# provider runs to tens of megabytes, some 50 for 200,000 channels and their
# logos, and to hundreds with a film library; see player/list_max_mb
MAX_LIST_FILE_BYTES = 512 * 1024 * 1024

# the tags only an HLS stream's own playlist has
_HLS_TAG = "#EXT-X-"

# a line that starts with one, looked for through the text at once,
# rather than through its lines: a channel list's are millions
_HLS_LINE = re.compile(r"(?:^|[\r\n])\s*" + re.escape(_HLS_TAG))

# a name="value" pair of an #EXTINF line, its value quoted, commas and all
_EXTINF_ATTRIBUTE = re.compile(r'([\w-]+)="([^"]*)"')

# an #EXTINF line's length and attributes, up to the first comma outside
# quotes, and the name after it
_EXTINF_HEAD_AND_NAME = re.compile(r'((?:[^,"]|"[^"]*")*),(.*)', re.DOTALL)

# how many items a list is read in between telling how far it has got
PROGRESS_EVERY_ITEMS = 2000

_XSPF_NS = "{http://xspf.org/ns/0/}"


class NotAListError(ValueError):
    """An HLS stream's playlist: one video, its pieces listed."""


class NoListThereError(ValueError):
    """What a link gave back is no list at all: a page, a picture."""


class ListTooLargeError(ValueError):
    """A list larger than the most that is read."""

    def __init__(self, max_bytes: int):
        super().__init__(too_large_txt(max_bytes))

        self.max_bytes = max_bytes


@dataclass(frozen=True)
class ReadList:
    # what the list calls itself, if anything
    name: str | None
    items: tuple[ListItem, ...]


def is_list_file_name(name: str) -> bool:
    _, dot, extension = name.rpartition(".")

    return bool(dot) and extension.lower() in LIST_FILE_EXT


def read_list_file(path: Path, progress=None, max_bytes=None) -> ReadList:
    """The list a file saved by a player or a channel provider holds, if it
    is no larger than max_bytes.

    Raises OSError where it cannot be read, NotAListError for an HLS
    stream, and ValueError for anything else it is not. progress is told
    how many items are read so far, now and then, and how far through the
    list that is: ("items", count, percent).
    """

    max_bytes = max_bytes or MAX_LIST_FILE_BYTES

    with path.open("rb") as list_file:
        # told by its size rather than by reading the most there may be:
        # asked for that much, a read sets aside that much to read into
        if os.fstat(list_file.fileno()).st_size > max_bytes:
            raise ListTooLargeError(max_bytes)

        data = list_file.read()

    extension = path.suffix.lower().lstrip(".")

    text = decode_list_text(data, is_utf8=extension in {"m3u8", "xspf"})

    # the text is all that is read from now on: the bytes it was are as
    # large again, for a list of hundreds of megabytes
    del data

    return parse_list(text, extension, path.parent, progress)


def too_large_txt(max_bytes: int) -> str:
    """Why a list was not read: what it was larger than."""

    return f"larger than {max_bytes // 2**20} MB, the largest playlist set to be read"


def parse_list(
    text: str, extension: str, base_dir: Path | None, progress=None
) -> ReadList:
    """The list in a list file's text, by its extension, or by what it
    looks like where the extension says nothing."""

    kind = _kind_of(text, extension)

    if kind == "pls":
        return parse_pls(text, base_dir)

    if kind == "xspf":
        return parse_xspf(text, base_dir)

    return parse_m3u(text, base_dir, progress)


def _kind_of(text: str, extension: str) -> str:
    if extension in PLS_EXT:
        return "pls"

    if extension in XSPF_EXT:
        return "xspf"

    if extension in M3U_EXT:
        return "m3u"

    head = text.lstrip()[:512].lower()

    if head.startswith("[playlist]"):
        return "pls"

    if head.startswith(("<?xml", "<playlist")):
        return "xspf"

    return "m3u"


def looks_like_list(text: str) -> bool:
    """Whether a page fetched from a link is a list of any kind, rather
    than whatever else a site answers with."""

    head = text.lstrip()[:512].lower()

    return head.startswith(("#extm3u", "[playlist]", "<?xml", "<playlist"))


def decode_list_text(data: bytes, is_utf8: bool) -> str:
    """The text of a list file, whatever it was written in.

    M3U8 and XSPF are UTF-8 by definition. A plain M3U is whatever the
    player that wrote it used, which for an old one is the system's own
    code page; UTF-8 is tried first, a file in it being far more likely to
    read as anything else than the other way round.
    """

    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8) :].decode("utf-8", errors="replace")

    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    if is_utf8:
        return data.decode("utf-8", errors="replace")

    encoding = locale.getpreferredencoding(False) or "cp1252"

    try:
        return data.decode(encoding, errors="replace")
    except LookupError:
        return data.decode("cp1252", errors="replace")


def is_hls_playlist(text: str) -> bool:
    return _HLS_LINE.search(text) is not None


def parse_m3u(text: str, base_dir: Path | None, progress=None) -> ReadList:
    """An M3U list, simple or extended, a channel list's tags and all.

    What a tag says goes with the entry that comes after it: the name and
    length in #EXTINF, the group in #EXTGRP or the group-title of #EXTINF,
    the user agent and referrer to fetch it with in #EXTVLCOPT, #EXTHTTP or
    after a "|" at the end of the link itself, and the aspect ratio and crop
    shape to show it in in #EXTVLCOPT. Nothing else a tag asks VLC to do is
    passed on: a list from the internet is no one to take orders from.
    """

    if is_hls_playlist(text):
        raise NotAListError

    name = None
    pending: dict = {}
    items = []

    # how far through the text, to tell how far reading has got
    size = len(text) or 1
    passed = 0

    for raw_line in _lines(text):
        passed += len(raw_line) + 1
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            tag, _, value = line[1:].partition(":")
            tag = tag.strip().upper()

            if tag == "EXTINF":
                # what it leaves unsaid is not unsaid by a tag of its own
                pending.update(
                    (key, said)
                    for key, said in _extinf(value).items()
                    if said is not None
                )
            elif tag == "EXTGRP":
                pending.setdefault("group", value.strip() or None)
            elif tag == "PLAYLIST":
                name = value.strip() or name
            elif tag == "EXTVLCOPT":
                pending.update(_vlc_option(value))
            elif tag == "EXTHTTP":
                pending.update(_http_headers(value))

            continue

        entry, pipe_headers = _split_pipe_headers(line)
        uri = entry_uri(entry, base_dir)

        if uri is not None:
            items.append(_item(uri, {**pipe_headers, **pending}))

            if progress is not None and not len(items) % PROGRESS_EVERY_ITEMS:
                try:
                    progress("items", len(items), min(passed * 100 // size, 100))
                except ReadingEnough:
                    break

        pending = {}

    return ReadList(name=name, items=tuple(items))


def _lines(text: str):
    """The lines of a text one after another, rather than all at once in a
    list beside it: a channel list's are millions of strings."""

    # a list written with a line end of a lone carriage return, as the old
    # Mac did, has no line feeds to look for
    if "\n" not in text:
        yield from text.splitlines()
        return

    start = 0
    size = len(text)

    while start < size:
        end = text.find("\n", start)

        if end == -1:
            end = size

        yield text[start:end]

        start = end + 1


def parse_pls(text: str, base_dir: Path | None) -> ReadList:
    entries: dict[int, dict] = {}

    for raw_line in text.splitlines():
        key, equals, value = raw_line.strip().partition("=")

        if not equals:
            continue

        match = re.fullmatch(r"(file|title|length)(\d+)", key.strip().lower())

        if match is None:
            continue

        field, number = match.group(1), int(match.group(2))
        entries.setdefault(number, {})[field] = value.strip()

    items = []

    for _number, entry in sorted(entries.items()):
        uri = entry_uri(entry.get("file", ""), base_dir)

        if uri is None:
            continue

        items.append(
            _item(
                uri,
                {
                    "title": entry.get("title") or None,
                    "duration_ms": _seconds_ms(entry.get("length")),
                },
            )
        )

    return ReadList(name=None, items=tuple(items))


def parse_xspf(text: str, base_dir: Path | None) -> ReadList:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"Not an XSPF list: {e}") from e

    def find(element, tag):
        found = element.find(f"{_XSPF_NS}{tag}")
        return found if found is not None else element.find(tag)

    track_list = find(root, "trackList")
    tracks = [] if track_list is None else list(track_list)

    items = []

    for track in tracks:
        location = find(track, "location")

        if location is None or not location.text:
            continue

        uri = entry_uri(location.text, base_dir)

        if uri is None:
            continue

        title = find(track, "title")
        duration = find(track, "duration")

        items.append(
            _item(
                uri,
                {
                    "title": title.text.strip()
                    if title is not None and title.text
                    else None,
                    "duration_ms": _int_or_none(
                        duration.text if duration is not None else None
                    ),
                },
            )
        )

    name = find(root, "title")

    return ReadList(
        name=name.text.strip() if name is not None and name.text else None,
        items=tuple(items),
    )


def entry_uri(entry: str, base_dir: Path | None) -> Path | str | None:
    """Where an entry of a list is: a link, or a file, one written relative
    to the list being where the list is. None for what is neither, or a
    link of a kind there is no playing."""

    entry = entry.strip()

    if not entry:
        return None

    if entry.lower().startswith("file:"):
        return _file_url_path(entry)

    if "://" in entry:
        scheme = entry.split("://", 1)[0].lower()

        if scheme not in URL_ALLOWED_SCHEMES:
            _log.debug(f"List entry of a kind there is no playing: {entry}")
            return None

        return entry

    # one written relative to a list read from a link stays so: nowhere
    # to find it from
    if base_dir is None:
        return Path(entry)

    return parse_uri(entry, base_dir)


def _file_url_path(entry: str) -> Path | None:
    parsed = urllib.parse.urlparse(entry)

    path = urllib.request.url2pathname(parsed.path)

    if parsed.netloc and parsed.netloc.lower() != "localhost":
        # a file on another machine: \\host\share\file
        path = f"//{parsed.netloc}{urllib.parse.unquote(parsed.path)}"

    return Path(path) if path else None


def _item(uri: Path | str, fields: dict) -> ListItem:
    """An item as read: made without checking every field of it again, the
    reading having made each what it is. A channel list has hundreds of
    thousands, and checking them all took longer than reading them.

    Every field is given, for none to be looked up as a default either:
    that is slower still, item by item.
    """

    said = {key: value for key, value in fields.items() if value is not None}

    # a group's name is the same string for every channel in it, the
    # headers to fetch with mostly the same for all, and the fields an item
    # was given one set for every item given those: a list of hundreds of
    # thousands holds them once rather than each its own
    if "group" in said:
        said["group"] = sys.intern(said["group"])

    if "user_agent" in said or "referrer" in said:
        said["http_headers"] = shared_http_headers(
            said.pop("user_agent", None), said.pop("referrer", None)
        )

    if "aspect_ratio" in said or "crop_ratio" in said:
        said["shape"] = shared_item_shape(
            said.pop("aspect_ratio", None), said.pop("crop_ratio", None)
        )

    # (a set, not a frozenset: an item copied with a change has the set
    # copied and then added to, and a frozenset copied is the same one)
    shape = frozenset(said)
    fields_set = _FIELD_SETS.get(shape)
    if fields_set is None:
        fields_set = _FIELD_SETS.setdefault(shape, {"uri", *said})

    return ListItem.model_construct(
        _fields_set=fields_set,
        **{**_ITEM_DEFAULTS, **said},
        uri=uri,
        key=new_item_key(),
    )


# the fields set of an item read, by the fields its list gave it; never
# added to in place, an item being frozen
_FIELD_SETS: dict[frozenset, set] = {}


# what an item read has where its list says nothing
_ITEM_DEFAULTS = MappingProxyType(
    {
        "title": None,
        "duration_ms": None,
        "group": None,
        "http_headers": None,
        "shape": None,
        "is_added": False,
        "is_renamed": False,
        "details": None,
    }
)


def _extinf(value: str) -> dict:
    """The length, name and group of an #EXTINF line:
    #EXTINF:-1 tvg-name="X" group-title="News, World",The Name"""

    head, title = _split_outside_quotes(value)

    length, _, attributes_txt = head.strip().partition(" ")
    attributes = dict(_EXTINF_ATTRIBUTE.findall(attributes_txt))

    title = title.strip() or attributes.get("tvg-name", "").strip() or None

    return {
        "title": title,
        "duration_ms": _seconds_ms(length),
        "group": attributes.get("group-title", "").strip() or None,
    }


def _split_outside_quotes(value: str) -> tuple[str, str]:
    """The part before the first comma outside quotes, and after it."""

    if '"' not in value:
        head, _, title = value.partition(",")
        return head, title

    matched = _EXTINF_HEAD_AND_NAME.match(value)

    if matched is not None:
        return matched.group(1), matched.group(2)

    # a quote left open: the long way, the rest of the line in quotes
    is_quoted = False

    for index, char in enumerate(value):
        if char == '"':
            is_quoted = not is_quoted
        elif char == "," and not is_quoted:
            return value[:index], value[index + 1 :]

    return value, ""


def _vlc_option(value: str) -> dict:
    key, _, option = value.strip().partition("=")
    key = key.strip().lower()
    option = option.strip().strip('"') or None

    if key == "http-user-agent":
        return {"user_agent": option}

    if key in {"http-referrer", "http-referer"}:
        return {"referrer": option}

    # a shape as VLC writes one, "16:9"; not its crop by a window or by
    # margins, which go by a frame size the list cannot know
    if key == "aspect-ratio" and _is_ratio(option):
        return {"aspect_ratio": option}

    if key == "crop" and _is_ratio(option):
        return {"crop_ratio": option}

    return {}


def _is_ratio(option: str | None) -> bool:
    return option is not None and parse_aspect_ratio(option) is not None


def _http_headers(value: str) -> dict:
    """#EXTHTTP:{"User-Agent": "...", "Referer": "..."}"""

    try:
        headers = json.loads(value)
    except ValueError:
        return {}

    if not isinstance(headers, dict):
        return {}

    return _known_headers(headers)


def _split_pipe_headers(entry: str) -> tuple[str, dict]:
    """A link with the headers to fetch it with after a "|", the way Kodi
    lists write them: http://host/live.m3u8|User-Agent=X&Referer=Y"""

    if "://" not in entry or "|" not in entry:
        return entry, {}

    link, _, headers_txt = entry.partition("|")

    headers = dict(
        urllib.parse.parse_qsl(headers_txt, keep_blank_values=False, separator="&")
    )

    return link, _known_headers(headers)


def _known_headers(headers: dict) -> dict:
    folded = {str(key).strip().lower(): value for key, value in headers.items()}

    known = {
        "user_agent": folded.get("user-agent"),
        "referrer": folded.get("referer") or folded.get("referrer"),
    }

    return {key: str(value).strip() for key, value in known.items() if value}


def _seconds_ms(seconds_txt: str | None) -> int | None:
    """A length in seconds as lists write it, -1 for none or for live."""

    try:
        seconds = float(seconds_txt)
    except (TypeError, ValueError):
        return None

    if seconds <= 0:
        return None

    return round(seconds * 1000)


def _int_or_none(value_txt: str | None) -> int | None:
    try:
        value = int(value_txt.strip())
    except (AttributeError, ValueError):
        return None

    return value if value > 0 else None


def m3u_text(name: str, items, base_dir: Path | None) -> str:
    """A list written as an extended M3U, for other players to read: each
    item's name, length, group, what to fetch it with and to show it in.

    Paths under base_dir, the folder the file goes in, are written relative
    to it, for the file to move along with what it lists.
    """

    lines = ["#EXTM3U"]

    if name:
        lines.append(f"#PLAYLIST:{_one_line(name)}")

    for item in items:
        seconds = -1 if item.duration_ms is None else round(item.duration_ms / 1000)
        group = (
            f' group-title="{_one_line(item.group).replace(chr(34), chr(39))}"'
            if item.group
            else ""
        )
        title = _one_line(item.title or item.uri_name)

        lines.append(f"#EXTINF:{seconds}{group},{title}")

        headers = item.http_headers

        if headers is not None and headers.user_agent:
            lines.append(f"#EXTVLCOPT:http-user-agent={_one_line(headers.user_agent)}")
        if headers is not None and headers.referrer:
            lines.append(f"#EXTVLCOPT:http-referrer={_one_line(headers.referrer)}")

        shape = item.shape

        if shape is not None and shape.aspect_ratio:
            lines.append(f"#EXTVLCOPT:aspect-ratio={shape.aspect_ratio}")
        if shape is not None and shape.crop_ratio:
            lines.append(f"#EXTVLCOPT:crop={shape.crop_ratio}")

        lines.append(_m3u_location(item.uri, base_dir))

    return "\n".join(lines) + "\n"


def _one_line(text: str) -> str:
    return " ".join(text.splitlines())


def _m3u_location(uri: Path | str, base_dir: Path | None) -> str:
    if not isinstance(uri, Path):
        return uri

    if base_dir is not None:
        try:
            return str(uri.relative_to(base_dir))
        except ValueError:
            pass

    return str(uri)
