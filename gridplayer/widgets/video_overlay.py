import sys
from enum import Enum, auto

from PyQt5.QtCore import (
    QEvent,
    QPoint,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import QGuiApplication, QPainter, QPalette, QRegion
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from gridplayer.params import env
from gridplayer.params.static import OVERLAY_ACTIVITY_EVENT
from gridplayer.utils.compositor_linux import should_make_overlay_opaque
from gridplayer.utils.drop_zone import DropIndicator
from gridplayer.utils.qt import MILLISECONDS, qt_connect, translate
from gridplayer.utils.time_txt import get_time_txt
from gridplayer.widgets.video_overlay_buttons import (
    OverlayButton,
    OverlayExitButton,
    OverlayListPlaceButton,
    OverlayPlayPauseButton,
    OverlayTextButton,
    OverlayVolumeButton,
)
from gridplayer.widgets.video_overlay_elements import (
    BOX_SHADOW_MARGIN,
    OverlayBar,
    OverlayBookmarkMarkers,
    OverlayBorder,
    OverlayDropIndicator,
    OverlayLabel,
    OverlayListWindowTag,
    OverlayProgressBar,
    OverlayShortLabel,
    OverlayShortLabelFloating,
    OverlayVolumeBar,
    OverlayWidget,
    OverlayZoomHint,
    OverlayZoomSelection,
)
from gridplayer.widgets.video_overlay_icons import draw_play, draw_stop

# how far in from the cell's edges the controls are: over a video, and as
# far in over a cell with no picture, clear of its frame, which runs close
# round the edge for them to stay where they are
CONTROL_MARGIN = 10


class OverlayMode(Enum):
    """What the cell under the overlay shows, which says what it offers."""

    # a video: play, the bar, the time and the sound
    VIDEO = auto()
    # stopped: a way to play it
    STOPPED = auto()
    # still loading: a way to stop it
    LOADING = auto()
    # failed: try again, more about why, and on to the next of its list
    ERROR = auto()


PROPAGATED_EVENTS = (
    QEvent.MouseButtonRelease,
    QEvent.MouseButtonPress,
    QEvent.MouseMove,
    QEvent.MouseButtonDblClick,
    QEvent.Wheel,
    QEvent.ContextMenu,
)

PROPAGATED_EVENTS_FILTERED = (
    QEvent.DragEnter,
    QEvent.DragMove,
    QEvent.DragLeave,
    QEvent.Drop,
)

# what a widget on the opaque overlay does that changes the shape the window
# is cut to
SHAPE_EVENTS = frozenset({QEvent.Show, QEvent.Hide, QEvent.Move, QEvent.Resize})

# The first Windows to layer a child window, not only a top-level one. The
# executable has to say in its manifest that it knows Windows 8 as well,
# which python.exe's and PyInstaller's both do.
WINDOWS_8 = (6, 2)


def is_layered_child_supported() -> bool:
    """Whether the overlay over a hardware video can be a child window."""

    return env.IS_WINDOWS and sys.getwindowsversion()[:2] >= WINDOWS_8


class OverlayBlock(QWidget):
    set_vid_pos = pyqtSignal(float)
    set_volume = pyqtSignal(float)

    exit_clicked = pyqtSignal()
    play_pause_clicked = pyqtSignal()
    mute_unmute_clicked = pyqtSignal()

    # a bookmark's marker clicked, by the bookmark's time
    bookmark_clicked = pyqtSignal(tuple)

    # a marker's menu asked for: where, and the times of its bookmarks
    bookmark_menu_requested = pyqtSignal(QPoint, tuple)

    # which item of its list the cell plays clicked, for the List window
    list_place_clicked = pyqtSignal()

    # the actions of a cell still loading, or failed
    stop_clicked = pyqtSignal()
    retry_clicked = pyqtSignal()
    details_clicked = pyqtSignal()
    next_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)

        self._is_chrome_visible = True
        self._is_active = False
        self._mode = OverlayMode.VIDEO
        self._is_on_chrome = False
        self._last_position = (0, 0)
        self._volume_button_wanted = True

        # what a failed cell offers past trying again; its Next goes back
        # where its list is played back to front
        self._has_error_details = False
        self._can_go_next = False
        self._is_going_back = False

        self.ui_setup()

        self._set_opacity(0.5)

        self.ui_customize_dynamic()

        self.ui_connect()

        # as it is to start with; from then on, as what it shows changes
        self._sync_bottom_bar()

        # the shadows round the boxes go where the boxes go
        for widget in self.findChildren(OverlayWidget):
            widget.installEventFilter(self)

    def ui_customize_dynamic(self):
        self.label_info_hide_timer = QTimer()
        self.label_info_hide_timer.setSingleShot(True)
        self.label_info_hide_timer.timeout.connect(self.label_info.hide)

        self.label_info.hide()
        self.list_place_button.hide()
        self.label_list_window.hide()
        self.floating_progress.hide()

        self.label_progress.hide()
        self.progress_bar.hide()
        self.progress_bar_placeholder.show()

        self.play_button.hide()
        self.stop_button.hide()
        self.retry_button.hide()
        self.details_button.hide()
        self.next_button.hide()

    def ui_connect(self):
        qt_connect(
            (self.progress_bar.mouse_over, self.floating_progress.on_mouse_over),
            (self.progress_bar.mouse_left, self.floating_progress.on_mouse_left),
            (self.bookmark_markers.marker_over, self.floating_progress.on_marker_over),
            (self.bookmark_markers.marker_left, self.floating_progress.on_mouse_left),
            (self.bookmark_markers.marker_clicked, self.bookmark_clicked),
            (
                self.bookmark_markers.marker_menu_requested,
                self.bookmark_menu_requested,
            ),
            (self.exit_button.clicked, self.exit),
            (self.list_place_button.clicked, self.list_place_clicked),
            (self.play_pause_button.clicked, self.play_pause),
            (self.progress_bar.position_changed, self.emit_position),
            (self.volume_button.clicked, self.mute_unmute),
            (self.volume_bar.position_changed, self.emit_volume_position),
            (self.play_button.clicked, self.play_pause),
            (self.stop_button.clicked, self.stop_clicked),
            (self.retry_button.clicked, self.retry_clicked),
            (self.details_button.clicked, self.details_clicked),
            (self.next_button.clicked, self.next_clicked),
        )

    def ui_setup(self):
        layout_main = QStackedLayout(self)

        layout_main.setContentsMargins(0, 0, 0, 0)
        layout_main.setStackingMode(QStackedLayout.StackAll)

        self.control_widget = QWidget(self)
        self.control_widget.setMouseTracking(True)

        self.border_widget = OverlayBorder(parent=self)
        self.border_widget.hide()

        layout_control = QVBoxLayout(self.control_widget)
        layout_control.setContentsMargins(
            CONTROL_MARGIN, CONTROL_MARGIN, CONTROL_MARGIN, CONTROL_MARGIN
        )

        self.drop_indicator = OverlayDropIndicator(parent=self)
        self.drop_indicator.hide()

        self.zoom_selection = OverlayZoomSelection(parent=self)
        self.zoom_hint = OverlayZoomHint(parent=self)

        layout_main.addWidget(self.control_widget)
        layout_main.addWidget(self.border_widget)
        layout_main.addWidget(self.drop_indicator)
        layout_main.addWidget(self.zoom_selection)
        layout_main.addWidget(self.zoom_hint)

        self.top_bar = QVBoxLayout()
        self.middle = QHBoxLayout()
        self.bottom_bar = QHBoxLayout()

        layout_control.addLayout(self.top_bar)
        layout_control.addLayout(self.middle, 1)
        layout_control.addLayout(self.bottom_bar)

        self.label_text = OverlayLabel(parent=self)
        self.exit_button = OverlayExitButton(parent=self)

        # which item of its list a cell plays, "3/12", for a cell with a
        # list: what its window is opened by
        self.list_place_button = OverlayListPlaceButton(parent=self)

        self.title_bar = QHBoxLayout()
        self.title_bar.addWidget(self.list_place_button)
        self.title_bar.addWidget(self.label_text, 1)
        self.title_bar.addWidget(self.exit_button)

        self.label_info = OverlayShortLabel(parent=self)

        # the List window is open on the cell, and plays in it
        self.label_list_window = OverlayListWindowTag(parent=self)
        self.label_list_window.text = translate("Lists", "Current list")

        self.info_bar = QHBoxLayout()
        self.info_bar.addWidget(self.label_list_window)
        self.info_bar.addWidget(self.label_info)
        self.info_bar.addStretch()

        self.top_bar.addLayout(self.title_bar)
        self.top_bar.addLayout(self.info_bar)

        self.right_bar = QVBoxLayout()

        self.middle.addStretch()
        self.middle.addLayout(self.right_bar)

        self.volume_bar = OverlayVolumeBar(parent=self)

        self.right_bar.addStretch()
        self.right_bar.addWidget(self.volume_bar, 1)

        self.play_pause_button = OverlayPlayPauseButton(parent=self)
        self.label_progress = OverlayShortLabel(parent=self)
        self.progress_bar = OverlayProgressBar(parent=self)
        self.progress_bar_placeholder = QWidget(parent=self)
        self.volume_button = OverlayVolumeButton(parent=self)

        self.play_button = OverlayTextButton(
            text=translate("Overlay", "Play"), sign=draw_play, parent=self
        )
        self.stop_button = OverlayTextButton(
            text=translate("Overlay", "Stop"), sign=draw_stop, parent=self
        )
        self.retry_button = OverlayTextButton(
            text=translate("Overlay", "Try Again"), parent=self
        )
        self.details_button = OverlayTextButton(
            text=translate("Overlay", "Details"), parent=self
        )
        self.next_button = OverlayTextButton(
            text=translate("Overlay", "Next"), parent=self
        )

        self.bottom_bar.addWidget(self.play_pause_button)
        self.bottom_bar.addWidget(self.play_button)
        self.bottom_bar.addWidget(self.stop_button)
        self.bottom_bar.addWidget(self.retry_button)
        self.bottom_bar.addWidget(self.details_button)
        self.bottom_bar.addWidget(self.label_progress)
        self.bottom_bar.addWidget(self.progress_bar, 1)
        self.bottom_bar.addWidget(self.progress_bar_placeholder, 1)
        self.bottom_bar.addWidget(self.next_button)
        self.bottom_bar.addWidget(self.volume_button)

        # right above the bar, outside of the layout; under the rest, so that
        # in a short cell a notice under the title shows over it
        self.bookmark_markers = OverlayBookmarkMarkers(
            bar=self.progress_bar, parent=self.control_widget
        )
        self.bookmark_markers.lower()

        self.floating_progress = OverlayShortLabelFloating(parent=self)

    def customEvent(self, event):
        if event.type() == OVERLAY_ACTIVITY_EVENT:
            QGuiApplication.sendEvent(self.parent(), QEvent(OVERLAY_ACTIVITY_EVENT))

    def resizeEvent(self, event):
        self._sync_progress_label()

    def paintEvent(self, event):
        self._paint_shadows(event.rect())

    def _paint_shadows(self, area: QRect):
        """The soft shadows round the boxes, under them, where they are.

        Painted by the overlay itself: a box's shadow falls past the box,
        where the box cannot paint. The boxes paint over this after.
        """

        if getattr(self, "is_opaque", False):
            return

        painter = None
        reach = BOX_SHADOW_MARGIN

        for widget in self._shadow_casters():
            origin = widget.mapTo(self, QPoint(0, 0))
            bounds = QRect(origin, widget.size())

            if not bounds.adjusted(-reach, -reach, reach, reach).intersects(area):
                continue

            shadow = widget.shadow()

            if shadow is None:
                continue

            if painter is None:
                painter = QPainter(self)

            pixmap, at = shadow
            painter.drawPixmap(origin + at, pixmap)

    def _shadow_casters(self) -> list[OverlayWidget]:
        return [
            widget
            for widget in self.findChildren(OverlayWidget)
            if widget.casts_shadow and widget.isVisibleTo(self)
        ]

    def _track_shadow(self, widget, event):
        """Paint again where a box's shadow was and where it is now: Qt
        paints again only where the box itself was and is."""

        if not isinstance(widget, OverlayWidget) or not widget.casts_shadow:
            return

        if event.type() not in SHAPE_EVENTS:
            return

        rects = [widget.geometry()]

        if event.type() == QEvent.Move:
            rects.append(QRect(event.oldPos(), widget.size()))
        elif event.type() == QEvent.Resize:
            rects.append(QRect(widget.pos(), event.oldSize()))

        parent = widget.parentWidget()
        reach = BOX_SHADOW_MARGIN

        for rect in rects:
            if parent is not self:
                rect = QRect(parent.mapTo(self, rect.topLeft()), rect.size())

            self.update(rect.adjusted(-reach, -reach, reach, reach))

    def eventFilter(self, event_object, event) -> bool:
        self._track_shadow(event_object, event)

        return super().eventFilter(event_object, event)

    @pyqtSlot(MILLISECONDS, MILLISECONDS)
    def set_position(self, position, length):
        position = max(0, position)
        _, last_length = self._last_position
        self._last_position = (position, length)

        # the bar is there or not by whether there is a length: told the
        # time several times a second, laid out again only as that changes
        if (length > 0) != (last_length > 0):
            self._sync_bottom_bar()

        if length <= 0:
            position_txt = get_time_txt(position // 1000)

            self.label_progress.text = f"{position_txt}"

            return

        position_percent = position / length
        position_txt = get_time_txt(position // 1000, length // 1000)
        length_txt = get_time_txt(length // 1000)

        self.floating_progress.length = length
        self.floating_progress.on_position(position)
        self.progress_bar.length = length
        self.bookmark_markers.set_length(length)
        self.label_progress.text = f"{position_txt} / {length_txt}"
        self.progress_bar.position = position_percent

    @pyqtSlot(float)
    def set_loop_start(self, position):
        self.progress_bar.loop_start = position

    @pyqtSlot(float)
    def set_loop_end(self, position):
        self.progress_bar.loop_end = position

    @pyqtSlot(tuple)
    def set_seek_marks(self, marks):
        self.progress_bar.marks = marks
        self.floating_progress.marks = marks
        self.bookmark_markers.set_marks(marks)

    @pyqtSlot(str)
    def set_label(self, label):
        self.label_text.label = label

    @pyqtSlot(str)
    def set_list_place(self, place_txt):
        """Which item of its list the cell plays; nothing, where it has none."""

        if place_txt:
            self.list_place_button.text = place_txt

        self.list_place_button.setVisible(bool(place_txt))

    def set_list_window_shown(self, is_shown: bool):
        """Said under the title while the List window plays in the cell."""

        self.label_list_window.setVisible(is_shown)

    @pyqtSlot(str)
    def set_color(self, color):
        for widget in self.findChildren(OverlayWidget):
            widget.color = color

    @pyqtSlot(str)
    def set_info_label(self, info_text):
        self.label_info.text = info_text
        self.label_info.show()
        self.label_info_hide_timer.start(1000 * 2)

    @pyqtSlot()
    def set_is_in_progress(self):
        self.play_pause_button.is_in_progress = True

    @pyqtSlot(bool)
    def set_is_paused(self, is_paused):
        self.play_pause_button.is_off = not is_paused

    @pyqtSlot(bool)
    def set_is_stopped(self, is_stopped):
        """Stopped or playing, where the cell is one or the other: a cell
        still loading, or failed, is told what it is by set_mode."""

        if self._mode not in {OverlayMode.VIDEO, OverlayMode.STOPPED}:
            return

        self.set_mode(OverlayMode.STOPPED if is_stopped else OverlayMode.VIDEO)

    @property
    def mode(self) -> OverlayMode:
        return self._mode

    def set_mode(self, mode: OverlayMode):
        # told again on every move of the mouse over the cell
        if mode is self._mode:
            return

        self._mode = mode
        self._sync_bottom_bar()

    def set_error_actions(
        self, has_details: bool, can_go_next: bool, is_going_back: bool = False
    ):
        """What a failed cell offers past trying again."""

        actions = (has_details, can_go_next, is_going_back)
        shown = (self._has_error_details, self._can_go_next, self._is_going_back)

        if actions == shown:
            return

        self._has_error_details = has_details
        self._can_go_next = can_go_next
        self._is_going_back = is_going_back

        if is_going_back:
            self.next_button.text = translate("Overlay", "Previous")
        else:
            self.next_button.text = translate("Overlay", "Next")

        self._sync_bottom_bar()

    def set_is_on_chrome(self, is_on_chrome: bool):
        """Over a cell with no picture, its controls drawn as the app's own
        boxes, and the frame itself telling the active cell rather than a
        border of its own."""

        if self._is_on_chrome == is_on_chrome:
            return

        self._is_on_chrome = is_on_chrome

        for widget in self.findChildren(OverlayWidget):
            widget.set_on_chrome(is_on_chrome)

        self._sync_border()
        self.update()

    @pyqtSlot(bool)
    def set_is_muted(self, is_muted):
        self.volume_button.is_off = is_muted
        self._sync_volume_chrome()

    @pyqtSlot(float)
    def set_volume_position(self, position):
        self.volume_bar.position = position

    @pyqtSlot()
    def exit(self):
        self.exit_clicked.emit()

    @pyqtSlot()
    def play_pause(self):
        self.play_pause_clicked.emit()

    @pyqtSlot()
    def mute_unmute(self):
        self.mute_unmute_clicked.emit()

    @pyqtSlot(float)
    def emit_position(self, position):
        self.set_vid_pos.emit(position)

    @pyqtSlot(float)
    def emit_volume_position(self, position):
        self.set_volume.emit(position)

    @pyqtSlot(bool)
    def set_is_active(self, is_active):
        self._is_active = is_active
        self._sync_border()
        self.update()

    def set_is_chrome_visible(self, visible: bool):
        self._is_chrome_visible = visible
        self.control_widget.setVisible(visible)
        if not visible:
            self.floating_progress.hide()
        self._sync_border()
        self._sync_bottom_bar()
        self.update()

    def _sync_border(self):
        # over a cell with no picture its frame says it is the active one
        self.border_widget.setVisible(
            self._is_active and self._is_chrome_visible and not self._is_on_chrome
        )

    def _sync_bottom_bar(self):
        mode = self._mode
        is_video = mode is OverlayMode.VIDEO

        _, length = self._last_position
        has_bar = is_video and length > 0

        self.play_pause_button.setVisible(is_video)

        self.progress_bar.setEnabled(length > 0)
        self.progress_bar.setVisible(has_bar)
        self.progress_bar_placeholder.setVisible(not has_bar)

        if not has_bar:
            self.floating_progress.hide()

        self.play_button.setVisible(mode is OverlayMode.STOPPED)
        self.stop_button.setVisible(mode is OverlayMode.LOADING)

        is_error = mode is OverlayMode.ERROR
        self.retry_button.setVisible(is_error)
        self.details_button.setVisible(is_error and self._has_error_details)
        self.next_button.setVisible(is_error and self._can_go_next)

        self._sync_volume_chrome()
        self._sync_progress_label()

    def _sync_progress_label(self):
        if self._mode is not OverlayMode.VIDEO:
            self.label_progress.hide()
            return
        too_narrow_to_fit = 250
        is_wide = self.width() > too_narrow_to_fit
        self.label_progress.setVisible(is_wide or not self.progress_bar.isEnabled())

    @pyqtSlot(bool)
    def set_volume_button_visible(self, is_visible):
        self._volume_button_wanted = is_visible
        self._sync_volume_chrome()

    def _sync_volume_chrome(self):
        if self._mode is not OverlayMode.VIDEO:
            self.volume_button.hide()
            self.volume_bar.hide()
            return

        self.volume_button.setVisible(self._volume_button_wanted)
        show_bar = self._volume_button_wanted and not self.volume_button.is_off
        self.volume_bar.setVisible(show_bar)

    def lay_out_now(self):
        """Its controls where they go now, rather than once the event loop
        comes round, for it to be painted at once as it is now."""

        self.layout().activate()
        self.control_widget.layout().activate()

    def set_drop_indicator(self, indicator: DropIndicator):
        self.drop_indicator.set_indicator(indicator)
        if indicator != DropIndicator.NONE:
            self.drop_indicator.raise_()
        self.update()

    def set_zoom_selection(self, selection: QRect | None):
        """Outline the part of the picture being selected to zoom to."""

        self.zoom_selection.set_selection(selection)

    def set_zoom_hint(self, is_shown: bool):
        """Say how to select a part of the picture to zoom to, or not."""

        self.zoom_hint.set_shown(is_shown)

    def is_control_at(self, global_pos: QPoint) -> bool:
        """Whether a press there is one of the overlay's own controls':
        a button, a bar or a bookmark's marker, which act on it themselves.

        Looked for here rather than with QApplication.widgetAt, which never
        looks inside a window of the cell's own, as OverlayBlockChild is.
        """

        if not self.isVisible():
            return False

        pos = self.mapFromGlobal(global_pos)
        widget = self.childAt(pos)

        if isinstance(widget, OverlayBookmarkMarkers):
            return widget.is_marker_at(widget.mapFrom(self, pos).x())

        return isinstance(widget, (OverlayButton, OverlayBar))

    def _set_opacity(self, opacity):
        # Opacity lives on each OverlayWidget, not on this parent. A single
        # QGraphicsOpacityEffect here cached the whole tree and left seams
        # when the seek timer moved. Each widget paints itself see-through,
        # by its own colours.
        self.setGraphicsEffect(None)
        self._overlay_opacity = opacity
        for widget in self.findChildren(OverlayWidget):
            widget.set_overlay_opacity(opacity)


class OverlayBlockChild(OverlayBlock):
    """The overlay over a hardware video, as a child window of the cell.

    Nothing a cell paints shows over a hardware video. VLC presents into
    native windows of its own inside the cell's, and Qt paints the widgets
    of a window into one opaque image that it copies into each native
    window there is, so an overlay drawn into it covers the video, or is
    covered by it. What shows over the video is a window stacked above
    VLC's with alpha of its own: layered. Up to Windows 7 only a top-level
    window can be layered, hence OverlayBlockFloating, kept over the cell
    by hand. From Windows 8 a child window can be layered as well, so this
    one is inside the cell's: it moves, clips and hides with the cell by
    itself, and stays over the video by being stacked above it (see
    VideoBlock._ensure_video_driver).
    """

    def __init__(self, parent):
        super().__init__(parent)

        # frameless with alpha is what Qt draws with UpdateLayeredWindow
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint
        )

        parent.winId()
        self.winId()
        self.windowHandle().setParent(parent.windowHandle())

    def event(self, event):
        # A window of its own, the mouse events nothing on it takes stop here
        # rather than going on to the cell. Drags never come: Qt takes them
        # only at the top-level window, the player.
        if event.type() in PROPAGATED_EVENTS:
            QApplication.sendEvent(self.parent(), event)

        return super().event(event)


class OverlayBlockFloating(OverlayBlock):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.ensure_black_text()

        self.init_flags()

        self.is_opaque = False

        if env.IS_LINUX and should_make_overlay_opaque():
            self.make_opaque()

        self.parent().window().installEventFilter(self)

    @pyqtSlot(str)
    def set_color(self, color):
        super().set_color(color)
        self._sync_opaque_window_color()

    @pyqtSlot(bool)
    def set_is_active(self, is_active):
        super().set_is_active(is_active)
        self.refresh_opaque_mask()

    def set_is_chrome_visible(self, visible: bool):
        super().set_is_chrome_visible(visible)
        self.refresh_opaque_mask()

    def set_is_stopped(self, is_stopped):
        super().set_is_stopped(is_stopped)
        self.refresh_opaque_mask()

    def set_drop_indicator(self, indicator: DropIndicator):
        super().set_drop_indicator(indicator)
        self.refresh_opaque_mask()

    def ensure_black_text(self):
        """Some window managers make text look gray when window is out of focus"""

        pal = self.palette()
        col = pal.color(QPalette.Active, QPalette.ButtonText)
        pal.setColor(QPalette.Inactive, QPalette.Text, col)
        self.setPalette(pal)

    def init_flags(self):
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Prevent from shooting up on top of other windows on show()
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Allow window to move beyond screen edge
        self.setAttribute(Qt.WA_X11NetWmWindowTypeDesktop)

        # Don't allow overlay to receive focus
        self.setAttribute(Qt.WA_X11DoNotAcceptFocus)

        # Drag and drop doesn't get through floating overlay
        # need to redirect drag events to Player window
        self.setAcceptDrops(True)

        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint
        )

        # workaround to avoid some compositors (KWin) making overlay opaque
        if env.IS_LINUX:
            self.setWindowOpacity(0.999)

    def make_opaque(self):
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.setGraphicsEffect(None)

        self._set_opacity(1.0)
        self.floating_progress.is_opaque = True
        self.is_opaque = True
        self._sync_opaque_window_color()

        # Whatever is outside the shape is not painted at all, so a widget
        # has to be inside it before it paints: the shape is cut again the
        # moment one is shown, hidden, moved or resized, never later.
        for widget in self.findChildren(OverlayWidget):
            widget.installEventFilter(self)

        # the hover label moves with the mouse, and says once it is in place
        # rather than at every step of getting there
        self.floating_progress.shape_changed.connect(self.refresh_opaque_mask)

        # the bookmarks' markers come and go without the strip moving
        self.bookmark_markers.is_opaque = True
        self.bookmark_markers.update_shape()
        self.bookmark_markers.shape_changed.connect(self.refresh_opaque_mask)

        # the outline of a selection to zoom to moves about the cell without
        # the widget it is drawn on moving, and the hint goes with its size
        self.zoom_selection.shape_changed.connect(self.refresh_opaque_mask)
        self.zoom_hint.shape_changed.connect(self.refresh_opaque_mask)

    def setGeometry(self, rect):
        new_pos = self.parent().mapToGlobal(QPoint())
        rect.moveTopLeft(new_pos)

        self.setFixedSize(rect.size())

        super().setGeometry(rect)

    def moveEvent(self, event):
        self.move_to_parent()

        event.accept()

    def paintEvent(self, event):
        if not self.is_opaque:
            super().paintEvent(event)
            return

        # setMask during paint clips to the old shape, so any newly shown
        # child (the border ring) would not be drawn this frame.
        self._apply_opaque_mask(self._opaque_mask())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_opaque_mask()

    def refresh_opaque_mask(self):
        if not self.is_opaque:
            return

        self._apply_opaque_mask(self._opaque_mask())

    def _apply_opaque_mask(self, new_mask: QRegion) -> None:
        # X11 Shape setMask briefly unmasks the window. Opaque fill is the
        # video color (default white), so a redundant reshape flashes the cell.
        old_mask = self.mask()

        if new_mask == old_mask:
            return

        self.setMask(new_mask)

        # Qt repaints nothing a window's shape grows into, and shows what it
        # last painted there: a label that changed while outside the shape
        # comes up as it was, or blank. Put off by Qt until the paint is done
        # when this is called from one.
        revealed = new_mask.subtracted(old_mask)

        if not revealed.isEmpty():
            self.update(revealed)

    def _opaque_mask(self) -> QRegion:
        mask = QRegion()

        # As shown once the overlay is, whether it is now or not: a shape
        # worked out while it is hidden is the one it comes back with, and
        # only what is inside that is painted when it does.
        for child in self.findChildren(OverlayWidget):
            if not child.isVisibleTo(self):
                continue
            mask += child.opaque_shape().translated(child.pos())

        if not mask.isEmpty():
            return mask

        # Empty mask is treated as unmasked on X11, so the opaque window
        # would cover the whole video. Keep a 1px hole while mapped.
        return QRegion(QRect(0, 0, 1, 1))

    def _sync_opaque_window_color(self):
        if not self.is_opaque:
            return

        pal = self.palette()
        pal.setColor(QPalette.Window, self.border_widget.color)
        self.setPalette(pal)
        self.setAutoFillBackground(True)

    def move_to_parent(self):
        new_pos = self.parent().mapToGlobal(QPoint())

        if new_pos != self.pos():
            self.move(new_pos)

    def eventFilter(self, event_object, event) -> bool:
        """Track parent window move events and follow it"""

        self._track_shadow(event_object, event)

        if isinstance(event_object, OverlayWidget) and event.type() in SHAPE_EVENTS:
            # the hover label says for itself once it has been put somewhere
            if event_object is not self.floating_progress or (
                event.type() == QEvent.Hide
            ):
                self.refresh_opaque_mask()

            return False

        if event_object == self.parent().window():
            if event.type() == QEvent.Move:
                QApplication.sendEvent(self, event)
            if event.type() == QEvent.LayoutRequest:
                self.move_to_parent()
        if event_object == self.parent() and event.type() == QEvent.Hide:
            self.hide()

        return super().eventFilter(event_object, event)

    def event(self, event):
        """Events are not propagated for independent windows (like this one),
        so have to do it manually to emulate regular child widget behaviour.

        https://stackoverflow.com/a/3184510/13100286
        https://forum.qt.io/post/352629

        Also drag events create recursion, so they are filtered separately"""

        if event.type() in PROPAGATED_EVENTS:
            QApplication.sendEvent(self.parent(), event)
        elif event.type() in PROPAGATED_EVENTS_FILTERED:
            # pos() is overlay-local; pass this widget so hit-testing can map it
            self.parent().window().filter_event(event, source=self)
            return True

        return super().event(event)


class OverlayFakeInvisible(OverlayBlockFloating):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_visible = False

    def show(self):
        if not self.isVisible():
            self.setVisible(True)

        self._is_visible = True

        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.update()

    def hide(self):
        if not self.isVisible():
            self.setVisible(True)

        self._is_visible = False

        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.update()

    def move_beyond_screen(self):
        self.move(QPoint(-self.width(), -self.height()))

    def move_to_parent(self):
        if not self._is_visible:
            return self.move_beyond_screen()

        super().move_to_parent()

    def paintEvent(self, event):
        if not self._is_visible and self.windowOpacity() != 0:
            self.move_beyond_screen()
            self.setMask(QRegion(0, 0, 1, 1))
            self.setWindowOpacity(0)
            return

        if self.windowOpacity() == 0:
            self.clearMask()
            self.setWindowOpacity(1)

        super().paintEvent(event)
