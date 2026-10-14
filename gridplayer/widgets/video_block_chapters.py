"""The chapters of a video block.

Every jump is a seek to where a chapter starts, never libVLC's own
chapter calls: those move the time without seek() knowing, and a jump
back of any size then reads as the video having finished a pass, which
sets off the end action. A loop narrows everything down to itself, the
same as it does for the seek bar.
"""

from gridplayer.models.chapter import Chapter
from gridplayer.utils.chapters import (
    chapter_index_at,
    chapter_span,
    clean_chapters,
    is_site_length_playing,
    is_span_reachable,
    next_stop,
    previous_stop,
    span_at,
)
from gridplayer.utils.qt import translate
from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_initialized,
    only_seekable,
)


class ChapterControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # the file's chapters, or the site's where it has none, as far as
        # they are any use; see clean_chapters
        self._chapters: tuple[Chapter, ...] = ()

        # what the site a URL resolved on lists, for when the file lists
        # none; see update
        self._site_chapters: tuple[Chapter, ...] = ()

    @property
    def all(self) -> tuple[Chapter, ...]:
        return self._chapters

    def set_site_chapters(self, chapters: tuple[Chapter, ...]):
        """What the site lists, as the URL resolved; none for a video that
        may not be the one it was listed for."""

        self._site_chapters = chapters

    def update(self):
        block = self._block

        if not block.is_video_initialized or block.is_live:
            self._set(())
            return

        length = block.video_driver.length

        # the file's own are in the time the player keeps, where the site's
        # are only as good as the site's idea of what it is serving
        chapters = block.video_driver.chapters or self._site_chapters_playing(length)

        self._set(clean_chapters(chapters, length))

    def _site_chapters_playing(self, length: int) -> tuple[Chapter, ...]:
        """The site's chapters, if what plays is the video they were made for."""

        if not self._site_chapters:
            return ()

        site_length_ms = self._block.site_length_ms

        if not is_site_length_playing(length, site_length_ms):
            self._block._log.debug(
                f"Site chapters left out, the site says {site_length_ms}ms"
                f" but {length}ms is playing"
            )
            return ()

        return self._site_chapters

    def clear(self):
        """No chapters until update finds some, the seek bar told so."""

        self._set(())

    def _set(self, chapters: tuple[Chapter, ...]):
        self._chapters = chapters

        self._block.update_seek_marks()

    def name(self, index: int) -> str:
        name = self._chapters[index].name

        if name:
            return name

        return translate("Actions", "Chapter {NUMBER}").format(NUMBER=index + 1)

    @property
    def playing(self) -> int | None:
        """Which chapter the video is in, None before the first one starts."""

        if not self._chapters:
            return None

        return chapter_index_at(self._chapters, self._block.arriving_time)

    def is_reachable(self, index: int) -> bool:
        """Whether a jump to this chapter would land inside the loop."""

        block = self._block

        if not block.is_video_initialized or not 0 <= index < len(self._chapters):
            return False

        span = chapter_span(self._chapters, index, block.video_driver.length)

        return is_span_reachable(span, block.loop_start, block.loop_end)

    @only_initialized
    @only_seekable
    def next(self):
        block = self._block

        if not self._chapters:
            return

        stop_ms = next_stop(
            self._chapters, block.arriving_time, block.loop_start, block.loop_end
        )

        if stop_ms is None:
            # past the last chapter is the end, arriving early
            block.loop_end_action()
            return

        self._seek_stop(stop_ms)

    @only_initialized
    @only_seekable
    def previous(self):
        block = self._block

        if not self._chapters:
            return

        self._seek_stop(
            previous_stop(
                self._chapters, block.arriving_time, block.loop_start, block.loop_end
            )
        )

    @only_initialized
    @only_seekable
    def seek(self, index: int):
        if not self.is_reachable(index):
            return

        # a chapter the loop starts part way into is joined where it does
        self._seek_stop(max(self._chapters[index].start_ms, self._block.loop_start))

    def _seek_stop(self, stop_ms: int):
        self._block.seek(stop_ms)

        index = chapter_index_at(self._chapters, stop_ms)

        if index is not None:
            self._block.info_change.emit(self.name(index))

    @only_initialized
    @only_seekable
    def loop(self):
        """Loop the chapter the video is in, as a segment of its own."""

        block = self._block

        if not self._chapters:
            return

        length = block.video_driver.length

        start_ms, end_ms = span_at(self._chapters, block.arriving_time, length)

        # cleared first: the new start can lie past the old end
        block.reset_loop()

        block.set_loop_start_time(start_ms)

        # the last chapter runs to the end of the file, which is where an
        # unset end already is
        if end_ms < length:
            block.set_loop_end_time(end_ms)
