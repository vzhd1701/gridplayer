from pathlib import Path

from PyQt5.QtCore import QEvent, pyqtSignal
from PyQt5.QtGui import QCursor

from gridplayer.dialogs.crop import SetCropDialog
from gridplayer.models.stream import (
    STREAM_QUALITY_AUDIO_ONLY,
    STREAM_QUALITY_AUTO,
    STREAM_QUALITY_BEST,
)
from gridplayer.params.static import AudioTrackMode
from gridplayer.player.managers.base import ManagerBase
from gridplayer.utils.qt import is_modal_open, translate
from gridplayer.utils.track_language import language_name
from gridplayer.vlc_player.static import DISABLED_TRACK
from gridplayer.widgets.video_block import VideoBlock

# A video that is loading or showing a network error is not playable, and
# these are the commands whose whole point is to be reachable from that
# state. Choosing audio is among them because choosing it is what started
# the reload that the next choice would otherwise land in.
LOADING_COMMANDS = frozenset(
    {
        "switch_stream_quality",
        "reload",
        "close",
        "set_network_retry_mode",
        "network_retry_times",
        "get_network_retry_times",
        "set_audio_track",
        "set_audio_language",
        "apply_audio_preference",
        "audio_languages_dialog",
        "get_audio_languages",
    }
)

# the mouse fires these continuously, so they are dropped all through a
# load as a matter of course and saying so only buries the drops that mean
# something
QUIETLY_DROPPED_COMMANDS = frozenset({"show_overlay"})


class ActiveBlockManager(ManagerBase):
    active_block_change = pyqtSignal(VideoBlock)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._ctx.active_block = None

    @property
    def event_map(self):
        return {
            QEvent.MouseMove: self.update_active_under_mouse,
            QEvent.MouseButtonPress: self.update_active_under_mouse,
            QEvent.MouseButtonRelease: self.update_active_under_mouse,
            QEvent.NonClientAreaMouseMove: self.update_active_reset,
            QEvent.NonClientAreaMouseButtonPress: self.update_active_reset,
            QEvent.DragEnter: self.update_active_from_drag,
            QEvent.DragMove: self.update_active_from_drag,
            QEvent.Drop: self.update_active_from_drag,
        }

    @property
    def commands(self):
        return {
            "active": self.cmd_active,
            "crop_dialog": self.cmd_crop_dialog,
            "is_active_runtime_param_set_to": self.is_active_runtime_param_set_to,
            "is_active_param_set_to": self.is_active_param_set_to,
            "is_active_initialized": self.is_active_initialized,
            "is_active_playable": self.is_active_playable,
            "is_active_seekable": self.is_active_seekable,
            "is_active_live": self.is_active_live,
            "is_active_multistream": self.is_active_multistream,
            "is_active_audio_language": self.is_active_audio_language,
            "is_active_audio_track": self.is_active_audio_track,
            "is_active_local_file": self.is_active_local_file,
            "is_active_has_audio": self.is_active_has_audio,
            "is_active_has_video": self.is_active_has_video,
            "menu_generator_stream_quality": self.menu_generator_stream_quality,
            "menu_generator_video_track": self.menu_generator_video_track,
            "menu_generator_audio_track": self.menu_generator_audio_track,
            "next_active": self.next_active,
            "previous_active": self.previous_active,
            "update_active_under_mouse": self.update_active_under_mouse,
            "get_video_block_under_mouse": self.get_video_block_under_mouse,
            "get_video_block_at": self.get_video_block_at,
        }

    @property
    def is_no_active_block(self):
        return self._ctx.active_block is None

    def cmd_active(self, command, *args):
        if self.is_no_active_block:
            return None

        if not self.is_active_playable() and command not in LOADING_COMMANDS:
            if command not in QUIETLY_DROPPED_COMMANDS:
                self._log.debug(f"Dropped {command}, active video is not playable")

            return None

        return getattr(self._ctx.active_block, command)(*args)

    def cmd_crop_dialog(self):
        if self.is_no_active_block or not self.is_active_has_video():
            return

        dialog = SetCropDialog.for_video_block(
            self._ctx.active_block, parent=self.parent()
        )

        dialog.exec_()

    def is_active_initialized(self):
        if self.is_no_active_block:
            return False

        return self._ctx.active_block.is_video_initialized

    def is_active_playable(self):
        if self.is_no_active_block:
            return False

        return self._ctx.active_block.is_playable

    def is_active_param_set_to(self, param_name, param_value):
        if self.is_no_active_block:
            return False

        active_video_param = getattr(self._ctx.active_block.video_params, param_name)

        return active_video_param == param_value

    def is_active_runtime_param_set_to(self, param_name, param_value):
        if self.is_no_active_block:
            return False

        active_video_param = getattr(self._ctx.active_block, param_name)

        return active_video_param == param_value

    def is_active_seekable(self):
        if not self.is_active_initialized():
            return False

        return not self._ctx.active_block.is_live

    def is_active_live(self):
        if not self.is_active_initialized():
            return False

        return self._ctx.active_block.is_live

    def is_active_local_file(self):
        if not self.is_active_playable():
            return False

        return isinstance(self._ctx.active_block.video_params.uri, Path)

    def is_active_has_audio(self):
        if not self.is_active_initialized():
            return False

        return bool(self._ctx.active_block.audio_tracks)

    def is_active_has_video(self):
        if not self.is_active_initialized():
            return False

        return bool(self._ctx.active_block.video_tracks)

    def is_active_multistream(self):
        if self.is_no_active_block:
            return False

        return len(self._ctx.active_block.streams) > 1

    def is_active_audio_language(self, language):
        """Ticked only where the viewer named this language themselves.

        Following a preference that happens to land here is the preference
        being ticked, not the language.
        """

        if self.is_no_active_block or not self._is_active_track_explicit:
            return False

        return self._ctx.active_block.audio_language == language

    def is_active_audio_track(self, track_id):
        if self.is_no_active_block or not self._is_active_track_explicit:
            return False

        return self._ctx.active_block.video_params.audio_track_id == track_id

    @property
    def _is_active_track_explicit(self) -> bool:
        mode = self._ctx.active_block.video_params.audio_track_mode

        return mode is AudioTrackMode.EXPLICIT

    def menu_generator_stream_quality(self):
        if self.is_no_active_block:
            return []

        # a dubbed video is the same ladder over again in every language,
        # and only one of them is the one being played
        ladder = self._ctx.active_block.stream_ladder

        playing = self._ctx.active_block.stream_quality_playing

        # a ladder is stored worst first, and a menu of it reads the other way
        video_rungs = [
            _stream_menu_item(quality, is_playing=quality == playing)
            for quality in reversed(list(ladder.video_streams))
        ]
        audio_rungs = [
            _stream_menu_item(quality, is_playing=quality == playing)
            for quality in reversed(list(ladder.audio_only_streams))
        ]

        return _separated(
            self._standing_quality_items(
                has_video=bool(video_rungs), has_audio=bool(audio_rungs)
            ),
            video_rungs,
            audio_rungs,
        )

    def _standing_quality_items(self, has_video: bool, has_audio: bool) -> list:
        """The choices that name what to pick rather than which rung.

        One of these stays chosen from one reload to the next, so it has
        to be on the menu even where this ladder cannot honour it. A
        choice left off the menu while it is still in force is a menu
        that looks like nothing is chosen at all, and the pane then has
        nowhere left to say why it is playing what it is playing.

        Where there are no video rungs the three of them all come to the
        same rung, so only the one that was asked for is worth offering.
        """

        wanted = (
            (STREAM_QUALITY_AUTO, translate("Actions", "Auto"), has_video),
            (STREAM_QUALITY_BEST, translate("Actions", "Best"), has_video),
            (STREAM_QUALITY_AUDIO_ONLY, translate("Actions", "Audio Only"), has_audio),
        )

        items = []

        for quality, title, is_on_offer in wanted:
            if not (is_on_offer or self._is_quality_chosen(quality)):
                continue

            items.append(self._standing_quality_menu_item(quality, title))

            # the wait belongs with the switch that makes it matter, and
            # there is nothing for a pane to adapt to without video rungs
            if quality == STREAM_QUALITY_AUTO and has_video:
                items.append(_quality_adapt_delay_menu_item())

        return items

    def _standing_quality_menu_item(self, quality: str, title: str):
        """A rung asked for by what it is rather than by name.

        The name the choice lands on is the one thing it does not say, and
        that name is the whole list underneath, so the menu is the only
        place the pane ever admits which rung it settled on. That goes
        double for a choice this ladder could not honour, where the rung
        named here is the only sign that it could not.
        """

        playing = self._ctx.active_block.stream_quality_playing

        if self._is_quality_chosen(quality) and playing:
            title = f"{title} ({playing})"

        return {
            "title": title,
            "icon": "empty",
            "func": ("active", "switch_stream_quality", quality),
            "check_if": ("is_active_param_set_to", "stream_quality", quality),
            "show_if": "is_active_multistream",
        }

    def _is_quality_chosen(self, quality: str) -> bool:
        return self._ctx.active_block.video_params.stream_quality == quality

    def menu_generator_video_track(self):
        if self.is_no_active_block or not self._ctx.active_block.video_tracks:
            return {}

        menu = [
            {
                "title": translate("Actions", "Disable Video"),
                "icon": "empty",
                "func": ("active", "set_video_track", -1),
                "check_if": ("is_active_param_set_to", "video_track_id", -1),
                "show_if": "is_active_initialized",
            }
        ]

        menu += [
            {
                "title": track.info,
                "icon": "empty",
                "func": ("active", "set_video_track", track_id),
                "check_if": ("is_active_param_set_to", "video_track_id", track_id),
                "show_if": "is_active_initialized",
            }
            for track_id, track in self._ctx.active_block.video_tracks.items()
        ]

        return menu

    def menu_generator_audio_track(self):
        """Every way this video's sound can be chosen, in one list.

        Which of them is on offer is a matter of where the choice can be
        made: a site that dubs hands VLC one track per language and the
        choice is made before it, where a file hands over all of them at
        once and the choice is made inside it.
        """

        if self.is_no_active_block or not self._ctx.active_block.audio_tracks:
            return {}

        return [
            self._preferred_audio_track_menu_item(),
            _audio_languages_menu_item(),
            {
                "title": translate("Actions", "Disable Audio"),
                "icon": "empty",
                "func": ("active", "set_audio_track", DISABLED_TRACK),
                "check_if": (
                    "is_active_param_set_to",
                    "audio_track_mode",
                    AudioTrackMode.DISABLED,
                ),
                "show_if": "is_active_initialized",
            },
            "---",
            *self._audio_choice_menu_items(),
        ]

    @property
    def _preferred_audio_name(self) -> str | None:
        """What following the preference would give, spelled out.

        A language says it for a video dubbed into several, where the
        whole ladder is reloaded to change it. A file is picked from by
        track, and one language can cover several of those, so there the
        track is named the way the list below names it.
        """

        block = self._ctx.active_block

        if len(block.audio_language_options) > 1:
            language = block.preferred_audio_language

            return language_name(language) or language

        track = self._preferred_audio_track

        if track is None:
            return None

        name = language_name(track.language) or track.language

        return _join_track_name(name, _track_description(track, name)) or None

    @property
    def _preferred_audio_track(self):
        """The track the preference settles on, out of the ones a file has.

        A file whose tracks answer to none of the languages asked for is
        left to open with its own choice, and while the preference is what
        is being followed, that choice is the answer it gave.
        """

        block = self._ctx.active_block

        track = block.audio_tracks.get(block.preferred_audio_track_id)

        if track is None and self._is_active_track_preferred:
            track = block.audio_tracks.get(block.video_params.audio_track_id)

        return track

    @property
    def _is_active_track_preferred(self) -> bool:
        mode = self._ctx.active_block.video_params.audio_track_mode

        return mode is AudioTrackMode.PREFERRED

    def _audio_choice_menu_items(self):
        languages = self._ctx.active_block.audio_language_options

        if len(languages) > 1:
            return [
                {
                    "title": language_name(language) or language,
                    "icon": "empty",
                    "func": ("active", "set_audio_language", language),
                    "check_if": ("is_active_audio_language", language),
                    "show_if": "is_active_initialized",
                }
                for language in languages
            ]

        return [
            {
                "title": _audio_track_title(track),
                "icon": "empty",
                "func": ("active", "set_audio_track", track_id),
                "check_if": ("is_active_audio_track", track_id),
                "show_if": "is_active_initialized",
            }
            for track_id, track in self._ctx.active_block.audio_tracks.items()
        ]

    def _preferred_audio_track_menu_item(self):
        """Going back to the languages asked for, from a track picked by hand.

        Which track that turns out to be is not the viewer's choice, so
        the menu is the only place it is ever spelled out.
        """

        title = translate("Actions", "Preferred")

        name = self._preferred_audio_name

        if name:
            title = f"{title} ({name})"

        return {
            "title": title,
            "icon": "empty",
            "func": ("active", "apply_audio_preference"),
            "check_if": (
                "is_active_param_set_to",
                "audio_track_mode",
                AudioTrackMode.PREFERRED,
            ),
            "show_if": "is_active_initialized",
        }

    def update_active_under_mouse(self):
        if is_modal_open():
            return

        self._update_active_block(self.get_video_block_under_mouse())
        self.cmd_active("show_overlay")

    def update_active_from_drag(self, event, event_object):
        # QCursor.pos() is stale during X11 DND from another process;
        # QDragMoveEvent.pos() is filled from XdndPosition and is current.
        if is_modal_open():
            return

        if not hasattr(event_object, "mapToGlobal"):
            return

        global_pos = event_object.mapToGlobal(event.pos())
        self._update_active_block(self.get_video_block_at(global_pos))
        self.cmd_active("show_overlay")

    def update_active_reset(self):
        if is_modal_open():
            return

        self._update_active_block(None)

    def _ordered_blocks(self):
        return self._ctx.video_blocks.blocks_for_ids(self._ctx.commands.layout_order())

    def next_active(self):
        blocks = self._ordered_blocks()
        if not blocks:
            return
        if self.is_no_active_block:
            next_active = blocks[0]
        else:
            next_block_index = (blocks.index(self._ctx.active_block) + 1) % len(blocks)
            next_active = blocks[next_block_index]

        self._update_active_block(next_active)
        self.cmd_active("show_overlay")

    def previous_active(self):
        blocks = self._ordered_blocks()
        if not blocks:
            return
        if self.is_no_active_block:
            next_active = blocks[-1]
        else:
            next_block_index = (blocks.index(self._ctx.active_block) - 1) % len(blocks)
            next_active = blocks[next_block_index]

        self._update_active_block(next_active)
        self.cmd_active("show_overlay")

    def _update_active_block(self, new_active_block):
        old_active_block = self._ctx.active_block
        self._ctx.active_block = new_active_block

        if self._ctx.active_block is not None:
            self._ctx.active_block.is_active = True

        if self._ctx.active_block != old_active_block:
            if old_active_block is not None:
                old_active_block.is_active = False

            self.active_block_change.emit(self._ctx.active_block)

    def get_video_block_under_mouse(self):
        return self.get_video_block_at(QCursor.pos())

    def get_video_block_at(self, global_pos):
        visible_blocks_under_pos = (
            v
            for v in self._ctx.video_blocks
            if v.isVisible() and v.rect().contains(v.mapFromGlobal(global_pos))
        )

        return next(visible_blocks_under_pos, None)


def _audio_languages_menu_item():
    """The preference itself, right under the entry that follows it.

    It stays put whatever is playing: a track picked by hand is not a
    reason to hide what going back to the preference would give, and it
    is the only place the list can be read at all without the settings.
    """

    return {
        "title": "{}: %v".format(translate("Actions", "Languages")),
        "icon": "empty",
        "func": ("active", "audio_languages_dialog"),
        "value_getter": ("active", "get_audio_languages"),
        "show_if": "is_active_initialized",
    }


def _audio_track_title(track) -> str:
    """Name a track by its language and by what the container called it.

    libVLC passes on whatever was written into the file, which is a three
    letter code more often than anything a viewer would recognise. Several
    tracks in one language is ordinary -- rival dubs, a commentary, the
    original kept alongside them -- and where that happens the name the
    container gave a track is the only thing telling them apart.
    """

    name = language_name(track.language) or track.language

    described = _track_description(track, name)

    titled = _join_track_name(name, described)

    return f"{titled}, {track.codec_info}" if titled else track.codec_info


def _join_track_name(name: str | None, described: str | None) -> str:
    """Language first, then what the container called the track."""

    return " \u2014 ".join(part for part in (name, described) if part)


def _track_description(track, language_name_: str | None) -> str | None:
    """What the container called this track, when that adds anything.

    Plenty of files just repeat the language there, which is already the
    first thing the entry says.
    """

    description = (track.description or "").strip()

    if not description:
        return None

    said_already = {
        value.casefold() for value in (language_name_, track.language) if value
    }

    return None if description.casefold() in said_already else description


def _separated(*groups) -> list:
    """The groups that have anything in them, with a line between them."""

    menu = []

    for group in groups:
        if not group:
            continue

        if menu:
            menu.append("---")

        menu += group

    return menu


def _quality_adapt_delay_menu_item():
    """Setting the wait belongs next to the switch that makes it matter."""

    return {
        "title": "{}: %v".format(translate("Actions", "Adapt after")),
        "icon": "empty",
        "func": ("active", "quality_adapt_delay"),
        "value_getter": ("active", "get_quality_adapt_delay"),
        "show_if": (
            "is_active_param_set_to",
            "stream_quality",
            STREAM_QUALITY_AUTO,
        ),
    }


def _stream_menu_item(quality: str, is_playing: bool = False):
    """One rung of the ladder, marked where it is the one on screen.

    Being chosen and being played are not the same thing here, and the
    menu shows them apart: the choice is the row with the background
    behind it, and this is the row it came to. A standing choice names
    no rung, so without this the list has nothing to say about which of
    them answered it.
    """

    return {
        "title": quality,
        "icon": "play" if is_playing else "empty",
        "func": ("active", "switch_stream_quality", quality),
        "check_if": ("is_active_param_set_to", "stream_quality", quality),
        "show_if": "is_active_multistream",
    }
