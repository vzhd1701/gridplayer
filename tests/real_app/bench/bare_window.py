"""A full-screen window and nothing else, repainted at 60 Hz with a pre-made picture: no video,
no GL, no decoding. What just being on screen asks of the compositor and the GPU."""

import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

seconds = float(sys.argv[1])
app = QApplication(["bare", "-platform", "xcb"])

images = []
for shade in (40, 80):
    image = QImage(1920, 1080, QImage.Format.Format_RGB32)
    image.fill(QColor(shade, shade, shade))
    images.append(image)


class Window(QWidget):
    index = 0

    def paintEvent(self, event):
        self.index = 1 - self.index
        painter = QPainter(self)
        painter.drawImage(0, 0, images[self.index])
        painter.end()


window = Window()
window.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
window.resize(1920, 1080)
window.show()

timer = QTimer()
timer.setTimerType(Qt.TimerType.PreciseTimer)
timer.setInterval(16)
timer.timeout.connect(window.update)
timer.start()

QTimer.singleShot(int(seconds * 1000), app.quit)
app.exec()
