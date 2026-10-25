from dataclasses import dataclass

from PyQt5.QtCore import pyqtSignal

from gridplayer.models.grid_state import GridCell
from gridplayer.models.media_list import MediaList
from gridplayer.models.video import Video
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.qt import count_txt, translate
from gridplayer.utils.time_txt import timed_title

# how many closes Reopen Closed Video can take back
KEPT_CLOSES = 10


@dataclass(frozen=True)
class ClosedVideo:
    """A video as it was closed: as a playlist saved then would have it, the
    list it played from, and where it was in the grid (see
    GridManager.place_of)."""

    video: Video
    media_list: MediaList | None
    place: GridCell | int | None


class ClosedVideosManager(ManagerBase):
    """The videos closed, for Reopen Last Closed to open again where they
    were, as a browser does its closed tabs: the last close first, and the
    videos closed at once, by a grid made smaller say, back together. The
    Recently Closed menu lists the closes, any of them to be reopened.

    Kept are the videos closed by hand, from the menu or Edit Grid, those
    closed at their end, and those a dropped one took the place of; not
    those closed with the playlist, which forgets them all, nor a cell
    whose list could not be read. Grid undo has nothing of it: undone, a
    close would load a video again, and redone, close one.
    """

    changed = pyqtSignal()
    warning = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._closes: list[tuple[ClosedVideo, ...]] = []

    @property
    def commands(self):
        return {
            "remember_closed": self.remember,
            "reopen_closed_video": self.reopen,
            "is_any_video_closed": lambda: bool(self._closes),
            "menu_generator_recently_closed": self.menu_generator,
        }

    def remember(self, blocks):
        """Videos about to close, as one close."""

        closed = tuple(c for c in map(self._closed, blocks) if c is not None)
        if not closed:
            return

        self._closes.append(closed)
        del self._closes[:-KEPT_CLOSES]
        self.changed.emit()

    def forget(self):
        if not self._closes:
            return

        self._closes.clear()
        self.changed.emit()

    def reopen(self, index: int = 0):
        """A close taken back: the last one, or one before it."""

        if index >= len(self._closes):
            return

        closed = self._closes[-1 - index]

        room = self._ctx.commands.grid_free_capacity()
        if room is not None and room < len(closed):
            self.warning.emit(
                translate("Warning", "No room to reopen. Make the grid bigger.")
            )
            return

        del self._closes[-1 - index]
        self._ctx.commands.put_back_videos(
            [self._reopened(c) for c in closed], [c.place for c in closed]
        )
        self.changed.emit()

    def menu_generator(self):
        """The closes, the last first: the video's name, and where it would
        play from beside it; those closed together as one."""

        return [
            {
                "title": _menu_title(closed),
                "icon": "empty",
                "func": ("reopen_closed_video", index),
            }
            for index, closed in enumerate(reversed(self._closes))
        ]

    def _closed(self, block) -> ClosedVideo | None:
        video = block.video_params
        # still waiting for its list to be read: nothing to open again
        if video is None or video.read_as_list:
            return None

        return ClosedVideo(
            video=video.model_copy(deep=True),
            media_list=self._ctx.lists.get(video.list_id),
            place=self._ctx.commands.grid_place_of(block.video_id),
        )

    def _reopened(self, closed: ClosedVideo) -> Video:
        video = closed.video

        # the list it played from, let go of by a save since: kept again
        if closed.media_list is not None and self._ctx.lists.get(video.list_id) is None:
            video.list_id = self._ctx.lists.add(closed.media_list).id

        return video


def _menu_title(closed: tuple[ClosedVideo, ...]) -> str:
    video = closed[0].video
    name = video.title or video.uri_name

    if len(closed) > 1:
        name = translate("Actions", "{NAME} and {COUNT} more").format(
            NAME=name, COUNT=count_txt(len(closed) - 1)
        )
    # where it plays from; none for a stream played live, which has no
    # place in it to go back to, nor for one barely begun
    elif video.current_position >= 1000:
        return timed_title(name, video.current_position, 0)

    return name.replace("&", "&&")
