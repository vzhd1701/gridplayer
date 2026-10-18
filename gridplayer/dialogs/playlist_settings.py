"""The Playlist window: the playlist's own settings, those of the videos
added to it from now on, and what it holds, its bookmarks and its lists.

The settings wait for OK. The bookmarks and the lists change as they go, as
they always have, and Cancel puts them back.
"""

from collections.abc import Callable

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from gridplayer.dialogs.messagebox import QCustomMessageBox
from gridplayer.dialogs.paged_dialog import PagedDialog
from gridplayer.models.grid_state import GridState
from gridplayer.models.settings_draft import SettingsMode, SetValue
from gridplayer.params.settings_bindings import (
    GRID_STATE_ATTR,
    PLAYLIST_ATTRS,
    VIDEO_DEFAULT_ATTRS,
)
from gridplayer.params.settings_fields.kinds import Page
from gridplayer.params.settings_fields.registry import FIELDS
from gridplayer.params.settings_pages import PLAYLIST, VIDEO
from gridplayer.playlist_settings import SAVE_ALL_KEY, grid_values_from_state
from gridplayer.settings import Settings
from gridplayer.utils.qt import translate
from gridplayer.widgets.settings_form import SettingsForm

SHARING_KEY = "playlist/bookmarks_shared"

# how a video added from now on starts, which means nothing to one open
NOT_FOR_VIDEOS_HERE = frozenset({"video_defaults/initial_state"})


class PlaylistSettingsDialog(PagedDialog):
    def __init__(
        self,
        overrides: dict,
        grid_state: GridState,
        parent=None,
        *,
        parts: dict[str, Callable[[QWidget], QWidget]] | None = None,
        page: str = "playlist",
        has_videos: bool = False,
    ):
        """The playlist's own settings, and the grid as it is. parts make
        the pages of what the playlist holds, "bookmarks" and "lists", each
        given the window: a page with cancel() for Cancel, and close_down()
        as the window closes. has_videos: whether there are videos in the
        grid that a change for new videos could be made to as well."""

        super().__init__(parent)

        self.setWindowTitle(translate("SettingsDialog", "Playlist"))

        self._has_videos = has_videos
        # the pages of what the playlist holds, once made, by their id
        self._parts: dict[str, QWidget] = {}
        # whether the videos already here are to be changed too, as asked
        self.is_for_all_videos = False

        body = self.build_index()

        root = QVBoxLayout(self)
        root.addLayout(body, 1)
        root.addWidget(self.buttonBox)

        # a reset goes back to the global settings
        self._playlist_form = SettingsForm(PLAYLIST.items, reset_to=Settings().get)
        self._video_form = SettingsForm(VIDEO.items, reset_to=Settings().get)

        self._build_pages(parts or {})

        self.connect_pages()

        self._load(overrides, grid_state)

        # what the playlist kept as it opened, to tell it was let go of
        self._was_keeping_all = self._is_keeping_all()
        self._playlist_form.values_changed.connect(self._follow_playlist)
        self._follow_playlist()

        self.show_page(page)
        self.fit_to_screen()

    def _build_pages(self, parts):
        if parts:
            self.add_heading(translate("SettingsDialog", "Settings"))

        # what it says hangs on the playlist's own switches, see _follow_playlist
        self.add_form_page(PLAYLIST, self._playlist_form, "")
        self.add_form_page(
            VIDEO,
            self._video_form,
            translate(
                "SettingsDialog",
                "For videos added from now on. Videos already here keep their own.",
            ),
        )

        if not parts:
            return

        self.add_heading(translate("SettingsDialog", "In this playlist"))

        if "bookmarks" in parts:
            self.add_later_page(
                Page(
                    "bookmarks",
                    translate("SettingsDialog", "Bookmarks"),
                    icon="page-bookmarks",
                ),
                lambda: self._made("bookmarks", parts["bookmarks"]),
            )
        if "lists" in parts:
            self.add_later_page(
                Page("lists", translate("SettingsDialog", "Lists"), icon="page-lists"),
                lambda: self._made("lists", parts["lists"]),
            )

    def _made(self, part_id, make) -> QWidget:
        part = make(self)
        self._parts[part_id] = part

        if part_id == "bookmarks":
            part.sharing_asked.connect(self._show_sharing)
            self._push_sharing()

        return part

    def part(self, part_id) -> QWidget | None:
        """The page of what the playlist holds, if made by now."""

        return self._parts.get(part_id)

    def reset_tooltip(self) -> str:
        return translate(
            "SettingsDialog", "Put the settings on this page back to your defaults"
        )

    def reset_info(self) -> str:
        return translate(
            "SettingsDialog",
            "They go back to your defaults. Nothing is saved until you press OK.",
        )

    # the settings

    def _load(self, overrides: dict, grid_state: GridState):
        playlist_values = {
            key: overrides.get(key, Settings().get(key)) for key in PLAYLIST_ATTRS
        }
        playlist_values.update(grid_values_from_state(grid_state))
        video_values = {
            key: overrides.get(key, Settings().get(key)) for key in VIDEO_DEFAULT_ATTRS
        }

        playlist_over = overrides.keys() & playlist_values.keys()
        video_over = overrides.keys() & video_values.keys()

        self._playlist_form.set_values(playlist_values, playlist_over)
        self._video_form.set_values(video_values, video_over)

        # as they were, to tell what was changed for new videos
        self._videos_before = self._video_form.saved_values()

    def _is_keeping_all(self) -> bool:
        return self._playlist_form.is_enabled(SAVE_ALL_KEY) and bool(
            self._playlist_form.value(SAVE_ALL_KEY)
        )

    def _follow_playlist(self):
        """What hangs on the playlist's own switches, as they are flipped:
        what is marked as changed, what the page says, and the sharing the
        bookmarks page says is to come."""

        is_all = self._is_keeping_all()

        # every value is the playlist's own then: marked, the ones other
        # than the defaults, for the marks to still say something
        mode = SettingsMode.DEFAULTS if is_all else SettingsMode.OVERRIDES
        for form in (self._playlist_form, self._video_form):
            form.set_mode(mode)

        if is_all:
            note = translate(
                "SettingsDialog",
                "This playlist keeps all its settings, so it plays the same"
                " anywhere. Your defaults don't change it.",
            )
        else:
            note = translate(
                "SettingsDialog",
                "Changes here are for this playlist only. The rest follow your"
                " defaults.",
            )
        self.notes["playlist"].setText(note)

        self._push_sharing()
        self.update_reset_page()

    def _push_sharing(self):
        """The sharing the switch is at, to the bookmarks page, if made."""

        bookmarks = self._parts.get("bookmarks")
        if bookmarks is not None:
            bookmarks.set_sharing_to_come(self._playlist_form.value(SHARING_KEY))

    def _show_sharing(self):
        """The switch the bookmarks' sharing is set with, pointed out."""

        self.show_page_of(SHARING_KEY)
        self._playlist_form.point_to(SHARING_KEY)

    def result_overrides(self) -> dict:
        if self._is_keeping_all():
            result = {}
            for form in (self._playlist_form, self._video_form):
                result.update(form.saved_values())
            return result

        # read off the grid as it is: the playlist's own only once edited
        grid_own = self._playlist_form.overridden_keys() & self._grid_in_use()

        result = {}
        for form in (self._playlist_form, self._video_form):
            for key, change in form.persistence_result().items():
                if key in GRID_STATE_ATTR and key not in grid_own:
                    continue
                if isinstance(change, SetValue):
                    result[key] = change.value

        if self._was_keeping_all:
            # let go of: only what differs from the defaults stays its own
            result = {
                key: value
                for key, value in result.items()
                if value != Settings().get(key)
            }

        return result

    def _grid_in_use(self) -> set[str]:
        """The grid's settings its mode has: the rest leave it as it is."""

        return {key for key in GRID_STATE_ATTR if self._playlist_form.is_enabled(key)}

    def result_grid_state(self, current: GridState) -> GridState:
        values = self._playlist_form.values()
        update = {GRID_STATE_ATTR[key]: values[key] for key in self._grid_in_use()}
        return current.model_copy(update=update)

    def video_changes(self) -> dict:
        """What was changed for new videos, by key: what the videos already
        here can be given too."""

        now = self._video_form.saved_values()

        return {
            key: value
            for key, value in now.items()
            if key not in NOT_FOR_VIDEOS_HERE and value != self._videos_before[key]
        }

    # closing

    def accept(self):
        changes = self.video_changes()

        if changes and self._has_videos:
            answer = self._ask_for_videos_here(changes)
            if answer is None:
                return
            self.is_for_all_videos = answer

        super().accept()

    def _ask_for_videos_here(self, changes) -> bool | None:
        """Whether the videos already here are changed too, or None to go
        back to the window."""

        names = ", ".join(FIELDS[key].label for key in changes)

        box = QCustomMessageBox(
            QMessageBox.Question,
            translate("SettingsDialog", "New Videos"),
            translate("SettingsDialog", "Change the videos already here too?"),
            parent=self,
        )
        box.setInformativeText(
            translate(
                "SettingsDialog",
                "Changed: {SETTINGS}. New videos get this either way.",
            ).format(SETTINGS=names)
        )
        all_button = box.addButton(
            translate("SettingsDialog", "All videos"), QMessageBox.AcceptRole
        )
        new_button = box.addButton(
            translate("SettingsDialog", "Only new"), QMessageBox.RejectRole
        )
        # Cancel, and Escape, back to the window
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(all_button)

        box.exec_()

        clicked = box.clickedButton()
        box.deleteLater()

        if clicked is all_button:
            return True
        if clicked is new_button:
            return False
        return None

    def reject(self):
        for part in self._parts.values():
            part.cancel()

        super().reject()

    def done(self, result):
        for part in self._parts.values():
            part.close_down()
        self._parts = {}

        super().done(result)
