"""The subtitles of a video block: its own tracks and files beside it.

The same shape as the sound (see the block's audio), with two differences
that run all the way through it: a video starts with none showing, and a
file picked for one goes on where it stands, since libVLC names every
subtitle track after whatever brought it and none of them ever has to be
told apart by counting.
"""

from pathlib import Path

from PyQt5.QtWidgets import QFileDialog

from gridplayer.dialogs.input_dialog import QCustomTextInput
from gridplayer.dialogs.subtitle_delay import SetSubtitleDelayDialog, subtitle_delay_txt
from gridplayer.dialogs.subtitle_encoding import SetSubtitleEncodingDialog
from gridplayer.models.subtitle_selection import (
    SubtitleDefault,
    SubtitleDisabled,
    SubtitleExternal,
    SubtitleLanguage,
    SubtitlePreferred,
    SubtitleTrackId,
)
from gridplayer.models.subtitle_selection import (
    track_of_file as subtitle_track_of_file,
)
from gridplayer.models.video import default_subtitle_selection
from gridplayer.params.extensions import SUPPORTED_SUBTITLE_EXT
from gridplayer.params.static import (
    MAX_SUBTITLE_DELAY_MS,
    MIN_SUBTITLE_DELAY_MS,
    SUBTITLE_DELAY_STEP_MS,
)
from gridplayer.utils.external_subtitles import (
    discover_subtitle_files,
    subtitle_file_label,
)
from gridplayer.utils.qt import translate
from gridplayer.utils.track_language import language_name, normalize, pick_track
from gridplayer.vlc_player.static import DISABLED_TRACK, wanted_subtitle_track_id
from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_initialized,
    only_local_file,
)


def _files_filter() -> str:
    extensions = " ".join(f"*.{ext}" for ext in sorted(SUPPORTED_SUBTITLE_EXT))

    subtitles = translate(
        "Dialog - Add external subtitles", "Subtitles", "File formats"
    )
    every = translate("Dialog - Add external subtitles", "All", "File formats")

    return f"{subtitles} ({extensions});;{every} (*)"


def _track_file_stem(track) -> str | None:
    """The file a subtitle track came from, as libVLC named it.

    libVLC puts the title it made for an attached file where an embedded
    track's language goes, and that title is the file's own path without
    its extension. Nothing but a file ever ends up there, so what reads as
    a path is the one sign of where a track came from.
    """

    if track is None or not track.language:
        return None

    return track.language.replace("\\", "/").rsplit("/", 1)[-1].casefold()


class SubtitleControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # the subtitle files libVLC has been handed so far, in the order it
        # was handed them, which is the order their tracks come back in.
        # More than one is allowed here: each arrives as a track of its own
        # wearing the name of the file it came from.
        self._attached_files: list[Path] = []

    def take_files_for_load(self):
        """The files the load about to start opens the video with: those
        picked that are still there, a pick of one gone let go of."""

        self._forget_files_that_are_gone()

        self._attached_files = self._files_to_attach

    @property
    def tracks(self):
        if self._block.video_driver is None or not self._block.is_video_initialized:
            return {}

        return self._block.video_driver.subtitle_tracks

    @property
    def has_any(self) -> bool:
        """Whether there is a subtitle to show and a picture to show it on."""

        if self._block.video_driver is None or not self._block.is_video_initialized:
            return False

        return self._block.video_driver.has_subtitles

    @property
    def track_showing(self) -> int | None:
        """Which subtitle is on screen, whatever was asked for.

        What was asked for can be a preference rather than a track, and
        then this is the only place the answer it came to is written down.
        """

        if self._block.video_driver is None or not self._block.is_video_initialized:
            return None

        return self._block.video_driver.cur_subtitle_track_id

    @property
    def preferred_track_id(self) -> int | None:
        """The subtitle this video would show, were nothing picked by hand."""

        return pick_track(self._block.video_params.subtitle_languages, self._own)

    @property
    def _own(self) -> dict:
        """The subtitle tracks the video carried, without the attached files.

        libVLC writes an attached file's own name where an embedded track's
        language belongs, so a file left in here is a path pretending to be
        a language, and every question about languages gets a wrong answer.
        """

        from_file = set(self.external_track_ids)

        return {
            track_id: track
            for track_id, track in self.tracks.items()
            if track_id not in from_file
        }

    def set_track(self, track_id):
        """Show this subtitle, or DISABLED_TRACK to show none at all."""

        self._block._log.debug(f"Set subtitle track {track_id}")

        # a subtitle chosen by hand outranks the languages asked for, and
        # has to outlive the reload that would otherwise resolve them again
        self._block.video_params.subtitle_selection = self._selection_for(track_id)

        # a video part way through a reload has no tracks to switch between
        # yet, and will settle on this one once it does
        if self._block.is_video_initialized:
            self._block.video_driver.set_subtitle_track(track_id)
            self._nudge_into_view()

    def disable(self):
        self.set_track(DISABLED_TRACK)

    def _selection_for(self, track_id):
        """How to remember this subtitle, by the steadiest name it answers to.

        A file of its own keeps its name whatever the tracks do, a language
        outlives a source that renumbers them, and an id is what is left
        where neither says anything.
        """

        if track_id == DISABLED_TRACK:
            return SubtitleDisabled()

        external_file = self.external_tracks.get(track_id)

        if external_file is not None:
            return SubtitleExternal(
                file=external_file,
                track=self.number_in_file(track_id, external_file),
            )

        language = self.language_key(track_id)

        if language is not None:
            return SubtitleLanguage(tag=language)

        return SubtitleTrackId(id=track_id)

    def number_in_file(self, track_id, file_path: Path) -> int:
        """Which of the tracks that file brought this one is."""

        from_file = [
            other_id
            for other_id, other_file in self.external_tracks.items()
            if other_file == file_path
        ]

        return from_file.index(track_id) if track_id in from_file else 0

    def language_key(self, track_id) -> str | None:
        """The language to remember this subtitle by, where one will do.

        An id is only as good as the media it was read from, and a stream
        is demuxed afresh on every reload. A language outlives that, but
        only while it picks out one track rather than several, and only for
        a track the video carried: see _own.
        """

        own_subtitles = self._own

        track = own_subtitles.get(track_id)

        if track is None or not track.language:
            return None

        wanted = normalize(track.language)

        if wanted is None:
            # a track tagged with nothing anyone can name is one that only
            # its number picks out
            return None

        namesakes = [
            other
            for other in own_subtitles.values()
            if normalize(other.language) == wanted
        ]

        return track.language if len(namesakes) == 1 else None

    def restore_selection(self, selection) -> None:
        """Put a remembered choice back in force, as a snapshot does."""

        self._block.video_params.subtitle_selection = selection

        self._apply_wanted_track()

    def apply_default(self):
        """Show whichever subtitle the container marks, as VLC would alone."""

        self._block.video_params.subtitle_selection = SubtitleDefault()

        self._apply_wanted_track()

    def apply_preference(self):
        """Follow the preferred languages again."""

        self._block.video_params.subtitle_selection = SubtitlePreferred()

        self._apply_wanted_track()

    def _apply_wanted_track(self):
        """Put the settings into effect on the video that is already playing."""

        if self._block.video_driver is None or not self._block.is_video_initialized:
            # part way through a reload, which will settle this on its own
            return

        track_id = self._wanted_track_id()

        if track_id is None:
            # "whatever the container marks", which is what it opened on
            track_id = self.default_track_id

        if track_id is None:
            return

        self._block.video_driver.set_subtitle_track(track_id)
        self._nudge_into_view()

    def _wanted_track_id(self) -> int | None:
        """Which subtitle this video's settings call for, its own files included.

        Only the block knows which track came out of which file, so a pick
        of one is answered here; everything else the video can answer for
        itself.
        """

        selection = self._block.video_params.subtitle_selection

        if isinstance(selection, SubtitleExternal):
            from_file = [
                track_id
                for track_id, file_path in self.external_tracks.items()
                if file_path == selection.file
            ]

            picked = subtitle_track_of_file(selection, from_file)

            if picked is not None:
                return picked

        return wanted_subtitle_track_id(
            self._block.video_params,
            self.tracks,
            self.external_track_ids,
        )

    def _nudge_into_view(self) -> None:
        """Show the subtitle that was just picked, rather than the next one.

        A track switched to part way through a line shows nothing until the
        line after it: VLC draws a subtitle when the packet carrying it goes
        past, and for the line already on screen that packet went past while
        another track was selected. Playing or paused makes no difference --
        paused is only the worse case, since there nothing arrives to end
        the wait at all.

        Seeking to where the video already is puts that packet through
        again, and is the cheapest thing that does. It costs a visible
        hitch, which beats a menu that looks as though it did nothing:
        subtitles are sparse, and the next line can be a minute away.
        """

        if self._block.is_live:
            # nothing to seek in, and nothing that stays on screen long
            # enough for the wait to matter
            return

        self._block.video_driver.set_time(self._block.time)

    @property
    def discovered_files(self) -> list[Path]:
        """Subtitle files named after this video that nobody has picked yet.

        Finding them is a directory listing and nothing else, the same as
        for the audio: a file here has not been opened and costs nothing
        until it is chosen.
        """

        if (
            not self._block.is_local_file
            or not self._block.video_params.is_external_subtitle_autodiscover
        ):
            return []

        attached = set(self._block.video_params.external_subtitles)

        return [
            found
            for found in discover_subtitle_files(self._block.video_params.uri)
            if found not in attached
        ]

    @property
    def external_track_ids(self) -> tuple[int, ...]:
        """The tracks the attached files brought, as the player saw them arrive."""

        if self._block.video_driver is None or not self._block.is_video_initialized:
            return ()

        return self._block.video_driver.external_subtitle_ids

    @property
    def default_track_id(self) -> int | None:
        """The subtitle the container marks default or forced, if any."""

        if self._block.video_driver is None or not self._block.is_video_initialized:
            return None

        return self._block.video_driver.default_subtitle_track_id

    @property
    def attached_files(self) -> list[Path]:
        """The subtitle files libVLC was really handed, in that order.

        Not the same question as which subtitle was chosen: libVLC never
        takes a file back, so one handed over is still there after the
        viewer switches to a track of the video's own.
        """

        return list(self._attached_files)

    @property
    def external_tracks(self) -> dict[int, Path]:
        """Which file each external subtitle came out of.

        libVLC writes the file's own name into the track where a language
        belongs, and that is the one place it ever says where a stream came
        from, so that is what these are matched on. Where a name answers to
        none of the files, the order they were attached in stands in, which
        is right wherever each file brought one track -- which is all but
        the rarest of them.
        """

        track_ids = self.external_track_ids
        files = self._attached_files

        if not track_ids or not files:
            return {}

        by_stem = {file_path.stem.casefold(): file_path for file_path in files}

        named = {
            track_id: by_stem.get(_track_file_stem(self.tracks.get(track_id)))
            for track_id in track_ids
        }

        if all(named.values()):
            return named

        return {
            track_id: files[min(position, len(files) - 1)]
            for position, track_id in enumerate(track_ids)
        }

    @property
    def offered_files(self) -> list[Path]:
        """Files this video can be shown with, other than the ones already on."""

        attached = set(self._attached_files)

        known = [
            file_path
            for file_path in self._block.video_params.external_subtitles
            # one that is not there cannot be shown, and a row that does
            # nothing is worse than no row
            if file_path not in attached and file_path.is_file()
        ]

        return known + self.discovered_files

    @property
    def selected_slave_uris(self) -> tuple[str, ...]:
        """The files the next load is to open this video with."""

        return tuple(file_path.as_uri() for file_path in self._files_to_attach)

    @property
    def _files_to_attach(self) -> list[Path]:
        """The picked files that are still where the playlist left them.

        One that has been renamed, or is on a drive nobody plugged in, is
        no use to libVLC, though it keeps its place in the list in case
        whatever moved it moves it back.
        """

        return [
            file_path
            for file_path in self._block.video_params.external_subtitles
            if file_path.is_absolute() and file_path.is_file()
        ]

    def file_name(self, file_path: Path) -> str:
        """What to call a subtitle file in the menu."""

        video_path = self._block.video_params.uri if self._block.is_local_file else None

        return subtitle_file_label(file_path, video_path)

    def external_track_name(self, track_id) -> str | None:
        """What tells one track of a file apart from the next, where anything does.

        A file holding several says which is which: a VobSub index carries
        a language per track, and so does a subtitle-only Matroska. A file
        holding one has nothing to say beyond its own name, and libVLC puts
        that name where the language belongs -- so a "language" that is the
        file over again is no language at all.
        """

        track = self.tracks.get(track_id)

        if track is None or not track.language:
            return None

        file_path = self.external_tracks.get(track_id)

        if file_path is not None and _track_file_stem(track) == (
            file_path.stem.casefold()
        ):
            return None

        return language_name(track.language) or track.language

    @only_local_file
    def add_external_dialog(self) -> None:
        """Pick subtitle files to show over this video."""

        file_names, _ = QFileDialog.getOpenFileNames(
            self._block.parent(),
            translate(
                "Dialog - Add external subtitles", "Add External Subtitles", "Header"
            ),
            str(self._block.video_params.uri.parent),
            _files_filter(),
        )

        self.add_external([Path(file_name) for file_name in file_names])

    def add_external(self, file_paths) -> None:
        """Show these subtitle files with the video, starting on the first."""

        new_files = [
            file_path
            for file_path in file_paths
            if file_path.is_absolute()
            and file_path not in self._block.video_params.external_subtitles
        ]

        if not new_files:
            return

        self._block.video_params.external_subtitles = [
            *self._block.video_params.external_subtitles,
            *new_files,
        ]

        # subtitles asked for by name outrank the languages asked for, the
        # same way picking a track by hand does
        self._block.video_params.subtitle_selection = SubtitleExternal(
            file=new_files[0]
        )

        self._put_external_into_effect()

    def show_external(self, file_name: str) -> None:
        """Show this file, whether it has been attached yet or not."""

        file_path = Path(file_name)

        if file_path in self._attached_files:
            # it is on already, and may only have been switched away from
            from_file = [
                track_id
                for track_id, attached in self.external_tracks.items()
                if attached == file_path
            ]

            if from_file:
                self.set_track(from_file[0])

            return

        if file_path not in self._block.video_params.external_subtitles:
            self.add_external([file_path])
            return

        self._block.video_params.subtitle_selection = SubtitleExternal(file=file_path)

        self._put_external_into_effect()

    def _put_external_into_effect(self) -> None:
        """Hand over whatever has been picked and is not on yet.

        No reload, ever, which is what sets this apart from external audio:
        libVLC takes a subtitle file at any time and names the track it
        brings after it, so however many go on they can still be told
        apart. Only taking one away costs a load.
        """

        if not self._block.is_video_initialized:
            # part way through a load, which will open them with the video
            return

        for file_path in self._files_to_attach:
            if file_path in self._attached_files:
                continue

            self._block._log.debug(f"Adding subtitle file {file_path.name}")

            self._attached_files.append(file_path)

            self._block.video_driver.add_subtitle_slave(file_path.as_uri())

    def remove_external(self) -> None:
        """Go back to the subtitles the video carries, if it carries any.

        libVLC has no way to take back a file it has been handed, so the
        video is loaded once more, this time without them.
        """

        if not self._block.video_params.external_subtitles:
            return

        self.drop_external()

        self._block.reload()

    def drop_external(self) -> None:
        """Let go of the files picked, and of the track one of them showed."""

        self._block.video_params.external_subtitles = []

        # the track that was showing leaves with the file it came from
        if isinstance(self._block.video_params.subtitle_selection, SubtitleExternal):
            self._block.video_params.subtitle_selection = default_subtitle_selection()

    def set_external_autodiscover(self, is_on: bool) -> None:
        """Whether to offer the subtitle files kept beside this video."""

        self._block.video_params.is_external_subtitle_autodiscover = is_on

    def _forget_files_that_are_gone(self) -> None:
        """Let go of a pick whose file is not where the playlist left it.

        The file keeps its place in the list, in case whatever moved it
        moves it back; only the choice of it is dropped, so that the video
        opens on something the menu can show as taken.
        """

        selection = self._block.video_params.subtitle_selection

        if not isinstance(selection, SubtitleExternal):
            return

        if selection.file in self._files_to_attach:
            return

        self._block._log.debug(f"{selection.file.name} is not there any more")

        self._block.video_params.subtitle_selection = default_subtitle_selection()

    @only_initialized
    def languages_dialog(self):
        """Edit the languages this video would rather be subtitled in."""

        languages = QCustomTextInput.get_text(
            parent=self._block.parent(),
            title=translate(
                "Dialog - Set preferred subtitle languages",
                "Preferred subtitle languages",
                "Header",
            ),
            initial_value=self._block.video_params.subtitle_languages,
            placeholder=translate(
                "Dialog - Set preferred subtitle languages", "en, ja"
            ),
        )

        self.set_languages(languages)

    def set_languages(self, languages: str):
        if languages == self._block.video_params.subtitle_languages:
            return

        self._block.video_params.subtitle_languages = languages

        if not isinstance(
            self._block.video_params.subtitle_selection, SubtitlePreferred
        ):
            return

        # the preference is what is being followed, so following it again
        # is the whole point of having changed it
        self.apply_preference()

    def get_languages(self) -> str:
        return self._block.video_params.subtitle_languages or translate(
            "Subtitle Languages", "any"
        )

    def set_encoding(self, encoding: str) -> None:
        """Read this video's subtitle files as a different character set.

        Which set a file is read as is settled when the input opens, so the
        video is handed back to itself and set_video reopens it.
        """

        if self._block.video_params.subtitle_encoding == encoding:
            return

        self._block.set_video(
            self._block.video_params.model_copy(update={"subtitle_encoding": encoding})
        )

    @only_initialized
    def encoding_dialog(self):
        """Pick what this video's subtitle files are read as."""

        encoding = SetSubtitleEncodingDialog.get_encoding(
            encoding=self._block.video_params.subtitle_encoding,
            parent=self._block.parent(),
        )

        if encoding is None:
            return

        self.set_encoding(encoding)

    def get_encoding(self) -> str:
        return self._block.video_params.subtitle_encoding or translate(
            "Subtitle Encoding", "Default"
        )

    @only_initialized
    def set_delay(self, delay_ms, is_silent=False):
        if not self.tracks:
            return

        delay_ms = min(max(delay_ms, MIN_SUBTITLE_DELAY_MS), MAX_SUBTITLE_DELAY_MS)

        self._block.video_params.subtitle_delay_ms = delay_ms
        self._block.video_driver.set_subtitle_delay(delay_ms)

        if not is_silent:
            self._block.info_change.emit(
                f"Subtitle delay: {subtitle_delay_txt(delay_ms)}"
            )

    @only_initialized
    def delay_increase(self):
        self.set_delay(
            self._block.video_params.subtitle_delay_ms + SUBTITLE_DELAY_STEP_MS
        )

    @only_initialized
    def delay_decrease(self):
        self.set_delay(
            self._block.video_params.subtitle_delay_ms - SUBTITLE_DELAY_STEP_MS
        )

    @only_initialized
    def delay_reset(self):
        self.set_delay(0)

    @only_initialized
    def delay_dialog(self):
        if not self.tracks:
            return

        dialog = SetSubtitleDelayDialog.for_video_block(
            self._block, parent=self._block.parent()
        )

        dialog.exec_()

    @only_initialized
    def get_delay(self):
        return subtitle_delay_txt(self._block.video_params.subtitle_delay_ms)
