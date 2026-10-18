"""What of its picture a video block shows: zoomed, cropped, moved, and
the same as another video shows of its own, where views are synced."""

from PyQt5.QtCore import QRect, QRectF
from PyQt5.QtGui import QCursor

from gridplayer.params.static import (
    VideoAnchor,
    VideoCellViewMode,
    VideoCrop,
    VideoShift,
    ViewParams,
)
from gridplayer.utils.aspect_calc import SyncedView
from gridplayer.utils.step_sizes import zoom_stepped
from gridplayer.widgets.video_block_guards import (
    VideoBlockPart,
    only_initialized,
    only_with_video_tacks,
)


class ViewControl(VideoBlockPart):
    def __init__(self, block):
        super().__init__(block)

        # the part of the picture being selected to zoom to, while it is
        self._zoom_selection: QRect | None = None
        # how to select one, said once Zoom to Selection is picked
        self._is_zoom_hint_shown = False
        # where the picture stands is a zoom to a selection's doing, which
        # the zoom's reset undoes along with it
        self._is_zoomed_to_selection = False
        # another video's view, to show once this one is playing
        self._view_to_follow: SyncedView | None = None

    @only_with_video_tacks
    @only_initialized
    def scale_increase(self):
        self._zoom_to(zoom_stepped(self._block.video_params.scale, 1))

    @only_with_video_tacks
    @only_initialized
    def scale_decrease(self):
        self._zoom_to(zoom_stepped(self._block.video_params.scale, -1))

    @only_with_video_tacks
    @only_initialized
    def scale_reset(self):
        """Back to the whole picture, and, zoomed about the pointer or to a
        selection, back in its place: where it stands then is the zooms'
        doing, not a move."""

        if self._block.video_params.is_zoom_to_cursor or self._is_zoomed_to_selection:
            self._set_zoom(1.0, VideoShift(0, 0))
        else:
            self.set_scale(1.0)

        self._is_zoomed_to_selection = False

    @only_with_video_tacks
    @only_initialized
    def set_scale(self, scale, is_silent=False):
        self._block.video_params.scale = scale

        self._block.video_driver.set_scale(scale)

        if not is_silent:
            self._block.info_change.emit(f"Zoom: {scale}")

    def _zoom_to(self, scale):
        """Zoom about the pointer where this video zooms to it, else as usual."""

        focus = self._zoom_focus()

        if focus is None or scale == self._block.video_params.scale:
            self.set_scale(scale)
            return

        self._set_zoom(scale, self._block.video_driver.zoomed_shift(scale, focus))

    def _set_zoom(self, scale, shift: VideoShift):
        self._block.video_params.scale = scale
        self._block.video_params.shift = shift

        self._block.video_driver.set_zoom(scale, shift)

        self._block.info_change.emit(f"Zoom: {scale}")

    def _zoom_focus(self) -> tuple[int, int] | None:
        """Where in the pane a zoom goes about, None for the anchor's place.

        The pointer, where this video zooms to it and it is over the video.
        A zoom picked from the context menu goes about where the menu was
        opened, the pointer being on the menu's item by then.
        """

        block = self._block

        if not block.video_params.is_zoom_to_cursor or not block.isVisible():
            return None

        pointer = getattr(block._ctx, "context_menu_pos", None)

        if pointer is None:
            pointer = QCursor.pos()

        if not block.rect().contains(block.mapFromGlobal(pointer)):
            return None

        focus = block.video_driver.mapFromGlobal(pointer)

        return focus.x(), focus.y()

    @only_with_video_tacks
    @only_initialized
    def zoom_to_selection(self, selection: QRect):
        """Fit a part of the picture into the cell, in its middle.

        The part is in this cell's pixels, where it was selected over the
        picture as drawn; see VideoFrameVLC.selection_zoom.
        """

        video_driver = self._block.video_driver

        origin = video_driver.pos()
        zoom = video_driver.selection_zoom(
            (
                selection.x() - origin.x(),
                selection.y() - origin.y(),
                selection.width(),
                selection.height(),
            )
        )

        if zoom is None:
            return

        self._is_zoomed_to_selection = True
        self._set_zoom(*zoom)

    def zoom_selection_area(self) -> QRect | None:
        """Where in this cell a part of the picture can be selected to zoom
        to: over the picture as drawn. None where there is none on show."""

        block = self._block

        if not block.is_video_initialized or not block.video_tracks:
            return None

        area = block.video_driver.shown_picture_area()

        if area is None:
            return None

        x, y, width, height = area
        origin = block.video_driver.pos()

        return (
            QRectF(x + origin.x(), y + origin.y(), width, height)
            .toAlignedRect()
            .intersected(block.rect())
        )

    def show_zoom_selection(self, selection: QRect | None):
        """Mark the part of the picture being selected to zoom to.

        On the overlay, with its chrome out of the way, and shown even where
        it is off or the cell is too small for it. In place of the hint,
        which it says all of. None once the selecting is over, which puts
        the overlay back the way it would be.
        """

        was_zoom_ui = self.is_zoom_ui()

        if selection is not None:
            self._zoom_selection = QRect(selection)
            self._is_zoom_hint_shown = False

            self._block.overlay.set_zoom_hint(False)
            self._block.overlay.set_zoom_selection(selection)
        elif self._zoom_selection is not None:
            self._zoom_selection = None

            self._block.overlay.set_zoom_selection(None)

        self._zoom_ui_changed(was_zoom_ui)

    def show_zoom_hint(self, is_shown: bool):
        """Say how to select a part of the picture to zoom to, or not.

        Once Zoom to Selection is picked, until the selecting starts, on
        the overlay as the selection itself is (see show_zoom_selection).
        """

        if is_shown == self._is_zoom_hint_shown:
            return

        was_zoom_ui = self.is_zoom_ui()
        self._is_zoom_hint_shown = is_shown

        self._block.overlay.set_zoom_hint(is_shown)

        self._zoom_ui_changed(was_zoom_ui)

    def is_zoom_ui(self) -> bool:
        """The overlay shows a selection to zoom to, or how to make one."""

        return self._zoom_selection is not None or self._is_zoom_hint_shown

    def _zoom_ui_changed(self, was_zoom_ui: bool):
        """The overlay shown for zooming to a selection, with that alone on
        it, or put back the way it would be once it is done with."""

        block = self._block

        if self.is_zoom_ui() == was_zoom_ui:
            return

        if self.is_zoom_ui():
            block.overlay_hide_timer.stop()
            block.overlay.set_is_chrome_visible(False)
            block.overlay.show()
            return

        block.overlay.set_is_chrome_visible(not block._ctx.is_drag_ui)

        if block._ctx.is_disable_overlay or not block.is_overlay_fits:
            block.overlay_hide_timer.stop()
            block.overlay.hide()
            return

        block.show_overlay()

    @only_with_video_tacks
    @only_initialized
    def sync_others(self):
        """Have the others show the part of their pictures this one shows."""

        synced = self.synced()

        if synced is not None:
            self._block.sync_view_single.emit(synced)

    def synced(self) -> SyncedView | None:
        """This video's view, for the others to follow; None for none."""

        block = self._block

        if not block.is_video_initialized or not block.video_tracks:
            return None

        shared = block.video_driver.shared_view()

        if shared is None:
            return None

        return SyncedView(shared, self._is_zoomed_to_selection)

    def follow(self, synced: SyncedView):
        """Show the part of the picture another video shows of its own.

        Quietly, the other saying what it shows. One that is not playing yet
        shows it once it is (see load_video_finish), and one waiting for its
        frame's size once that is known (see VideoFrameVLC.follow_view).
        """

        block = self._block

        if not block.is_video_initialized:
            self._view_to_follow = synced
            return

        if not block.video_tracks:
            return

        self._is_zoomed_to_selection = synced.is_zoomed_to_selection

        view = block.video_driver.follow_view(synced.view)

        if view is not None:
            self.remember_followed(view)

    def remember_followed(self, view: ViewParams):
        video_params = self._block.video_params

        video_params.scale = view.scale
        video_params.anchor = view.anchor
        video_params.shift = view.shift

    def follow_synced(self):
        """Show the view this one was to follow once playing, or else the
        one the videos are synced to, having just loaded."""

        synced = self._view_to_follow or getattr(self._block._ctx, "synced_view", None)
        self._view_to_follow = None

        if synced is not None:
            self.follow(synced)

    def forget_view_to_follow(self):
        """Let go of another video's view this one was to show once playing:
        one of its own is to be shown instead."""

        self._view_to_follow = None

    @only_with_video_tacks
    @only_initialized
    def toggle_zoom_to_cursor(self):
        self.set_zoom_to_cursor(not self._block.video_params.is_zoom_to_cursor)

    def set_zoom_to_cursor(self, is_zoom_to_cursor: bool):
        """Zoom about the point under the pointer, or about the anchor's.

        Kept for a video stopped or still loading too: nothing but a zoom
        looks at it, and that is only made with a picture on show.
        """

        self._block.video_params.is_zoom_to_cursor = is_zoom_to_cursor

    @only_with_video_tacks
    def set_cell_view_mode(self, mode: VideoCellViewMode):
        self._block.video_params.cell_view_mode = mode

        self._block.video_driver.set_cell_view_mode(mode)

    @only_with_video_tacks
    @only_initialized
    def crop(self, left, top, right, bottom, is_silent=False):
        video_params = self._block.video_params

        crop = VideoCrop(
            video_params.crop.Left + left,
            video_params.crop.Top + top,
            video_params.crop.Right + right,
            video_params.crop.Bottom + bottom,
        )

        self.set_crop(crop, is_silent)

    @only_with_video_tacks
    @only_initialized
    def crop_reset(self, is_silent=False):
        self.set_crop(VideoCrop(0, 0, 0, 0), is_silent)

    @only_with_video_tacks
    @only_initialized
    def set_crop(self, crop: VideoCrop, is_silent=False):
        video_params = self._block.video_params

        crop = VideoCrop(
            max(crop.Left, 0),
            max(crop.Top, 0),
            max(crop.Right, 0),
            max(crop.Bottom, 0),
        )

        if video_params.crop != crop:
            video_params.crop = crop
            self._block.video_driver.set_crop(video_params.crop)

        if not is_silent:
            self._block.info_change.emit(
                "Crop: L{} T{} R{} B{}".format(*video_params.crop)
            )

    @only_with_video_tacks
    @only_initialized
    def set_anchor(self, anchor: VideoAnchor):
        """Put the picture against a side or corner, or in the middle.

        Picking one is putting the picture there, so a move made from the
        one before is let go of.
        """

        self._block.video_params.anchor = anchor
        self._block.video_driver.set_anchor(anchor)

        self.set_shift(VideoShift(0, 0), is_silent=True)
        self._is_zoomed_to_selection = False

    @only_with_video_tacks
    @only_initialized
    def set_shift(self, shift: VideoShift, is_silent=False):
        video_params = self._block.video_params

        if video_params.shift != shift:
            video_params.shift = shift
            self._block.video_driver.set_shift(shift)

        if not is_silent:
            self._block.info_change.emit("Position: X{} Y{}".format(*shift))

    @only_with_video_tacks
    @only_initialized
    def shift_by(self, steps_x: int, steps_y: int):
        """Move so many steps right and down, left and up negative.

        Where the picture is bigger than the pane, that is looking further
        that way; where it is smaller, the picture goes that way itself.
        """

        self.set_shift(self._block.video_driver.shifted_by(steps_x, steps_y))

    @only_with_video_tacks
    @only_initialized
    def pan_by(self, moved_x: float, moved_y: float) -> tuple[float, float]:
        """Take the picture along with the pointer, so many pane pixels.

        Right and down, left and up negative. The picture goes the way the
        pointer does, as a sheet of paper under a hand would. Hands back
        what is left over of the move, for the next one to go on from.
        """

        shift, left_over = self._block.video_driver.dragged_shift(moved_x, moved_y)

        self.set_shift(shift, is_silent=True)

        return left_over

    @only_with_video_tacks
    @only_initialized
    def shift_reset(self):
        self.set_shift(VideoShift(0, 0))
        self._is_zoomed_to_selection = False

    @only_with_video_tacks
    @only_initialized
    def toggle_shift_past_edges(self):
        self.set_shift_past_edges(not self._block.video_params.is_shift_past_edges)

    def set_shift_past_edges(self, is_shift_past_edges: bool):
        """Let the picture be moved past the edges of the pane, or not.

        Kept within them again, it stays where they hold it, which is where
        the next move goes from. Kept for a video stopped or still loading
        too, which takes it up with the rest of its view as it loads.
        """

        block = self._block

        block.video_params.is_shift_past_edges = is_shift_past_edges

        if block.video_driver is None:
            return

        # one loading already has its view: it goes by this one instead
        block.video_driver.set_shift_past_edges(is_shift_past_edges)

        if block.is_video_initialized and block.video_tracks:
            # no steps is where the picture stands now
            self.set_shift(block.video_driver.shifted_by(0, 0), is_silent=True)
