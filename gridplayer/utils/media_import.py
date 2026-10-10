"""What a drop, a file dialog or a command line hands the player, made into
what the cells play: a file or a link each, or a list one after the other,
read from a folder, a list file or a link to one.

Reading may take a while -- a folder tree, a list on a network drive, a
channel list from a provider -- so expand_inputs is meant to be run off the
interface thread; what is done with the result is not.
"""

import logging
import urllib.parse
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from gridplayer.models.media_list import ListItem, ListSource
from gridplayer.params.static import AddMode, ListSourceKind
from gridplayer.utils.list_cache import keep_read
from gridplayer.utils.list_files import (
    NoListThereError,
    NotAListError,
    ReadList,
    decode_list_text,
    is_list_file_name,
    looks_like_list,
    parse_list,
    read_list_file,
)
from gridplayer.utils.list_progress import ReadingEnough, ReadingStopped
from gridplayer.utils.misc import is_url
from gridplayer.utils.next_file import ScanRules, scan_folder
from gridplayer.utils.web_lists import is_web_list_url

_log = logging.getLogger(__name__)

# the query a channel provider's list link asks for its list with
_LIST_URL_TYPES = frozenset(("m3u", "m3u_plus", "m3u8"))


@dataclass(frozen=True)
class ListInput:
    """A list of things to play one after the other, as it was read."""

    name: str
    items: tuple[ListItem, ...]
    source: ListSource | None = None
    # the item to play first: a video opened from a playlist is where the
    # playlist is played from
    start: int = 0


# a thing to play, or a list of them
Group = ListItem | ListInput


@dataclass(frozen=True)
class Expanded:
    groups: tuple[Group, ...] = ()
    # what could not be read, and why
    failed: tuple[tuple[str, str], ...] = ()


@dataclass
class _Expanding:
    groups: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    progress: Callable[[str, int], None] | None = None
    max_list_bytes: int | None = None


def is_list_url(url: str) -> bool:
    """Whether a link looks like one to a list rather than to a video: a
    list file, or a channel provider's link asking for its list.

    An HLS stream ends in .m3u8 just the same; it is told apart once it is
    fetched, by what is in it.
    """

    parsed = urllib.parse.urlparse(url)

    if parsed.scheme.lower() not in {"http", "https"}:
        return False

    if is_list_file_name(urllib.parse.unquote(parsed.path)):
        return True

    query = urllib.parse.parse_qs(parsed.query)

    return any(kind.lower() in _LIST_URL_TYPES for kind in query.get("type", ()))


def expand_inputs(
    uris: Iterable[str | Path],
    rules: ScanRules,
    fetch: Callable[[str], bytes] | None = None,
    read_web: Callable[[str], "Group"] | None = None,
    progress: Callable[[str, int], None] | None = None,
    max_list_bytes: int | None = None,
) -> Expanded:
    """Each thing handed over as what is played: a file or link as it is,
    a folder as a list of the media files in it and under it, and a list
    file, or a link to one, as the list in it.

    fetch reads a link to a list file, and read_web the list a site keeps
    behind a link; without them such links are taken to be videos, as every
    link was before there were lists. progress is told how many items of a
    list are read so far, now and then: ("items", count), and how many
    files of a folder are found: ("files", count). A list file larger than
    max_list_bytes is not read.

    Where progress raises ReadingEnough, a folder is what was found of it
    by then, and a list what was read of it; one still being downloaded is
    let go.
    """

    expanding = _Expanding(progress=progress, max_list_bytes=max_list_bytes)

    for uri in uris:
        _expand_one(str(uri), rules, fetch, read_web, expanding)

    return Expanded(groups=tuple(expanding.groups), failed=tuple(expanding.failed))


def _expand_one(uri, rules, fetch, read_web, expanding) -> None:
    if is_url(uri):
        if fetch is not None and is_list_url(uri):
            _expand_list_url(uri, fetch, expanding)
        elif read_web is not None and is_web_list_url(uri):
            _expand_web_list(uri, read_web, expanding)
        else:
            expanding.groups.append(ListItem(uri=uri))
        return

    path = Path(uri).absolute()

    try:
        is_folder = path.is_dir()
    except OSError:
        is_folder = False

    if is_folder:
        _expand_folder(path, rules, expanding)
        return

    if is_list_file_name(path.name):
        _expand_list_file(path, expanding)
        return

    expanding.groups.append(ListItem(uri=path))


def _expand_folder(path: Path, rules: ScanRules, expanding) -> None:
    folder = folder_list(path, rules, progress=expanding.progress)

    if folder is None:
        expanding.failed.append((str(path), "no media files"))
        return

    expanding.groups.append(folder)


def folder_list(
    path: Path, rules: ScanRules, is_recursive: bool = True, progress=None
) -> ListInput | None:
    """The media files of a folder as a list, and of its subfolders if
    asked for; None for none. progress is told how many are found so far,
    as in scan_folder."""

    scan = scan_folder(path, is_recursive=is_recursive, rules=rules, progress=progress)

    if not scan.files:
        return None

    return ListInput(
        name=path.name or str(path),
        items=tuple(ListItem(uri=file_path) for file_path in scan.files),
        source=ListSource(
            kind=ListSourceKind.FOLDER, location=path, is_recursive=is_recursive
        ),
    )


def read_source(
    source: ListSource,
    rules: ScanRules,
    fetch: Callable[[str], bytes] | None = None,
    read_web: Callable[[str], "Group"] | None = None,
    max_list_bytes: int | None = None,
    progress: Callable | None = None,
) -> tuple[ListItem, ...]:
    """What is where a list was read from, as it is now. Raises OSError or
    ValueError for what cannot be read: a folder gone, a link down.

    Meant for off the interface thread, as reading it the first time was.
    progress is told how many items of a list are read so far, as in
    read_list_file, and how many files of a folder are found; how much of
    a link is downloaded is fetch's to tell.
    """

    if source.kind == ListSourceKind.FOLDER:
        path = Path(source.location)

        if not path.is_dir():
            raise FileNotFoundError(f"Folder not found: {path}")

        folder = folder_list(path, rules, source.is_recursive, progress)

        return () if folder is None else folder.items

    if source.kind == ListSourceKind.FILE:
        return read_list_file(
            Path(source.location), progress, max_bytes=max_list_bytes
        ).items

    url = str(source.location)

    if fetch is not None and is_list_url(url):
        items = _fetched_list(url, fetch, progress).items
    elif read_web is not None:
        read = read_web(url)
        items = read.items if isinstance(read, ListInput) else (read,)
    else:
        raise ValueError(f"Cannot read {url}")

    # for a list read from it to be there at once the next time the
    # playlist opens, before it is read again
    keep_read(source, items)

    return items


def _fetched_list(url: str, fetch, progress=None) -> ReadList:
    data = fetch(url)

    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    extension = path.rpartition(".")[2].lower() if "." in path else ""

    text = decode_list_text(data, is_utf8=extension != "m3u")

    # the text is all that is read from now on: let go of the bytes
    del data

    if not looks_like_list(text):
        raise NoListThereError(f"Not a list: {url}")

    return parse_list(text, extension, base_dir=None, progress=progress)


def _expand_list_file(path: Path, expanding) -> None:
    try:
        read = read_list_file(path, expanding.progress, expanding.max_list_bytes)
    except NotAListError:
        # an HLS stream saved to a file, with its pieces beside it
        expanding.groups.append(ListItem(uri=path))
        return
    except (OSError, ValueError) as e:
        _log.error(f"Failed to read list {path}: {e}")
        expanding.failed.append((str(path), str(e)))
        return

    _add_read_list(
        read,
        path.stem,
        ListSource(kind=ListSourceKind.FILE, location=path),
        str(path),
        expanding,
    )


def _expand_web_list(url: str, read_web, expanding) -> None:
    try:
        read = read_web(url)
    except ReadingStopped:
        # nothing more read: whoever stopped it lets go of what was
        raise
    except Exception as e:
        _log.error(f"Failed to read list {url}: {e}")
        expanding.failed.append((url, str(e)))
        return

    if isinstance(read, ListInput) and read.source is not None:
        keep_read(read.source, read.items)

    expanding.groups.append(read)


def _expand_list_url(url: str, fetch, expanding) -> None:
    try:
        read = _fetched_list(url, fetch, expanding.progress)
    except ReadingEnough:
        # asked to end before it was downloaded: nothing of it to keep
        return
    except ReadingStopped:
        raise
    except (NoListThereError, NotAListError):
        # an HLS stream, or a page that is not a list at all: played as a
        # video, which says for itself what is wrong with it if anything is
        expanding.groups.append(ListItem(uri=url))
        return
    except Exception as e:
        _log.error(f"Failed to read list {url}: {e}")
        expanding.failed.append((url, str(e)))
        return

    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).stem or parsed.netloc

    _add_read_list(
        read,
        name,
        ListSource(kind=ListSourceKind.URL, location=url),
        url,
        expanding,
    )


def _add_read_list(read: ReadList, name, source, where, expanding) -> None:
    if not read.items:
        expanding.failed.append((where, "nothing on the list"))
        return

    # a link's, for its list to be there at once the next time the
    # playlist opens, before it is read again
    keep_read(source, read.items)

    expanding.groups.append(
        ListInput(name=read.name or name, items=read.items, source=source)
    )


def plan_cells(groups: Sequence[Group], mode: AddMode) -> list[Group]:
    """What each cell plays, the groups put into cells the way asked for."""

    if mode == AddMode.ONE_CELL and len(groups) > 1:
        return [ListInput(name=_joint_name(groups), items=tuple(items_of(groups)))]

    if mode == AddMode.CELL_PER_FILE:
        return list(items_of(groups))

    return list(groups)


def count_cells(groups: Sequence[Group], mode: AddMode) -> int:
    """How many cells plan_cells puts the groups into, without putting them
    into any."""

    if mode == AddMode.ONE_CELL:
        return min(len(groups), 1)

    if mode == AddMode.CELL_PER_FILE:
        return sum(
            len(group.items) if isinstance(group, ListInput) else 1 for group in groups
        )

    return len(groups)


def choices_for(groups: Sequence[Group]) -> list[AddMode]:
    """The ways of putting the groups into cells that come out different,
    to offer where the viewer is asked; one way or none is no question."""

    choices = [AddMode.CELL_EACH]

    if len(groups) > 1:
        choices.append(AddMode.ONE_CELL)

    if any(isinstance(group, ListInput) and len(group.items) > 1 for group in groups):
        choices.append(AddMode.CELL_PER_FILE)

    return choices


def items_of(groups: Iterable[Group]) -> Iterable[ListItem]:
    """The things to play in the groups, those on the lists one by one."""

    for group in groups:
        if isinstance(group, ListInput):
            yield from group.items
        else:
            yield group


def _joint_name(groups: Sequence[Group]) -> str:
    """The name of a list made of several things: the folder the first of
    them is in, which is where they were most likely picked from."""

    first = groups[0]

    if isinstance(first, ListInput):
        return first.name

    if isinstance(first.uri, Path):
        return first.uri.parent.name or str(first.uri.parent)

    return urllib.parse.urlparse(first.uri).netloc or first.uri


def recent_uris(groups: Iterable[Group]) -> list[Path | str]:
    """What to remember the groups by in the recent list: a list by where
    it was read from, for it to be read again."""

    uris = []

    for group in groups:
        if isinstance(group, ListInput):
            if group.source is not None:
                uris.append(group.source.location)
        else:
            uris.append(group.uri)

    return uris
