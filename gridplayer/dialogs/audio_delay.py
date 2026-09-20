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
    AUDIO_DELAY_STEP_MS,
    MAX_AUDIO_DELAY_MS,
    MIN_AUDIO_DELAY_MS,
)
from gridplayer.utils.qt import translate


class SetAudioDelayDialog(QDialog):
    """Moves a video's sound against its picture.

    Two modes, the same way SetCropDialog has two:
    - video mode (live_block set): every change goes to the video as it is
      made, since whether a delay is right is a thing the viewer hears
      rather than works out; cancel puts back the delay it opened on.
    - value mode (live_block None): edits a plain number, read back with
      get_delay_ms(), for the videos that have no one pane to be heard in.
    """

    def __init__(self, delay_ms=0, parent=None, live_block=None):
        super().__init__(parent)

        self._block = live_block
        self._original_delay_ms = delay_ms

        self.setWindowTitle(
            translate("Dialog - Set audio delay", "Set audio delay", "Header")
        )
        self.setModal(True)

        self.spinbox = QSpinBox(self)
        self.spinbox.setRange(MIN_AUDIO_DELAY_MS, MAX_AUDIO_DELAY_MS)
        self.spinbox.setSingleStep(AUDIO_DELAY_STEP_MS)
        self.spinbox.setSuffix(" {}".format(translate("Audio Delay", "ms")))
        self.spinbox.setAlignment(Qt.AlignRight)
        self.spinbox.setValue(delay_ms)
        self.spinbox.valueChanged.connect(self._on_value_changed)

        hint = QLabel(
            translate("Dialog - Set audio delay", ">0 = later, <0 = sooner"), self
        )

        reset = QPushButton(translate("Dialog - Set audio delay", "Reset"), self)
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
        """Video mode: edits the block's delay, heard as it is edited."""

        return cls(
            delay_ms=video_block.video_params.audio_delay_ms,
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
            self._block.set_audio_delay(self.spinbox.value())

        super().accept()

    def reject(self):
        if self._block is not None:
            if self._block.video_params.audio_delay_ms != self._original_delay_ms:
                self._block.set_audio_delay(self._original_delay_ms, is_silent=True)

        super().reject()

    def _on_reset(self):
        self.spinbox.setValue(0)

    def _on_value_changed(self, delay_ms):
        if self._block is not None:
            self._block.set_audio_delay(delay_ms, is_silent=True)
