from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from gridplayer.params.static import (
    MAX_SUBTITLE_DELAY_MS,
    MIN_SUBTITLE_DELAY_MS,
    SUBTITLE_DELAY_STEP_MS,
)
from gridplayer.utils.qt import translate


class SetSubtitleDelayDialog(QDialog):
    """Moves a video's subtitles against its picture.

    The same two modes SetAudioDelayDialog has, and for the same reasons:
    - video mode (live_block set): every change goes to the video as it is
      made, since whether a delay is right is a thing the viewer sees
      rather than works out; cancel puts back the delay it opened on.
    - value mode (live_block None): edits a plain number, read back with
      get_delay_ms(), for the videos that have no one pane to be seen in.
    """

    def __init__(self, delay_ms=0, parent=None, live_block=None):
        super().__init__(parent)

        self._block = live_block
        self._original_delay_ms = delay_ms

        self.setWindowTitle(
            translate("Dialog - Set subtitle delay", "Set subtitle delay", "Header")
        )
        self.setModal(True)

        self.spinbox = QSpinBox(self)
        self.spinbox.setRange(MIN_SUBTITLE_DELAY_MS, MAX_SUBTITLE_DELAY_MS)
        self.spinbox.setSingleStep(SUBTITLE_DELAY_STEP_MS)
        self.spinbox.setSuffix(" {}".format(translate("Subtitle Delay", "ms")))
        self.spinbox.setAlignment(Qt.AlignRight)
        self.spinbox.setValue(delay_ms)
        self.spinbox.valueChanged.connect(self._on_value_changed)

        hint = QLabel(
            translate("Dialog - Set subtitle delay", ">0 = later, <0 = sooner"), self
        )

        reset = QPushButton(translate("Dialog - Set subtitle delay", "Reset"), self)
        reset.clicked.connect(self._on_reset)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(reset)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        root = QVBoxLayout(self)
        root.addWidget(self.spinbox)
        root.addWidget(hint)
        root.addLayout(bottom)

        self.setFixedSize(self.sizeHint())

    @classmethod
    def for_video_block(cls, video_block, parent=None):
        """Video mode: edits the block's delay, seen as it is edited."""

        return cls(
            delay_ms=video_block.video_params.subtitle_delay_ms,
            parent=parent,
            live_block=video_block,
        )

    @classmethod
    def get_delay_ms(cls, delay_ms=0, parent=None) -> int | None:
        """Value mode: returns the delay that was set, or None on cancel."""

        dialog = cls(delay_ms=delay_ms, parent=parent)

        return dialog.spinbox.value() if dialog.exec_() else None

    def accept(self):
        if self._block is not None:
            # the same number over again, this time said out loud
            self._block.set_subtitle_delay(self.spinbox.value())

        super().accept()

    def reject(self):
        if self._block is not None:
            if self._block.video_params.subtitle_delay_ms != self._original_delay_ms:
                self._block.set_subtitle_delay(self._original_delay_ms, is_silent=True)

        super().reject()

    def _on_reset(self):
        self.spinbox.setValue(0)

    def _on_value_changed(self, delay_ms):
        if self._block is not None:
            self._block.set_subtitle_delay(delay_ms, is_silent=True)
