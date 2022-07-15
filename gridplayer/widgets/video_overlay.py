from PyQt5.QtCore import QEvent, QPoint, QRect, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QGuiApplication, QPalette, QRegion
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from gridplayer.params.static import OVERLAY_ACTIVITY_EVENT
from gridplayer.settings import Settings
from gridplayer.utils.qt import qt_connect
from gridplayer.utils.time_txt import get_time_txt
from gridplayer.widgets.video_overlay_buttons import (
    OverlayExitButton,
    OverlayPlayPauseButton,
    OverlayVolumeButton,
)
from gridplayer.widgets.video_overlay_elements import (
    OverlayBorder,
    OverlayLabel,
    OverlayProgressBar,
    OverlayShortLabel,
    OverlayShortLabelFloating,
    OverlayVolumeBar,
    OverlayWidget,
)

PROPAGATED_EVENTS = (
    QEvent.MouseButtonRelease,
    QEvent.MouseButtonPress,
    QEvent.MouseMove,
    QEvent.MouseButtonDblClick,
    QEvent.Wheel,
    QEvent.ContextMenu,
    QEvent.DragEnter,
)

PROPAGATED_EVENTS_FILTERED = (
    QEvent.DragMove,
    QEvent.DragLeave,
    QEvent.Drop,
)


class OverlayBlock(QWidget):  # noqa: WPS230
    set_vid_pos = pyqtSignal(float)
    set_volume = pyqtSignal(float)

    exit_clicked = pyqtSignal()
    play_pause_clicked = pyqtSignal()
    mute_unmute_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)

        self._set_opacity(0.5)

        self.ui_setup()

        self.ui_customize_dynamic()

        self.ui_connect()

    def ui_customize_dynamic(self):
        self.label_info_hide_timer = QTimer()
        self.label_info_hide_timer.setSingleShot(True)
        self.label_info_hide_timer.timeout.connect(self.label_info.hide)

        self.label_info.hide()
        self.floating_progress.hide()

        self.label_progress.hide()
        self.progress_bar.hide()
        self.progress_bar_placeholder.show()

    def ui_connect(self):  # noqa: WPS213
        qt_connect(
            (self.progress_bar.mouse_over, self.floating_progress.on_mouse_over),
            (self.progress_bar.mouse_left, self.floating_progress.on_mouse_left),
            (self.exit_button.clicked, self.exit),
            (self.play_pause_button.clicked, self.play_pause),
            (self.progress_bar.position_changed, self.emit_position),
            (self.volume_button.clicked, self.mute_unmute),
            (self.volume_bar.position_changed, self.emit_volume_position),
        )

    def ui_setup(self):  # noqa: WPS213
        layout_main = QStackedLayout(self)

        layout_main.setContentsMargins(0, 0, 0, 0)
        layout_main.setStackingMode(QStackedLayout.StackAll)

        self.control_widget = QWidget(self)
        self.control_widget.setMouseTracking(True)

        self.border_widget = OverlayBorder(parent=self)
        self.border_widget.hide()

        layout_control = QVBoxLayout(self.control_widget)
        layout_control.setContentsMargins(10, 10, 10, 10)

        layout_main.addWidget(self.control_widget)
        layout_main.addWidget(self.border_widget)

        self.top_bar = QVBoxLayout()
        self.middle = QHBoxLayout()
        self.bottom_bar = QHBoxLayout()

        layout_control.addLayout(self.top_bar)
        layout_control.addLayout(self.middle, 1)
        layout_control.addLayout(self.bottom_bar)

        self.label_text = OverlayLabel(parent=self)
        self.exit_button = OverlayExitButton(parent=self)

        self.title_bar = QHBoxLayout()
        self.title_bar.addWidget(self.label_text, 1)
        self.title_bar.addWidget(self.exit_button)

        self.label_info = OverlayShortLabel(parent=self)

        self.info_bar = QHBoxLayout()
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

        self.bottom_bar.addWidget(self.play_pause_button)
        self.bottom_bar.addWidget(self.label_progress)
        self.bottom_bar.addWidget(self.progress_bar, 1)
        self.bottom_bar.addWidget(self.progress_bar_placeholder, 1)
        self.bottom_bar.addWidget(self.volume_button)

        self.floating_progress = OverlayShortLabelFloating(parent=self)

    def customEvent(self, event):
        if event.type() == OVERLAY_ACTIVITY_EVENT:
            QGuiApplication.sendEvent(self.parent(), QEvent(OVERLAY_ACTIVITY_EVENT))

    def resizeEvent(self, event):
        too_narrow_to_fit = 250
        is_wide = event.size().width() > too_narrow_to_fit

        self.label_progress.setVisible(is_wide or not self.progress_bar.isEnabled())

    @pyqtSlot(int, int)
    def set_position(self, position, length):
        position_percent = position / length

        position_txt = get_time_txt(position // 1000, length // 1000)
        length_txt = get_time_txt(length // 1000)

        if length == -1:
            self.floating_progress.hide()

            self.progress_bar.setEnabled(False)
            self.progress_bar.hide()

            self.progress_bar_placeholder.show()

            self.label_progress.text = f"{position_txt}"
            self.label_progress.show()
        else:
            self.progress_bar.setEnabled(True)
            self.progress_bar.show()

            self.progress_bar_placeholder.hide()

            self.floating_progress.length = length
            self.label_progress.text = f"{position_txt} / {length_txt}"
            self.progress_bar.position = position_percent

    @pyqtSlot(float)
    def set_loop_start(self, position):
        self.progress_bar.loop_start = position

    @pyqtSlot(float)
    def set_loop_end(self, position):
        self.progress_bar.loop_end = position

    @pyqtSlot(str)
    def set_label(self, label):
        self.label_text.label = label

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
    def set_is_muted(self, is_muted):
        self.volume_button.is_off = is_muted

        self.volume_bar.setHidden(self.volume_button.is_off)

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
        self.border_widget.setVisible(is_active)

    def _set_opacity(self, opacity):
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(opacity)
        self.setGraphicsEffect(effect)


class OverlayBlockFloating(OverlayBlock):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.ensure_black_text()

        self.init_flags()

        if Settings().get("internal/opaque_hw_overlay"):
            self.make_opaque()
        else:
            self.is_opaque = False

        self.parent().window().installEventFilter(self)

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

    def make_opaque(self):
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.setGraphicsEffect(None)

        self.floating_progress.is_opaque = True
        self.is_opaque = True

    def setGeometry(self, rect):
        new_pos = self.parent().mapToGlobal(QPoint())
        rect.moveTopLeft(new_pos)

        self.setFixedSize(rect.size())

        super().setGeometry(rect)

    def moveEvent(self, event):
        self.move_to_parent()

        event.accept()

    def paintEvent(self, event):
        self.move_to_parent()

        if self.is_opaque:
            # 0 coord to keep children from sliding off
            mask = QRegion(QRect(0, 0, 1, 1))

            if self.border_widget.isVisible():
                frame_width = 5
                frame = QRegion(self.rect())
                frame -= QRegion(
                    QRect(
                        frame_width,
                        frame_width,
                        self.width() - frame_width * 2,
                        self.height() - frame_width * 2,
                    )
                )
                mask = mask.united(frame)

            mask = mask.united(self.control_widget.childrenRegion())

            self.setMask(mask)

    def move_to_parent(self):
        new_pos = self.parent().mapToGlobal(QPoint())

        if new_pos != self.pos():
            self.move(new_pos)

    def eventFilter(self, event_object, event) -> bool:
        """Track parent window move events and follow it"""

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
            self.parent().window().filter_event(event)

        return super().event(event)


class OverlayFakeInvisible(OverlayBlockFloating):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_visible = False

    def show(self):
        if not self.isVisible():
            super().show()

        self._is_visible = True

        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.update()

    def hide(self):
        self._is_visible = False

        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.update()

    def paintEvent(self, event):
        if not self._is_visible and self.windowOpacity() != 0:
            self.setMask(QRegion(0, 0, 1, 1))
            self.setWindowOpacity(0)
            return

        if self.windowOpacity() == 0:
            self.clearMask()
            self.setWindowOpacity(1)

        super().paintEvent(event)
