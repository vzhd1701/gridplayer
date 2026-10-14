"""The sound of a video block: its tracks, where they go out of the machine,
the languages it would rather be heard in, audio files kept beside it, and
how loud it is.

A dubbed stream that changes its language by loading another rung is the
stream part's to follow (see StreamControl.follow_audio_language); everything that
plays within what was loaded is here.
"""

from pathlib import Path

from PyQt5.QtWidgets import QFileDialog

from gridplayer.dialogs.audio_delay import SetAudioDelayDialog, audio_delay_txt
from gridplayer.dialogs.input_dialog import QCustomTextInput
from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioDisabled,
    AudioExternal,
    AudioLanguage,
    AudioPreferred,
    AudioTrackId,
    track_of_file,
)
from gridplayer.models.video import default_audio_selection
from gridplayer.params.extensions import SUPPORTED_AUDIO_EXT
from gridplayer.params.static import (
    AUDIO_DELAY_STEP_MS,
    MAX_AUDIO_DELAY_MS,
    MIN_AUDIO_DELAY_MS,
)
from gridplayer.utils.external_audio import (
    discover_audio_files,
    silenced_by_seeking,
    unplayable_as_audio_slave,
)
from gridplayer.utils.qt import translate
from gridplayer.utils.track_language import normalize, pick_track
from gridplayer.vlc_player.static import DISABLED_TRACK, NO_TRACK, wanted_audio_track_id
from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_initialized,
    only_local_file,
)


def _file_names(file_paths) -> str:
    return ", ".join(file_path.name for file_path in file_paths)


def _files_filter() -> str:
    extensions = " ".join(f"*.{ext}" for ext in sorted(SUPPORTED_AUDIO_EXT))

    audio = translate("Dialog - Add external audio", "Audio", "File formats")
    every = translate("Dialog - Add external audio", "All", "File formats")

    return f"{audio} ({extensions});;{every} (*)"


class AudioControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # the audio file this load was opened with, which libVLC holds on to
        # until the next one whatever track is picked meanwhile
        self._attached_file: Path | None = None

    def take_file_for_load(self):
        """The file the load about to start opens the video with: the one
        picked, if it is still there, a pick of one gone let go of."""

        self._forget_file_that_is_gone()

        self._attached_file = self._file_to_attach

    @property
    def tracks(self):
        if self._block.video_driver is None or not self._block.is_video_initialized:
            return {}
        return self._block.video_driver.audio_tracks

    @property
    def devices(self):
        """Every way out of the machine the process playing this can reach.

        Nothing until it has loaded: the list is read where VLC lives,
        and comes back with the media.
        """

        if self._block.video_driver is None or not self._block.is_video_initialized:
            return ()

        return self._block.video_driver.audio_devices

    def set_track(self, track_id):
        self._block._log.debug(
            f"Set audio track {track_id},"
            f" initialized={self._block.is_video_initialized},"
            f" video track off={self._is_video_track_off}"
        )

        if track_id == DISABLED_TRACK and self._is_video_track_off:
            self._block._ctx.commands.warning(
                translate("Warning", "Cannot disable both video & audio tracks")
            )
            return

        # a track chosen by hand outranks the languages asked for, and has
        # to outlive the reload that would otherwise resolve them again
        self._block.video_params.audio_selection = self._selection_for(track_id)

        # a video part way through a reload has no tracks to switch between
        # yet, and will settle on this one once it does
        if self._block.is_video_initialized:
            self._block.video_driver.set_audio_track(track_id)

    def _selection_for(self, track_id):
        """How to remember this track, by the steadiest name it answers to.

        A file of its own keeps its name whatever the tracks do, a language
        outlives a source that renumbers them, and an id is what is left
        where neither says anything.
        """

        if track_id == DISABLED_TRACK:
            return AudioDisabled()

        external_file = self.external_tracks.get(track_id)

        if external_file is not None:
            return AudioExternal(
                file=external_file,
                track=self.external_track_ids.index(track_id),
            )

        language = self._language_key(track_id)

        if language is not None:
            return AudioLanguage(tag=language)

        return AudioTrackId(id=track_id)

    def set_device(self, device) -> None:
        """Send this video's sound another way out of the machine.

        Remembered on the video rather than anywhere shared, which is the
        whole point: telling one video's sound from another's is what this
        is for, and an id names a jack on this machine and nothing at all
        on the next; see models/audio_device.py
        """

        self._block._log.debug(f"Set audio device {device}")

        self._block.video_params.audio_device = device

        # a video part way through a load is told when it gets there, by
        # whatever opens it; see PlayerBase._apply_wanted_audio_device
        if self._block.is_video_initialized:
            self._block.video_driver.set_audio_device(device)

    def restore_selection(self, selection) -> None:
        """Put a remembered choice of sound back in force, as a snapshot does."""

        self._block.video_params.audio_selection = selection

        self.apply_wanted_track()

    @property
    def _is_video_track_off(self) -> bool:
        """Whether there would be nothing left to watch without the sound.

        Only an id of -1 says the picture was switched off. None says the
        player had nothing to report when it was last asked, which is not
        the same thing and must not cost the sound.
        """

        if self._block.video_driver is None or not self._block.is_video_initialized:
            # part way through a load, where the player settles this itself
            return False

        return self._block.video_driver.cur_video_track_id == DISABLED_TRACK

    def _language_key(self, track_id) -> str | None:
        """The language to remember this track by, where one will do.

        An id is only as good as the media it was read from, and a stream
        is demuxed afresh on every reload. A language outlives that, but
        only while it picks out one track rather than several.
        """

        track = self.tracks.get(track_id)

        if track is None or not track.language:
            return None

        namesakes = [
            other
            for other in self.tracks.values()
            if normalize(other.language) == normalize(track.language)
        ]

        return track.language if len(namesakes) == 1 else None

    @property
    def track_playing(self) -> int | None:
        """Which track the sound is coming from, whatever was asked for.

        What was asked for can be a preference rather than a track, and
        then this is the only place the answer it came to is written down.
        """

        if self._block.video_driver is None or not self._block.is_video_initialized:
            return None

        return self._block.video_driver.cur_audio_track_id

    @property
    def preferred_track_id(self) -> int | None:
        """The track this file would open with, were nothing picked by hand."""

        return pick_track(self._block.video_params.audio_languages, self.tracks)

    def apply_default(self):
        """Leave the sound to the video's own file, preference and all.

        A dubbed video's own is the language it was made in, which may be
        another one than the dub on screen.
        """

        self._block.video_params.audio_selection = AudioDefault()

        self._block.stream.follow_audio_language()

    def apply_preference(self):
        """Follow the preferred languages again, whichever way this video dubs."""

        self._block.video_params.audio_selection = AudioPreferred()

        self._block.stream.follow_audio_language()

    def apply_wanted_track(self):
        """Put the settings into effect on the video that is already playing."""

        if self._block.video_driver is None or not self._block.is_video_initialized:
            # part way through a reload, which will settle this on its own
            return

        track_id = self._wanted_track_id()

        if track_id is None:
            if self._block.video_driver.cur_audio_track_id not in NO_TRACK:
                # something is playing already and nothing was asked for by
                # name, so there is nothing here worth moving off
                return

            # a "disable" is still in force and the preference has no
            # opinion, so any track at all beats going on in silence
            track_id = next(iter(self.tracks), None)

        if track_id is None:
            return

        self._block.video_driver.set_audio_track(track_id)

    def _wanted_track_id(self) -> int | None:
        """Which track this video's settings call for, its own files included.

        Only the block knows which track came out of which file, so a pick
        of one is answered here; everything else the video can answer for
        itself.
        """

        selection = self._block.video_params.audio_selection

        if isinstance(selection, AudioDefault):
            return self.default_track_id

        if isinstance(selection, AudioExternal):
            if selection.file == self.attached_file:
                picked = track_of_file(selection, self.external_track_ids)

                if picked is not None:
                    return picked

        return wanted_audio_track_id(self._block.video_params, self.tracks)

    @only_initialized
    def languages_dialog(self):
        """Edit the languages this video would rather be heard in."""

        languages = QCustomTextInput.get_text(
            parent=self._block.parent(),
            title=translate(
                "Dialog - Set preferred audio languages",
                "Preferred audio languages",
                "Header",
            ),
            initial_value=self._block.video_params.audio_languages,
            placeholder=translate("Dialog - Set preferred audio languages", "en, ja"),
        )

        self.set_languages(languages)

    def set_languages(self, languages: str):
        if languages == self._block.video_params.audio_languages:
            return

        self._block.video_params.audio_languages = languages

        if not isinstance(self._block.video_params.audio_selection, AudioPreferred):
            return

        # the preference is what is being followed, so following it again
        # is the whole point of having changed it
        self.apply_preference()

    def get_languages(self) -> str:
        return self._block.video_params.audio_languages or translate(
            "Audio Languages", "any"
        )

    @property
    def discovered_files(self) -> list[Path]:
        """Audio files named after this video that nobody has picked yet.

        Finding them is a directory listing and nothing else. A file here
        has not been opened and costs nothing until it is chosen, which is
        what makes it safe to look on every video in the grid.
        """

        if (
            not self._block.is_local_file
            or not self._block.video_params.is_external_audio_autodiscover
        ):
            return []

        attached = set(self._block.video_params.external_audio)

        return [
            found
            for found in discover_audio_files(self._block.video_params.uri)
            if found not in attached
        ]

    @property
    def external_track_ids(self) -> tuple[int, ...]:
        """The tracks that came out of a file, as the player saw them arrive.

        More than one where the file holds more than one, which is theirs
        to tell apart: with a single file attached, every track past the
        video's own came out of it.
        """

        if self._block.video_driver is None or not self._block.is_video_initialized:
            return ()

        return self._block.video_driver.external_audio_ids

    @property
    def default_track_id(self) -> int | None:
        """The track the video's own file puts forward.

        What libVLC opened on, as long as that was the video's own doing.
        A file attached at load takes the sound for itself as soon as its
        stream arrives, and what libVLC opened on is then that file -- no
        answer at all to what the video would have played alone. The first
        of its own tracks is as close as this gets to one.
        """

        if self._block.video_driver is None or not self._block.is_video_initialized:
            return None

        from_file = set(self.external_track_ids)

        own_tracks = [track_id for track_id in self.tracks if track_id not in from_file]

        opened_on = self._block.video_driver.default_audio_track_id

        if opened_on in own_tracks:
            return opened_on

        return own_tracks[0] if own_tracks else None

    @property
    def attached_file(self) -> Path | None:
        """The external audio libVLC was really handed, if any.

        Not the same question as which sound was chosen: libVLC never takes
        a file back, so one handed over is still there after the viewer
        switches to a track of the video's own, and its track is still in
        the list wearing its name. Only a fresh load changes this.

        One at a time, since libVLC never says which stream came from which
        file and two of them would leave the pair to be told apart by
        guesswork.
        """

        return self._attached_file

    @property
    def _file_to_attach(self) -> Path | None:
        """The file the next load is to open this video with.

        A file that is no longer where the playlist left it -- renamed, or
        on a drive nobody plugged in -- is no use to libVLC, though it
        keeps its place in the list in case whatever moved it moves it back.
        """

        selection = self._block.video_params.audio_selection

        if not isinstance(selection, AudioExternal):
            return None

        if not selection.file.is_absolute() or not selection.file.is_file():
            return None

        return selection.file

    @property
    def offered_files(self) -> list[Path]:
        """Files this video can be played with, other than the one it is on."""

        attached = self.attached_file

        known = [
            file_path
            for file_path in self._block.video_params.external_audio
            # one that is not there cannot be played, and a row that does
            # nothing is worse than no row
            if file_path != attached and file_path.is_file()
        ]

        return known + self.discovered_files

    @property
    def external_tracks(self) -> dict[int, Path]:
        """Which file each external track came out of, where there is one."""

        file_path = self.attached_file

        if file_path is None:
            return {}

        return dict.fromkeys(self.external_track_ids, file_path)

    @property
    def selected_slave_uri(self) -> str | None:
        """The file the video is to be played with, for the player to find."""

        wanted = self._file_to_attach

        return None if wanted is None else wanted.as_uri()

    @only_local_file
    def add_external_dialog(self) -> None:
        """Pick audio files to play this video with."""

        file_names, _ = QFileDialog.getOpenFileNames(
            self._block.parent(),
            translate("Dialog - Add external audio", "Add External Audio", "Header"),
            str(self._block.video_params.uri.parent),
            _files_filter(),
        )

        self.add_external([Path(file_name) for file_name in file_names])

    def add_external(self, file_paths) -> None:
        """Play these audio files with the video, starting on the first.

        One picked while the video is up goes on where it stands: VLC takes
        a file at any time, so nothing has to be loaded again for it.
        """

        new_files = [
            file_path
            for file_path in file_paths
            if file_path.is_absolute()
            and file_path not in self._block.video_params.external_audio
        ]

        if not new_files:
            return

        self._warn_about_awkward(new_files)

        self._block.video_params.external_audio = [
            *self._block.video_params.external_audio,
            *new_files,
        ]

        # sound asked for by name outranks the languages asked for, the same
        # way picking a track by hand does
        self._block.video_params.audio_selection = AudioExternal(file=new_files[0])

        self._put_external_into_effect()

    def _forget_file_that_is_gone(self) -> None:
        """Let go of a pick whose file is not where the playlist left it.

        A choice naming nothing on the disk is one the menu cannot show as
        taken, and a video that looks as though nothing at all is chosen
        reads worse than one back on the sound it would otherwise open on.
        The file keeps its place in the list, in case whatever moved it
        moves it back.
        """

        selection = self._block.video_params.audio_selection

        if not isinstance(selection, AudioExternal):
            return

        if self._file_to_attach is not None:
            return

        self._block._log.debug(f"{selection.file.name} is not there any more")

        self._block.video_params.audio_selection = default_audio_selection()

    def _put_external_into_effect(self) -> None:
        """Play the file that was picked, the cheapest way that is certain.

        libVLC takes a file at any time but never gives one back, and it
        never says which stream came from which file. A video that has one
        already is therefore loaded again rather than handed a second,
        which costs a moment and leaves no room for a mix-up.
        """

        if not self._block.is_video_initialized:
            # part way through a load, which will open it with the video
            return

        if self._attached_file is not None:
            self._block._log.debug("A file is on already, loading the video again")

            self._block.reload()
            return

        wanted = self._file_to_attach

        if wanted is not None:
            self._attached_file = wanted

            self._block.video_driver.add_audio_slave(wanted.as_uri())

    def _warn_about_awkward(self, file_paths) -> None:
        """Say so where libVLC will not make a sound of what was picked.

        The files are taken anyway: this is what one build of VLC does with
        them, and being told beats a track that sits there silently.
        """

        unplayable = unplayable_as_audio_slave(file_paths)
        silenced = silenced_by_seeking(file_paths)

        warnings = []

        if unplayable:
            warnings.append(
                translate(
                    "Warning",
                    "VLC cannot play {FILES} alongside a video.",
                ).format(FILES=_file_names(unplayable))
            )

        if silenced:
            warnings.append(
                translate(
                    "Warning",
                    "{FILES} will fall silent once the video is seeked.",
                ).format(FILES=_file_names(silenced))
            )

        if not warnings:
            return

        warnings.append(
            translate("Warning", "Convert to MP3, M4A, FLAC or AC3 to play it.")
        )

        self._block._ctx.commands.warning("\n\n".join(warnings))

    def play_external(self, file_name: str) -> None:
        """Hear this file, whether it has been attached yet or not."""

        file_path = Path(file_name)

        if file_path == self.attached_file:
            # it is on already, and may only have been switched away from
            if self.external_track_ids:
                self.set_track(self.external_track_ids[0])

            return

        if file_path not in self._block.video_params.external_audio:
            self.add_external([file_path])
            return

        self._block.video_params.audio_selection = AudioExternal(file=file_path)

        self._put_external_into_effect()

    def remove_external(self) -> None:
        """Play the video on its own sound again.

        libVLC has no way to take back a file it has been handed, so the
        video is loaded once more, this time without them.
        """

        if not self._block.video_params.external_audio:
            return

        self.drop_external()

        self._block.reload()

    def drop_external(self) -> None:
        self._block.video_params.external_audio = []

        # the track that was playing leaves with the file it came from, so
        # the video goes back to whatever it would have opened on
        if isinstance(self._block.video_params.audio_selection, AudioExternal):
            self._block.video_params.audio_selection = default_audio_selection()

    def set_external_autodiscover(self, is_on: bool) -> None:
        """Whether to offer the audio files kept beside this video."""

        self._block.video_params.is_external_audio_autodiscover = is_on

    def tracks_changed(self) -> None:
        """Take note of a track that appeared after the video was loaded.

        What is playing is the player's business, not the choice's: writing
        it back here is what used to turn "go by my languages" into "play
        track three" behind the viewer's back.
        """

        self._block.is_audio_present_change.emit(bool(self.tracks))

        if self._is_external_short:
            # libVLC took the file and brought nothing back, which some
            # formats do when handed to a video that is already playing.
            # Opening them with the video is the way that always works.
            self._block._log.debug("External audio brought no track, loading it again")

            self._block.reload()

    @property
    def _is_external_short(self) -> bool:
        """Whether the file that was handed over has no track to show for it."""

        return self.attached_file is not None and not self.external_track_ids

    def adopt_if_silent(self) -> None:
        """Give a video with no sound of its own the one file found beside it.

        A silent video next to an audio file named after it is the one case
        where doing nothing reads as a fault rather than as a choice. Where
        several were found, which of them to play is nobody's guess but the
        viewer's, and they are left in the menu to be picked from.
        """

        if self.tracks or self._block.video_params.external_audio:
            return

        found = self.discovered_files

        if len(found) != 1:
            return

        self._block._log.debug(
            f"Adopting {found[0].name} as the sound of a silent video"
        )

        self.add_external(found)

    def mute_unmute(self):
        self.set_muted(not self._block.video_params.is_muted)

    @only_initialized
    def set_muted(self, muted):
        self._block.video_params.is_muted = muted

        self._block.video_driver.audio_set_mute(self._block.video_params.is_muted)

        self._block.is_muted_change.emit(self._block.video_params.is_muted)

    @only_initialized
    def set_volume(self, percent):
        self._block.video_params.volume = round(percent, 2)

        self._block.video_driver.audio_set_volume(self._block.video_params.volume)

        self._block.volume_change.emit(percent)

    @only_initialized
    def volume_increase(self):
        self.set_muted(False)

        self._block.video_params.volume += 0.05
        self._block.video_params.volume = min(
            round(self._block.video_params.volume, 2), 1.0
        )

        self.set_volume(self._block.video_params.volume)

    @only_initialized
    def volume_decrease(self):
        self.set_muted(False)

        self._block.video_params.volume -= 0.05
        self._block.video_params.volume = max(
            round(self._block.video_params.volume, 2), 0
        )

        self.set_volume(self._block.video_params.volume)

    @only_initialized
    def set_channel_mode(self, mode):
        if not self.tracks:
            return

        self._block.video_params.audio_channel_mode = mode
        self._block.video_driver.set_audio_channel_mode(mode)

    @only_initialized
    def set_delay(self, delay_ms, is_silent=False):
        if not self.tracks:
            return

        delay_ms = min(max(delay_ms, MIN_AUDIO_DELAY_MS), MAX_AUDIO_DELAY_MS)

        self._block.video_params.audio_delay_ms = delay_ms
        self._block.video_driver.set_audio_delay(delay_ms)

        if not is_silent:
            self._block.info_change.emit(f"Audio delay: {audio_delay_txt(delay_ms)}")

    @only_initialized
    def delay_increase(self):
        self.set_delay(self._block.video_params.audio_delay_ms + AUDIO_DELAY_STEP_MS)

    @only_initialized
    def delay_decrease(self):
        self.set_delay(self._block.video_params.audio_delay_ms - AUDIO_DELAY_STEP_MS)

    @only_initialized
    def delay_reset(self):
        self.set_delay(0)

    @only_initialized
    def delay_dialog(self):
        if not self.tracks:
            return

        dialog = SetAudioDelayDialog.for_video_block(
            self._block, parent=self._block.parent()
        )

        dialog.exec_()

    @only_initialized
    def get_delay(self):
        return audio_delay_txt(self._block.video_params.audio_delay_ms)
