from collections import Counter
from pathlib import Path

from PyQt5.QtCore import QEvent, pyqtSignal
from PyQt5.QtGui import QCursor

from gridplayer.dialogs.crop import SetCropDialog
from gridplayer.models.audio_device import resolve_device_id
from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioDisabled,
    AudioExternal,
    AudioLanguage,
    AudioPreferred,
    AudioTrackId,
)
from gridplayer.models.stream import (
    STREAM_QUALITY_AUDIO_ONLY,
    STREAM_QUALITY_AUTO,
    STREAM_QUALITY_BEST,
)
from gridplayer.models.subtitle_selection import (
    SubtitleDefault,
    SubtitleDisabled,
    SubtitleExternal,
    SubtitleLanguage,
    SubtitlePreferred,
    SubtitleTrackId,
)
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
        "set_audio_device",
        "set_audio_language",
        "apply_audio_preference",
        "apply_audio_default",
        "audio_languages_dialog",
        "get_audio_languages",
        "add_external_audio_dialog",
        "play_external_audio",
        "remove_external_audio",
        "set_external_audio_autodiscover",
        "set_subtitle_track",
        "apply_subtitle_preference",
        "apply_subtitle_default",
        "disable_subtitles",
        "subtitle_languages_dialog",
        "get_subtitle_languages",
        "add_external_subtitles_dialog",
        "show_external_subtitle",
        "remove_external_subtitles",
        "set_external_subtitle_autodiscover",
        "set_subtitle_encoding",
        "subtitle_encoding_dialog",
        "get_subtitle_encoding",
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
            "is_active_audio_device": self.is_active_audio_device,
            "is_active_audio_device_default": self.is_active_audio_device_default,
            "is_active_audio_device_missing": self.is_active_audio_device_missing,
            "is_active_audio_preferred": self.is_active_audio_preferred,
            "is_active_audio_disabled": self.is_active_audio_disabled,
            "is_active_audio_default": self.is_active_audio_default,
            "is_active_local_file": self.is_active_local_file,
            "is_active_has_audio": self.is_active_has_audio,
            "is_active_has_video": self.is_active_has_video,
            "is_active_has_subtitles": self.is_active_has_subtitles,
            "is_active_subtitle_track": self.is_active_subtitle_track,
            "is_active_subtitle_preferred": self.is_active_subtitle_preferred,
            "is_active_subtitle_default": self.is_active_subtitle_default,
            "is_active_subtitle_disabled": self.is_active_subtitle_disabled,
            "menu_generator_stream_quality": self.menu_generator_stream_quality,
            "menu_generator_video_track": self.menu_generator_video_track,
            "menu_generator_audio_track": self.menu_generator_audio_track,
            "menu_generator_audio_device": self.menu_generator_audio_device,
            "menu_generator_subtitle_track": self.menu_generator_subtitle_track,
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

        selection = self._active_audio_selection()

        return isinstance(selection, AudioLanguage) and selection.tag == language

    def is_active_audio_track(self, track_id):
        """Ticked where this track is the one that was named by hand.

        A track out of a file is named by the file, so it answers to that
        instead: the id it happens to have is nobody's choice.
        """

        selection = self._active_audio_selection()

        if isinstance(selection, AudioExternal):
            block = self._ctx.active_block

            if block.external_audio_tracks.get(track_id) != selection.file:
                return False

            return block.external_audio_track_ids.index(track_id) == selection.track

        return isinstance(selection, AudioTrackId) and selection.id == track_id

    def is_active_audio_device(self, device_id) -> bool:
        """Ticked on the device the sound is really going to.

        Which is not always the one that was picked: a choice found again
        by name, after the ids all changed underneath it, belongs to the
        row it landed on rather than the row it was made on.
        """

        block = self._ctx.active_block

        if self.is_no_active_block:
            return False

        chosen = block.video_params.audio_device

        return (
            chosen is not None
            and resolve_device_id(chosen, block.audio_devices) == device_id
        )

    def is_active_audio_device_default(self) -> bool:
        """Ticked where this video never asked for a way out of its own."""

        if self.is_no_active_block:
            return False

        return self._ctx.active_block.video_params.audio_device is None

    def is_active_audio_device_missing(self) -> bool:
        """Whether what this video asked for is not here to be asked for."""

        if self.is_no_active_block:
            return False

        block = self._ctx.active_block

        chosen = block.video_params.audio_device

        return chosen is not None and not resolve_device_id(chosen, block.audio_devices)

    def is_active_audio_preferred(self) -> bool:
        return isinstance(self._active_audio_selection(), AudioPreferred)

    def is_active_audio_default(self) -> bool:
        return isinstance(self._active_audio_selection(), AudioDefault)

    def is_active_audio_disabled(self) -> bool:
        return isinstance(self._active_audio_selection(), AudioDisabled)

    def _active_audio_selection(self):
        if self.is_no_active_block:
            return None

        return self._ctx.active_block.video_params.audio_selection

    def is_active_has_subtitles(self):
        if not self.is_active_initialized():
            return False

        return self._ctx.active_block.has_subtitles

    def is_active_subtitle_track(self, track_id):
        """Ticked where this track is the one that was named by hand.

        A track out of a file answers to that file, and one the viewer
        picked by its language answers to the language: the id it happens
        to have is nobody's choice in either case.
        """

        selection = self._active_subtitle_selection()

        if self.is_no_active_block:
            return False

        block = self._ctx.active_block

        if isinstance(selection, SubtitleExternal):
            if block.external_subtitle_tracks.get(track_id) != selection.file:
                return False

            return block.subtitle_number_in_file(track_id, selection.file) == (
                selection.track
            )

        if isinstance(selection, SubtitleLanguage):
            return block.subtitle_language_key(track_id) == selection.tag

        return isinstance(selection, SubtitleTrackId) and selection.id == track_id

    def is_active_subtitle_preferred(self) -> bool:
        return isinstance(self._active_subtitle_selection(), SubtitlePreferred)

    def is_active_subtitle_default(self) -> bool:
        return isinstance(self._active_subtitle_selection(), SubtitleDefault)

    def is_active_subtitle_disabled(self) -> bool:
        return isinstance(self._active_subtitle_selection(), SubtitleDisabled)

    def _active_subtitle_selection(self):
        if self.is_no_active_block:
            return None

        return self._ctx.active_block.video_params.subtitle_selection

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
            (STREAM_QUALITY_AUTO, translate("Stream Quality", "Auto"), has_video),
            (STREAM_QUALITY_BEST, translate("Stream Quality", "Best"), has_video),
            (
                STREAM_QUALITY_AUDIO_ONLY,
                translate("Stream Quality", "Audio Only"),
                has_audio,
            ),
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
        once and the choice is made inside it. A file kept beside the video
        is a third place again, and one the video itself knows nothing of.
        """

        if self.is_no_active_block:
            return {}

        external = self._external_audio_menu_items()

        if not self._ctx.active_block.audio_tracks:
            # a silent video has nothing to choose between, but what is
            # lying next to it is the whole point of looking
            return external or {}

        return _separated(
            [
                _audio_default_menu_item(),
                self._preferred_audio_track_menu_item(),
                _audio_languages_menu_item(),
                {
                    "title": translate("Audio Track", "Disable Audio"),
                    "icon": "empty",
                    "func": ("active", "set_audio_track", DISABLED_TRACK),
                    "check_if": "is_active_audio_disabled",
                    "show_if": "is_active_initialized",
                },
            ],
            self._audio_choice_menu_items(),
            external,
        )

    def menu_generator_audio_device(self):
        """Every way out of the machine this video's sound could take.

        The machine's own heads the list, which is what a video that was
        never asked is already using. Nothing is offered until the video
        has loaded: the list belongs to the process playing it, and the
        window keeps no VLC of its own to ask.
        """

        if self.is_no_active_block:
            return {}

        devices = self._ctx.active_block.audio_devices

        if not devices:
            return {}

        return _separated(
            [_audio_device_default_menu_item()],
            [
                {
                    "title": device.name or device.id,
                    "icon": "empty",
                    "func": ("active", "set_audio_device", device),
                    "check_if": ("is_active_audio_device", device.id),
                    "show_if": "is_active_has_audio",
                }
                for device in devices
            ],
            self._missing_audio_device_menu_items(),
        )

    def _missing_audio_device_menu_items(self):
        """The device this video was told to use, where it is not here.

        Named rather than quietly dropped. libVLC takes an id that is no
        longer there without a word and then plays the video in silence,
        so a viewer who unplugs a headset has nothing else to go on.
        The sound falls back to the machine's own way out; picking that
        row is how the choice is cleared for good.
        """

        block = self._ctx.active_block

        chosen = block.video_params.audio_device

        if chosen is None or resolve_device_id(chosen, block.audio_devices):
            return []

        return [
            {
                "title": translate("Actions", "{} (not connected)").format(
                    chosen.name or chosen.id
                ),
                "icon": "empty",
                "func": ("active", "set_audio_device", chosen),
                "check_if": "is_active_audio_device_missing",
                "show_if": "is_active_has_audio",
            }
        ]

    def _external_audio_menu_items(self):
        """The audio kept beside this video: what is there, and how to add more.

        A file found next to the video is a name and nothing else until it
        is picked, so these sit below the tracks rather than among them.
        The one already playing is a track by now, and is listed there.

        What can be played and what can be done about it are two different
        lists, and read as two.
        """

        block = self._ctx.active_block

        if not block.is_local_file:
            return []

        files = self._attached_audio_menu_items() + [
            {
                "title": file_path.name,
                "icon": "empty",
                "func": ("active", "play_external_audio", str(file_path)),
                "show_if": "is_active_local_file",
            }
            for file_path in block.offered_audio_files
        ]

        commands = [
            {
                "title": translate("Actions", "Add External Audio..."),
                "icon": "empty",
                "func": ("active", "add_external_audio_dialog"),
                "show_if": "is_active_local_file",
            }
        ]

        if block.video_params.external_audio:
            commands.append(
                {
                    "title": translate("Actions", "Remove External Audio"),
                    "icon": "empty",
                    "func": ("active", "remove_external_audio"),
                    "show_if": "is_active_local_file",
                }
            )

        commands.append(
            {
                "title": translate("Actions", "Detect Audio Files"),
                "icon": "empty",
                "func": (
                    "active",
                    "set_external_audio_autodiscover",
                    not block.video_params.is_external_audio_autodiscover,
                ),
                "check_if": (
                    "is_active_param_set_to",
                    "is_external_audio_autodiscover",
                    True,
                ),
                "show_if": "is_active_local_file",
            }
        )

        # the files are things to play, the rest are things to do with them
        return _separated(files, commands)

    def _attached_audio_menu_items(self):
        """The file the video was opened with, a row for each track it holds.

        Most hold one. A file holding several is listed once per track,
        since which of them to play is as much a choice as which file.
        A file that brought none at all is still named, so that it does
        not look as though nothing was opened.
        """

        block = self._ctx.active_block

        file_path = block.attached_audio_file

        if file_path is None:
            return []

        tracks = block.audio_tracks
        playing = block.audio_track_playing

        from_file = [
            track_id
            for track_id in block.external_audio_track_ids
            if track_id in tracks
        ]

        # a file with one track in it needs no telling apart from itself
        numbers = range(1, len(from_file) + 1) if len(from_file) > 1 else [None]

        rows = [
            {
                "title": _external_track_title(file_path, tracks[track_id], number),
                "icon": "play" if track_id == playing else "empty",
                "func": ("active", "set_audio_track", track_id),
                "check_if": ("is_active_audio_track", track_id),
                "show_if": "is_active_local_file",
            }
            for track_id, number in zip(from_file, numbers)
        ]

        return rows or [
            {
                "title": file_path.name,
                "icon": "empty",
                "func": ("active", "play_external_audio", str(file_path)),
                "show_if": "is_active_local_file",
            }
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

        if track is None and self.is_active_audio_preferred():
            track = block.audio_tracks.get(block.audio_track_playing)

        return track

    def _audio_choice_menu_items(self):
        """What there is to choose between, with the one being heard marked.

        Being chosen and being heard are not the same thing: a preference
        names no track, and the row it settles on is ticked nowhere. The
        mark is the only place the pane says which one answered it, the
        same way the stream ladder marks the rung it came to.
        """

        block = self._ctx.active_block

        languages = block.audio_language_options

        if len(languages) > 1:
            playing = block.audio_language_playing

            return [
                {
                    "title": language_name(language) or language,
                    "icon": "play" if language == playing else "empty",
                    "func": ("active", "set_audio_language", language),
                    "check_if": ("is_active_audio_language", language),
                    "show_if": "is_active_initialized",
                }
                for language in languages
            ]

        # what came out of a file of its own is listed with that file, under
        # its own heading, rather than among the tracks the video came with
        external_ids = set(block.external_audio_track_ids)
        playing = block.audio_track_playing

        return [
            {
                "title": _audio_track_title(track),
                "icon": "play" if track_id == playing else "empty",
                "func": ("active", "set_audio_track", track_id),
                "check_if": ("is_active_audio_track", track_id),
                "show_if": "is_active_initialized",
            }
            for track_id, track in block.audio_tracks.items()
            if track_id not in external_ids
        ]

    def menu_generator_subtitle_track(self):
        """Every way this video's subtitles can be chosen, in one list.

        The same list the sound gets, read from the other end. It opens on
        "off", because that is where every video starts and going back to
        it is the commonest thing asked of this menu, and everything under
        it is a way of asking for something instead.
        """

        if self.is_no_active_block:
            return {}

        block = self._ctx.active_block

        external = self._external_subtitle_menu_items()

        if not block.subtitle_tracks:
            # a video carrying none is still worth looking beside, which is
            # where most subtitles live anyway
            return external or {}

        return _separated(
            [
                _subtitles_off_menu_item(),
                *self._subtitle_default_menu_items(),
                self._preferred_subtitle_menu_item(),
                _subtitle_languages_menu_item(),
            ],
            self._subtitle_choice_menu_items(),
            external,
            [_subtitle_encoding_menu_item()],
        )

    def _subtitle_default_menu_items(self):
        """The track the container marks, where it marks one at all.

        Left out otherwise. "Whichever one the file puts forward" reads as
        a choice only where the file put one forward, and most do not --
        the ones that do are films carrying forced captions for their
        subtitled passages, which is exactly who wants this row.
        """

        if self._ctx.active_block.default_subtitle_track_id is None:
            return []

        return [
            {
                "title": translate("Subtitle Track", "Default"),
                "icon": "empty",
                "func": ("active", "apply_subtitle_default"),
                "check_if": "is_active_subtitle_default",
                "show_if": "is_active_initialized",
            }
        ]

    def _preferred_subtitle_menu_item(self):
        """Going back to the languages asked for, from a track picked by hand."""

        title = translate("Subtitle Track", "Preferred")

        name = self._preferred_subtitle_name

        if name:
            title = f"{title} ({name})"

        return {
            "title": title,
            "icon": "empty",
            "func": ("active", "apply_subtitle_preference"),
            "check_if": "is_active_subtitle_preferred",
            "show_if": "is_active_initialized",
        }

    @property
    def _preferred_subtitle_name(self) -> str | None:
        """What following the preference would give, spelled out.

        Nothing at all is a real answer here, where the sound would fall
        back on whatever it could find: subtitles in a language nobody
        asked for are worse than a bare picture.
        """

        block = self._ctx.active_block

        track = block.subtitle_tracks.get(block.preferred_subtitle_track_id)

        if track is None:
            return None

        name = language_name(track.language) or track.language

        return _join_track_name(name, _track_description(track, name)) or None

    def _subtitle_choice_menu_items(self):
        """The tracks the video carries, with the one on screen marked.

        Being chosen and being shown are not the same thing: a preference
        names no track, and the row it settles on is ticked nowhere. The
        mark is the only place the pane says which one answered it.
        """

        block = self._ctx.active_block

        external_ids = set(block.external_subtitle_track_ids)
        showing = block.subtitle_track_showing

        return [
            {
                "title": _subtitle_track_title(track),
                "icon": "play" if track_id == showing else "empty",
                "func": ("active", "set_subtitle_track", track_id),
                "check_if": ("is_active_subtitle_track", track_id),
                "show_if": "is_active_initialized",
            }
            for track_id, track in block.subtitle_tracks.items()
            if track_id not in external_ids
        ]

    def _external_subtitle_menu_items(self):
        """The subtitle files beside this video: what is there, and how to add.

        A file found next to the video is a name and nothing else until it
        is picked, so these sit below the tracks rather than among them.
        One already showing is a track by now, and is listed here under the
        name of the file it came from.
        """

        block = self._ctx.active_block

        if not block.is_local_file:
            return []

        files = self._attached_subtitle_menu_items() + [
            {
                "title": block.subtitle_file_name(file_path),
                "icon": "empty",
                "func": ("active", "show_external_subtitle", str(file_path)),
                "show_if": "is_active_local_file",
            }
            for file_path in block.offered_subtitle_files
        ]

        commands = [
            {
                "title": translate("Actions", "Add External Subtitles..."),
                "icon": "empty",
                "func": ("active", "add_external_subtitles_dialog"),
                "show_if": "is_active_local_file",
            }
        ]

        if block.video_params.external_subtitles:
            commands.append(
                {
                    "title": translate("Actions", "Remove External Subtitles"),
                    "icon": "empty",
                    "func": ("active", "remove_external_subtitles"),
                    "show_if": "is_active_local_file",
                }
            )

        commands.append(
            {
                "title": translate("Actions", "Detect Subtitle Files"),
                "icon": "empty",
                "func": (
                    "active",
                    "set_external_subtitle_autodiscover",
                    not block.video_params.is_external_subtitle_autodiscover,
                ),
                "check_if": (
                    "is_active_param_set_to",
                    "is_external_subtitle_autodiscover",
                    True,
                ),
                "show_if": "is_active_local_file",
            }
        )

        # the files are things to show, the rest are things to do with them
        return _separated(files, commands)

    def _attached_subtitle_menu_items(self):
        """A row for every track the files already handed over brought.

        Most files hold one, and the name they were saved under is the
        whole answer. One holding several is listed once per track, since
        which of them to show is as much a choice as which file: a VobSub
        index off a DVD can carry a dozen languages, and it says which
        each of them is.
        """

        block = self._ctx.active_block

        by_track = block.external_subtitle_tracks

        if not by_track:
            return []

        showing = block.subtitle_track_showing

        tracks_per_file = Counter(by_track.values())
        seen_in_file: Counter = Counter()

        rows = []

        for track_id, file_path in by_track.items():
            if track_id not in block.subtitle_tracks:
                continue

            number = None

            # a file with one track in it needs no telling apart from itself
            if tracks_per_file[file_path] > 1:
                seen_in_file[file_path] += 1
                number = seen_in_file[file_path]

            rows.append(
                {
                    "title": _external_subtitle_title(
                        block.subtitle_file_name(file_path),
                        block.external_subtitle_track_name(track_id),
                        number,
                    ),
                    "icon": "play" if track_id == showing else "empty",
                    "func": ("active", "set_subtitle_track", track_id),
                    "check_if": ("is_active_subtitle_track", track_id),
                    "show_if": "is_active_local_file",
                }
            )

        return rows

    def _preferred_audio_track_menu_item(self):
        """Going back to the languages asked for, from a track picked by hand.

        Which track that turns out to be is not the viewer's choice, so
        the menu is the only place it is ever spelled out.
        """

        title = translate("Audio Track", "Preferred")

        name = self._preferred_audio_name

        if name:
            title = f"{title} ({name})"

        return {
            "title": title,
            "icon": "empty",
            "func": ("active", "apply_audio_preference"),
            "check_if": "is_active_audio_preferred",
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


def _audio_device_default_menu_item():
    """Whichever way out of the machine everything else is using.

    What every video gets unless it was told otherwise, and the row that
    puts one back where it started.
    """

    return {
        "title": translate("Actions", "System Default"),
        "icon": "empty",
        "func": ("active", "set_audio_device", None),
        "check_if": "is_active_audio_device_default",
        "show_if": "is_active_has_audio",
    }


def _audio_default_menu_item():
    """The track the video's own file puts forward, nothing asked of VLC.

    The preferred languages do not reach it, which is the whole point of
    having it: a standing preference is not always wanted here.
    """

    return {
        "title": translate("Audio Track", "Default"),
        "icon": "empty",
        "func": ("active", "apply_audio_default"),
        "check_if": "is_active_audio_default",
        "show_if": "is_active_initialized",
    }


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


def _subtitles_off_menu_item():
    """Showing none, which is what every video starts on."""

    return {
        "title": translate("Subtitle Track", "Off"),
        "icon": "empty",
        "func": ("active", "disable_subtitles"),
        "check_if": "is_active_subtitle_disabled",
        "show_if": "is_active_initialized",
    }


def _subtitle_languages_menu_item():
    """The preference itself, right under the entry that follows it."""

    return {
        "title": "{}: %v".format(translate("Actions", "Languages")),
        "icon": "empty",
        "func": ("active", "subtitle_languages_dialog"),
        "value_getter": ("active", "get_subtitle_languages"),
        "show_if": "is_active_initialized",
    }


def _subtitle_encoding_menu_item():
    """What the subtitle text is read as, under the subtitles themselves.

    Last because it is the row nobody needs: a file written in UTF-8 is
    recognised as such on its own and nothing here touches it, so this is
    only ever reached for by somebody looking at the wrong letters. It
    opens a box rather than a submenu because forty-odd character sets is
    a list to scroll, not a column to walk. ASS and SSA are read by libass
    on its own account and are not affected either way.
    """

    return {
        "title": "{}: %v".format(translate("Actions", "Encoding")),
        "icon": "empty",
        "func": ("active", "subtitle_encoding_dialog"),
        "value_getter": ("active", "get_subtitle_encoding"),
        "show_if": "is_active_initialized",
    }


def _subtitle_track_title(track) -> str:
    """Name a subtitle by its language and by what the container called it.

    Without the codec the sound tracks carry: how many channels a dub has
    is worth knowing before picking it, where one line of text is much
    like another. The codec stands in only where there is nothing else.
    """

    return _track_name(track) or track.codec


def _external_subtitle_title(label: str, track_name=None, number=None) -> str:
    """Name a subtitle by the file it came in, and by whatever tells it apart.

    The file's own name is the whole answer for the ones holding a single
    track. A file holding several usually says which language each of them
    is; where it does not, their place in it is all there is to go on.
    """

    told_apart = track_name

    if not told_apart and number is not None:
        told_apart = f"#{number}"

    return _join_track_name(label, told_apart)


def _external_track_title(file_path, track, number=None) -> str:
    """Name a track by the file it came in, and by whatever tells it apart.

    Most files hold one track, and the name they were saved under is the
    whole answer -- the audio inside says nothing about which of several
    dubs it is. One holding several has to say which is which: by language
    or by the name the file gave them where there is one, and by their
    place in the file where there is nothing else to go on.
    """

    told_apart = _track_name(track)

    if not told_apart and number is not None:
        told_apart = f"#{number}"

    return f"{_join_track_name(file_path.name, told_apart)}, {track.codec_info}"


def _audio_track_title(track) -> str:
    """Name a track by its language and by what the container called it.

    libVLC passes on whatever was written into the file, which is a three
    letter code more often than anything a viewer would recognise. Several
    tracks in one language is ordinary -- rival dubs, a commentary, the
    original kept alongside them -- and where that happens the name the
    container gave a track is the only thing telling them apart.
    """

    titled = _track_name(track)

    return f"{titled}, {track.codec_info}" if titled else track.codec_info


def _track_name(track) -> str:
    """What the track itself has to go by, where it has anything at all."""

    name = language_name(track.language) or track.language

    return _join_track_name(name, _track_description(track, name))


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
