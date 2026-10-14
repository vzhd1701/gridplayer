"""Screenshots of a video block: the frame asked of the player, and the file
it is saved into off the GUI thread."""

from datetime import datetime
from functools import partial

from gridplayer.settings import Settings
from gridplayer.utils.qt import qt_connect, translate
from gridplayer.utils.screenshots import (
    ScreenshotJob,
    ScreenshotName,
    remove_frame_file,
    screenshots_dir,
)
from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_initialized,
    only_with_video_tacks,
)


class ScreenshotControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # held until they are done, the pool only has the C++ side of them
        self._jobs: set[ScreenshotJob] = set()
        self._is_quiet = False

    @only_initialized
    @only_with_video_tacks
    def take(self, is_quiet=False):
        # Every video at once would be a warning box per video that fails,
        # one on top of the other, and all for the same reason more often
        # than not. Quiet says so on the video's overlay instead.
        self._is_quiet = is_quiet

        self._block.video_driver.take_screenshot()

    def taken(self, frame, view):
        if frame is None:
            self._report_failure(
                translate("Warning", "There is no video frame to take a screenshot of")
            )
            return

        try:
            name = ScreenshotName(
                template=Settings().get("screenshots/filename_template"),
                title=self._block.title or self._block.video_params.uri_name,
                position_ms=0 if self._block.is_live else (self._block.time or 0),
                now=datetime.now().astimezone(),
            )

            job = ScreenshotJob(
                source=frame,
                directory=screenshots_dir(Settings().get("screenshots/dir")),
                name=name,
                image_format=Settings().get("screenshots/format"),
                jpg_quality=Settings().get("screenshots/jpg_quality"),
                view=view,
            )
        except Exception:
            if isinstance(frame, str):
                remove_frame_file(frame)
            raise

        qt_connect(
            (job.saved, self._saved),
            (job.failed, self._failed),
            (job.saved, partial(self._jobs.discard, job)),
            (job.failed, partial(self._jobs.discard, job)),
        )

        self._jobs.add(job)
        job.start()

    def _saved(self, _path):
        self._block.show_overlay()
        self._block.info_change.emit(translate("Screenshot", "Screenshot saved"))

    def _failed(self, error):
        self._report_failure(
            translate("Warning", "Could not save the screenshot"), error
        )

    def _report_failure(self, message, detail=""):
        if self._is_quiet:
            self._block.show_overlay()
            self._block.info_change.emit(translate("Screenshot", "Screenshot failed"))
            return

        self._block._ctx.commands.warning(
            f"{message}\n\n{detail}" if detail else message
        )
