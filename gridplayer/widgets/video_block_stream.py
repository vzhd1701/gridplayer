"""What a video block plays of a link with several streams: which rung of
the quality ladder, fitted to the pane or picked by hand, in which of the
languages it is dubbed into, and handed to the stream proxy with what it
needs to fetch it again; and reloading a live one every so often.

The tracks of whatever was loaded are the audio part's (see AudioControl);
a dub served as a ladder of its own is here, as it takes a reload.
"""

import dataclasses
import time

from PyQt5.QtCore import QTimer

from gridplayer.dialogs.input_dialog import QCustomSpinboxInput
from gridplayer.models.audio_selection import (
    AudioDefault,
    AudioLanguage,
    AudioPreferred,
)
from gridplayer.models.stream import (
    STANDING_QUALITIES,
    STREAM_QUALITY_AUTO,
    HashableDict,
    StreamOrigin,
    Streams,
    short_quality_name,
)
from gridplayer.utils.qt import translate
from gridplayer.utils.video_errors import ProxyFailure
from gridplayer.vlc_player.static import MediaInput
from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_initialized,
    only_live,
    only_streamable,
)

# a pane that has to sit still for an hour before following its size is
# as good as one that never follows it at all
MAX_QUALITY_ADAPT_DELAY_S = 3600


class StreamControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # the proxy's URL of the stream, for what it was told fetching it,
        # and from when
        self._proxied_url: str | None = None
        self._loaded_at = 0.0

        # what was loaded, as opposed to what was asked for
        self._quality_playing = None
        self._audio_language_playing = None

        # whether what plays is opened by VLC's adaptive demuxer, the one
        # that turns seeks down; see SEEK_RETRIES in video_block
        self.is_adaptive = False

        self._adapt_timer = QTimer(block)
        self._adapt_timer.setSingleShot(True)
        self._adapt_timer.timeout.connect(self._adapt)

        self._reload_timer = QTimer(block)
        self._reload_timer.timeout.connect(block.reload)

    def stop_adapting(self):
        """Fit the stream to the pane no more: it is about to be loaded
        afresh, or let go of."""

        self._adapt_timer.stop()

    def proxy_failure(self) -> ProxyFailure | None:
        if self._proxied_url is None:
            return None

        failure = self._block._ctx.commands.stream_failure(self._proxied_url)

        if not isinstance(failure, ProxyFailure):
            return None

        # what it was told fetching it this time, not before
        if failure.at < self._loaded_at:
            return None

        return failure

    def quality_detail(self) -> str:
        """The stream picked, of a link with several.

        A link with one stream has nothing to pick, and what its one
        stream is called ("generic", "[0]", "9300k") is no news to anyone.
        The Quality menu is left out for it on the same grounds.
        """

        if len(self._block.streams) > 1 and self._quality_playing:
            return short_quality_name(self._quality_playing)

        return ""

    @only_streamable
    def adapt_delay_dialog(self):
        delay_sec = QCustomSpinboxInput.get_int(
            parent=self._block.parent(),
            title=translate(
                "Dialog - Set quality adapt delay", "Set quality adapt delay", "Header"
            ),
            initial_value=self._block.video_params.quality_adapt_delay_sec,
            _min=1,
            _max=MAX_QUALITY_ADAPT_DELAY_S,
        )

        self.set_adapt_delay(delay_sec)

    @only_streamable
    def set_adapt_delay(self, delay_sec):
        self._block.video_params.quality_adapt_delay_sec = delay_sec

        # a pane already waiting was counting to the old delay
        if self._adapt_timer.isActive():
            self._adapt_timer.start(self._adapt_delay_ms)

    @only_streamable
    def get_adapt_delay(self):
        return "{} {}".format(
            self._block.video_params.quality_adapt_delay_sec,
            translate("Quality Adapt Delay", "second(s)"),
        )

    @only_initialized
    @only_live
    def reload_timer_dialog(self):
        time_min = QCustomSpinboxInput.get_int(
            parent=self._block.parent(),
            title=translate(
                "Dialog - Set auto reload timer", "Set auto reload timer", "Header"
            ),
            special_text=translate("Auto Reload Timer", "Disabled"),
            initial_value=self._block.video_params.auto_reload_timer_min,
            _min=0,
            _max=1000,
        )

        self.set_reload_timer(time_min)

    @only_initialized
    @only_live
    def set_reload_timer(self, time_min):
        self._block.video_params.auto_reload_timer_min = time_min

        time_ms = time_min * 60 * 1000

        if time_ms == 0:
            self._reload_timer.stop()
            self._reload_timer.setInterval(0)
            return

        self._reload_timer.setInterval(time_ms)
        self._reload_timer.start()

    @only_initialized
    @only_live
    def get_reload_timer(self):
        if self._block.video_params.auto_reload_timer_min == 0:
            return translate("Auto Reload Timer", "Disabled")

        return "{} {}".format(
            self._block.video_params.auto_reload_timer_min,
            translate("Auto Reload Timer", "minute(s)"),
        )

    @property
    def audio_language_playing(self) -> str | None:
        """Which of the languages on offer the rung on screen was loaded for."""

        return self._audio_language_playing

    @property
    def _language_variants(self) -> Streams:
        """Where this video's languages live, out of the two places they can.

        A site either dubs a video by handing back the whole ladder once
        per language, or by offering one ladder and several audio tracks
        to pair with it. Either way it is a set of streams that differ in
        nothing but the language of their sound.
        """

        if not self._block.streams:
            return Streams()

        if self._block.streams.is_multilingual:
            return self._block.streams

        audio_tracks = next(
            (
                stream.audio_tracks
                for _, stream in self._block.streams.items()
                if stream.audio_tracks
            ),
            None,
        )

        return audio_tracks or Streams()

    @property
    def audio_language_options(self) -> tuple[str, ...]:
        """The languages this video is dubbed into, as the site offered them."""

        return self._language_variants.languages

    @property
    def audio_language(self) -> str | None:
        """Which language this video plays, out of the several it is dubbed into.

        Nothing to choose between leaves this empty, and so does a video
        whose sound names no language at all.
        """

        return self._language_among(self._language_variants)

    def _language_among(self, variants: Streams) -> str | None:
        """Which of these languages the sound asked for comes to."""

        if not variants.is_multilingual:
            return None

        selection = self._block.video_params.audio_selection

        if isinstance(selection, AudioLanguage) and selection.tag in variants.languages:
            return selection.tag

        if isinstance(selection, AudioDefault):
            # the languages asked for do not apply to the video's own sound,
            # which is the language it was made in
            return variants.language_for("")

        return variants.language_for(self._block.video_params.audio_languages)

    @property
    def preferred_audio_language(self) -> str | None:
        """Which language the preference alone would settle on.

        What is playing may be a pick made by hand instead, so this is the
        only way to say what going back to the preference would give.
        """

        return self._language_variants.language_for(
            self._block.video_params.audio_languages
        )

    @property
    def ladder(self) -> Streams:
        """The rungs this video may switch between, all in the one language."""

        return self._block.streams.for_language(self.audio_language)

    @only_streamable
    def set_audio_language(self, language: str | None):
        """Play the same video in another one of the languages it is dubbed into.

        The ladder is a different one per language, so the rung has to be
        found again; asking for the one playing now finds the same size.
        """

        self._block.video_params.audio_selection = (
            AudioPreferred() if language is None else AudioLanguage(tag=language)
        )

        self._block._log.debug(
            f"Set audio language {language},"
            f" resolved to {self.audio_language},"
            f" playing {self._audio_language_playing}"
        )

        self.follow_audio_language()

    def follow_audio_language(self):
        """Put the sound asked for into effect, in whichever dub it calls for.

        A dubbed stream is served one language at a time, so another one
        means fetching the ladder again rather than reaching for a track
        that was never handed over.
        """

        if (
            not self._block.streams
            or self.audio_language == self._audio_language_playing
        ):
            # the rung on screen already carries it, so there is nothing to
            # reload -- but the sound may have been switched off since it
            # was loaded, and asking for a language means wanting it
            self._block.audio.apply_wanted_track()
            return

        # the pane is about to be reloaded anyway, and on a ladder that no
        # longer holds the rung the timer was comparing against
        self._adapt_timer.stop()

        self._block.reset(is_link_kept=True)

        self.load_quality(self._block.video_params.stream_quality)

    @only_streamable
    def switch_quality(self, quality: str):
        if quality == self._block.video_params.stream_quality:
            return

        # picking a rung by hand calls off whatever the pane was about to do
        self._adapt_timer.stop()

        self._block.reset(is_link_kept=True)

        self.load_quality(quality)

    @property
    def quality_playing(self) -> str | None:
        """Which rung of the ladder is on screen, as opposed to what was asked."""

        return self._quality_playing

    def load_quality(self, wanted_quality: str):
        is_auto = wanted_quality == STREAM_QUALITY_AUTO

        ladder = self.ladder

        self._audio_language_playing = self.audio_language

        if is_auto:
            quality, stream = ladder.fit_to_height(self._pane_height_px)
        else:
            quality, stream = ladder.by_quality(wanted_quality)

        # a standing instruction outlives the rung it picked, where a rung
        # chosen by name is kept as the name it was chosen by
        self._block.video_params.stream_quality = (
            wanted_quality if wanted_quality in STANDING_QUALITIES else quality
        )
        self._quality_playing = quality

        # switching quality resets the block, which leaves it without a driver
        self._block._ensure_video_driver()

        if stream.protocol == "direct":
            url = stream.url
            self._proxied_url = None
        else:
            stream = self._with_audio_language(stream)
            url = self._block._ctx.commands.add_stream(
                self._with_origin(stream, quality)
            )
            self._proxied_url = url if isinstance(url, str) else None

        self._loaded_at = time.monotonic()

        self.is_adaptive = stream.is_adaptive

        self._block.status.show_opening()

        self._block.load_video.emit(
            MediaInput(
                uri=url,
                is_live=self._block.is_live,
                is_audio_only=stream.is_audio_only,
                video_codec=stream.video_codec,
                is_adaptive=stream.is_adaptive,
                size=self._block.size_tuple,
                video=self._block.video_params,
                # the proxy fetches the rest with them already
                http_headers=(
                    self._block._item_headers if stream.protocol == "direct" else {}
                ),
            )
        )

    @property
    def _adapt_delay_ms(self) -> int:
        """How long a pane has to keep its new size before the stream follows.

        Dragging a window edge resizes every pane dozens of times on the way,
        and every switch costs a reload, so the size has to settle down first.
        """

        return max(self._block.video_params.quality_adapt_delay_sec, 1) * 1000

    @property
    def _pane_height_px(self) -> int:
        """How tall this pane is in the pixels a screen actually has.

        The widget measures itself in the logical pixels Qt scales, so on a
        200% display a pane reports half the detail it can really show.
        """

        return int(self._block.height() * self._block.devicePixelRatioF())

    def schedule_adapt(self):
        if self._block.video_params is None or not self._block.streams:
            return

        if self._block.video_params.stream_quality != STREAM_QUALITY_AUTO:
            return

        self._adapt_timer.start(self._adapt_delay_ms)

    def _adapt(self):
        """Fit the stream to the size the pane has settled on."""

        if (
            self._block.is_closing
            or self._block.video_params is None
            or not self._block.streams
        ):
            return

        if self._block.video_params.stream_quality != STREAM_QUALITY_AUTO:
            return

        if self._block.is_error:
            # a video that is already failing has the retry timer looking
            # after it, and reloading underneath that would only confuse it
            return

        if self._block._is_state_change_in_progress:
            self._adapt_timer.start(self._adapt_delay_ms)
            return

        quality, _ = self.ladder.fit_to_height(self._pane_height_px)

        if quality == self._quality_playing:
            return

        self._block._log.debug(
            f"Pane now fits {quality}, switching from {self._quality_playing}"
        )

        self._block.reset(is_link_kept=True)

        self.load_quality(STREAM_QUALITY_AUTO)

    def _with_audio_language(self, stream):
        """Hand the proxy only the audio tracks in the language being played.

        VLC is served a playlist with one audio rendition in it, so which
        of them it is has to be settled here; the proxy is left to pick
        the best of whatever it is given.
        """

        if not stream.audio_tracks:
            return stream

        language = self._language_among(stream.audio_tracks)

        if language is None:
            return stream

        return dataclasses.replace(
            stream, audio_tracks=stream.audio_tracks.for_language(language)
        )

    def _with_origin(self, stream, quality: str):
        """Tell the proxy where this stream came from.

        Services sign the URLs they hand out and stop honouring them after a
        while, so the proxy has to be able to ask for them again rather than
        serve a video that dies partway through.
        """

        origin = StreamOrigin(
            url=str(self._block.video_params.uri),
            quality=quality,
            headers=HashableDict(self._block._item_headers) or None,
        )

        return dataclasses.replace(stream, origin=origin)
