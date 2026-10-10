"""How often a linked list is read again from its source: as the playlist
says, or as the list itself does where it was given a way of its own."""

from gridplayer.params.static import ListSourceKind, ListUpdate

# how old what was read gets before it is read again
INTERVALS_S = {
    ListUpdate.FIVE_MINUTES: 5 * 60,
    ListUpdate.FIFTEEN_MINUTES: 15 * 60,
    ListUpdate.HOURLY: 3600,
    ListUpdate.SIX_HOURS: 6 * 3600,
    ListUpdate.DAILY: 24 * 3600,
}

# a list from a link read more often than this is warned of: a site may turn
# it away, and each time downloads the whole of it
SHORT_UPDATE_S = 15 * 60


def update_of(media_list, playlist_update: ListUpdate) -> ListUpdate:
    """The way the list is read again: its own, or else the playlist's."""

    return playlist_update if media_list.update is None else media_list.update


def interval_of(media_list, playlist_update: ListUpdate) -> int | None:
    """How old what was read gets before it is read again, in seconds; None
    for not by how old it is: as the playlist is loaded, or by hand."""

    update = update_of(media_list, playlist_update)

    if update == ListUpdate.CUSTOM:
        return media_list.update_every_s

    return INTERVALS_S.get(update)


def is_due(media_list, has_copy: bool, is_loading: bool, playlist_update, now) -> bool:
    """Whether a linked list is read again from its source now: as the
    playlist is loaded, or while it is open.

    As it is loaded, one with no copy kept to show is read whatever it
    says, and so is one from a file on the disk: next to nothing to read,
    and nothing kept of it.
    """

    if is_loading and (not has_copy or media_list.source.kind != ListSourceKind.URL):
        return True

    update = update_of(media_list, playlist_update)

    if update == ListUpdate.ON_LOAD:
        return is_loading

    interval = interval_of(media_list, playlist_update)

    # only by Refresh
    if interval is None:
        return False

    return media_list.read_at is None or now - media_list.read_at >= interval


def next_update_at(media_list, playlist_update: ListUpdate) -> float | None:
    """When it is read again while the playlist is open, in seconds since
    the epoch; None for not while it is open."""

    interval = interval_of(media_list, playlist_update)

    if interval is None or media_list.read_at is None:
        return None

    return media_list.read_at + interval


def is_short(interval_s: int | None, source) -> bool:
    """Whether reading a list that often is warned of: one from a link, a
    site being asked."""

    return (
        interval_s is not None
        and interval_s < SHORT_UPDATE_S
        and source is not None
        and source.kind == ListSourceKind.URL
    )
