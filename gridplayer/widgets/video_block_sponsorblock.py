"""What SponsorBlock's users marked in a video block's YouTube video.

Its segments are no chapters: they overlap the chapters, leave gaps
between one another, and are nowhere to jump to. They are marked on the
bar in a look of their own, and some are skipped.
"""

import contextlib

from gridplayer.models.sponsor_segment import SponsorSegment
from gridplayer.params.sponsorblock import category_name
from gridplayer.params.static import SponsorBlockMode
from gridplayer.utils.chapters import is_site_length_playing
from gridplayer.utils.qt import translate
from gridplayer.utils.sponsorblock import (
    SKIP_END_MARGIN_MS,
    SKIP_MIN_MS,
    SkipSpan,
    category_modes,
    is_sponsorblock_enabled,
    skip_span_at,
    skip_spans,
    sponsorblock_fetcher,
)
from gridplayer.widgets.video_block_guards import VideoBlockPart


class SponsorBlockControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # every segment SponsorBlock's users marked in the video, the one
        # the block's youtube_id is; see update
        self._segments: tuple[SponsorSegment, ...] = ()

        # the ones the settings mark on the seek bar, and the stretches they
        # skip, each as far as the video playing is the one they were for
        self._shown_segments: tuple[SponsorSegment, ...] = ()
        self._skip_spans: tuple[SkipSpan, ...] = ()

        # a stretch to be skipped that the viewer went into, or the one just
        # skipped, left to play until the time is out of it
        self._span_left_alone: SkipSpan | None = None

        sponsorblock_fetcher().fetched.connect(self._fetched)

    @property
    def shown_segments(self) -> tuple[SponsorSegment, ...]:
        """The segments the seek bar marks."""

        return self._shown_segments

    def stop_listening(self):
        """The lookup outlives the video, it answers every one of them."""

        with contextlib.suppress(TypeError):
            sponsorblock_fetcher().fetched.disconnect(self._fetched)

    def apply_settings(self):
        """Take up a change to the settings: to what is looked up, or to what
        is done with what was found."""

        self.look_up()
        self.update()

    def look_up(self):
        """Ask SponsorBlock about the video, if it is one to ask about."""

        youtube_id = self._block.youtube_id
        site_length_ms = self._block.site_length_ms

        if youtube_id is None or site_length_ms <= 0:
            return

        if not is_sponsorblock_enabled():
            return

        segments = sponsorblock_fetcher().fetch(youtube_id, site_length_ms)

        # on their way otherwise, see _fetched
        if segments is not None:
            self._set(segments)

    def _fetched(self, video_id: str, segments):
        # another video's, or the one before this video was switched
        if video_id != self._block.youtube_id:
            return

        self._set(segments)

    def _set(self, segments: tuple[SponsorSegment, ...]):
        self._segments = segments

        self.update()

    def forget(self):
        """Let go of everything found: the video may not be the one it was
        found for."""

        self._segments = ()
        self.forget_shown()

    def forget_shown(self):
        """Mark and skip nothing until update says to again."""

        self._shown_segments = ()
        self._skip_spans = ()
        self._span_left_alone = None

    def update(self):
        """Work out which of the segments to mark, and what to skip."""

        segments = self._playing()

        modes = category_modes()

        self._shown_segments = tuple(
            segment
            for segment in segments
            if modes[segment.category] is not SponsorBlockMode.OFF
        )
        self._skip_spans = skip_spans(segments, modes)

        self._block.update_seek_marks()

    def _playing(self) -> tuple[SponsorSegment, ...]:
        """The segments, if what plays is the video they were marked on."""

        block = self._block

        if not self._segments or not is_sponsorblock_enabled():
            return ()

        if not block.is_video_initialized or block.is_live:
            return ()

        length = block.video_driver.length
        site_length_ms = block.site_length_ms

        if not is_site_length_playing(length, site_length_ms):
            block._log.debug(
                f"SponsorBlock segments left out, the site says"
                f" {site_length_ms}ms but {length}ms is playing"
            )
            return ()

        return self._segments

    def note_seek(self, seek_ms: int, is_viewers: bool):
        """A seek of the viewer's into a stretch to be skipped is them choosing
        to watch it: it is left alone until the time is out of it."""

        self._span_left_alone = (
            skip_span_at(self._skip_spans, seek_ms) if is_viewers else None
        )

    def skip_if_played_into(self):
        """Pass over a stretch set to be skipped, if the video played into one.

        Played into it, not put there: a seek into one is the viewer choosing
        to watch it, and it is left alone until the time is out of it. Never
        from a seek still landing either, which time_changed has already seen
        to: that is seconds short of where it is going on a stream, and could
        be inside a stretch the seek was made to get past.
        """

        block = self._block

        span = skip_span_at(self._skip_spans, block.time)

        if span is None:
            self._span_left_alone = None
            return

        if span == self._span_left_alone or block.video_params.is_paused:
            return

        if span.end_ms - block.time < SKIP_MIN_MS:
            return

        is_to_end = span.end_ms >= block.loop_end - SKIP_END_MARGIN_MS

        # one that takes up the whole of what is played would only take the
        # video round to the start of it again, which is back inside it
        if is_to_end and span.start_ms <= block.loop_start:
            return

        block._log.debug(f"Skipping {span.category} from {block.time} to {span.end_ms}")

        block.info_change.emit(
            translate("SponsorBlock", "Skipped: {CATEGORY}").format(
                CATEGORY=category_name(span.category)
            )
        )

        # One that runs to the end of the pass ends it, whatever that means
        # for this video: another pass, the next file, a stop. A seek right
        # into the end is also where a seek on a stream is least reliable.
        if is_to_end:
            block.loop_end_action()
            return

        block.seek(span.end_ms, is_viewers=False)

        # VLC reports where a seek landed a hair short, inside it still
        self._span_left_alone = span
