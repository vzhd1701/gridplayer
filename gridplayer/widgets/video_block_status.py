"""What a video block says over its cell while there is no video to show:
how far it got loading, what went wrong and why, and which of the overlay's
faces goes with that.

When to fail and what comes after is the block's and its recovery's (see
VideoBlock.error and RecoveryControl); this is how it is shown.
"""

from datetime import datetime, timezone

from gridplayer.dialogs.error_details import (
    DetailRows,
    ErrorDetailsDialog,
    code_rows,
)
from gridplayer.utils.list_errors import ReadErrorKind
from gridplayer.utils.qt import translate
from gridplayer.utils.video_errors import (
    ShownError,
    file_error,
    player_error,
    proxy_error,
)
from gridplayer.widgets.video_block_guards import VideoBlockPart
from gridplayer.widgets.video_overlay import OverlayMode
from gridplayer.widgets.video_status import LoadStage, StepState, step_label


class StatusControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # how far it got loading: the stage it is at, and the ones it goes
        # through
        self.load_stage: LoadStage | None = None
        self.load_steps: tuple[LoadStage, ...] = ()

        # what went wrong last; the stage it went wrong at and how many times
        # it was tried, for its Details
        self.last_error: ShownError | None = None
        self._error_stage: LoadStage | None = None
        self._error_tries = 0

        # the loading status left over a video just loaded until there is a
        # picture of it on show, see VideoFrameVLC.is_picture_pending
        self.is_kept_for_picture = False

    def resolve_failed(self, error: ShownError):
        self.last_error = error
        self.set_text(error.title)

    def player_error(self, message: str, vlc_lines: tuple[str, ...]) -> ShownError:
        """Why VLC could not play it: the file gone, what the proxy was
        told fetching the stream, or what VLC said."""

        uri = self._block.video_params.uri

        if self._block.video_params.is_local_file:
            if not uri.exists():
                return file_error(ReadErrorKind.MISSING, uri)

            return player_error(message, vlc_lines)

        failure = self._block.stream.proxy_failure()

        if failure is not None:
            return proxy_error(failure, vlc_lines)

        return player_error(message, vlc_lines, url=str(uri))

    def show_error_card(self, tries: int = 0):
        """Why it failed, on the cell: in a few words, what that means,
        the tag of where it broke, and what comes next; tries, the reloads
        made of it before it was left at that, for its Details."""

        self._error_tries = tries

        error = self.last_error

        # not what the status said last: that is how far it loaded
        if error is None:
            error = ShownError(title=translate("Video Error", "Can't play the video"))
            self.last_error = error

        # where it got to, kept for its Details; the next load starts afresh
        self._error_stage = self.load_stage
        self.load_stage = None

        self._block.video_status.show_error(error, self._block.recovery.skip_note())
        self.sync_overlay_mode()

    def show_error_details(self):
        """Everything known of why it failed, in a window of its own."""

        error = self.last_error

        if error is None:
            return

        # held while it is read, for its Try Again to be for this item and
        # not the one the list would have gone on to meanwhile
        is_skipping = self._block.recovery.is_skip_counting
        self._block.recovery.stop_skip()
        self._block.recovery.refresh_skip_note()

        dialog = ErrorDetailsDialog(
            error, self._error_rows(error), parent=self._block.window()
        )
        dialog.try_again.connect(self._block.reload)
        dialog.exec_()
        dialog.deleteLater()

        # left as it was: on through the list, the count started over
        if is_skipping and self.last_error is error and not self._block.is_closing:
            self._block.recovery.start_skip_count()
            self._block.recovery.refresh_skip_note()

    def _error_rows(self, error: ShownError) -> DetailRows:
        """What its Details window says of the video besides."""

        uri = self._block.video_params.uri

        # a link named by itself is said once, as the link
        rows = []

        if self._block.title and self._block.title != str(uri):
            rows.append((translate("Error Details", "Video"), self._block.title))

        media_list = self._block.media_list

        if media_list is not None:
            name = media_list.name or translate("Error Details", "List")
            place = self._block.navigation.place()

            if place is not None and place.is_found:
                name = translate("Error Details", "{LIST}, {PLACE} of {COUNT}").format(
                    LIST=name, PLACE=place.index + 1, COUNT=len(media_list.items)
                )

            rows.append((translate("Error Details", "List"), name))

        if self._block.video_params.is_local_file:
            rows.append((translate("Error Details", "File"), str(uri)))
        else:
            rows.append((translate("Error Details", "Link"), str(uri)))

        step = {
            LoadStage.LIST: translate("Error Details", "Reading the list"),
            LoadStage.LINK: translate("Error Details", "Resolving the link"),
            LoadStage.VIDEO: translate("Error Details", "Opening the video"),
            LoadStage.RECONNECT: translate("Error Details", "Opening the video"),
        }.get(self._error_stage)

        if step:
            rows.append((translate("Error Details", "Step"), step))

        rows.extend(code_rows(error))

        if self._error_tries:
            limit = self._block.recovery.retry_limit

            if limit > 0:
                tries = translate("Error Details", "{COUNT} of {LIMIT}").format(
                    COUNT=self._error_tries, LIMIT=limit
                )
            else:
                tries = str(self._error_tries)

            rows.append((translate("Error Details", "Tries"), tries))

        rows.append(
            (
                translate("Error Details", "When"),
                datetime.fromtimestamp(error.at, tz=timezone.utc)
                .astimezone()
                .strftime("%H:%M:%S"),
            )
        )

        return tuple(rows)

    def show(self, status):
        self.is_kept_for_picture = False

        self._block._hide_video_driver()

        self._block.video_status.icon = status
        self._block.video_status.show()

        # still there, to close the cell or stop it, now for what it shows,
        # and painted so along with the status: a reload lets the old player
        # go before the event loop comes round to paint it
        self.sync_overlay_mode()
        self._block.overlay.lay_out_now()

        self._block.repaint()

        # a window of its own is not painted along with the cell
        if self._block.overlay.isWindow() and self._block.overlay.isVisible():
            self._block.overlay.repaint()

    def _overlay_mode(self) -> OverlayMode:
        if self._block.is_error:
            return OverlayMode.ERROR

        if self._block.is_stopped:
            return OverlayMode.STOPPED

        # the status over the cell, whatever player is still behind it, as
        # a reload says so before the old one is gone
        is_status_shown = not self._block.video_status.isHidden()

        if self._block.is_loading or self.is_kept_for_picture or is_status_shown:
            return OverlayMode.LOADING

        return OverlayMode.VIDEO

    def sync_overlay_mode(self):
        mode = self._overlay_mode()

        if mode is OverlayMode.ERROR:
            self._block.overlay.set_error_actions(
                has_details=self.last_error is not None,
                can_go_next=self._block.recovery.can_skip,
                is_going_back=self._block.recovery.is_going_back,
            )

        self._block.overlay.set_mode(mode)
        self._block.overlay.set_is_on_chrome(mode is not OverlayMode.VIDEO)

    def set_text(self, info_text):
        self._block.video_status.status_text = translate("Video Status", info_text)
        self._block.video_status.percent = 0

    def show_stage(
        self,
        stage: LoadStage,
        text: str,
        detail: str = "",
        percent: int | None = None,
    ):
        """Loading, at this stage of it, and where that is among the ones
        it goes through."""

        self.load_stage = stage

        self._block.video_status.show_loading(
            stage, text, detail, percent, steps=self._steps_at(stage)
        )

    def _steps_at(self, stage: LoadStage) -> tuple[tuple[str, StepState], ...]:
        steps = self.load_steps

        if stage not in steps or len(steps) < 2:
            return ()

        at = steps.index(stage)

        return tuple(
            (
                step_label(step),
                StepState.DONE
                if index < at
                else StepState.CURRENT
                if index == at
                else StepState.TODO,
            )
            for index, step in enumerate(steps)
        )

    def on_resolving(self, name: str):
        self.show_resolving_link(name)

    def show_resolving_link(self, resolver: str = ""):
        self.show_stage(
            LoadStage.LINK,
            translate("Video Status", "Resolving the link…"),
            resolver,
        )

    def on_link_list_reading(self, said: str):
        """The link turned out to be a list, read as it is."""

        self.load_steps = (LoadStage.LINK, LoadStage.LIST, LoadStage.VIDEO)
        self.show_stage(LoadStage.LIST, said)

    def on_driver_status(self, status: str, percent: int = 0):
        """What the player says as it opens the video, said plainly."""

        if status in {"Buffering", translate("Video Status", "Buffering")}:
            self.show_stage(
                LoadStage.VIDEO,
                translate("Video Status", "Buffering {PERCENT}%").format(
                    PERCENT=percent
                ),
                self._block.stream.quality_detail(),
                percent,
            )
            return

        self.show_opening()

    def show_opening(self):
        self.show_stage(
            LoadStage.VIDEO,
            translate("Video Status", "Opening…"),
            self._block.stream.quality_detail(),
        )

    def show_load_start(self):
        """The first stage of a load begun afresh: its link, or its video."""

        is_link = self._block.video_params.is_http_url
        self.load_steps = (*((LoadStage.LINK,) if is_link else ()), LoadStage.VIDEO)

        if is_link:
            self.show_resolving_link()
        else:
            self.show_opening()

    def on_waiting_progress(self, video_id, text: str, percent: int = 0):
        if (
            self._block.video_params is not None
            and self._block.video_params.id == video_id
        ):
            self.show_stage(LoadStage.LIST, text, percent=percent or None)
